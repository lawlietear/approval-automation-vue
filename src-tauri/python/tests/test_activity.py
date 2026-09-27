import json
from pathlib import Path
import sys
import tempfile
import runpy
import unittest
from unittest.mock import Mock, patch

import requests

sys.path.insert(0, str(Path(__file__).parents[1]))
from src.activity import Activity
from src.registration import Registration
from src.webhook import WebhookHelper
from src.diagnostics import diagnose


class ActivityTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.config = self.root / 'config.json'
        self.config.write_text('{}')
        self.journal = Activity(self.config)
        self.settings = dict(wechat_enabled=True, obsidian_enabled=True, obsidian_directory=str(self.root))
        self.webhook = WebhookHelper({'webhook': {'url': 'https://example.invalid/?key=secret',
                                                'schema': {'title': 'title', 'time': 'date'}}})
        self.registration = Registration(self.settings, self.webhook, Mock())
        self.item = self.journal.begin('old')
        self.item.update(approval='flow_returned', created='2026-09-24T12:30:00+08:00')
        self.journal.add_records(self.item, [{'事项名称': 'fixture', '数量': '2'}], self.registration)

    def response(self, code=0):
        result = Mock(status_code=200)
        result.json.return_value = {'errcode': code, 'errmsg': 'fixture failure'}
        return result

    def recover(self, channel, action='retry', revision=None):
        latest = self.journal.get(self.item['id'])
        return self.journal.recover(latest['id'], 0, channel, revision or latest['revision'], action, self.registration)

    def test_partial_success_and_retry_only_failed_channel_with_original_date(self):
        with patch('src.webhook.requests.post', return_value=self.response(40001)):
            outcomes = self.journal.submit_record(self.item, 0, self.registration)
        self.assertEqual(outcomes, {'Obsidian': True, '企业微信': False})
        files = list(self.root.glob('*.md'))
        self.assertEqual(len(files), 1)
        self.assertEqual(files[0].name, '2026-9-24.md')
        with patch('src.webhook.requests.post', return_value=self.response()) as post:
            item = self.recover('企业微信')
        self.assertEqual(item['records'][0]['channels']['企业微信']['state'], 'success')
        payload = json.loads(post.call_args.kwargs['data'])
        self.assertEqual(payload['add_records'][0]['values']['date'], '1790224200000')
        self.assertEqual(list(self.root.glob('*.md')), files)
        with self.assertRaisesRegex(ValueError, '禁止重复'):
            self.recover('企业微信')

    def test_timeout_requires_manual_resolution_before_retry(self):
        with patch('src.webhook.requests.post', side_effect=requests.exceptions.Timeout()):
            self.journal.send(self.item, 0, '企业微信', self.registration)
        with self.assertRaisesRegex(ValueError, '禁止重复'):
            self.recover('企业微信')
        with patch('src.webhook.requests.post') as post:
            item = self.recover('企业微信', 'absent')
            post.assert_not_called()
        self.assertEqual(item['records'][0]['channels']['企业微信']['state'], 'failed')
        with patch('src.webhook.requests.post', return_value=self.response()) as post:
            self.recover('企业微信')
        self.assertEqual(post.call_count, 1)

    def test_manual_received_never_sends(self):
        self.item['records'][0]['channels']['企业微信']['state'] = 'sending'
        self.journal.save(self.item)
        with patch('src.webhook.requests.post') as post:
            item = self.recover('企业微信', 'received')
            post.assert_not_called()
        self.assertEqual(item['records'][0]['channels']['企业微信']['state'], 'success')

    def test_interrupted_dispatch_persists_uncertainty_across_restart(self):
        with patch.object(self.registration, 'send_channel', side_effect=KeyboardInterrupt()):
            with self.assertRaises(KeyboardInterrupt):
                self.journal.send(self.item, 0, '企业微信', self.registration)
        self.journal = Activity(self.config)
        self.assertEqual(self.journal.recent()['items'][0]['records'][0]['channels']['企业微信']['state'], 'sending')
        with self.assertRaises(ValueError):
            self.recover('企业微信')

    def test_changed_destination_or_stale_revision_rejected(self):
        old_revision = self.item['revision']
        self.journal.save(self.item)
        with self.assertRaisesRegex(ValueError, '记录已变化'):
            self.recover('企业微信', revision=old_revision)
        self.webhook.url = 'https://different.invalid'
        with self.assertRaisesRegex(ValueError, '目标已变更'):
            self.recover('企业微信')

    def test_unknown_approval_and_disabled_channel_cannot_retry(self):
        self.item['approval'] = 'unknown'
        self.journal.save(self.item)
        with self.assertRaisesRegex(ValueError, '审批结果未确认'):
            self.recover('企业微信')
        self.item['approval'] = 'flow_returned'
        self.item['records'][0]['channels']['企业微信']['state'] = 'disabled'
        self.journal.save(self.item)
        with self.assertRaises(ValueError):
            self.recover('企业微信')

    def test_os_lock_prevents_parallel_recovery(self):
        with self.journal.lock():
            with self.assertRaisesRegex(ValueError, '已有审批'):
                with Activity(self.config).lock():
                    self.fail('must not acquire second lock')

    def test_partial_local_write_is_unknown_and_remote_still_runs(self):
        with patch.object(self.registration, 'write_note', side_effect=OSError()), \
                patch('src.webhook.requests.post', return_value=self.response()):
            self.assertEqual(self.journal.submit_record(self.item, 0, self.registration), {'Obsidian': False, '企业微信': True})
        self.assertEqual(self.item['records'][0]['channels']['Obsidian']['state'], 'unknown')

    def test_missing_folder_known_failure_is_retryable(self):
        self.settings['obsidian_directory'] = str(self.root / 'missing')
        self.item['records'][0]['channels']['Obsidian']['target'] = self.journal.destination(self.registration, 'Obsidian')
        self.journal.save(self.item)
        self.journal.send(self.item, 0, 'Obsidian', self.registration)
        self.assertEqual(self.item['records'][0]['channels']['Obsidian']['state'], 'failed')
        (self.root / 'missing').mkdir()
        item = self.recover('Obsidian')
        self.assertEqual(item['records'][0]['channels']['Obsidian']['state'], 'success')

    def test_pagination_and_no_secret_destination_in_history(self):
        for _ in range(21):
            self.journal.begin('new')
        self.assertTrue(self.journal.recent()['has_more'])
        self.assertEqual(len(self.journal.recent(20)['items']), 2)
        self.assertNotIn('key=secret', self.journal.path.read_bytes().decode('utf-8', errors='ignore'))

    def test_diagnostics_does_not_submit_write_or_navigate(self):
        config = {'webhook': {'enabled': True, 'url': 'https://qyapi.weixin.qq.com/cgi-bin/wedoc/smartsheet/webhook?key=secret',
                              'schema': {'title': 'id'}}}
        self.config.write_text(json.dumps(config))
        self.config.with_name('push-settings.json').write_text(json.dumps(self.settings))
        browser = Mock()
        browser.browser.contexts = []
        with patch('src.diagnostics.BrowserHelper', return_value=browser), \
                patch('src.webhook.requests.post') as post, patch.object(Registration, 'write_note') as note:
            result = diagnose(self.config, 'http://localhost:9222')
        post.assert_not_called()
        note.assert_not_called()
        self.assertTrue(result['read_only'])
        self.assertNotIn('key=secret', json.dumps(result))
        self.assertFalse(list(self.root.glob('*.md')))

    def test_diagnostics_survives_corrupt_config_and_failed_connection(self):
        self.config.write_text('invalid')
        browser = Mock()
        browser.connect.side_effect = RuntimeError('secret')
        with patch('src.diagnostics.BrowserHelper', return_value=browser):
            result = diagnose(self.config, 'http://localhost:9222')
        self.assertGreaterEqual(len([c for c in result['checks'] if c['status'] == 'error']), 2)
        self.assertNotIn('secret', json.dumps(result))

    def test_diagnostics_rejects_incompatible_type_and_stale_option_mapping(self):
        for metadata in [
            {'columns': {'id': {'title': '项目名称', 'type': 'number'}}},
            {'value_mappings': {'dept': {'风控部': '不存在的选项'}}},
        ]:
            with self.subTest(metadata=metadata):
                self.config.write_text(json.dumps({'webhook': {
                    'enabled': True, 'url': 'https://qyapi.weixin.qq.com/cgi-bin/wedoc/smartsheet/webhook?key=secret',
                    'schema': {'title': 'id'}, **metadata}}))
                browser = Mock()
                browser.browser.contexts = []
                with patch('src.diagnostics.BrowserHelper', return_value=browser), patch('src.webhook.requests.post') as post:
                    result = diagnose(self.config, 'http://localhost:9222')
                check = next(c for c in result['checks'] if c['name'] == '企业微信')
                self.assertEqual(check['status'], 'error')
                post.assert_not_called()
                self.assertNotIn('secret', json.dumps(result))

    def runner(self):
        stdout = sys.stdout
        try:
            return runpy.run_path(str(Path(__file__).parents[1] / 'runner.py'))
        finally:
            sys.stdout = stdout

    def test_retry_runner_never_constructs_browser_or_approver(self):
        self.config.write_text(json.dumps({'webhook': {'url': self.webhook.url, 'schema': self.webhook.schema}}))
        self.config.with_name('push-settings.json').write_text(json.dumps(self.settings))
        module = self.runner()
        forbidden = Mock(side_effect=AssertionError('approval must not be reached'))
        emit = Mock()
        with patch.dict(module['main'].__globals__, {'BrowserHelper': forbidden, 'ApprovalHelper': forbidden, 'emit': emit}), \
                patch.object(sys, 'argv', ['runner', '--config', str(self.config), '--activity-action', 'retry',
                    '--activity-id', self.item['id'], '--channel', '企业微信', '--revision', self.item['revision']]), \
                patch('src.webhook.requests.post', return_value=self.response()):
            self.assertEqual(module['main'](), 0)
        forbidden.assert_not_called()
        self.assertEqual(emit.call_args.args[0], 'activity_result')

    def test_debug_mode_blocks_recovery_without_sending(self):
        self.config.with_name('workflow.json').write_text('{"debug_enabled":true,"debug_steps":1}')
        module = self.runner()
        with patch.dict(module['main'].__globals__, {'emit': Mock()}), patch.object(sys, 'argv', [
                'runner', '--config', str(self.config), '--activity-action', 'retry']), \
                patch('src.webhook.requests.post') as post:
            self.assertEqual(module['main'](), 1)
        post.assert_not_called()

    def test_gui_failure_preserves_snapshot_and_never_registers(self):
        self.config.write_text('{"approval":{"approve_button_selector":"#agree"}}')
        self.config.with_name('push-settings.json').write_text(json.dumps(dict(self.settings, wechat_enabled=False)))
        module = self.runner()
        browser = Mock()
        page = Mock(url='http://10.0.150.1/amcs/index.htm')
        browser.list_pages.return_value = [dict(index=0, page=page, title='fixture', url=page.url)]
        browser.get_approval_page.return_value = page
        browser.find_frame_with_selector.return_value = page
        helper = Mock()
        def fail_after_extract(*args):
            helper.before_approval([{'事项名称': 'preserved-before-click'}])
            raise RuntimeError('click outcome unknown')
        helper.process_current_page.side_effect = fail_after_extract
        with patch.dict(module['main'].__globals__, {'BrowserHelper': Mock(return_value=browser),
                'ApprovalHelper': Mock(return_value=helper), 'emit': Mock()}), \
                patch.object(sys, 'argv', ['runner', '--config', str(self.config), '--oa-type', 'old']), \
                patch.object(Registration, 'send_channel') as send:
            module['main']()
        send.assert_not_called()
        latest = self.journal.recent()['items'][0]
        self.assertEqual(latest['approval'], 'unknown')
        self.assertEqual(latest['records'][0]['data']['事项名称'], 'preserved-before-click')


if __name__ == '__main__':
    unittest.main()
