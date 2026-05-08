from playwright.sync_api import Page
from .browser import BrowserHelper
import time


class TencentFormHelper:
    def __init__(self, browser: BrowserHelper, config: dict):
        self.browser = browser
        self.form_cfg = config.get("tencent_form", {})
        self.form_url = self.form_cfg.get("form_url", "")
        self.field_mapping = self.form_cfg.get("field_mapping", {})
        self.submit_button_text = self.form_cfg.get("submit_button_text", "提交")

    def submit(self, data: dict, context=None):
        """
        在已有 browser context 中打开腾讯表格表单新标签页，填写数据并提交。
        """
        if not self.form_url:
            print("[错误] 未配置腾讯表单链接 tencent_form.form_url")
            return False

        if context is None:
            context = self.browser.context

        form_page = context.new_page()
        form_page.goto(self.form_url)
        form_page.wait_for_load_state("networkidle")
        form_page.wait_for_timeout(1500)

        print(f"\n[腾讯表单] 开始填写数据 → {self.form_url}")

        for field_name, value in data.items():
            form_field_name = self.field_mapping.get(field_name, field_name)
            if not form_field_name:
                continue
            self._fill_field(form_page, form_field_name, value)

        # 点击提交
        submitted = False
        try:
            # 先尝试通过按钮文字定位
            submit_locator = form_page.locator(f"button:has-text('{self.submit_button_text}')").first
            if submit_locator.is_visible():
                submit_locator.click()
                submitted = True
            else:
                # 再尝试通用选择器
                for sel in ["button[type='submit']", ".submit-btn", ".form-submit"]:
                    loc = form_page.locator(sel).first
                    if loc.is_visible():
                        loc.click()
                        submitted = True
                        break
        except Exception as e:
            print(f"[错误] 提交表单失败: {e}")

        if submitted:
            form_page.wait_for_timeout(2000)
            print("  [完成] 表单提交成功")
        else:
            print("  [警告] 未找到提交按钮，请检查 submit_button_text 配置")
            self.browser.screenshot(form_page, "tencent_form_submit_failed")

        form_page.close()
        return submitted

    def _fill_field(self, page: Page, form_field_name: str, value: str):
        """
        尝试多种策略定位并填写表单字段。
        """
        value_str = str(value) if value is not None else ""

        strategies = [
            lambda: self._fill_select(page, form_field_name, value_str),
            lambda: self._fill_by_label(page, form_field_name, value_str),
            lambda: self._fill_by_placeholder(page, form_field_name, value_str),
            lambda: self._fill_by_preceding_text(page, form_field_name, value_str),
            lambda: self._fill_by_attribute(page, form_field_name, value_str),
        ]

        for strategy in strategies:
            try:
                if strategy():
                    print(f"  [填写] {form_field_name}: {value_str}")
                    return
            except Exception:
                continue

        print(f"  [警告] 无法定位表单字段: {form_field_name}，请检查 field_mapping 配置或运行 discover.py 查看页面结构")

    def _fill_select(self, page: Page, text: str, value: str) -> bool:
        """尝试找到 label 为 text 的下拉选择框，并选中对应选项。"""
        try:
            # 先通过 label 定位父容器
            container = page.locator(f"label:has-text('{text}')").first
            if container.count() == 0:
                return False
            # 在容器内找 select
            select = container.locator("select").first
            if select.count() == 0:
                # 尝试通用兄弟/父级查找
                select = page.locator(f"xpath=//label[contains(text(), '{text}')]/following::select[1] | //label[contains(text(), '{text}')]/parent::*/select").first
            if select.count() == 0:
                return False
            select.select_option(label=value)
            return True
        except Exception:
            pass

        # 如果按 label 找不到，直接按 name/title 找 select
        try:
            for sel in [f"select[name='{text}']", f"select[title='{text}']", f"select[data-field='{text}']"]:
                loc = page.locator(sel).first
                if loc.count() > 0:
                    loc.select_option(label=value)
                    return True
        except Exception:
            pass
        return False

    def _fill_by_label(self, page: Page, text: str, value: str) -> bool:
        """label[text()='...'] / label:has-text('...') → for=input_id"""
        label = page.locator(f"label:has-text('{text}')").first
        if label.count() == 0:
            return False
        input_id = label.get_attribute("for")
        if input_id:
            inp = page.locator(f"#{input_id}")
            if inp.count() > 0:
                inp.fill(value)
                return True
        inp = label.locator("input, textarea").first
        if inp.count() > 0:
            inp.fill(value)
            return True
        return False

    def _fill_by_placeholder(self, page: Page, text: str, value: str) -> bool:
        loc = page.locator(f"input[placeholder='{text}'], textarea[placeholder='{text}']").first
        if loc.count() > 0:
            loc.fill(value)
            return True
        return False

    def _fill_by_preceding_text(self, page: Page, text: str, value: str) -> bool:
        """通过包含文字的 div/span/p，然后找它后面的 input"""
        container = page.locator(f"xpath=//*[contains(text(), '{text}')]")
        for i in range(min(container.count(), 5)):
            elem = container.nth(i)
            tag = elem.evaluate("el => el.tagName.toLowerCase()")
            if tag in ("input", "textarea", "select"):
                if tag == "select":
                    elem.select_option(label=value)
                else:
                    elem.fill(value)
                return True
            inp = elem.locator("xpath=./following::input[1] | ./following::textarea[1] | ./following::select[1] | ../input | ../textarea | ../select | ./parent::*/input | ./parent::*/textarea | ./parent::*/select").first
            if inp.count() > 0:
                try:
                    tag2 = inp.evaluate("el => el.tagName.toLowerCase()")
                    if tag2 == "select":
                        inp.select_option(label=value)
                    else:
                        inp.fill(value)
                    return True
                except Exception:
                    continue
        return False

    def _fill_by_attribute(self, page: Page, text: str, value: str) -> bool:
        selectors = [
            f"input[name='{text}']",
            f"textarea[name='{text}']",
            f"select[name='{text}']",
            f"input[title='{text}']",
            f"textarea[title='{text}']",
            f"select[title='{text}']",
            f"input[data-field='{text}']",
            f"textarea[data-field='{text}']",
            f"select[data-field='{text}']",
            f"input[data-name='{text}']",
            f"textarea[data-name='{text}']",
            f"select[data-name='{text}']",
        ]
        for sel in selectors:
            loc = page.locator(sel).first
            if loc.count() > 0:
                try:
                    tag = loc.evaluate("el => el.tagName.toLowerCase()")
                    if tag == "select":
                        loc.select_option(label=value)
                    else:
                        loc.fill(value)
                    return True
                except Exception:
                    continue
        return False
