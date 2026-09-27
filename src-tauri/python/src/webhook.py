import json
import re
import time
from decimal import Decimal, InvalidOperation
from urllib.parse import parse_qsl, urlsplit
import requests


class WebhookHelper:
    def __init__(self, config: dict):
        self.webhook_cfg = config.get("webhook", {})
        self.url = self.webhook_cfg.get("url", "")
        self.schema = self.webhook_cfg.get("schema", {})
        self.columns = self.webhook_cfg.get("columns", {})
        self.value_mappings = self.webhook_cfg.get("value_mappings", {})
        self.headers = self.webhook_cfg.get("headers", {
            "Content-Type": "application/json"
        })
        self.timeout = self.webhook_cfg.get("timeout", 10)
        self.last_error = ""
        self.last_state = 'unknown'

    def _fail(self, message, state='unknown'):
        # Server messages can echo the secret webhook URL or its query credentials.
        message = str(message).replace(self.url, "[Webhook链接]") if self.url else str(message)
        for _, value in parse_qsl(urlsplit(self.url).query):
            if value:
                message = message.replace(value, "[已隐藏]")
        message = re.sub(r"https?://[^\s<>\"']+", "[链接已隐藏]", message)
        self.last_error = " ".join(message.split())[:500]
        self.last_state = state
        return False

    FIELDS = {
        'title': ('事项名称', '项目名称'), 'time': ('时间', '时间'),
        'dept': ('部门', '部门'), 'biz_type': ('业务类型', '业务类型'),
        'work_type': ('工作类型', '工作类型'), 'qty': ('数量', '数量'),
        'remark': ('备注', '备注'), 'counterparty': ('交易对手', '交易对手'),
        'contract_amount': ('合同金额', '金额'), 'contract_name': ('合同名称', '合同名称'),
        'contract_no': ('合同编号', '合同编号'),
    }

    def validate_schema(self):
        if not all(isinstance(v, dict) for v in (self.schema, self.columns, self.value_mappings)):
            raise ValueError('企业微信字段配置格式无效')
        ids = [value for value in self.schema.values() if value]
        if any(not isinstance(value, str) for value in ids) or len(set(ids)) != len(ids):
            raise ValueError('企业微信字段标识格式无效或重复')
        if not isinstance(self.schema.get('title'), str) or not self.schema['title'].strip():
            raise ValueError('请配置项目名称对应的字段标识')
        for key, field_id in self.schema.items():
            if not field_id:
                continue
            if key not in self.FIELDS:
                raise ValueError('企业微信字段配置包含不支持的审批信息')
            col = self.columns.get(field_id, {})
            if self.columns and field_id not in self.columns:
                raise ValueError(f'{self.FIELDS[key][1]}对应的列不在已导入表格中')
            if not isinstance(col, dict) or (col and (not isinstance(col.get('title'), str) or not col['title'].strip())):
                raise ValueError('表格列说明格式无效')
            kind = col.get('type', '')
            allowed = ['date_time'] if key == 'time' else ['text'] if key == 'title' else (
                ['text', 'number'] if key in ('qty', 'contract_amount') else ['text', 'single_select'])
            if kind and kind not in allowed:
                raise ValueError(f'{self.FIELDS[key][1]}目标列类型不兼容，请重新选择')
            if 'enum' in col:
                options = col['enum']
                if not isinstance(options, list) or any(not isinstance(v, str) or not v.strip() for v in options) or len(set(options)) != len(options):
                    raise ValueError('目标列的下拉选项格式无效')
        for key, rules in self.value_mappings.items():
            if not isinstance(rules, dict):
                raise ValueError('选项对应关系格式无效')
            if not rules:
                continue
            col = self.columns.get(self.schema.get(key), {})
            if col.get('type') != 'single_select' or 'enum' not in col:
                raise ValueError('选项对应关系未绑定有效的单选列')
            if any(not isinstance(k, str) or not k.strip() or v not in col['enum'] for k, v in rules.items()):
                raise ValueError('选项对应关系包含无效原值或目标选项')

    def build_payload(self, data, recorded_at=None):
        """Validate everything before the first network request; never infer units/options."""
        self.validate_schema()
        record, schema = {}, {}
        for key, (source, default_title) in self.FIELDS.items():
            field_id = self.schema.get(key)
            if not field_id:
                continue
            col = self.columns.get(field_id, {})
            schema[field_id] = col.get('title') or default_title
            kind = col.get('type', '')
            value = data.get(source)
            if key == 'time':
                from datetime import datetime
                timestamp = datetime.fromisoformat(recorded_at).timestamp() if recorded_at else time.time()
                value = str(int(timestamp * 1000))
            elif key == 'qty':
                value = data.get(source, 1)
                if not kind:
                    try:
                        value = int(value)
                    except (ValueError, TypeError):
                        value = 1
            if value is None or value == '':
                continue
            label = default_title
            if kind == 'number':
                text = str(value).strip()
                if not re.fullmatch(r'[+-]?(?:[0-9]+|[0-9]{1,3}(?:,[0-9]{3})+)(?:\.[0-9]+)?', text):
                    raise ValueError(f'{label}需要纯数字；不会自动换算万元、元或清理单位')
                try:
                    number = Decimal(text.replace(',', ''))
                    converted = int(number) if number == number.to_integral_value() else float(number)
                except (InvalidOperation, ValueError, OverflowError):
                    raise ValueError(f'{label}数字无效') from None
                if abs(number) > 9007199254740991 or Decimal(str(converted)) != number:
                    raise ValueError(f'{label}超出安全数字精度，请改用文本列')
                if key == 'qty' and (number != number.to_integral_value() or number < 1):
                    raise ValueError('数量必须是正整数')
                value = converted
            elif kind == 'text':
                value = str(value)
            elif kind == 'single_select':
                if not isinstance(value, str):
                    raise ValueError(f'{label}单选值必须是文字')
                value = self.value_mappings.get(key, {}).get(value, value)
                if 'enum' in col and value not in col['enum']:
                    raise ValueError(f'{label}的值“{value}”不在目标表格选项中；请在设置中添加明确对应关系')
                value = [{'text': value}]
            elif not kind and key in ('dept', 'biz_type', 'work_type'):
                value = [{'text': value}]
            record[field_id] = value
        return {'schema': schema, 'add_records': [{'values': record}]}

    def submit(self, data: dict, recorded_at=None) -> bool:
        """
        通过 HTTP POST 将数据发送到企业微信文档 webhook。
        数据格式遵循 schema + add_records 结构。
        """
        self.last_error = ""
        self.last_state = 'unknown'
        if not self.url:
            return self._fail("未配置 Webhook 链接，请在设置中填写", 'failed')

        if not self.schema:
            return self._fail("未配置表格字段映射，请在设置中导入 schema", 'failed')

        try:
            payload = self.build_payload(data, recorded_at)
        except (ValueError, TypeError, OverflowError) as exc:
            return self._fail(f'发送前校验失败：{exc}；未发送企业微信请求', 'failed')

        try:
            response = requests.post(
                self.url,
                headers=self.headers,
                data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
                timeout=self.timeout,
                allow_redirects=False,
            )
            status = response.status_code
            try:
                result = response.json()
            except ValueError:
                return self._fail(f"HTTP {status}，返回内容不是 JSON，无法确认登记；请检查链接或网络拦截，不要直接重跑审批")
            if not isinstance(result, dict):
                return self._fail(f"HTTP {status}，接口响应格式异常，无法确认登记")
            code = result.get("errcode")
            valid_code = type(code) is int or (isinstance(code, str) and code.isdigit())
            if not 200 <= status < 300 or not valid_code or code not in (0, "0"):
                state = 'failed' if 200 <= status < 300 and valid_code and int(code) != 0 else 'unknown'
                return self._fail(f"HTTP {status}，errcode={code if code is not None else '缺失'}，errmsg={result.get('errmsg', '未提供错误说明')}；请核对 Webhook 链接及目标表格字段映射", state)
            self.last_state = 'success'
            return True
        except requests.exceptions.ProxyError:
            return self._fail("代理连接失败，请检查单位电脑代理设置及代理程序是否运行")
        except requests.exceptions.SSLError:
            return self._fail("HTTPS 证书验证失败，请检查单位网络证书或联系网络管理员")
        except requests.exceptions.Timeout:
            return self._fail("请求超时，无法确认服务器是否已登记；请先检查表格，不要直接重跑审批")
        except requests.exceptions.ConnectionError:
            return self._fail("网络连接中断或无法连接企业微信；请检查网络，并先确认表格是否已收到记录")
        except Exception as exc:
            return self._fail(f"请求异常（{type(exc).__name__}），无法确认登记；请检查链接和设置")
