"""Core command safety and complete synthetic approval/registration flow."""
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import Mock, patch

from playwright.sync_api import sync_playwright

sys.path.insert(0, str(Path(__file__).parents[1]))
from src.browser import BrowserHelper
from src.approver import ApprovalHelper
from src.pending import PendingReader
from src.core_commands import CoreCommands


class CoreCommandTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.playwright = sync_playwright().start()
        cls.chrome = cls.playwright.chromium.launch(channel='msedge', headless=True)

    @classmethod
    def tearDownClass(cls):
        cls.chrome.close()
        cls.playwright.stop()

    def setUp(self):
        self.context = self.chrome.new_context()
        self.addCleanup(self.context.close)
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.page = self.context.new_page()
        self.context.route('**/*', self.route)
        self.page.goto('http://fixture.test/amcs/index.htm')
        browser = BrowserHelper()
        browser.browser = Mock(contexts=[self.context])
        self.config = {'approval': {'fields': {'事项名称': '#title'}, 'approve_button_selector': '#agree',
            'confirm_button_selector': '#confirm', 'final_confirm_button_selector': '#final', 'dept_select_text': 'Risk'}}
        self.reader = PendingReader(browser, self.config, Mock())
        self.registration = Mock()
        self.registration.submit.return_value = {'Obsidian': True, '企业微信': True}
        self.commands = CoreCommands(self.reader, self.registration, self.config, self.tmp.name)
        self.review = self.commands.review('12')
        self.token = self.review['review_token']

    def route(self, route):
        if '/amcs/index.htm' in route.request.url:
            body = '''<div id="trust_pagelet_lcdb" style="min-height:1px"><input type="hidden" id="trust_pagelet_lcdb-itemnumber" value="1">
              <div class="_dataitem_" paramcacheid="a" onclick="openTask()">project</div></div>
              <ul id="tab-con"><li class="active" tabid="MSG_12" title="待办事宜处理"
                url="/amcs/bpm/client/mw/open?taskId=12">project</li></ul><iframe id="details"></iframe>
              <script>window.TrustUI={getComp:()=>({_dataparamCaches:{a:{msgContent:{taskId:'12',PROC_TITLE:'project'},
                  tcmpUrl:'/amcs/bpm/client/mw/open?taskId=12'}}})};
                if(localStorage.done){document.querySelector('._dataitem_').remove();
                  document.querySelector('#trust_pagelet_lcdb-itemnumber').value='0';}
                function openTask(){document.querySelector('#details').src='/detail?taskId=12';}
              </script>'''
        else:
            body = '''<div id="title">project</div><button id="agree">Agree</button><script>
              agree.onclick=()=>{
                parent.localStorage.clicks=Number(parent.localStorage.clicks||0)+1;
                document.body.insertAdjacentHTML('beforeend','<button id="confirm">Confirm</button>');
                document.querySelector('#confirm').onclick=()=>{
                  document.body.insertAdjacentHTML('beforeend','<button id="risk">Risk</button><button id="final" disabled>Final</button>');
                  risk.onclick=()=>final.disabled=false;
                  final.onclick=()=>parent.localStorage.done='yes';
                };
              };
              </script>'''
        route.fulfill(content_type='text/html; charset=utf-8', body=body)

    def approve(self):
        with self.commands.lock():
            return self.commands.approve('12', self.token, '12', '2', '金融不良资产')

    def test_view_then_approve_register_and_durable_duplicate_rejection(self):
        self.assertIsNone(self.page.evaluate('localStorage.clicks'))
        result = self.approve()
        self.assertEqual(result['approval'], 'confirmed', result)
        self.assertTrue(result['registration_complete'])
        self.assertEqual(self.page.evaluate('localStorage.clicks'), '1')
        self.assertEqual(self.registration.submit.call_args.args[0]['数量'], '2')
        restarted = CoreCommands(self.reader, self.registration, self.config, self.tmp.name)
        with self.assertRaisesRegex(ValueError, '禁止重复'):
            restarted.approve('12', self.token, '12')
        self.assertEqual(restarted.status('12', self.token)['approval'], 'confirmed')

    def test_explicit_confirmation_and_token_required(self):
        for token, confirm in [(self.token, ''), ('wrong', '12'), (self.token, '99')]:
            with self.subTest(token=token, confirm=confirm), self.assertRaises(ValueError):
                self.commands.approve('12', token, confirm)
        self.assertIsNone(self.page.evaluate('localStorage.clicks'))
        self.registration.submit.assert_not_called()

    def test_expiry_configuration_and_snapshot_changes_rejected(self):
        other = CoreCommands(self.reader, self.registration, {'different': True}, self.tmp.name)
        with self.assertRaisesRegex(ValueError, '配置已变化'):
            other.approve('12', self.token, '12')
        with self.commands.connect() as db:
            db.execute('UPDATE reviews SET snapshot=? WHERE token=?',
                       (json.dumps(dict(self.commands.snapshot(self.review), title='different')), self.token))
        with self.assertRaisesRegex(ValueError, '字段发生变化'):
            self.approve()
        with self.commands.connect() as db:
            db.execute('UPDATE reviews SET created=0')
        with self.assertRaisesRegex(ValueError, '过期'):
            self.approve()
        self.assertIsNone(self.page.evaluate('localStorage.clicks'))

    def test_registration_preflight_blocks_clicks(self):
        self.registration.validate.side_effect = ValueError('directory missing')
        with self.assertRaisesRegex(ValueError, 'directory missing'):
            self.approve()
        self.assertIsNone(self.page.evaluate('localStorage.clicks'))
        self.assertEqual(self.commands.status('12', self.token)['approval'], 'not_started')

    def test_uncertain_result_is_durable_and_never_registers(self):
        self.commands.verify_removed = Mock(return_value=False)
        result = self.approve()
        self.assertEqual(result['approval'], 'unknown')
        self.registration.submit.assert_not_called()
        with self.assertRaisesRegex(ValueError, '禁止重复'):
            self.approve()

    def test_partial_registration_does_not_repeat_approval(self):
        self.registration.submit.return_value = {'Obsidian': True, '企业微信': False}
        result = self.approve()
        self.assertEqual(result['approval'], 'confirmed', result)
        self.assertFalse(result['registration_complete'])
        self.assertEqual(self.commands.status('12', self.token)['registration'][0]['channels']['企业微信'], False)
        with self.assertRaises(ValueError):
            self.approve()

    def test_inactive_task_rejected_without_click(self):
        self.page.locator('#tab-con li').evaluate("el => el.setAttribute('tabid', 'MSG_99')")
        with self.assertRaisesRegex(ValueError, '激活'):
            self.approve()
        self.assertIsNone(self.page.evaluate('localStorage.clicks'))

    def test_command_lock_rejects_concurrent_calls(self):
        other = CoreCommands(self.reader, self.registration, self.config, self.tmp.name)
        with self.commands.lock():
            with self.assertRaisesRegex(ValueError, '另一个本地命令'):
                with other.lock():
                    self.fail('second command acquired lock')

    def test_click_exception_never_becomes_success_or_registration(self):
        with patch.object(ApprovalHelper, '_wait_click', side_effect=RuntimeError('click failed')):
            result = self.approve()
        self.assertEqual(result['approval'], 'unknown')
        self.assertIn('同意点击结果未确认', result['error'])
        self.registration.submit.assert_not_called()
        self.assertEqual(self.commands.status('12', self.token)['approval'], 'unknown')

    def test_task_switch_before_final_confirmation_stops(self):
        original = self.commands.guard
        calls = []

        def guard(task):
            calls.append(task)
            if len(calls) == 5:
                self.page.locator('#tab-con li').evaluate("el => el.setAttribute('tabid', 'MSG_99')")
            original(task)

        self.commands.guard = guard
        result = self.approve()
        self.assertEqual(result['approval'], 'unknown')
        self.assertIsNone(self.page.evaluate('localStorage.done'))
        self.registration.submit.assert_not_called()


if __name__ == '__main__':
    unittest.main()
