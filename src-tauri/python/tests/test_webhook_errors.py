import importlib.util
import json
from pathlib import Path
import unittest
from unittest.mock import Mock, patch


def load_module(name):
    spec = importlib.util.spec_from_file_location(name, Path(__file__).parents[1] / 'src' / f'{name}.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


webhook = load_module('webhook')
registration = load_module('registration')


class WebhookErrorTests(unittest.TestCase):
    def setUp(self):
        self.helper = webhook.WebhookHelper({'webhook': {
            'url': 'https://example.invalid/hook?key=private-token',
            'schema': {'title': 'field-title', 'dept': ''},
        }})

    def test_business_error_reaches_ui_log_without_secret(self):
        response = Mock(status_code=200)
        response.json.return_value = {'errcode': 40001, 'errmsg':
            'invalid field at https://example.invalid/hook?key=private-token private-token'}
        log = Mock()
        service = registration.Registration(
            {'wechat_enabled': True, 'obsidian_enabled': False}, self.helper, log)
        with patch.object(webhook.requests, 'post', return_value=response):
            self.assertEqual(service.submit({'事项名称': 'test'}), {'企业微信': False})
        message, level = log.call_args.args
        self.assertIn('40001', message)
        self.assertIn('invalid field', message)
        self.assertNotIn('private-token', message)
        self.assertNotIn('https://', message)
        self.assertEqual(level, 'error')

    def test_transport_errors_have_safe_distinct_messages(self):
        for exception, expected in (
            (webhook.requests.exceptions.ProxyError, '代理'),
            (webhook.requests.exceptions.SSLError, '证书'),
            (webhook.requests.exceptions.Timeout, '超时'),
            (webhook.requests.exceptions.ConnectionError, '网络'),
        ):
            with self.subTest(exception=exception), patch.object(
                webhook.requests, 'post', side_effect=exception('private-token')
            ) as post:
                self.assertFalse(self.helper.submit({}))
                self.assertIn(expected, self.helper.last_error)
                self.assertNotIn('private-token', self.helper.last_error)
                self.assertEqual(post.call_count, 1)

    def test_html_and_missing_success_code_are_not_success(self):
        for payload in (ValueError('html'), [], {}, {'errmsg': 'unknown'}):
            response = Mock(status_code=200)
            if isinstance(payload, Exception):
                response.json.side_effect = payload
            else:
                response.json.return_value = payload
            with self.subTest(payload=payload), patch.object(webhook.requests, 'post', return_value=response):
                self.assertFalse(self.helper.submit({}))
                self.assertIn('HTTP 200', self.helper.last_error)

    def test_http_error_cannot_be_masked_by_zero_business_code(self):
        response = Mock(status_code=403)
        response.json.return_value = {'errcode': 0, 'errmsg': 'denied'}
        with patch.object(webhook.requests, 'post', return_value=response):
            self.assertFalse(self.helper.submit({}))
        self.assertIn('HTTP 403', self.helper.last_error)

    def test_success_clears_error_and_omits_empty_mapping(self):
        response = Mock(status_code=200)
        response.json.return_value = {'errcode': 0}
        self.helper.last_error = 'previous failure'
        with patch.object(webhook.requests, 'post', return_value=response) as post:
            self.assertTrue(self.helper.submit({'事项名称': 'test'}))
        self.assertEqual(self.helper.last_error, '')
        payload = json.loads(post.call_args.kwargs['data'])
        self.assertEqual(payload['schema'], {'field-title': '项目名称'})


if __name__ == '__main__':
    unittest.main()
