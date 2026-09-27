"""Isolated HTTP fixture: live query, pagination and zero workflow callbacks."""
import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
import sys
import threading
import unittest
from urllib.parse import parse_qs
from unittest.mock import Mock

from playwright.sync_api import sync_playwright

sys.path.insert(0, str(Path(__file__).parents[1]))
from src.department_reader import PATH
from src.safe_debug import inspect


class DepartmentReaderTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *_):
                pass

            def do_GET(self):
                self.server.gets.append(self.path)
                self.send_response(200)
                self.send_header('Content-Type', 'text/html')
                self.end_headers()
                self.wfile.write(b'<body></body>')

            def do_POST(self):
                params = parse_qs(self.rfile.read(int(self.headers['Content-Length'])).decode())
                self.server.posts.append((self.path, params, self.headers.get('Cookie')))
                page = int(params['pageNo'][0])
                mode = self.server.mode
                status = 302 if mode == 'redirect' else 200
                self.send_response(status)
                if mode == 'redirect':
                    self.send_header('Location', '/forbidden-submit')
                self.send_header('Content-Type', 'text/html' if mode == 'login' else 'application/json')
                self.end_headers()
                rows = self.server.rows
                total = len(rows)
                selected = rows[(page-1)*10:page*10]
                if mode == 'duplicate' and page == 2:
                    selected = rows[:len(selected)]
                if mode == 'changed-total' and page == 2:
                    total += 1
                if mode == 'changed-first' and page == 1 and len(self.server.posts) > 1:
                    selected = list(reversed(selected))
                if mode == 'short':
                    selected = []
                data = {'total': total, 'rows': selected}
                if mode == 'string-total':
                    data['total'] = str(total)
                if mode == 'redirect-field':
                    data['redirectUrl'] = '/forbidden-submit'
                if mode == 'missing-name':
                    data['rows'] = [{'orgid': 'a'}] * len(selected)
                if mode == 'failed':
                    data['returncode'] = '0'
                if mode == 'bad-total':
                    data['total'] = True
                body = b'not-json' if mode == 'malformed' else json.dumps(data).encode()
                self.wfile.write(body)

        cls.server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()
        cls.origin = f'http://127.0.0.1:{cls.server.server_port}'
        cls.p = sync_playwright().start()
        cls.chrome = cls.p.chromium.launch(channel='msedge', headless=True)
        cls.capture = (Path(__file__).parents[3] / 'captures/department-window-2026-09-26.html').read_text(encoding='utf-8')

    @classmethod
    def tearDownClass(cls):
        cls.chrome.close()
        cls.p.stop()
        cls.server.shutdown()
        cls.server.server_close()
        cls.thread.join()

    def setUp(self):
        self.server.mode = 'ok'
        self.server.posts, self.server.gets = [], []
        self.server.rows = [{'orgid': f'fresh-{i}', 'orgname': f'实时部门{i}'} for i in range(12)]
        self.context = self.chrome.new_context()
        self.addCleanup(self.context.close)
        self.context.add_cookies([{'name': 'session', 'value': 'fixture', 'url': self.origin}])
        self.page = self.context.new_page()
        self.page.goto(self.origin + '/amcs/index.htm')
        self.page.set_content(self.capture)
        self.page.evaluate("""() => {
          document.querySelector('#selectPartjobOrgWin').style.display='none';
          window.clicks=0; document.addEventListener('click',()=>window.clicks++);
          window._setComebackWin_args=['unchanged'];
          window._setComebackWin_callBack=()=>{throw Error('must not run')};
          window.savedCallback=window._setComebackWin_callBack;
          window.Horn={getComp:()=>{throw Error('must not invoke components')}};
        }""")
        self.browser = Mock(browser=Mock(contexts=[self.context]))

    def read(self):
        return inspect(self.browser, {}, {'debug_steps': 4}, Mock(), options_only=True)

    def assert_no_side_effects(self):
        self.assertEqual(self.page.evaluate('window.clicks'), 0)
        self.assertTrue(self.page.evaluate("_setComebackWin_callBack===savedCallback && _setComebackWin_args[0]==='unchanged'"))
        self.assertFalse(self.page.locator('#selectPartjobOrgWin').is_visible())
        self.assertTrue(all(path == PATH and cookie == 'session=fixture' for path, _, cookie in self.server.posts))
        self.assertNotIn('/forbidden-submit', self.server.gets)

    def test_reads_hidden_window_fresh_paginated_data_without_callbacks(self):
        result = self.read()
        self.assertEqual(result['departments']['items'], [{'id': r['orgid'], 'name': r['orgname']} for r in self.server.rows])
        self.assertEqual([p[1]['pageNo'] for p in self.server.posts], [['1'], ['2'], ['1']])
        self.assertTrue(result['departments']['complete'])
        self.assertEqual(result['records'], [])
        self.assertFalse(result['registration_enabled'])
        self.assert_no_side_effects()

    def test_single_page_and_string_total_compatible(self):
        self.server.rows = self.server.rows[:2]
        self.server.mode = 'string-total'
        result = self.read()
        self.assertEqual(result['departments']['pages'], '1')
        self.assertEqual(len(self.server.posts), 1)
        self.assert_no_side_effects()

    def test_errors_never_fall_back_to_cached_rows_or_follow_redirect(self):
        for mode in ['redirect', 'login', 'malformed', 'duplicate', 'changed-total',
                     'changed-first', 'short', 'redirect-field', 'missing-name', 'failed', 'bad-total']:
            with self.subTest(mode=mode):
                self.server.mode = mode
                self.server.posts = []
                with self.assertRaises(ValueError):
                    self.read()
                self.assert_no_side_effects()

    def test_visible_password_blocks_request(self):
        self.page.evaluate("document.body.insertAdjacentHTML('beforeend','<input type=password>')")
        with self.assertRaisesRegex(ValueError, '登录或解锁'):
            self.read()
        self.assertEqual(self.server.posts, [])

    def test_multiple_core_windows_block_request(self):
        other = self.context.new_page()
        other.goto(self.origin + '/amcs/index.htm')
        other.set_content(self.capture)
        with self.assertRaisesRegex(ValueError, '唯一'):
            self.read()
        self.assertEqual(self.server.posts, [])


if __name__ == '__main__':
    unittest.main()
