"""Independent registration channels and portable, machine-local settings."""

import json
import re
import tempfile
from datetime import datetime
from pathlib import Path


def load_settings(config_path, config):
    path = Path(config_path).with_name("push-settings.json")
    settings = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
    return {
        "wechat_enabled": settings.get("wechat_enabled", config.get("webhook", {}).get("enabled", True)),
        "obsidian_enabled": settings.get("obsidian_enabled", False),
        "obsidian_directory": settings.get("obsidian_directory", ""),
    }


def apply_wechat_settings(config_path, config):
    """Missing keys retain legacy config; explicit empty values clear old mappings."""
    path = Path(config_path).with_name("push-settings.json")
    if not path.exists():
        return
    settings = json.loads(path.read_text(encoding="utf-8"))
    webhook = config.setdefault("webhook", {})
    for setting, key in (("wechat_url", "url"), ("wechat_schema", "schema"), ("wechat_timeout", "timeout")):
        if settings.get(setting) is not None:
            webhook[key] = settings[setting]


class Registration:
    def __init__(self, settings, webhook, log):
        self.settings = settings
        self.webhook = webhook
        self.log = log

    def validate(self):
        if self.settings["wechat_enabled"] and (not self.webhook.url or not self.webhook.schema):
            raise ValueError("企业微信推送已启用，但 Webhook 地址或字段映射未配置")
        if self.settings["obsidian_enabled"]:
            directory = Path(self.settings["obsidian_directory"])
            if not directory.is_absolute() or not directory.is_dir():
                raise ValueError("请选择存在的 Obsidian 记录文件夹（绝对路径），不能选择 .base 文件")
            # Check before OA actions; a disconnected drive must not silently lose records.
            with tempfile.TemporaryFile(dir=directory):
                pass

    def write_note(self, data):
        now = datetime.now().astimezone()
        title = str(data.get("事项名称") or "未命名审批")
        directory = Path(self.settings["obsidian_directory"])
        date_name = f"{now.year}-{now.month}-{now.day}"
        pattern = re.compile(rf"{re.escape(date_name)}(?: ([0-9]+))?\.md", re.IGNORECASE)
        last = -1
        for entry in directory.iterdir():
            match = pattern.fullmatch(entry.name)
            if match:
                last = max(last, int(match.group(1) or 0))
        properties = {"登记类型": "流程审核", **data}
        properties.pop("时间", None)
        properties["日期"] = now.date().isoformat()
        properties["项目名称"] = title
        properties["金额"] = properties.pop("合同金额", properties.get("金额", ""))
        try:
            properties["数量"] = int(data.get("数量", 1))
        except (TypeError, ValueError):
            pass
        # JSON-quoted scalar strings are valid YAML and preserve colons/newlines safely.
        frontmatter = "\n".join(
            f"{json.dumps(str(key), ensure_ascii=False)}: {json.dumps(value, ensure_ascii=False)}"
            for key, value in properties.items()
        )
        content = f"---\n{frontmatter}\n---\n\n# {title.replace(chr(10), ' ')}\n"
        # Exclusive creation prevents two writers from claiming the same number.
        while True:
            last += 1
            suffix = f" {last}" if last else ""
            path = directory / f"{date_name}{suffix}.md"
            try:
                note = path.open("x", encoding="utf-8", newline="\n")
                break
            except FileExistsError:
                continue
        with note:
            note.write(content)
        return path

    def submit(self, data):
        outcomes = {}
        # Local first so an HTTP failure never prevents the local record.
        for channel, enabled, submit in (
            ("Obsidian", self.settings["obsidian_enabled"], lambda: self.write_note(data)),
            ("企业微信", self.settings["wechat_enabled"], lambda: self.webhook.submit(data)),
        ):
            if not enabled:
                continue
            try:
                result = submit()
                outcomes[channel] = bool(result)
                detail = f": {result}" if channel == "Obsidian" and result else ""
                if channel == "企业微信" and not result:
                    reason = getattr(self.webhook, "last_error", "")
                    if isinstance(reason, str) and reason:
                        detail = f": {reason}"
                self.log(f"{channel}登记{'成功' if result else '失败'}{detail}", "info" if result else "error")
            except Exception as exc:
                outcomes[channel] = False
                self.log(f"{channel}登记失败: {exc}", "error")
        return outcomes
