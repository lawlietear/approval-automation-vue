from playwright.sync_api import sync_playwright, BrowserContext, Page
import time


class BrowserHelper:
    """通过 CDP 连接用户已打开的 Chrome 浏览器。"""

    def __init__(self, cdp_endpoint: str = "http://localhost:9222", log_callback=None):
        self.cdp_endpoint = cdp_endpoint
        self.log_callback = log_callback
        self.playwright = None
        self.browser = None
        self.context = None

    def _log(self, msg):
        if self.log_callback:
            self.log_callback(msg)

    def connect(self) -> BrowserContext:
        # 检测 asyncio loop：某些环境（如同时运行 VS Code/Jupyter）会创建 running loop，
        # 导致 Playwright sync API 拒绝启动。给出明确提示而非报内部错误。
        import asyncio
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            pass  # 没有 running loop，正常
        else:
            # 有 running loop，必须提前报错，否则 Playwright 会卡住或报内部 greenlet 错误
            raise RuntimeError(
                "检测到当前线程存在 asyncio 事件循环，Playwright 无法启动。\n\n"
                "常见原因：同时运行了 VS Code、Jupyter Notebook 或其他 Python 程序。\n\n"
                "解决方法：关闭这些程序后重新运行本工具。"
            )

        self._log("[browser] 开始初始化 Playwright driver...")
        self.playwright = sync_playwright().start()
        self._log("[browser] Playwright driver 初始化完成，开始 connect_over_cdp...")
        try:
            self.browser = self.playwright.chromium.connect_over_cdp(
                self.cdp_endpoint
            )
        except Exception as e:
            self._log(f"[browser] connect_over_cdp 失败: {type(e).__name__}: {e}")
            raise
        self._log("[browser] connect_over_cdp 成功")
        self.context = self.browser.contexts[0] if self.browser.contexts else self.browser.new_context()
        return self.context

    def list_pages(self) -> list:
        """返回所有有效页面的摘要信息列表（跨所有窗口/context）。"""
        results = []
        global_idx = 0
        for ctx in self.browser.contexts:
            for p in ctx.pages:
                url = p.url or ""
                # 跳过扩展页面和空白页
                if url.startswith("chrome-extension://") or url.startswith("devtools://") or url in ("", "about:blank"):
                    continue
                try:
                    title = p.title() or "(无标题)"
                except Exception:
                    title = "(无标题)"
                results.append({
                    "index": global_idx,
                    "page": p,
                    "title": title,
                    "url": url,
                })
                global_idx += 1
        return results

    def get_approval_page(self, url_hint: str = None, title_hint: str = None) -> Page:
        """
        获取当前最可能是审批页面的标签页。
        优先顺序：
        1. url_hint 匹配 URL
        2. title_hint 匹配页面标题
        3. 最后一个有效页面
        """
        candidates = self.list_pages()
        if not candidates:
            raise RuntimeError("未在 Chrome 中找到任何有效标签页，请确认已用 --remote-debugging-port=9222 启动 Chrome 并打开了审批页面。")

        if url_hint:
            for c in candidates:
                if url_hint in c["url"]:
                    return c["page"]

        if title_hint:
            for c in candidates:
                if title_hint in c["title"]:
                    return c["page"]

        return candidates[-1]["page"]

    def safe_click(self, page: Page, selector: str, timeout: int = 5000):
        """等待元素可见后点击。若元素不存在则立即抛出异常，避免超时阻塞。"""
        if page.locator(selector).count() == 0:
            raise Exception(f"Selector not found: {selector}")
        page.wait_for_selector(selector, state="visible", timeout=timeout)
        page.click(selector)

    def safe_fill(self, page: Page, selector: str, text: str, timeout: int = 5000):
        """等待元素可见后填写内容。若元素不存在则立即抛出异常，避免超时阻塞。"""
        if page.locator(selector).count() == 0:
            raise Exception(f"Selector not found: {selector}")
        page.wait_for_selector(selector, state="visible", timeout=timeout)
        page.fill(selector, text)

    def extract_text(self, page: Page, selector: str, timeout: int = 3000) -> str:
        """提取元素的 inner_text，若不存在则返回空字符串。"""
        try:
            if page.locator(selector).count() == 0:
                return ""
            page.wait_for_selector(selector, state="visible", timeout=timeout)
            return page.inner_text(selector).strip()
        except Exception:
            return ""

    def find_frame_with_selector(self, page: Page, selector: str, timeout: int = 3000):
        """
        如果主页面没有该选择器，则遍历所有 iframe 查找。

        返回值：
        - 如果在 iframe 中找到：返回该 Frame 对象
        - 如果在主页面找到：返回 None（这是正常情况，表示无需切 iframe）
        - 如果都没找到：返回 None

        ⚠️ 调用方注意：返回 None 不代表"没找到"！必须先检查主页面
           `page.locator(selector).count() > 0` 才能确定是否真的没找到。
        """
        if not selector:
            return None
        try:
            if page.locator(selector).count() > 0:
                page.wait_for_selector(selector, state="visible", timeout=500)
                return None
        except Exception:
            pass

        iframe_handles = page.locator("iframe").element_handles()
        for iframe in iframe_handles:
            try:
                frame = iframe.content_frame()
                if frame:
                    # 先用 count() 快速判断是否存在，避免每个 iframe 都等满超时
                    if frame.locator(selector).count() > 0:
                        frame.wait_for_selector(selector, state="visible", timeout=timeout)
                        return frame
            except Exception:
                continue
        return None

    def screenshot(self, page: Page, name: str, full_page: bool = False):
        """截图保存到 _Temp/ 目录。兼容页面尺寸异常的情况。"""
        import os
        os.makedirs("_Temp", exist_ok=True)
        path = f"_Temp/{name}_{int(time.time())}.png"
        try:
            # 某些页面 full_page 会报 0 width，先尝试普通截图
            page.screenshot(path=path, full_page=full_page)
        except Exception:
            try:
                # 普通截图也失败时，设置一个默认 viewport 再截
                page.set_viewport_size({"width": 1920, "height": 1080})
                page.screenshot(path=path, full_page=False)
            except Exception as e2:
                print(f"[截图失败] {e2}")
                return None
        print(f"[截图已保存] {path}")
        return path

    def test_selector(self, page, selector: str):
        """
        测试某个选择器是否能在当前页面（含 iframe）中找到可见元素。
        返回 (found: bool, location: str)
        """
        if not selector or not selector.strip():
            return False, "未配置"

        # 纯数字固定值不视为选择器
        import re
        if re.fullmatch(r"\d+", selector.strip()):
            return True, "固定值"

        # 主页面
        try:
            loc = page.locator(selector)
            if loc.count() > 0:
                for i in range(min(loc.count(), 5)):
                    try:
                        if loc.nth(i).is_visible():
                            return True, "主页面"
                    except Exception:
                        continue
                return True, "主页面（存在但不可见）"
        except Exception:
            pass

        # iframe
        try:
            iframe_handles = page.locator("iframe").element_handles()
            for idx, iframe in enumerate(iframe_handles):
                try:
                    frame = iframe.content_frame()
                    if frame:
                        loc = frame.locator(selector)
                        if loc.count() > 0:
                            for i in range(min(loc.count(), 5)):
                                try:
                                    if loc.nth(i).is_visible():
                                        return True, f"iframe[{idx}]"
                                except Exception:
                                    continue
                            return True, f"iframe[{idx}]（存在但不可见）"
                except Exception:
                    continue
        except Exception:
            pass

        return False, "未找到"

    def find_contract_frame(self, page: Page):
        """
        查找包含合同标签的 frame。先检查传入的 frame/page 自身，
        再检查其内部嵌套 iframe，返回评分最高的那个。
        """
        best_frame = None
        best_score = 0

        # 1. 先检查自身
        try:
            cnt = page.evaluate(
                "() => document.querySelectorAll('span.jresui_label-left-content').length"
            )
            if cnt and cnt > 0:
                score = page.evaluate(
                    """() => {
                        const spans = document.querySelectorAll('span.jresui_label-left-content');
                        let s = 0;
                        for (const el of spans) {
                            const t = el.textContent.trim();
                            if (t === '合同金额：' || t === '合同名称：' || t === '合同ID：') s += 10;
                            else if (t.includes('合同')) s += 1;
                        }
                        return s;
                    }"""
                )
                if score > best_score:
                    best_score = score
                    best_frame = page
        except Exception:
            pass

        # 2. 再检查内部 iframe
        try:
            iframe_handles = page.locator("iframe").element_handles()
            for iframe in iframe_handles:
                try:
                    frame = iframe.content_frame()
                    if not frame:
                        continue
                    cnt = frame.evaluate(
                        "() => document.querySelectorAll('span.jresui_label-left-content').length"
                    )
                    if cnt and cnt > 0:
                        score = frame.evaluate(
                            """() => {
                                const spans = document.querySelectorAll('span.jresui_label-left-content');
                                let s = 0;
                                for (const el of spans) {
                                    const t = el.textContent.trim();
                                    if (t === '合同金额：' || t === '合同名称：' || t === '合同ID：') s += 10;
                                    else if (t.includes('合同')) s += 1;
                                }
                                return s;
                            }"""
                        )
                        if score > best_score:
                            best_score = score
                            best_frame = frame
                except Exception:
                    continue
        except Exception:
            pass

        return best_frame

    def extract_contract_fields_from_frame(self, frame) -> dict:
        """
        从合同审批页面的 iframe 中提取合同特有字段。
        致远 OA 合同页使用成对的 span.jresui_label-left-content / span.jresui_label-right-content，
        通过索引一一对应。
        合同名称优先从报审附件（文档类型=合同文本）提取，其次才用表单字段。
        """
        result = {}
        form_name = ""
        try:
            left_count = frame.evaluate(
                "() => document.querySelectorAll('span.jresui_label-left-content').length"
            )
            right_count = frame.evaluate(
                "() => document.querySelectorAll('span.jresui_label-right-content').length"
            )
            limit = min(left_count, right_count)

            for i in range(limit):
                label = frame.evaluate(
                    "(idx) => { const s = document.querySelectorAll('span.jresui_label-left-content')[idx]; return s ? s.textContent.trim() : ''; }",
                    i,
                )
                if not label:
                    continue
                val = frame.evaluate(
                    "(idx) => { const s = document.querySelectorAll('span.jresui_label-right-content')[idx]; return s ? (s.textContent || '').trim() : ''; }",
                    i,
                )

                if label == "合同金额：":
                    result["合同金额"] = val
                elif label in ("合同ID：", "纸质合同编号："):
                    if not result.get("合同编号"):
                        result["合同编号"] = val
                elif label == "合同名称：":
                    form_name = val
                elif label == "交易对手：":
                    result["交易对手"] = val
                elif label == "合同概要：":
                    result["备注"] = val
                elif label == "审批事项说明：":
                    if not result.get("备注"):
                        result["备注"] = val
                elif label == "备注：":
                    if not result.get("备注"):
                        result["备注"] = val
                # 备用交易对手字段
                elif label in ("乙方：", "受让方："):
                    if not result.get("交易对手"):
                        result["交易对手"] = val

            # 优先从报审附件中提取 "合同文本" 对应的所有文档名称
            doc_names = self.extract_contract_doc_names_from_frame(frame)
            if doc_names:
                result["合同名称列表"] = doc_names
                result["合同名称"] = doc_names[0]
            else:
                # 附件中未找到，尝试从 "合同信息" 链接中提取
                try:
                    link_text = frame.evaluate(
                        """() => {
                            const links = document.querySelectorAll('a.trust-workflow-tag-a');
                            for (const a of links) {
                                const t = a.textContent || '';
                                if (t.includes('合同编号：') && t.includes('合同名称：')) {
                                    return t.trim();
                                }
                            }
                            return null;
                        }"""
                    )
                    if link_text:
                        m = __import__('re').search(r"合同名称：\s*([^|]+)", link_text)
                        if m:
                            name_from_link = m.group(1).strip()
                            if name_from_link:
                                result["合同名称"] = name_from_link
                except Exception:
                    pass

                # 最后兜底：使用表单中的 "合同名称" 字段
                if not result.get("合同名称") and form_name:
                    result["合同名称"] = form_name

        except Exception:
            pass
        return result

    def extract_contract_doc_names_from_frame(self, frame) -> list:
        """
        从合同审批页面的 iframe 中提取"报审附件"区域里文档类型为"合同文本"的所有文档名称。
        采用多策略兜底，兼容多种 DOM 结构。返回去重后的列表。
        """
        found_names = []

        # ── Strategy 0: 嵌套 iframe（projectTextManageForIframe.htm）中的附件表格 ──
        try:
            nested_count = frame.evaluate("() => document.querySelectorAll('iframe').length")
            for nidx in range(nested_count):
                nested_src = frame.evaluate(
                    "(idx) => { const fr = document.querySelectorAll('iframe')[idx]; return fr ? (fr.src || fr.getAttribute('src') || '') : ''; }",
                    nidx,
                )
                if "projectTextManageForIframe.htm" not in nested_src:
                    continue
                nested_handle = frame.locator("iframe").nth(nidx).element_handle()
                if not nested_handle:
                    continue
                nested_frame = nested_handle.content_frame()
                if not nested_frame:
                    continue
                text = nested_frame.evaluate("() => document.body.innerText") or ""

                # 解析 innerText：按行拆分，优先按 \t 分割取字段
                lines = text.split("\n")
                for line in lines:
                    line = line.strip()
                    if "合同文本" not in line:
                        continue
                    parts = [p.strip() for p in line.split("\t") if p.strip()]
                    for j, part in enumerate(parts):
                        if part == "合同文本" and j + 1 < len(parts):
                            candidate = parts[j + 1]
                            if candidate and candidate not in ("操作", "已审批", "未审批", "下载"):
                                found_names.append(candidate)

                # 若按 \t 未命中，退化为逐行扫描
                if not found_names:
                    for i, line in enumerate(lines):
                        line_stripped = line.strip()
                        if line_stripped != "合同文本" and "\t合同文本\t" not in line:
                            continue
                        for j in range(i + 1, min(i + 6, len(lines))):
                            candidate = lines[j].strip()
                            if candidate in ("操作", "已审批", "未审批", "下载", "打印"):
                                continue
                            if candidate.replace(".", "").replace("-", "").isdigit():
                                continue
                            if "KB" in candidate or "MB" in candidate:
                                continue
                            if len(candidate) < 3:
                                continue
                            if "-" in candidate and ":" in candidate:
                                continue
                            found_names.append(candidate)
                            break
        except Exception:
            pass

        if found_names:
            # 去重同时保持顺序
            seen = set()
            unique = []
            for name in found_names:
                if name not in seen:
                    seen.add(name)
                    unique.append(name)
            return unique

        # ── Strategy 1: 直接扫描 table tr，寻找某单元格包含"合同文本"，取同行其他单元格的文本 ──
        try:
            for i in range(50):
                row_text = frame.evaluate(
                    "(idx) => { const r = document.querySelectorAll('table tr')[idx]; return r ? r.innerText.trim() : ''; }",
                    i,
                )
                if not row_text:
                    continue
                if "合同文本" in row_text:
                    cells = row_text.split("\n")
                    for j, cell in enumerate(cells):
                        if "合同文本" in cell and j + 1 < len(cells):
                            candidate = cells[j + 1].strip()
                            if candidate and len(candidate) > 1:
                                return [candidate]
                    candidates = [c.strip() for c in cells if c.strip() and "合同文本" not in c]
                    if candidates:
                        return [max(candidates, key=len)]
        except Exception:
            pass

        # ── Strategy 2: 扫描所有文本节点，找"合同文本"附近的内容 ──
        try:
            nearby_text = frame.evaluate(
                """() => {
                    const walker = document.createTreeWalker(document.body, NodeFilter.SHOW_TEXT, null, false);
                    while (walker.nextNode()) {
                        const t = walker.currentNode.textContent.trim();
                        if (t === '合同文本' || t.includes('合同文本')) {
                            let n = walker.currentNode.parentElement;
                            if (n) {
                                let sib = n.nextElementSibling;
                                if (sib) return sib.textContent.trim().substring(0, 100);
                                let p = n.parentElement;
                                if (p) {
                                    let ps = p.nextElementSibling;
                                    if (ps) return ps.textContent.trim().substring(0, 100);
                                    let children = Array.from(p.children);
                                    let texts = children.map(c => c.textContent.trim()).filter(txt => txt && !txt.includes('合同文本'));
                                    if (texts.length) return texts.reduce((a, b) => a.length > b.length ? a : b).substring(0, 100);
                                }
                            }
                        }
                    }
                    return '';
                }"""
            )
            if nearby_text:
                return [nearby_text]
        except Exception:
            pass

        # ── Strategy 3: 找包含"报审附件"的容器，在其内部搜索最长的非空文本作为文档名 ──
        try:
            container_text = frame.evaluate(
                """() => {
                    const walker = document.createTreeWalker(document.body, NodeFilter.SHOW_TEXT, null, false);
                    while (walker.nextNode()) {
                        const t = walker.currentNode.textContent.trim();
                        if (t === '报审附件' || t === '附件' || t.includes('报审附件')) {
                            const container = walker.currentNode.parentElement.closest('div, table, section, fieldset');
                            if (container) {
                                const allTexts = Array.from(container.querySelectorAll('td, span, a, div, li'))
                                    .map(el => el.textContent.trim())
                                    .filter(txt => txt && txt.length > 3 && !txt.includes('报审附件') && !txt.includes('附件类型') && !txt.includes('文档类型') && !txt.includes('合同文本') && !txt.includes('上传') && !txt.includes('操作'));
                                if (allTexts.length) return allTexts.reduce((a, b) => a.length > b.length ? a : b).substring(0, 100);
                            }
                        }
                    }
                    return '';
                }"""
            )
            if container_text:
                return [container_text]
        except Exception:
            pass

        # ── Strategy 4: 兜底 —— 扫描所有 a 标签，找包含"合同"或"协议"且长度合适的文本 ──
        try:
            link_texts = frame.evaluate(
                """() => {
                    const links = document.querySelectorAll('a');
                    const out = [];
                    for (const a of links) {
                        const t = a.textContent.trim();
                        if ((t.includes('合同') || t.includes('协议')) && t.length > 4 && t.length < 80 && !t.includes('合同编号') && !t.includes('合同名称') && !t.includes('合同类型')) {
                            out.push(t);
                        }
                    }
                    return out;
                }"""
            )
            if link_texts and len(link_texts) > 0:
                return [link_texts[0]]
        except Exception:
            pass

        return []

    def close(self):
        # 连接已有 Chrome 时不应关闭浏览器，只需停止 playwright 实例
        if self.playwright:
            self.playwright.stop()
