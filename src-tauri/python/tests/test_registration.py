import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock, patch
from datetime import datetime, timezone
from concurrent.futures import ThreadPoolExecutor


spec = importlib.util.spec_from_file_location(
    "registration", Path(__file__).parents[1] / "src" / "registration.py"
)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


class RegistrationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.directory = Path(self.temp.name)
        self.webhook = Mock(url="https://example.invalid", schema={"title": "id"})
        self.webhook.submit.return_value = True
        self.settings = {"wechat_enabled": True, "obsidian_enabled": True,
                         "obsidian_directory": str(self.directory)}
        self.log = Mock()
        self.registration = module.Registration(self.settings, self.webhook, self.log)

    def test_all_switch_combinations(self):
        for wechat in (False, True):
            for obsidian in (False, True):
                with self.subTest(wechat=wechat, obsidian=obsidian):
                    self.settings.update(wechat_enabled=wechat, obsidian_enabled=obsidian)
                    self.webhook.reset_mock()
                    before = len(list(self.directory.glob("*.md")))
                    result = self.registration.submit({"事项名称": "审核"})
                    self.assertEqual(set(result), ({"企业微信"} if wechat else set()) | ({"Obsidian"} if obsidian else set()))
                    self.assertEqual(self.webhook.submit.call_count, int(wechat))
                    self.assertEqual(len(list(self.directory.glob("*.md"))) - before, int(obsidian))

    def test_http_failure_does_not_lose_local_record(self):
        self.webhook.submit.side_effect = RuntimeError("proxy unavailable")
        result = self.registration.submit({"事项名称": "审批"})
        self.assertEqual(result, {"Obsidian": True, "企业微信": False})

    def test_local_failure_does_not_block_wechat(self):
        self.settings["obsidian_directory"] = str(self.directory / "missing")
        result = self.registration.submit({"事项名称": "审批"})
        self.assertEqual(result, {"Obsidian": False, "企业微信": True})

    def test_preflight_rejects_missing_directory_and_base_file(self):
        base = self.directory / "table.base"
        base.touch()
        for path in ("", str(base), str(self.directory / "missing")):
            self.settings["obsidian_directory"] = path
            with self.assertRaises(ValueError):
                self.registration.validate()
        self.settings["obsidian_directory"] = str(self.directory)
        self.registration.validate()

    def test_unicode_properties_and_no_overwrite(self):
        data = {"事项名称": '工资:/\\*?"<>|申请', "备注": "多行\n冒号: '引号'", "数量": "2"}
        first = self.registration.write_note(data)
        second = self.registration.write_note(data)
        self.assertNotEqual(first, second)
        text = first.read_text(encoding="utf-8")
        lines = text.split("---", 2)[1].strip().splitlines()
        properties = {}
        decoder = json.JSONDecoder()
        for line in lines:
            key, end = decoder.raw_decode(line)
            properties[key] = json.loads(line[end + 1:])
        self.assertEqual(properties["备注"], data["备注"])
        self.assertEqual(properties["项目名称"], data["事项名称"])
        self.assertEqual(properties["数量"], 2)
        self.assertEqual(first.parent, self.directory)

    def test_settings_default_and_reloaded_from_file(self):
        config = self.directory / "config.json"
        self.assertEqual(module.load_settings(config, {})["wechat_enabled"], True)
        self.assertEqual(module.load_settings(config, {})["obsidian_enabled"], False)
        saved = {**self.settings, "wechat_enabled": False}
        config.with_name("push-settings.json").write_text(json.dumps(saved), encoding="utf-8")
        self.assertEqual(module.load_settings(config, {}), saved)

    def test_daily_sequence_restart_gaps_and_rollover(self):
        with patch.object(module, "datetime") as clock:
            clock.now.return_value = datetime(2026, 9, 22, 12, tzinfo=timezone.utc)
            first = self.registration.write_note({"事项名称": "first", "合同金额": "125", "时间": "旧时间"})
            self.assertEqual(first.name, "2026-9-22.md")
            existing = self.directory / "2026-9-22 3.md"
            existing.write_text("keep", encoding="utf-8")
            restarted = module.Registration(self.settings, self.webhook, self.log)
            self.assertEqual(restarted.write_note({}).name, "2026-9-22 4.md")
            self.assertEqual(existing.read_text(encoding="utf-8"), "keep")
            content = first.read_text(encoding="utf-8")
            self.assertIn('"日期": "2026-09-22"', content)
            self.assertNotIn('"时间":', content)
            self.assertIn('"金额": "125"', content)
            self.assertNotIn('"合同金额":', content)
            clock.now.return_value = datetime(2026, 9, 23, 12, tzinfo=timezone.utc)
            self.assertEqual(restarted.write_note({}).name, "2026-9-23.md")

    def test_concurrent_writers_do_not_overwrite(self):
        with patch.object(module, "datetime") as clock:
            clock.now.return_value = datetime(2026, 9, 22, 12, tzinfo=timezone.utc)
            with ThreadPoolExecutor(max_workers=8) as pool:
                paths = list(pool.map(lambda i: self.registration.write_note({"事项名称": str(i)}), range(24)))
        self.assertEqual(len(set(paths)), 24)
        self.assertEqual({p.name for p in paths}, {"2026-9-22.md"} | {f"2026-9-22 {i}.md" for i in range(1, 24)})
        for i, path in enumerate(paths):
            self.assertIn(f'"项目名称": "{i}"', path.read_text(encoding="utf-8"))

    def test_collision_between_scan_and_create(self):
        original_open = Path.open
        collided = []
        def racing_open(path, mode="r", *args, **kwargs):
            if mode == "x" and not collided:
                collided.append(path)
                with original_open(path, "w", encoding="utf-8") as note:
                    note.write("other writer")
            return original_open(path, mode, *args, **kwargs)
        with patch.object(Path, "open", racing_open):
            result = self.registration.write_note({"事项名称": "mine"})
        self.assertNotEqual(result, collided[0])
        self.assertEqual(collided[0].read_text(encoding="utf-8"), "other writer")

    def test_saved_wechat_values_override_legacy_and_can_clear(self):
        path = self.directory / "config.json"
        config = {"webhook": {"url": "old", "schema": {"title": "old-id"}, "timeout": 10}}
        settings_path = path.with_name("push-settings.json")
        settings_path.write_text(json.dumps({"wechat_enabled": False}), encoding="utf-8")
        module.apply_wechat_settings(path, config)
        self.assertEqual(config["webhook"]["url"], "old")
        settings_path.write_text(json.dumps({"wechat_url": "new", "wechat_schema": {"title": "new-id"}, "wechat_timeout": 25}), encoding="utf-8")
        module.apply_wechat_settings(path, config)
        self.assertEqual(config["webhook"], {"url": "new", "schema": {"title": "new-id"}, "timeout": 25})
        settings_path.write_text(json.dumps({"wechat_url": "", "wechat_schema": {}}), encoding="utf-8")
        module.apply_wechat_settings(path, config)
        self.assertEqual(config["webhook"]["url"], "")
        self.assertEqual(config["webhook"]["schema"], {})

    def test_webhook_uses_saved_url_mapping_and_timeout(self):
        from unittest.mock import patch
        spec = importlib.util.spec_from_file_location("webhook", Path(__file__).parents[1] / "src" / "webhook.py")
        webhook_module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(webhook_module)
        path = self.directory / "config.json"
        path.with_name("push-settings.json").write_text(json.dumps({
            "wechat_url": "https://example.invalid/new", "wechat_schema": {"title": "new-id"}, "wechat_timeout": 25
        }), encoding="utf-8")
        config = {"webhook": {"url": "https://example.invalid/old", "schema": {"title": "old-id"}}}
        module.apply_wechat_settings(path, config)
        response = Mock(status_code=200)
        response.json.return_value = {"errcode": 0}
        with patch.object(webhook_module.requests, "post", return_value=response) as post:
            self.assertTrue(webhook_module.WebhookHelper(config).submit({"事项名称": "测试事项"}))
        self.assertEqual(post.call_args.args[0], "https://example.invalid/new")
        self.assertEqual(post.call_args.kwargs["timeout"], 25)
        payload = json.loads(post.call_args.kwargs["data"])
        self.assertEqual(payload["add_records"][0]["values"], {"new-id": "测试事项"})


if __name__ == "__main__":
    unittest.main()
