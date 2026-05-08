import json
import time
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

    def submit(self, data: dict) -> bool:
        """
        通过 HTTP POST 将数据发送到企业微信文档 webhook。
        数据格式遵循 schema + add_records 结构。
        """
        if not self.url:
            print("[错误] 未配置 webhook.url")
            return False

        if not self.schema:
            print("[错误] 未配置 webhook.schema")
            return False

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
        payload["schema"] = {k: v for k, v in payload["schema"].items() if k is not None}

        try:
            print(f"\n[Webhook] 正在发送数据到企业微信文档...")
            response = requests.post(
                self.url,
                headers=self.headers,
                data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
                timeout=self.timeout
            )
            if response.status_code < 400:
                print(f"  [完成] Webhook 发送成功，状态码: {response.status_code}")
                try:
                    resp_json = response.json()
                    if resp_json.get("errcode", 0) != 0:
                        print(f"  [警告] 企业微信返回业务错误: {resp_json.get('errmsg', '')}")
                        return False
                except Exception:
                    pass
                return True
            else:
                print(f"  [错误] Webhook 返回异常状态码: {response.status_code}")
                print(f"  响应内容: {response.text[:200]}")
                return False
        except Exception as e:
            print(f"  [错误] Webhook 发送失败: {e}")
            return False
