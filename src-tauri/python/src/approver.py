from playwright.sync_api import Page
from .browser import BrowserHelper
import time
import re


class ApprovalHelper:
    def __init__(self, browser: BrowserHelper, config: dict, test_mode: bool = False, log_callback=None, oa_type: str = "auto"):
        self.browser = browser
        self.config = config
        self.approval_cfg = config.get("approval", {})
        self.test_mode = test_mode
        self.log_callback = log_callback
        self.oa_type = oa_type  # "auto" | "old" | "new"

    def _log(self, msg, level="info"):
        if self.log_callback:
            self.log_callback(msg, level)
        else:
            print(msg)

    def process_current_page(self, page: Page):
        """
        判断当前页面是列表页还是详情页，并执行相应处理。
        测试模式下支持无按钮页面（已审批历史页）的字段提取测试。
        支持OA系统页面（input#subject + 特有按钮）。
        """
        # 若明确指定了 OA 类型，直接走对应分支，不再做混合检测
        if self.oa_type == "new":
            self._log("[识别] 强制OA系统处理模式")
            return self._process_new_oa_page(page)

        if self.oa_type == "old":
            self._log("[识别] 强制核心业务系统处理模式")
            return self._process_old_oa_page(page)

        # auto 模式：自动检测
        if self._is_new_oa_page(page):
            self._log("[识别] 检测到OA系统页面")
            return self._process_new_oa_page(page)

        return self._process_old_oa_page(page)

    def _process_old_oa_page(self, page: Page) -> list:
        """核心业务系统处理逻辑。"""
        pending_selector = self.approval_cfg.get("pending_items_selector", "")
        self._log(f"[诊断] 检测列表页: pending_selector='{pending_selector}'")
        try:
            cnt = page.locator(pending_selector).count() if pending_selector else 0
            self._log(f"[诊断] 列表选择器 count={cnt}")
            if pending_selector and cnt > 0:
                page.wait_for_selector(pending_selector, state="visible", timeout=1000)
                self._log("[识别] 当前为审批列表页，开始批量处理...")
                return self._process_list(page)
        except Exception as e:
            self._log(f"[诊断] 列表页检测异常: {e}", "warning")

        approve_selector = self.approval_cfg.get("approve_button_selector", "")
        self._log(f"[诊断] 检测详情页: approve_selector='{approve_selector}'")
        try:
            cnt = page.locator(approve_selector).count() if approve_selector else 0
            self._log(f"[诊断] 通过按钮 count={cnt}")
            if approve_selector and cnt > 0:
                page.wait_for_selector(approve_selector, state="visible", timeout=1000)
                self._log("[识别] 当前为审批详情页，开始处理...")
                return self._process_detail(page)
        except Exception as e:
            self._log(f"[诊断] 详情页检测异常: {e}", "warning")

        # 无按钮页面（已审批历史页）也尝试提取字段
        self._log("[识别] 未找到审批按钮，尝试作为已审批历史页提取字段...")
        return self._process_detail(page)

    def _process_list(self, page: Page) -> list:
        results = []
        pending_selector = self.approval_cfg.get("pending_items_selector", "")
        detail_link_selector = self.approval_cfg.get("detail_link_selector", "")

        items = page.locator(pending_selector).all()
        self._log(f"[列表] 发现 {len(items)} 个待审批项")

        for idx in range(len(items)):
            self._log(f"\n--- 处理第 {idx + 1}/{len(items)} 个 ---")
            items = page.locator(pending_selector).all()
            if idx >= len(items):
                break

            item = items[idx]
            if detail_link_selector:
                link = item.locator(detail_link_selector).first
                if link.is_visible():
                    link.click()
                    page.wait_for_load_state("networkidle")
                else:
                    item.click()
                    page.wait_for_load_state("networkidle")
            else:
                item.click()
                page.wait_for_load_state("networkidle")

            records = self._process_detail(page)
            results.extend(records)

            # Frame 没有 go_back，只有 Page 有
            if hasattr(page, "go_back"):
                page.go_back()
                page.wait_for_load_state("networkidle")
                page.wait_for_timeout(800)
            else:
                # 如果在 iframe 中，暂时不支持自动返回列表，结束批量处理
                self._log("[提示] iframe 内无法自动返回列表页，列表批量处理结束。")
                break

        return results

    def _process_detail(self, page: Page) -> list:
        """在审批详情页提取字段并点击同意。返回记录列表（合同类可能有多条）。"""
        try:
            url = page.url
        except Exception:
            url = "unknown"
        self._log(f"[诊断] _process_detail 开始，page url={url}")
        fields_cfg = self.approval_cfg.get("fields", {})
        transforms = self.approval_cfg.get("field_transforms", {})
        data = {}

        for name, selector in fields_cfg.items():
            value = self._extract_field(page, name, selector, transforms.get(name))
            data[name] = value
            self._log(f"  [提取] {name}: {value}")

        # 部门名称规范化映射
        dept_mapping = self.approval_cfg.get("dept_mapping", {})
        if "部门" in data and data["部门"]:
            raw_dept = data["部门"]
            for canonical_name, aliases in dept_mapping.items():
                for alias in aliases:
                    if alias in raw_dept:
                        if canonical_name != raw_dept:
                            self._log(f"  [映射] 部门: '{raw_dept}' -> '{canonical_name}'")
                            data["部门"] = canonical_name
                        break
                else:
                    continue
                break

        # 工作类型规范化映射
        workflow_type_mapping = self.approval_cfg.get("workflow_type_mapping", {})
        if workflow_type_mapping:
            source_text = data.get("工作类型") or data.get("事项名称") or ""
            if source_text:
                mapped = False
                for canonical_name, aliases in workflow_type_mapping.items():
                    for alias in aliases:
                        if alias in source_text:
                            if data.get("工作类型") != canonical_name:
                                self._log(f"  [映射] 工作类型: '{source_text}' -> '{canonical_name}'")
                                data["工作类型"] = canonical_name
                            mapped = True
                            break
                    if mapped:
                        break

        # 立项审批检测：若页面包含"项目编号"标签，强制标记为立项审批
        try:
            has_project_no = page.evaluate(
                """() => {
                    const spans = document.querySelectorAll('span.jresui_label-left-content');
                    for (const s of spans) {
                        if (s.textContent.trim() === '项目编号：') return true;
                    }
                    return false;
                }"""
            )
            if has_project_no and data.get("工作类型") != "立项审批":
                self._log("  [检测] 立项审批页面，强制设置工作类型为立项审批")
                data["工作类型"] = "立项审批"
        except Exception as e:
            self._log(f"  [诊断] 立项检测异常: {e}", "warning")

        # 合同类审批：补充提取合同特有字段
        is_contract_page = data.get("工作类型") == "合同审批"
        if not is_contract_page:
            source = data.get("事项名称") or data.get("工作类型") or ""
            is_contract_page = "合同类审批" in source or "合同" in source

        # 若仍不确定，尝试直接查找合同标签
        contract_frame = self.browser.find_contract_frame(page)
        if contract_frame and not is_contract_page:
            has_contract_labels = contract_frame.evaluate(
                """() => {
                    const spans = document.querySelectorAll('span.jresui_label-left-content');
                    for (const s of spans) {
                        const t = s.textContent.trim();
                        if (t === '合同金额：' || t === '合同名称：' || t === '合同ID：') return true;
                    }
                    return false;
                }"""
            )
            if has_contract_labels:
                is_contract_page = True

        doc_names = []
        if is_contract_page and contract_frame:
            self._log("  [检测] 合同类审批页面，尝试提取合同字段...")
            contract_data = self.browser.extract_contract_fields_from_frame(contract_frame)
            doc_names = contract_data.pop("合同名称列表", [])
            for k, v in contract_data.items():
                if v and (not data.get(k) or data.get(k) == ""):
                    data[k] = v
                    self._log(f"  [提取] {k}: {v}")
            if doc_names:
                self._log(f"  [提取] 合同文本共 {len(doc_names)} 个: {doc_names}")
        elif is_contract_page:
            self._log("  [提示] 未找到合同表单 iframe，跳过合同字段提取")

        # 测试模式：提取字段后继续点击以验证后续流程，但最后一步会点取消
        if self.test_mode:
            self._log("  [测试模式] 已启用：将执行点击以验证流程，最后一步会点取消")

        # 点击同意
        approve_selector = self.approval_cfg.get("approve_button_selector", "")
        self._log(f"[诊断] 准备点击同意，selector='{approve_selector}'，page类型={type(page).__name__}")
        if not approve_selector:
            self._log("[错误] 未配置 approve_button_selector", "error")
            return [data]

        try:
            cnt = page.locator(approve_selector).count()
            self._log(f"[诊断] 同意按钮 count={cnt}")
            self.browser.safe_click(page, approve_selector, timeout=5000)
            self._log("  [操作] 点击同意成功")
        except Exception as e:
            self._log(f"[错误] 点击同意失败: {e}", "error")
            return [data]

        page.wait_for_timeout(1000)

        # 处理确认/评论框
        comment_selector = self.approval_cfg.get("comment_input_selector", "")
        confirm_selector = self.approval_cfg.get("confirm_button_selector", "")
        comment_text = self.approval_cfg.get("comment_text", "同意")

        if comment_selector:
            try:
                page.wait_for_selector(comment_selector, state="visible", timeout=3000)
                self.browser.safe_fill(page, comment_selector, comment_text, timeout=3000)
                self._log(f"  [操作] 填写意见: {comment_text}")
            except Exception as e:
                self._log(f"  [诊断] 填写意见跳过: {e}", "warning")

        if confirm_selector:
            try:
                self.browser.safe_click(page, confirm_selector, timeout=5000)
                self._log("  [操作] 点击确认成功")
            except Exception as e:
                self._log(f"[错误] 点击确认失败: {e}", "error")

        page.wait_for_timeout(1500)

        # 处理可能的后续页面（如选择下一步处理人等）
        self._handle_subsequent_pages(page)

        # 组装返回记录：若有多份合同文本，每条记录共享其他字段，合同名称各自独立
        records = []
        if doc_names:
            for name in doc_names:
                record = dict(data)
                record["合同名称"] = name
                records.append(record)
            self._log(f"  [完成] 该审批项处理完毕，生成 {len(records)} 条记录")
        else:
            records = [data]
            self._log("  [完成] 该审批项处理完毕")

        return records

    def _handle_subsequent_pages(self, page: Page):
        """
        点击确认后，后续两步流程：
        1. 点击"风险合规部"
        2. 再次点击"确定"

        说明：
        - 第一步"确定"已经在 _process_detail 中点击过了
        - 弹出层可能在主页面或 iframe 中，因此同时在两个上下文中查找
        """
        dept_text = self.approval_cfg.get("dept_select_text", "风险合规部")
        final_confirm_selector = self.approval_cfg.get("final_confirm_button_selector", "")
        main_page = getattr(self, "main_page", None)
        contexts = []
        if main_page and main_page != page:
            contexts.append((main_page, "主页面"))
        contexts.append((page, "iframe"))
        self._log(f"[诊断] _handle_subsequent_pages 开始，contexts={[n for _, n in contexts]}")

        # 1. 点击部门选择（如"风险合规部"）——仅当配置了部门文本时才执行
        clicked = False
        if dept_text:
            # 等待弹窗渲染
            for ctx, name in contexts:
                ctx.wait_for_timeout(1200)

            selectors = [
                f"div[title='{dept_text}']",
                f"span[title='{dept_text}']",
                f"a[title='{dept_text}']",
                f"span:has-text('{dept_text}')",
                f"div:has-text('{dept_text}')",
                f"a:has-text('{dept_text}')",
                f"button:has-text('{dept_text}')",
                f"label:has-text('{dept_text}')",
                f"input[value='{dept_text}']",
                f"td:has-text('{dept_text}')",
                f"li:has-text('{dept_text}')",
            ]
            for sel in selectors:
                for ctx, name in contexts:
                    try:
                        locs = ctx.locator(sel).all()
                        for idx, loc in enumerate(locs):
                            try:
                                if loc.is_visible():
                                    loc.click()
                                    self._log(f"  [操作] 点击'{dept_text}'（{name}，选择器: {sel}，第 {idx + 1} 个匹配）")
                                    clicked = True
                                    break
                            except Exception:
                                continue
                        if clicked:
                            break
                    except Exception:
                        continue
                if clicked:
                    break

            if not clicked:
                self._log(f"  [提示] 未找到'{dept_text}'选项，跳过部门选择步骤")

            # 等待选择生效（弹窗动画可能较慢，给足时间）
            for ctx, name in contexts:
                ctx.wait_for_timeout(1500)
        else:
            self._log("  [提示] 未配置 dept_select_text，跳过部门选择步骤")

        # 2. 最终操作：测试模式点取消，正常模式点最终确定
        if self.test_mode:
            # 测试模式：尝试点击取消按钮来回退
            cancel_selectors = [
                "button#buttonCancel",
                "button[name=\"取消\"]",
                "a:has-text(\"取消\")",
                "button:has-text(\"取消\")",
                "span:has-text(\"取消\")",
                "div:has-text(\"取消\")",
            ]
            clicked_cancel = False
            for sel in cancel_selectors:
                for ctx, name in contexts:
                    try:
                        locs = ctx.locator(sel).all()
                        for idx, loc in enumerate(locs):
                            try:
                                if loc.is_visible():
                                    loc.click()
                                    self._log(f"  [测试模式] 点击取消（{name}，选择器: {sel}，第 {idx + 1} 个匹配）")
                                    clicked_cancel = True
                                    break
                            except Exception:
                                continue
                        if clicked_cancel:
                            break
                    except Exception:
                        continue
                if clicked_cancel:
                    break
            if not clicked_cancel:
                self._log("  [测试模式] 未找到取消按钮，无法自动回退，请手动关闭弹窗")
        elif final_confirm_selector:
            clicked_final = False
            for ctx, name in contexts:
                # 2.1 先尝试标准可见点击
                try:
                    self.browser.safe_click(ctx, final_confirm_selector, timeout=5000)
                    self._log(f"  [操作] 点击最终确定（{name}，选择器: {final_confirm_selector}）")
                    clicked_final = True
                    break
                except Exception:
                    pass

                # 2.2 如果标准点击失败，尝试 force 点击（元素存在但 hidden 时）
                try:
                    loc = ctx.locator(final_confirm_selector)
                    if loc.count() > 0:
                        loc.first.click(force=True, timeout=3000)
                        self._log(f"  [操作] 点击最终确定（{name}，force 模式）")
                        clicked_final = True
                        break
                except Exception:
                    pass

                # 2.3 最后尝试 JS 直接点击
                try:
                    loc = ctx.locator(final_confirm_selector)
                    if loc.count() > 0:
                        loc.first.evaluate("el => el.click()")
                        self._log(f"  [操作] 点击最终确定（{name}，JS 点击模式）")
                        clicked_final = True
                        break
                except Exception as e:
                    self._log(f"  [提示] 在{name}中点击最终确定失败: {e}")

            if not clicked_final:
                self._log("  [提示] 未找到最终确定按钮，流程可能已直接结束（无需部门选择）")
        else:
            self._log("  [提示] 未配置 final_confirm_button_selector，跳过最终确定步骤")

    def _extract_field(self, page: Page, name: str, selector: str, transform: dict) -> str:
        """
        提取单个字段。
        - selector 为空或纯数字：直接作为固定值
        - 否则按 CSS/XPath 选择器提取文本
        - 如有 transform 配置，应用正则转换
        """
        # 固定值支持
        if selector.strip() == "" or re.fullmatch(r"\d+", selector.strip()):
            text = selector.strip()
        else:
            selectors = [s.strip() for s in selector.split(",")]
            # 第一轮：在当前 page 尝试第一个精确选择器
            if selectors:
                text = self.browser.extract_text(page, selectors[0], timeout=2000)

            # 第二轮：精确选择器没找到，回退到主页面（避免误匹配 iframe 中的兜底大容器）
            if not text and hasattr(self, "main_page") and self.main_page and self.main_page != page:
                text = self.browser.extract_text(self.main_page, selectors[0], timeout=2000)
                if text:
                    self._log(f"  [提示] {name} 通过主页面提取")

            # 第三轮：主页面也没找到，在当前 page 尝试后续兜底选择器
            if not text:
                for sel in selectors[1:]:
                    text = self.browser.extract_text(page, sel, timeout=2000)
                    if text:
                        break

        # 如果文本仍为空，尝试一些备用选择器（针对工作类型、备注等难定位字段）
        if not text and name == "工作类型":
            fallback_selectors = [
                "span:has-text('审批流程')",
                "span:has-text('流程')",
                "div.process-name",
                "div.workflow-name",
            ]
            for fs in fallback_selectors:
                text = self.browser.extract_text(page, fs, timeout=1000)
                if text:
                    break

        if not text and name == "备注":
            fallback_selectors = [
                ("通用用印", "div[name='fieldsqsxgsID'] pre"),
                ("诉讼事务", "div[name='fielditemSpecificDescID'] pre"),
                ("债权资料交接", "div[name='fieldapply_remarkID']"),
                ("业务通用(factor-panel)", "pre.factor-panel-textedit-pre"),
                ("通用兜底(fieldRemark)", "div[name='fieldRemark'] pre"),
                ("通用兜底(fieldSummary)", "div[name='fieldSummary'] pre"),
                ("通用兜底(textarea-view)", "div.textarea-view pre"),
            ]
            for label, fs in fallback_selectors:
                text = self.browser.extract_text(page, fs, timeout=1000)
                if text:
                    self._log(f"  [提示] 备注通过备用选择器提取: [{label}] {fs}")
                    break

        # 立项/合同类页面兜底：通过标签对提取
        from_label_pairs = False
        if not text:
            text = self._extract_from_label_pairs(page, name)
            if text:
                from_label_pairs = True

        # 应用转换规则（标签对提取的结果已规范化，跳过 transform）
        if transform and text and not from_label_pairs:
            regex = transform.get("regex", "")
            group = transform.get("group", 0)
            attr = transform.get("attribute", "text")

            # 如需提取属性值
            if attr != "text" and selector.strip():
                try:
                    page.wait_for_selector(selector, state="visible", timeout=2000)
                    text = page.locator(selector).first.get_attribute(attr) or text
                except Exception:
                    pass

            if regex:
                match = re.search(regex, text)
                if match:
                    try:
                        text = match.group(group)
                    except IndexError:
                        text = match.group(0)
                else:
                    text = ""

        return text

    def _extract_from_label_pairs(self, page: Page, name: str) -> str:
        """
        立项/合同类页面兜底：通过 span.jresui_label-left-content / right-content
        成对标签按字段名查找对应值。
        """
        label_map = {
            "部门": ["承做部门-牵头：", "承做部门：", "部门：", "发起部门："],
            "事项名称": ["项目名称：", "事项名称：", "标题："],
            "工作类型": ["业务类型：", "工作类型：", "流程类型："],
            "备注": ["资产包情况简述：", "情况说明：", "其他情况说明：", "备注：", "审批事项说明："],
        }
        candidates = label_map.get(name, [])
        if not candidates:
            return ""

        try:
            left_count = page.evaluate(
                "() => document.querySelectorAll('span.jresui_label-left-content').length"
            )
            right_count = page.evaluate(
                "() => document.querySelectorAll('span.jresui_label-right-content').length"
            )
            limit = min(left_count, right_count)
            for i in range(limit):
                label = page.evaluate(
                    "(idx) => { const s = document.querySelectorAll('span.jresui_label-left-content')[idx]; return s ? s.textContent.trim() : ''; }",
                    i,
                )
                if label in candidates:
                    val = page.evaluate(
                        "(idx) => { const s = document.querySelectorAll('span.jresui_label-right-content')[idx]; return s ? (s.textContent || '').trim() : ''; }",
                        i,
                    )
                    if val:
                        self._log(f"  [提示] {name} 通过标签对提取: {label} {val[:40]}")
                        return val
        except Exception:
            pass
        return ""

    # ── OA系统支持 ──

    def _is_new_oa_page(self, page: Page) -> bool:
        """检测是否为OA系统页面（日照资产专属或通用）。特征：input#subject + 特有按钮。"""
        try:
            has_subject = page.locator("input#subject").count() > 0
            has_rizhao_btn = page.locator("input#operation_btn_14_a").count() > 0
            has_sd_btn = page.locator("input#_dealSubmit").count() > 0
            return has_subject and (has_rizhao_btn or has_sd_btn)
        except Exception:
            return False

    def _process_new_oa_page(self, page: Page) -> list:
        """
        处理OA系统页面（日照资产专属或通用）。
        字段：事项名称(input#subject.value)、部门、工作类型、备注(textarea.value)。
        审批：日照资产点击 input#operation_btn_14_a（同意），OA系统通用页面点击 input#_dealSubmit（提交）。
        """
        data = {}

        # 判断页面类型：日照资产专属页面有 input#operation_btn_14_a
        try:
            is_rizhao_page = page.locator("input#operation_btn_14_a").count() > 0
        except Exception:
            is_rizhao_page = False
        if is_rizhao_page:
            self._log("  [识别] 页面类型: 日照资产专属页面")
        else:
            self._log("  [识别] 页面类型: OA系统通用页面")

        # 1. 事项名称
        try:
            data["事项名称"] = page.locator("input#subject").first.get_attribute("value") or ""
        except Exception as e:
            self._log(f"  [诊断] 提取事项名称异常: {e}", "warning")
            data["事项名称"] = ""
        self._log(f"  [提取] 事项名称: {data['事项名称']}")

        # 2. 部门
        if is_rizhao_page:
            # 日照资产专属页面：部门固定为日照合资公司
            data["部门"] = "日照合资公司"
            self._log("  [固定] 日照资产页面部门: 日照合资公司")
        else:
            # OA系统通用页面：从 a#panleStart 文本中提取括号内容
            try:
                start_text = page.locator("a#panleStart").first.inner_text() or ""
                m = re.search(r"\((.*?)\)", start_text)
                if m:
                    data["部门"] = m.group(1)
                else:
                    data["部门"] = start_text
            except Exception as e:
                self._log(f"  [诊断] 提取部门异常: {e}", "warning")
                data["部门"] = ""
            self._log(f"  [提取] 部门: {data['部门']}")

        # 3. 工作类型
        if is_rizhao_page:
            # 日照资产专属页面：固定为用印审批
            data["工作类型"] = "用印审批"
            self._log("  [固定] 日照资产页面工作类型: 用印审批")
        else:
            # OA系统通用页面：尝试多种方式提取
            # 3a. 优先从页面标题提取，如 "【山东金融资产】-用印审批单(...)"
            page_title = ""
            try:
                page_title = page.title() or ""
            except Exception:
                pass
            if "用印审批单" in page_title:
                data["工作类型"] = "用印审批"
                self._log(f"  [提取] 页面标题含'用印审批单'，工作类型: 用印审批")
            elif "合同审批" in page_title:
                data["工作类型"] = "合同审批"
                self._log(f"  [提取] 页面标题含'合同审批'，工作类型: 合同审批")
            else:
                # 3b. 回退到 pre 标签提取
                try:
                    pre_locators = page.locator("pre").all()
                    pre_text = ""
                    for pl in pre_locators:
                        txt = pl.inner_text() or ""
                        if "审批" in txt or "合同" in txt or "用印" in txt:
                            pre_text = txt
                            break
                    if not pre_text and pre_locators:
                        pre_text = pre_locators[0].inner_text() or ""
                    lines = [l.strip() for l in pre_text.splitlines() if l.strip()]
                    if len(lines) >= 2:
                        data["工作类型"] = lines[1]
                    elif lines:
                        data["工作类型"] = lines[0]
                    else:
                        data["工作类型"] = ""
                except Exception as e:
                    self._log(f"  [诊断] 提取工作类型异常: {e}", "warning")
                    data["工作类型"] = ""
                self._log(f"  [提取] 工作类型: {data['工作类型']}")

                # 映射到规范名称
                raw_work_type = data.get("工作类型", "")
                if "合同" in raw_work_type:
                    data["工作类型"] = "合同审批"
                    self._log(f"  [映射] 工作类型: '{raw_work_type}' -> '合同审批'")
                elif "用印" in raw_work_type or "通用" in raw_work_type:
                    data["工作类型"] = "用印审批"
                    self._log(f"  [映射] 工作类型: '{raw_work_type}' -> '用印审批'")

                # fallback：通过事项名称关键词推断
                if not data.get("工作类型"):
                    subject = data.get("事项名称", "")
                    if "合同" in subject:
                        data["工作类型"] = "合同审批"
                        self._log(f"  [fallback] 事项名称含'合同'，推断工作类型: 合同审批")
                    elif any(k in subject for k in ["用印", "公章", "印章", "盖章"]):
                        data["工作类型"] = "用印审批"
                        self._log(f"  [fallback] 事项名称含用印关键词，推断工作类型: 用印审批")

        # 4. 备注：textarea 的 value（该 textarea opacity:0，需用 JS 获取）
        # 若页面有多个 textarea，选文本最长的那个，提高健壮性
        try:
            remark = page.evaluate(
                """() => {
                    const tas = document.querySelectorAll('textarea');
                    let best = '';
                    for (const ta of tas) {
                        const v = ta.value || '';
                        if (v.length > best.length) best = v;
                    }
                    return best;
                }"""
            )
            data["备注"] = remark or ""
        except Exception as e:
            self._log(f"  [诊断] 提取备注异常: {e}", "warning")
            data["备注"] = ""
        self._log(f"  [提取] 备注: {data['备注'][:60]}...")

        # 业务类型和数量由用户选择覆盖，先留空
        data["业务类型"] = ""
        data["数量"] = ""

        # 测试模式：只提取字段，不点击按钮
        if self.test_mode:
            self._log("  [测试模式] 已启用：只提取字段，不点击同意")
            return [data]

        # 5. 点击按钮（日照资产：同意；OA系统通用页面：提交）
        try:
            if is_rizhao_page:
                self.browser.safe_click(page, "input#operation_btn_14_a", timeout=5000)
                self._log("  [操作] 点击同意成功")
            else:
                self.browser.safe_click(page, "input#_dealSubmit", timeout=5000)
                self._log("  [操作] 点击提交成功")
        except Exception as e:
            btn_name = "同意" if is_rizhao_page else "提交"
            self._log(f"[错误] 点击{btn_name}失败: {e}", "error")
            return [data]

        self._log("  [完成] OA系统审批项处理完毕")
        return [data]
