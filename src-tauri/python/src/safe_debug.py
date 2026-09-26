"""Inspection and trial clicks only. Never dispatch a DOM click or registration."""
import json
from pathlib import Path
from urllib.parse import urlsplit

from .approver import ApprovalHelper

WINDOW = '#selectPartjobOrgWin'


def load_workflow(config_path):
    path = Path(config_path).with_name('workflow.json')
    value = json.loads(path.read_text(encoding='utf-8-sig')) if path.exists() else {}
    defaults = dict(debug_enabled=False, debug_steps=0, show_department=False,
                    department_id='', departments=[], source='')
    if not isinstance(value, dict):
        raise ValueError('调试与部门设置格式无效')
    defaults.update(value)
    if any(type(defaults[key]) is not bool for key in ('debug_enabled', 'show_department')):
        raise ValueError('调试开关格式无效')
    if type(defaults['debug_steps']) is not int or not 0 <= defaults['debug_steps'] <= 10:
        raise ValueError('请确认审批步骤数（1至10）')
    if defaults['debug_enabled'] and not defaults['debug_steps']:
        raise ValueError('启用调试前请先确认当前流程的审批步骤数')
    if not isinstance(defaults['departments'], list) or not isinstance(defaults['department_id'], str) or not isinstance(defaults['source'], str):
        raise ValueError('部门设置格式无效')
    ids = []
    for item in defaults['departments']:
        if not isinstance(item, dict) or not isinstance(item.get('id'), str) or not item['id'] or not isinstance(item.get('name'), str) or not item['name']:
            raise ValueError('部门选项格式无效')
        ids.append(item['id'])
    if len(ids) != len(set(ids)) or (defaults['department_id'] and defaults['department_id'] not in ids):
        raise ValueError('所选部门不在已读取的唯一选项中')
    if defaults['departments']:
        source = urlsplit(defaults['source'])
        if source.scheme not in ('http', 'https') or not source.netloc or source.path or source.query or source.fragment or source.username:
            raise ValueError('部门来源无效，请重新读取')
    return defaults


def visible_frame(frame):
    frame = getattr(frame, 'main_frame', frame)
    while frame.parent_frame:
        if not frame.frame_element().is_visible():
            return False
        frame = frame.parent_frame
    return True


def department_options(frame):
    window = frame.locator(WINDOW).filter(visible=True)
    if window.count() != 1 or not visible_frame(frame):
        raise ValueError('请先由用户手动打开唯一的“选择部门”窗口')
    return window.evaluate("""root => {
      if (root.querySelector('.m-message-title')?.textContent.trim() !== '选择部门') throw Error('部门窗口标题不匹配');
      const items = [...root.querySelectorAll('#body_PartjobOrgTable > tr')].filter(row => row.getClientRects().length).map(row => {
        const id = row.querySelector('td[name="orgid"]')?.textContent.trim();
        const name = row.querySelector('td[name="orgname"]')?.textContent.trim();
        const radios = row.querySelectorAll('input[type="radio"]');
        if (!id || !name || radios.length !== 1) throw Error('部门行结构无法识别');
        return {id, name, checked: radios[0].checked};
      });
      if (!items.length || new Set(items.map(item => item.id)).size !== items.length) throw Error('部门列表为空或编号重复');
      const pages = root.querySelector('#totalPages_PartjobOrgTable')?.textContent.trim();
      const info = root.querySelector('#pageInfo_PartjobOrgTable')?.textContent || '';
      const total = info.match(/共\\s*(\\d+)\\s*条记录/);
      const controls = ['.first_page_btn','.pre_page_btn','.next_page_btn','.last_page_btn'];
      const complete = pages === '1' && !!total && Number(total[1]) === items.length
        && controls.every(sel => root.querySelector(sel)?.classList.contains('disabled'));
      return {items, complete, pages: pages || null};
    }""")


def department_radio(frame, department_id):
    import re
    # Match the ID cell, never the display name or the non-unique footer IDs.
    return frame.locator(f'{WINDOW} #body_PartjobOrgTable > tr').filter(
        has=frame.locator('td[name="orgid"]').filter(has_text=re.compile(r'^\s*' + re.escape(department_id) + r'\s*$'))
    ).locator('input[type="radio"]').filter(visible=True)


def inspect(browser, config, workflow, log, options_only=False):
    selector = config.get('approval', {}).get('approve_button_selector', '')
    details, windows = [], []
    for context in browser.browser.contexts:
        for page in context.pages:
            if urlsplit(page.url).path != '/amcs/index.htm':
                continue
            for frame in page.frames:
                if not visible_frame(frame):
                    continue
                if (urlsplit(frame.url).scheme, urlsplit(frame.url).netloc) != (urlsplit(page.url).scheme, urlsplit(page.url).netloc):
                    continue
                has_window = frame.locator(WINDOW).filter(visible=True).count() == 1
                if has_window:
                    windows.append(frame)
                if not options_only and selector and frame.locator(selector).filter(visible=True).count():
                    details.append(frame)
    if len(windows) > 1 or len(details) > 1 or not (windows or details):
        raise ValueError('未找到唯一核心详情/部门窗口；请关闭重复详情并由用户打开目标页面')
    if windows and details and windows[0].page != details[0].page:
        raise ValueError('详情与部门窗口不属于同一页面，请关闭重复页面')
    frame = windows[0] if windows else details[0]
    url = urlsplit(frame.url)
    result = dict(read_only=True, clicks_sent=0, registration_enabled=False, declared_steps=workflow['debug_steps'],
                  source=f'{url.scheme}://{url.netloc}', departments=None, checks=[], records=[])
    if not options_only:
        helper = ApprovalHelper(browser, config, log_callback=log, oa_type='old')
        detail = details[0] if details else frame
        helper.main_page = detail
        result['records'] = helper.extract_current_page(detail)
    if frame.locator(WINDOW).filter(visible=True).count() == 1:
        before = department_options(frame)
        result['departments'] = before
        selected = workflow['department_id']
        if selected and not options_only:
            if workflow['source'] != result['source'] or selected not in [item['id'] for item in before['items']]:
                raise ValueError('所选部门来源或编号与当前窗口不匹配，请重新读取')
            try:
                department_radio(frame, selected).click(trial=True, timeout=1500)
                result['checks'].append('所选部门可点击（仅检测，未选中）')
            except Exception:
                result['checks'].append('所选部门当前不可点击；未强制点击')
        if department_options(frame) != before:
            raise ValueError('检测期间部门窗口发生变化，请重新读取')
        result['checks'].append('部门窗口确定会提交审批，禁止点击；其他按钮也不发送点击')
    elif selector:
        try:
            frame.locator(selector).filter(visible=True).click(trial=True, timeout=1500)
            result['checks'].append('同意按钮可点击（仅检测，未点击）')
        except Exception:
            result['checks'].append('同意按钮当前不可点击；未强制点击')
    result['checks'].append('步骤数仅作为用户声明；中间确定可能直接提交，不能据此放行点击')
    return result
