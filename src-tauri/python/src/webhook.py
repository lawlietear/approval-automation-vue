import json
import re
import time
from urllib.parse import parse_qsl, urlsplit
import requests


class WebhookHelper:
    def __init__(self, config: dict):
        self.webhook_cfg = config.get("webhook", {})
        self.url = self.webhook_cfg.get("url", "")
        self.schema = self.webhook_cfg.get("schema", {})
        self.headers = self.webhook_cfg.get("headers", {
            "Content-Type": "application/json"
        })
        self.timeout = self.webhook_cfg.get("timeout", 10)
        self.last_error = ""

    def _fail(self, message):
        # Server messages can echo the secret webhook URL or its query credentials.
        message = str(message).replace(self.url, "[Webhook链接]") if self.url else str(message)
        for _, value in parse_qsl(urlsplit(self.url).query):
            if value:
                message = message.replace(value, "[已隐藏]")
        message = re.sub(r"https?://[^\s<>\"']+", "[链接已隐藏]", message)
        self.last_error = " ".join(message.split())[:500]
        return False

    def submit(self, data: dict) -> bool:
        """
        通过 HTTP POST 将数据发送到企业微信文档 webhook。
        数据格式遵循 schema + add_records 结构。
        """
        self.last_error = ""
        if not self.url:
            return self._fail("未配置 Webhook 链接，请在设置中填写")

        if not self.schema:
            return self._fail("未配置表格字段映射，请在设置中导入 schema")

        record = {}

        # 时间：当前时间戳（毫秒）
        time_field = self.schema.get("time")
        if time_field:
            record[time_field] = str(int(time.time() * 1000))

        # 部门
        dept_field = self.schema.get("dept")
        if dept_field and data.get("部门"):
            record[dept_field] = [{"text": data["部门"]}]

        # 项目名称（对应事项名称）
        title_field = self.schema.get("title")
        if title_field and data.get("事项名称"):
            record[title_field] = data["事项名称"]

        # 业务类型
        biz_type_field = self.schema.get("biz_type")
        if biz_type_field and data.get("业务类型"):
            record[biz_type_field] = [{"text": data["业务类型"]}]

        # 工作类型
        work_type_field = self.schema.get("work_type")
        if work_type_field and data.get("工作类型"):
            record[work_type_field] = [{"text": data["工作类型"]}]

        # 数量
        qty_field = self.schema.get("qty")
        if qty_field:
            try:
                record[qty_field] = int(data.get("数量", 1))
            except (ValueError, TypeError):
                record[qty_field] = 1

        # 备注
        remark_field = self.schema.get("remark")
        if remark_field and data.get("备注"):
            record[remark_field] = data["备注"]

        # 合同特有字段
        counterparty_field = self.schema.get("counterparty")
        if counterparty_field and data.get("交易对手"):
            record[counterparty_field] = data["交易对手"]

        contract_amount_field = self.schema.get("contract_amount")
        if contract_amount_field and data.get("合同金额"):
            record[contract_amount_field] = data["合同金额"]

        contract_name_field = self.schema.get("contract_name")
        if contract_name_field and data.get("合同名称"):
            record[contract_name_field] = data["合同名称"]

        contract_no_field = self.schema.get("contract_no")
        if contract_no_field and data.get("合同编号"):
            record[contract_no_field] = data["合同编号"]

        payload = {
            "schema": {
                time_field: "时间",
                dept_field: "部门",
                title_field: "项目名称",
                biz_type_field: "业务类型",
                work_type_field: "工作类型",
                qty_field: "数量",
                remark_field: "备注",
                counterparty_field: "交易对手",
                contract_amount_field: "合同金额",
                contract_name_field: "合同名称",
                contract_no_field: "合同编号",
            },
            "add_records": [{"values": record}]
        }

        # 清理 schema 中可能为 None 的键
        payload["schema"] = {k: v for k, v in payload["schema"].items() if k}

        try:
            response = requests.post(
                self.url,
                headers=self.headers,
                data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
                timeout=self.timeout
            )
            status = response.status_code
            try:
                result = response.json()
            except ValueError:
                return self._fail(f"HTTP {status}，返回内容不是 JSON，无法确认登记；请检查链接或网络拦截，不要直接重跑审批")
            if not isinstance(result, dict):
                return self._fail(f"HTTP {status}，接口响应格式异常，无法确认登记")
            code = result.get("errcode")
            if not 200 <= status < 300 or code not in (0, "0"):
                return self._fail(f"HTTP {status}，errcode={code if code is not None else '缺失'}，errmsg={result.get('errmsg', '未提供错误说明')}；请核对 Webhook 链接及目标表格字段映射")
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
