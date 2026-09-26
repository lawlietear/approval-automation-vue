"""Core lock-screen command only interacts with the verified lock dialog."""
from pathlib import Path
import sys
import unittest
from unittest.mock import Mock

from playwright.sync_api import sync_playwright

sys.path.insert(0, str(Path(__file__).parents[1]))
from src.browser import BrowserHelper
from src.pending import PendingReader


class UnlockTests(unittest.TestCase):
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
        self.context.route('**/amcs/index.htm', lambda route: route.fulfill(
            content_type='text/html; charset=utf-8', body='''
              <iframe id="homepage_iframe"></iframe>
              <div class="h_floatdiv m-message-positon" style="width:400px;height:200px">
                <div class="m-message-title">当前会话已经失效,屏幕已锁定,请激活!</div>
                <input type="password" name="pwd"><button type="button" onclick="unlock()">确定</button>
                <button type="button">扫码登录</button>
              </div><button id="agree" onclick="window.approved=true">同意</button>
              <script>function unlock(){window.unlockClicks=(window.unlockClicks||0)+1;
                if(document.querySelector('input[name=pwd]').value==='synthetic-secret')
                  document.querySelector('.h_floatdiv').style.display='none';}</script>'''))
        self.page = self.context.new_page()
        self.page.goto('http://fixture.test/amcs/index.htm')
        browser = BrowserHelper()
        browser.browser = Mock(contexts=[self.context])
        self.reader = PendingReader(browser, {}, Mock())

    def test_only_lock_dialog_is_unlocked(self):
        result = self.reader.unlock_session('synthetic-secret')
        self.assertTrue(result['unlocked'])
        self.assertEqual(self.page.evaluate('window.unlockClicks'), 1)
        self.assertEqual(self.page.locator('input[name=pwd]').input_value(), '')
        self.assertIsNone(self.page.evaluate('window.approved'))

    def test_other_password_dialog_is_rejected_without_click(self):
        self.page.locator('.m-message-title').evaluate(
            "el => el.textContent = '您的密码已经过期，需修改密码！'")
        with self.assertRaisesRegex(ValueError, '未找到唯一'):
            self.reader.unlock_session('synthetic-secret')
        self.assertIsNone(self.page.evaluate('window.unlockClicks'))
        self.assertIsNone(self.page.evaluate('window.approved'))

    def test_two_locked_pages_are_rejected(self):
        other = self.context.new_page()
        other.goto('http://fixture.test/amcs/index.htm')
        with self.assertRaisesRegex(ValueError, '未找到唯一'):
            self.reader.unlock_session('synthetic-secret')
        self.assertIsNone(self.page.evaluate('window.unlockClicks'))
        self.assertIsNone(other.evaluate('window.unlockClicks'))


if __name__ == '__main__':
    unittest.main()
