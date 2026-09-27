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
    for setting, key in (("wechat_url", "url"), ("wechat_schema", "schema"), ("wechat_timeout", "timeout"),
                         ("wechat_columns", "columns"), ("wechat_value_mappings", "value_mappings")):
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
        if self.settings["wechat_enabled"]:
            self.webhook.validate_schema()
        if self.settings["obsidian_enabled"]:
            directory = Path(self.settings["obsidian_directory"])
            if not directory.is_absolute() or not directory.is_dir():
                raise ValueError("请选择存在的 Obsidian 记录文件夹（绝对路径），不能选择 .base 文件")
            # Check before OA actions; a disconnected drive must not silently lose records.
            with tempfile.TemporaryFile(dir=directory):
                pass

    def write_note(self, data, recorded_at=None):
        now = datetime.fromisoformat(recorded_at) if recorded_at else datetime.now().astimezone()
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

    def send_channel(self, data, channel, recorded_at=None):
        """One channel only, with an explicit uncertainty state for recovery."""
        key = {'Obsidian': 'obsidian_enabled', '企业微信': 'wechat_enabled'}.get(channel)
        if not key or not self.settings.get(key):
            return dict(state='failed', detail='通道未启用，请先在设置中启用原通道')
        if channel == 'Obsidian':
            directory = Path(self.settings.get('obsidian_directory', ''))
            if not directory.is_absolute() or not directory.is_dir():
                return dict(state='failed', detail='Obsidian目录不可用，请连接磁盘并核对设置')
            try:
                path = self.write_note(data, recorded_at)
                return dict(state='success', detail=str(path))
            except Exception:
                # A partial file may already exist, especially on a disconnected share.
                return dict(state='unknown', detail='本地写入异常，可能已创建文件；请先核实文件内容，勿直接重写')
        try:
            ok = self.webhook.submit(data, recorded_at=recorded_at)
            return dict(state='success' if ok else self.webhook.last_state,
                        detail='' if ok else self.webhook.last_error)
        except Exception:
            return dict(state='unknown', detail='登记请求异常，无法确认结果；请先核实目标表格')

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
