"""Read-only checks: no workflow clicks, navigation, webhook POSTs or note writes."""
import json
import os
from pathlib import Path
from urllib.parse import urlsplit, parse_qs

from .browser import BrowserHelper
from .registration import load_settings, apply_wechat_settings
from .webhook import WebhookHelper
from .safe_debug import load_workflow, visible_frame, department_options, WINDOW


def diagnose(config_path, endpoint):
    checks = []
    def add(name, status, message):
        checks.append(dict(name=name, status=status, message=message))
    config = None
    try:
        config = json.loads(Path(config_path).read_text(encoding='utf-8-sig'))
        if not isinstance(config, dict) or not isinstance(config.get('approval', {}), dict):
            raise ValueError()
        add('基础配置', 'ok', '配置结构可读取')
    except Exception:
        add('基础配置', 'error', '配置缺失或格式错误；请检查本机配置，不要用分享包覆盖个人设置')
    try:
        workflow = load_workflow(config_path)
        add('运行模式', 'ok', '安全调试已开启，不允许审批或补登' if workflow['debug_enabled'] else '正式模式；诊断仍不执行审批')
    except Exception:
        add('运行模式', 'error', '调试/部门配置无效，请检查步骤数和部门选项')
    try:
        prefs_path = Path(config_path).with_name('browser.json')
        if prefs_path.exists():
            prefs = json.loads(prefs_path.read_text(encoding='utf-8-sig'))
            if not isinstance(prefs, dict) or prefs.get('mode', 'smart') not in ('smart', 'auto', 'port') or type(prefs.get('port', 9222)) is not int or not 1 <= prefs.get('port', 9222) <= 65535:
                raise ValueError()
        add('连接配置', 'ok', '浏览器连接参数格式可读取')
    except Exception:
        add('连接配置', 'error', '浏览器连接设置无效；本次可能使用默认9222入口，请修正连接设置')
    if config is not None:
        try:
            settings = load_settings(config_path, config)
            apply_wechat_settings(config_path, config)
            if settings['wechat_enabled']:
                webhook = config.get('webhook', {})
                url = urlsplit(webhook.get('url', ''))
                schema = webhook.get('schema', {})
                valid = (url.scheme == 'https' and url.hostname == 'qyapi.weixin.qq.com'
                         and url.path == '/cgi-bin/wedoc/smartsheet/webhook' and parse_qs(url.query).get('key')
                         and isinstance(schema, dict) and schema.get('title'))
                values = [v for v in schema.values() if v] if isinstance(schema, dict) else []
                valid = valid and all(isinstance(v, str) for v in values) and len(values) == len(set(values))
                if valid:
                    try:
                        WebhookHelper(config).validate_schema()
                    except (ValueError, TypeError):
                        valid = False
                add('企业微信', 'ok' if valid else 'error',
                    '链接、字段类型和选项规则格式正常；未发送请求，不能据此确认链接有效或网络可达' if valid else '链接、字段类型或选项对应规则无效，请到数据登记设置修正')
            else:
                add('企业微信', 'skip', '通道已关闭')
            if settings['obsidian_enabled']:
                directory = Path(settings.get('obsidian_directory', ''))
                exists = directory.is_absolute() and directory.is_dir()
                writable = exists and os.access(directory, os.W_OK)
                add('Obsidian', 'ok' if writable else 'error',
                    '记录文件夹存在，权限初检通过；未创建文件，实际写入仍可能受网络或权限影响' if writable else '目录不可用或权限初检失败，请检查盘符、网络共享和目录')
            else:
                add('Obsidian', 'skip', '通道已关闭')
        except Exception:
            add('登记配置', 'error', '登记设置格式无效，请检查数据登记设置')
    browser = BrowserHelper(cdp_endpoint=endpoint)
    try:
        address = urlsplit(endpoint)
        if address.scheme not in ('http', 'https', 'ws', 'wss') or address.hostname not in ('localhost', '127.0.0.1', '::1'):
            raise ValueError('local endpoint required')
        browser.connect()
        add('浏览器连接', 'ok', '已连接本机调试浏览器；未新建业务页面')
        pages = [p for context in browser.browser.contexts for p in context.pages
                 if urlsplit(p.url).path == '/amcs/index.htm' or '/seeyon/' in urlsplit(p.url).path]
        add('业务页面', 'ok' if pages else 'warn', f'发现 {len(pages)} 个核心/OA页面；请确保目标详情已打开' if pages else '未找到核心/OA页面，请手动打开并登录')
        locks, departments, approves = 0, 0, 0
        for page in pages:
            for frame in page.frames:
                if not visible_frame(frame):
                    continue
                locks += frame.locator('input[type="password"]').filter(visible=True).count()
                if frame.locator(WINDOW).filter(visible=True).count():
                    options = department_options(frame)
                    departments += 1
                    add('部门窗口', 'ok' if options['complete'] else 'warn',
                        f"当前可读 {len(options['items'])} 项，{'列表完整' if options['complete'] else '仅当前页，不是完整列表'}；未选择选项")
                selector = (config or {}).get('approval', {}).get('approve_button_selector', '')
                if selector:
                    approves += frame.locator(selector).filter(visible=True).count()
        add('登录/锁屏', 'warn' if locks else 'ok', '发现可见密码输入框，请手动确认登录或解锁状态' if locks else '未发现可见密码输入框；不等于已确认登录有效')
        add('核心审批按钮', 'ok' if approves == 1 else 'warn', f'配置选择器匹配 {approves} 个可见按钮；仅检查存在性，未点击')
        if not departments:
            add('部门窗口', 'skip', '尚未打开部门窗口；无需为诊断点击同意或中间确定')
    except Exception:
        add('浏览器/页面检查', 'error', '连接或页面检查失败；请检测调试入口，并检查页面是否关闭、刷新或选择器失效')
    finally:
        browser.close()
    return dict(checks=checks, read_only=True,
                note='未执行审批、未发送Webhook、未创建Obsidian记录；诊断不保证真实提交成功。')
