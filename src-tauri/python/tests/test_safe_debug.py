"""Captured department DOM, isolated browser only; debug must dispatch zero clicks."""
import json
from pathlib import Path
import sys
import tempfile
import runpy
import unittest
from unittest.mock import Mock, patch

from playwright.sync_api import sync_playwright

sys.path.insert(0, str(Path(__file__).parents[1]))
from src.browser import BrowserHelper
from src.approver import ApprovalHelper
from src.safe_debug import inspect, department_options, load_workflow


class SafeDebugTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.p = sync_playwright().start()
        cls.chrome = cls.p.chromium.launch(channel='msedge', headless=True)
        cls.capture = (Path(__file__).parents[3] / 'captures/department-window-2026-09-26.html').read_text(encoding='utf-8')

    @classmethod
    def tearDownClass(cls):
        cls.chrome.close()
        cls.p.stop()

    def setUp(self):
        self.context = self.chrome.new_context()
        self.addCleanup(self.context.close)
        self.context.route('**/*', lambda route: route.fulfill(body='<body></body>', content_type='text/html'))
        self.page = self.context.new_page()
        self.page.goto('http://fixture.test/amcs/index.htm')
        self.page.set_content('<style>#selectPartjobOrgWin,.h_floatdiv-con{height:auto!important;position:static!important}</style><div id="title">fixture</div><button id="wf_btn_2">通过</button>' + self.capture)
        self.page.evaluate("""() => {
          document.querySelector('#selectPartjobOrgWin').style.top='20px';
          window.clicks=0;
          document.querySelectorAll('button,input[type=radio]').forEach(el => {el.removeAttribute('onclick');el.addEventListener('click',()=>window.clicks++);});
        }""")
        self.browser = BrowserHelper()
        self.browser.browser = Mock(contexts=[self.context])
        self.config = {'approval': {'approve_button_selector': '#wf_btn_2', 'fields': {'事项名称': '#title'},
            'final_confirm_button_selector': '#selectPartjobOrgWin button[name="selectPartjobOrgWinBtn"]'}}
        self.workflow = dict(debug_steps=3, department_id='0_0_0610', source='http://fixture.test')

    def test_capture_reads_complete_options_and_trial_does_not_select_or_submit(self):
        result = inspect(self.browser, self.config, self.workflow, Mock())
        self.assertTrue(result['departments']['complete'])
        self.assertEqual([item['id'] for item in result['departments']['items']], ['0_RZ001', '0_0_0610'])
        self.assertEqual(result['records'][0]['事项名称'], 'fixture')
        self.assertEqual(self.page.evaluate('window.clicks'), 0)
        self.assertFalse(self.page.locator('#cb_PartjobOrgTable_2').is_checked())
        self.assertFalse(result['registration_enabled'])

    def test_one_step_never_clicks_approve(self):
        self.page.locator('#selectPartjobOrgWin').evaluate('el=>el.remove()')
        self.workflow['debug_steps'] = 1
        result = inspect(self.browser, self.config, self.workflow, Mock())
        self.assertEqual(result['clicks_sent'], 0)
        self.assertEqual(self.page.evaluate('window.clicks'), 0)

    def test_parent_dialog_and_child_detail_are_one_workflow(self):
        self.page.locator('#wf_btn_2').evaluate('el=>el.remove()')
        self.page.locator('#title').evaluate('el=>el.remove()')
        self.page.evaluate("""() => {
          const child = document.createElement('iframe');
          child.src = '/amcs/detail.htm'; document.body.append(child);
        }""")
        child = self.page.frame(url='http://fixture.test/amcs/detail.htm')
        if child is None:
            self.page.wait_for_event('framenavigated', predicate=lambda frame: frame.url.endswith('/detail.htm'))
            child = self.page.frame(url='http://fixture.test/amcs/detail.htm')
        child.set_content('<div id="title">child record</div><button id="wf_btn_2">通过</button>')
        result = inspect(self.browser, self.config, self.workflow, Mock())
        self.assertEqual(result['records'][0]['事项名称'], 'child record')
        self.assertTrue(result['departments']['complete'])
        self.assertEqual(self.page.evaluate('window.clicks'), 0)

    def test_options_only_does_not_require_valid_approval_selector(self):
        self.config['approval']['approve_button_selector'] = '['
        result = inspect(self.browser, self.config, self.workflow, Mock(), options_only=True)
        self.assertTrue(result['departments']['complete'])
        self.assertEqual(result['records'], [])

    def test_partial_pagination_not_reported_as_all_options(self):
        self.page.locator('#totalPages_PartjobOrgTable').evaluate("el=>el.textContent='2'")
        self.assertFalse(department_options(self.page)['complete'])

    def test_duplicate_option_ids_fail_closed(self):
        self.page.locator('#tr_PartjobOrgTable_1 td[name=orgid]').evaluate("el=>el.textContent='0_0_0610'")
        with self.assertRaisesRegex(Exception, '编号重复'):
            department_options(self.page)

    def test_unknown_saved_department_rejected_but_can_rescan(self):
        self.workflow['department_id'] = 'missing'
        with self.assertRaisesRegex(ValueError, '不匹配'):
            inspect(self.browser, self.config, self.workflow, Mock())
        self.assertTrue(inspect(self.browser, self.config, self.workflow, Mock(), options_only=True)['departments']['complete'])
        self.assertEqual(self.page.evaluate('window.clicks'), 0)

    def test_multiple_pages_rejected_without_clicks(self):
        other = self.context.new_page()
        other.goto('http://fixture.test/amcs/index.htm')
        other.set_content('<button id="wf_btn_2">通过</button>')
        with self.assertRaisesRegex(ValueError, '唯一'):
            inspect(self.browser, self.config, self.workflow, Mock())
        self.assertEqual(self.page.evaluate('window.clicks'), 0)

    def test_normal_mode_uses_exact_id_not_duplicate_display_name(self):
        self.config['approval'].update(dept_select_id='0_RZ001', dept_select_source='http://fixture.test')
        self.page.locator('#tr_PartjobOrgTable_2 td[name=orgname]').evaluate("el=>el.textContent='公司领导'")
        helper = ApprovalHelper(self.browser, self.config, log_callback=Mock())
        helper._handle_subsequent_pages(self.page)
        self.assertTrue(self.page.locator('#cb_PartjobOrgTable_1').is_checked())
        self.assertFalse(self.page.locator('#cb_PartjobOrgTable_2').is_checked())
        self.assertEqual(self.page.evaluate('window.clicks'), 2)

    def test_settings_fail_closed_and_preserve_debug_default(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'config.json'
            self.assertFalse(load_workflow(path)['debug_enabled'])
            path.with_name('workflow.json').write_text(json.dumps({'debug_enabled': True, 'debug_steps': 0}))
            with self.assertRaises(ValueError):
                load_workflow(path)

    def test_changed_department_before_final_click_stops_submission(self):
        self.config['approval'].update(dept_select_id='0_RZ001', dept_select_source='http://fixture.test')
        helper = ApprovalHelper(self.browser, self.config, log_callback=Mock())
        calls = []
        def guard():
            calls.append(True)
            if len(calls) == 2:
                self.page.locator('#cb_PartjobOrgTable_2').evaluate('el=>el.checked=true')
        with self.assertRaisesRegex(RuntimeError, '选中状态已变化'):
            helper._handle_subsequent_pages(self.page, action_guard=guard)
        self.assertEqual(self.page.evaluate('window.clicks'), 1)

    def test_final_confirmation_is_scoped_to_department_dialog(self):
        self.config['approval'].update(dept_select_id='0_RZ001', dept_select_source='http://fixture.test',
                                       final_confirm_button_selector='button')
        helper = ApprovalHelper(self.browser, self.config, log_callback=Mock())
        helper._handle_subsequent_pages(self.page)
        self.assertEqual(self.page.evaluate('window.clicks'), 2)

    def test_missing_final_confirmation_cannot_report_completion(self):
        self.config['approval'].update(dept_select_id='0_RZ001', dept_select_source='http://fixture.test',
                                       final_confirm_button_selector='')
        helper = ApprovalHelper(self.browser, self.config, log_callback=Mock())
        with self.assertRaisesRegex(RuntimeError, '缺少最终确认'):
            helper._handle_subsequent_pages(self.page)
        self.assertEqual(self.page.evaluate('window.clicks'), 0)

    def test_department_failure_cannot_reenter_approval_as_detection_fallback(self):
        helper = ApprovalHelper(self.browser, self.config, log_callback=Mock(), oa_type='old')
        helper._process_detail = Mock(side_effect=RuntimeError('department failed'))
        with self.assertRaisesRegex(RuntimeError, 'department failed'):
            helper.process_current_page(self.page)
        helper._process_detail.assert_called_once()

    def test_runner_debug_bypasses_all_registration_and_approval_objects(self):
        old_stdout = sys.stdout
        try:
            module = runpy.run_path(str(Path(__file__).parents[1] / 'runner.py'))
        finally:
            sys.stdout = old_stdout
        with tempfile.TemporaryDirectory() as tmp:
            config = Path(tmp) / 'config.json'
            config.write_text('{}')
            config.with_name('workflow.json').write_text(json.dumps({'debug_enabled': True, 'debug_steps': 1}))
            forbidden = Mock(side_effect=AssertionError('must not construct side-effect pipeline'))
            emit = Mock()
            main = module['main']
            with patch.dict(main.__globals__, {'BrowserHelper': Mock(), 'Registration': forbidden,
                    'WebhookHelper': forbidden, 'ApprovalHelper': forbidden,
                    'inspect': Mock(return_value={'read_only': True}), 'emit': emit}), \
                 patch.object(sys, 'argv', ['runner', '--config', str(config), '--oa-type', 'old']):
                self.assertEqual(main(), 0)
            forbidden.assert_not_called()
            emit.assert_called_with('debug_result', read_only=True)


if __name__ == '__main__':
    unittest.main()
