"""
审批自动化 runner — 命令行入口 + JSON Lines 事件流输出

用法:
    python runner.py --cdp http://localhost:9222 --config config.json --qty 1 --biz-type "金融不良资产" --oa-type old

输出:
    每行一个 JSON 对象到 stdout，前端/Rust 通过逐行读取解析。
    所有非 JSON 的 print / 日志 被重定向到 stderr，不会污染 stdout。

事件类型:
    log          - 普通日志
    data_extracted - 提取到一条审批数据
    submit_success - 单条数据提交成功
    all_done     - 全部处理完成
    error        - 错误/异常

取消:
    向 stdin 写入 "cancel\n" 可在下一条数据提交前中断流程。
"""

import argparse
import json
import os
import sys
import threading
import time

# ── 关键：把 sys.stdout 重定向到 stderr，防止 src/*.py 中的 print 污染 JSON Lines ──
# emit() 直接使用原始 stdout 写 JSON
_original_stdout = sys.stdout
sys.stdout = sys.stderr

from src.browser import BrowserHelper
from src.approver import ApprovalHelper
from src.tencent_form import TencentFormHelper
from src.webhook import WebhookHelper


def emit(event_type, **kwargs):
    """向原始 stdout 输出一条 JSON Lines 事件。"""
    payload = {"event": event_type}
    payload.update(kwargs)
    line = json.dumps(payload, ensure_ascii=False) + "\n"
    try:
        # 直接系统调用写 fd 1，绕过 Python 缓冲层，避免 Windows pipe flush 失败
        os.write(1, line.encode("utf-8"))
    except OSError:
        pass


def main():
    parser = argparse.ArgumentParser(description="Approval Automation Runner")
    parser.add_argument("--cdp", default="http://localhost:9222", help="Chrome DevTools Protocol endpoint")
    parser.add_argument("--config", required=True, help="Path to config.json")
    parser.add_argument("--qty", default="1", help="Override quantity")
    parser.add_argument("--biz-type", default="", help="Override business type")
    parser.add_argument("--oa-type", default="auto", choices=["auto", "old", "new"], help="OA system type")
    parser.add_argument("--test-mode", action="store_true", help="Test mode: extract only, no click/submit")
    args = parser.parse_args()

    # 加载配置
    if not os.path.exists(args.config):
        emit("error", msg=f"配置文件不存在: {args.config}")
        return

    with open(args.config, "r", encoding="utf-8") as f:
        config = json.load(f)

    # 覆盖字段
    config.setdefault("approval", {}).setdefault("fields", {})
    config["approval"]["fields"]["数量"] = args.qty
    if args.biz_type:
        config["approval"]["fields"]["业务类型"] = args.biz_type

    # ── 取消监听线程 ──
    cancelled = threading.Event()

    def _stdin_listener():
        try:
            while not cancelled.is_set():
                line = sys.stdin.readline()
                if not line:
                    break
                if line.strip().lower() == "cancel":
                    cancelled.set()
                    emit("log", level="info", msg="收到取消信号，将在当前操作完成后停止")
                    break
        except Exception:
            pass

    stdin_thread = threading.Thread(target=_stdin_listener, daemon=True)
    stdin_thread.start()

    # ── 日志回调 ──
    def log_callback(msg, level="info"):
        emit("log", level=level, msg=msg)

    browser = BrowserHelper(cdp_endpoint=args.cdp, log_callback=log_callback)
    approver = ApprovalHelper(
        browser,
        config,
        test_mode=args.test_mode,
        log_callback=log_callback,
        oa_type=args.oa_type,
    )
    webhook_helper = WebhookHelper(config)
    form_helper = TencentFormHelper(browser, config)

    try:
        emit("log", level="info", msg="正在连接 Chrome...")
        browser.connect()

        candidates = browser.list_pages()
        if not candidates:
            emit("error", msg="未找到有效标签页，请确认 Chrome 已启动 --remote-debugging-port=9222")
            return

        page_hint = config.get("page_hint", "核心业务管理系统")
        url_hint = config.get("url_hint", "")
        page = browser.get_approval_page(url_hint=url_hint, title_hint=page_hint)

        # 尝试定位 iframe（与原 run.py 保持一致的多策略兜底）
        approve_selector = config.get("approval", {}).get("approve_button_selector", "")
        approval_target = browser.find_frame_with_selector(page, approve_selector)
        if approval_target:
            emit("log", level="info", msg="检测到 iframe，已自动切换")
        else:
            # find_frame_with_selector 返回 None 有两种可能：
            # 1. 主页面找到按钮（正常，不需要 iframe）
            # 2. 主页面和 iframe 都没找到，尝试内容选择器回退
            try:
                if page.locator(approve_selector).count() > 0:
                    emit("log", level="info", msg="通过按钮在主页面，无需 iframe")
                    approval_target = page
                else:
                    for content_sel in [
                        "a.trust-workflow-tag-a, div.unit-value-text:has-text('[')",
                        "i#hsBpmDescTitle, #workflowFormDiv",
                    ]:
                        approval_target = browser.find_frame_with_selector(page, content_sel)
                        if approval_target:
                            emit("log", level="info", msg=f"通过内容选择器定位到 iframe: {content_sel}")
                            break
            except Exception:
                pass
        if not approval_target:
            approval_target = page

        approver.main_page = page

        # ── 处理审批 ──
        results = approver.process_current_page(approval_target)

        if not results:
            emit("error", msg="未提取到任何审批数据")
            return

        # 应用覆盖值
        for data in results:
            data["数量"] = args.qty
            if args.biz_type:
                data["业务类型"] = args.biz_type

        if args.test_mode:
            for data in results:
                emit("data_extracted", data=data)
            emit("all_done", count=len(results), success_count=0)
            return

        # ── 提交数据 ──
        success_count = 0
        for idx, data in enumerate(results):
            if cancelled.is_set():
                emit("log", level="info", msg="流程已取消，停止后续提交")
                break

            emit("data_extracted", data=data)

            ok = False
            if webhook_helper.url:
                ok = webhook_helper.submit(data)
                if not ok:
                    emit("log", level="warning", msg="Webhook 失败，尝试腾讯表格...")
                    ok = form_helper.submit(data, context=browser.context)
            else:
                ok = form_helper.submit(data, context=browser.context)

            if ok:
                success_count += 1
                emit("submit_success", idx=idx, data=data)
            else:
                emit("log", level="error", msg=f"第 {idx + 1} 条数据提交失败")

        emit("all_done", count=len(results), success_count=success_count)

    except Exception as e:
        import traceback
        emit("error", msg=str(e), traceback=traceback.format_exc())
    finally:
        browser.close()
        cancelled.set()


if __name__ == "__main__":
    main()
