"""Synthetic browser pages only; prove viewing never dispatches approval clicks."""
import json
from pathlib import Path
import sys
import unittest
from unittest.mock import Mock
from playwright.sync_api import sync_playwright

sys.path.insert(0, str(Path(__file__).parents[1]))
from src.browser import BrowserHelper
from src.approver import ApprovalHelper
from src.pending import PendingReader, SNAPSHOT


class PendingTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.p = sync_playwright().start()
        cls.chrome = cls.p.chromium.launch(channel='msedge', headless=True)

    @classmethod
    def tearDownClass(cls):
        cls.chrome.close()
        cls.p.stop()

    def setUp(self):
        self.context = self.chrome.new_context()
        self.addCleanup(self.context.close)
        self.page = self.context.new_page()
        self.browser = BrowserHelper()
        # Scope fixture browsing to this context, not other tests.
        self.browser.browser = Mock(contexts=[self.context])
        self.config = {'approval': {'approve_button_selector': '#agree', 'fields': {'事项名称': '#title'}}}
        self.reader = PendingReader(self.browser, self.config, Mock())
        self.mode = 'frame'
        self.detail = '<div id="title">detail-12</div><button id="agree" onclick="window.approved=true">同意</button>'
        self.context.route('**/*', self.route)
        self.page.goto('http://fixture.test/home')

    def route(self, route):
        if '/home' not in route.request.url:
            route.fulfill(content_type='text/html', body=self.detail)
            return
        cache = {key: {'msgContent': {'taskId': task, 'PROC_TITLE': 'same title', 'PROC_NAME': '审批', 'ACTIVITY_NAME': 'risk'},
                       'tcmpUrl': '/detail?taskId=' + task} for key, task in [('a', '11'), ('b', '12')]}
        handler = {
            'frame': "document.querySelector('#details').src='/detail?taskId='+id",
            'popup': "window.open('/detail?taskId='+id)",
            'wrong': "document.querySelector('#details').src='/detail?taskId=999'",
            'delegate': "document.querySelector('#delegate').innerHTML='<input name=clientUserId>'",
        }[self.mode]
        route.fulfill(content_type='text/html', body=f'''<div id="trust_pagelet_lcdb">
            <input id="trust_pagelet_lcdb-itemnumber" value="7" type="hidden">
            <div class="_dataitem_" paramcacheid="a" onclick="openTask('11')">same title</div>
            <div class="_dataitem_" paramcacheid="b" onclick="openTask('12')">same title</div>
            </div><div id="delegate"></div><iframe id="details"></iframe><script>
            const cache={json.dumps(cache)}; window.TrustUI={{getComp:()=>({{_dataparamCaches:cache}})}};
            function openTask(id){{ window.opened=id; {handler} }}
            </script>''')

    def test_partial_list_keeps_duplicate_titles_distinct(self):
        result = self.reader.list_tasks()
        self.assertEqual(result['total'], 7)
        self.assertFalse(result['complete'])
        self.assertEqual([x['task_id'] for x in result['items']], ['11', '12'])
        self.assertIsNone(self.page.evaluate('window.opened'))

    def test_exact_task_opens_frame_and_does_not_approve(self):
        result = self.reader.view_task('12', timeout=2)
        self.assertEqual(result['records'][0]['事项名称'], 'detail-12')
        self.assertTrue(result['read_only'])
        self.assertEqual(self.page.evaluate('window.opened'), '12')
        self.assertIsNone(self.page.frames[1].evaluate('window.approved'))

    def test_popup_supported_without_approval(self):
        self.mode = 'popup'
        self.page.reload()
        result = self.reader.view_task('12', timeout=2)
        self.assertEqual(result['task_id'], '12')
        self.assertIsNone(self.context.pages[-1].evaluate('window.approved'))

    def test_wrong_task_and_delegation_stop(self):
        for mode in ['wrong', 'delegate']:
            self.mode = mode
            self.page.reload()
            with self.subTest(mode=mode), self.assertRaises(ValueError):
                self.reader.view_task('12', timeout=.4)

    def test_unknown_task_and_external_url_never_click(self):
        with self.assertRaises(ValueError):
            self.reader.view_task('99', timeout=.1)
        self.page.evaluate("cache.b.tcmpUrl='https://other.test/detail?taskId=12'")
        with self.assertRaises(ValueError):
            self.reader.view_task('12', timeout=.1)
        self.assertIsNone(self.page.evaluate('window.opened'))

    def test_duplicate_homepages_rejected(self):
        self.context.new_page().goto('http://fixture.test/home')
        with self.assertRaises(ValueError):
            self.reader.list_tasks()

    def test_stale_other_task_cannot_supply_missing_title(self):
        self.page.evaluate("document.body.insertAdjacentHTML('beforeend', '<div id=title>unrelated portal title</div>')")
        self.detail = '<button id="agree" onclick="window.approved=true">同意</button>'
        with self.assertRaisesRegex(ValueError, '未提取到事项名称'):
            self.reader.view_task('12', timeout=2)
        self.assertIsNone(self.page.frames[1].evaluate('window.approved'))

    def test_new_oa_extract_never_clicks(self):
        self.page.set_content('<input id="subject" value="OA title"><input id="operation_btn_14_a" type="button" onclick="window.approved=true"><textarea>remarks</textarea>')
        helper = ApprovalHelper(self.browser, {}, oa_type='new', log_callback=Mock())
        result = helper.extract_current_page(self.page)
        self.assertEqual(result[0]['事项名称'], 'OA title')
        self.assertIsNone(self.page.evaluate('window.approved'))

    def test_pagination_waits_for_records_with_reused_row_keys(self):
        self.page.evaluate("""() => {
          document.querySelector('#trust_pagelet_lcdb-itemnumber').value = '2';
          const root = document.querySelector('#trust_pagelet_lcdb');
          root.querySelectorAll('._dataitem_').forEach(el => el.remove());
          root.insertAdjacentHTML('beforeend', `<div id="rows"></div>
            <div id="trust_pagelet_lcdb-footer"><div class="layui-laypage">
            <a class="layui-laypage-prev">prev</a>
            <span class="layui-laypage-curr"><em></em><em>1</em></span>
            <a class="layui-laypage-next">next</a></div></div>`);
          window.renderPage = n => {
            document.querySelector('.layui-laypage-curr em:last-child').textContent = n;
            for (const [dir, target, disabled] of [['prev', n-1, n===1], ['next', n+1, n===2]]) {
              const link = document.querySelector('.layui-laypage-'+dir);
              link.classList.toggle('layui-disabled', disabled);
              link.setAttribute('data-page', target);
              link.onclick = () => { if (!disabled) renderPage(target); };
            }
            document.querySelector('#rows').innerHTML = '';
            setTimeout(() => {
              cache.a = {msgContent:{taskId:String(n+10)}, tcmpUrl:'/detail?taskId='+(n+10)};
              document.querySelector('#rows').innerHTML = '<div class="_dataitem_" paramcacheid="a">task</div>';
            }, 120);
          };
          renderPage(1);
        }""")
        self.page.locator('._dataitem_').wait_for()
        result = self.reader.list_tasks()
        self.assertEqual([item['task_id'] for item in result['items']], ['11', '12'])
        self.assertTrue(result['complete'])
        self.assertEqual(self.page.locator('.layui-laypage-curr em:last-child').inner_text(), '1')

    def test_task_identity_checks_all_ancestors(self):
        parent = Mock(url='http://fixture.test/detail?taskId=99', parent_frame=None)
        child = Mock(url='http://fixture.test/detail?taskId=12', parent_frame=parent)
        child.frame_element.return_value.is_visible.return_value = True
        self.assertFalse(self.reader._task_frame(child, '12', ('http', 'fixture.test')))

    def test_invalid_enabled_pager_is_not_treated_as_last_page(self):
        self.page.evaluate("""() => document.querySelector('#trust_pagelet_lcdb').insertAdjacentHTML('beforeend',
          '<div id="trust_pagelet_lcdb-footer"><div class="layui-laypage">' +
          '<span class="layui-laypage-curr"><em>1</em></span>' +
          '<a class="layui-laypage-next" data-page="invalid">next</a></div></div>')""")
        with self.assertRaisesRegex(Exception, '分页目标无效'):
            self.reader.list_tasks()

    def test_restore_error_does_not_hide_original_failure(self):
        snapshot = self.page.evaluate(SNAPSHOT)
        snapshot['items'].append(dict(snapshot['items'][0]))
        self.reader._first_page = Mock(side_effect=[snapshot, ValueError('restore failed')])
        with self.assertRaisesRegex(ValueError, '当前页出现多次'):
            self.reader.list_tasks()
        self.reader.log.assert_called_once()

    def close_fixture(self, task='12', hidden=False):
        self.page.goto('http://fixture.test/amcs/index.htm')
        self.page.set_content(f'''<iframe id="homepage_iframe"></iframe><ul id="tab-con">
          <li class="active" tabid="MSG_12" title="待办事宜处理"
              url="/amcs/bpm/client/mw/open?taskId={task}">
            <span class="h-tab-close" style="visibility:{'hidden' if hidden else 'visible'}"
              onclick="window.closedTask=true;this.parentElement.remove()">close</span></li>
          <li tabid="MSG_13">other task</li></ul>''')

    def test_close_only_matching_active_internal_tab(self):
        self.close_fixture()
        self.assertTrue(self.reader.close_task('12')['closed'])
        self.assertEqual(self.page.locator('[tabid="MSG_13"]').count(), 1)
        self.assertFalse(self.page.is_closed())

    def test_close_rejects_wrong_hidden_or_inactive_tab(self):
        for task, hidden, requested in [('99', False, '12'), ('12', True, '12'), ('12', False, '13')]:
            with self.subTest(task=task, hidden=hidden, requested=requested):
                self.close_fixture(task, hidden)
                with self.assertRaises(ValueError):
                    self.reader.close_task(requested)
                self.assertIsNone(self.page.evaluate('window.closedTask'))


if __name__ == '__main__':
    unittest.main()
