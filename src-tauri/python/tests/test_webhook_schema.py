import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import Mock, patch

sys.path.insert(0, str(Path(__file__).parents[1]))
from src.webhook import WebhookHelper
from src.registration import Registration, apply_wechat_settings
from src.activity import Activity


class WebhookSchemaTests(unittest.TestCase):
    def setUp(self):
        self.config = {'url':'https://example.invalid/hook',
            'schema':{'title':'t','dept':'d','contract_amount':'a','qty':'q'},
            'columns':{'t':{'title':'自定义项目','type':'text'},
                'd':{'title':'办理部门','type':'single_select','enum':['合规部','投资部']},
                'a':{'title':'合同额','type':'number'}, 'q':{'title':'数量','type':'number'}},
            'value_mappings':{'dept':{'风控部':'合规部'}}}
        self.helper = WebhookHelper({'webhook':self.config})

    def test_types_and_explicit_option_translation_drive_actual_payload(self):
        result = self.helper.build_payload({'事项名称':'项目','部门':'风控部','合同金额':'1,234.50','数量':'2'})
        self.assertEqual(result['schema']['t'], '自定义项目')
        self.assertEqual(result['add_records'][0]['values'], {'t':'项目','d':[{'text':'合规部'}],'a':1234.5,'q':2})
        self.config['columns']['d'] = {'title':'部门','type':'text'}
        self.config['value_mappings'].clear()
        self.assertEqual(self.helper.build_payload({'部门':'风控部'})['add_records'][0]['values']['d'], '风控部')

    def test_enum_mismatch_and_invalid_numbers_fail_before_network(self):
        for data in [{'部门':'未知部'}, {'合同金额':'12万元'}, {'合同金额':'1,23'},
                     {'合同金额':'NaN'}, {'合同金额':'9007199254740992'}, {'合同金额':'0.1234567890123456789'},
                     {'数量':'1.5'}, {'数量':'0'}]:
            with self.subTest(data=data), patch('src.webhook.requests.post') as post:
                self.assertFalse(self.helper.submit(data))
                self.assertEqual(self.helper.last_state, 'failed')
                self.assertIn('未发送', self.helper.last_error)
                post.assert_not_called()

    def test_unsupported_type_missing_metadata_and_stale_enum_rule_fail(self):
        for modify in [lambda c:c['columns']['t'].update(type='number'),
                       lambda c:c['columns'].pop('t'),
                       lambda c:c['columns']['d'].update(enum=['投资部'])]:
            with self.subTest(modify=modify):
                config = json.loads(json.dumps(self.config))
                modify(config)
                helper = WebhookHelper({'webhook':config})
                with patch('src.webhook.requests.post') as post:
                    self.assertFalse(helper.submit({'事项名称':'项目'}))
                    post.assert_not_called()

    def test_old_config_and_unspecified_enum_still_work(self):
        old = WebhookHelper({'webhook':{'schema':{'title':'t','dept':'d','qty':'q','contract_amount':'a'}}})
        values = old.build_payload({'部门':'旧部门','数量':'bad','合同金额':'12万元'})['add_records'][0]['values']
        self.assertEqual(values, {'d':[{'text':'旧部门'}],'q':1,'a':'12万元'})
        self.assertEqual(old.build_payload({})['schema']['a'], '金额')
        self.config['value_mappings'].clear()
        del self.config['columns']['d']['enum']
        self.assertEqual(self.helper.build_payload({'部门':'任意值'})['add_records'][0]['values']['d'], [{'text':'任意值'}])

    def test_missing_title_mapping_is_rejected_before_approval_or_send(self):
        self.config['schema'].pop('title')
        registration = Registration({'wechat_enabled': True, 'obsidian_enabled': False}, self.helper, Mock())
        with self.assertRaisesRegex(ValueError, '项目名称'):
            registration.validate()
        with patch('src.webhook.requests.post') as post:
            self.assertFalse(self.helper.submit({'事项名称': '项目', '部门': '合规部'}))
            self.assertEqual(self.helper.last_state, 'failed')
            post.assert_not_called()

    def test_saved_metadata_reaches_sender_and_can_be_explicitly_cleared(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp)/'config.json'
            saved = {'wechat_schema':self.config['schema'],'wechat_columns':self.config['columns'],
                     'wechat_value_mappings':self.config['value_mappings']}
            path.with_name('push-settings.json').write_text(json.dumps(saved),encoding='utf-8')
            config = {'webhook':{'url':'https://example.invalid'}}
            apply_wechat_settings(path, config)
            self.assertEqual(WebhookHelper(config).build_payload({'部门':'风控部'})['add_records'][0]['values']['d'], [{'text':'合规部'}])
            path.with_name('push-settings.json').write_text(json.dumps({'wechat_columns':{},'wechat_value_mappings':{}}))
            apply_wechat_settings(path, config)
            self.assertEqual(config['webhook']['columns'], {})

    def test_failed_validation_preserves_local_record_and_retry_only_sends_remote(self):
        with tempfile.TemporaryDirectory() as tmp:
            settings = {'wechat_enabled':True,'obsidian_enabled':True,'obsidian_directory':tmp}
            reg = Registration(settings, self.helper, Mock())
            journal = Activity(Path(tmp)/'config.json')
            item = journal.begin('old')
            item['approval'] = 'flow_returned'
            journal.add_records(item, [{'事项名称':'项目','部门':'未知部'}], reg)
            with patch('src.webhook.requests.post') as post:
                self.assertEqual(journal.submit_record(item, 0, reg), {'Obsidian':True,'企业微信':False})
                post.assert_not_called()
            self.config['value_mappings']['dept']['未知部'] = '投资部'
            latest = journal.get(item['id'])
            response = Mock(status_code=200)
            response.json.return_value = {'errcode':0}
            with patch('src.webhook.requests.post',return_value=response) as post:
                journal.recover(item['id'],0,'企业微信',latest['revision'],'retry',reg)
                self.assertEqual(post.call_count,1)
            self.assertEqual(len(list(Path(tmp).glob('*.md'))),1)


if __name__ == '__main__':
    unittest.main()
