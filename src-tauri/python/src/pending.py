"""Read the TrustUI pending widget and open only a verified task row."""
import json
import time
from urllib.parse import parse_qs, urljoin, urlsplit

from .approver import ApprovalHelper


WIDGET = '#trust_pagelet_lcdb'
SNAPSHOT = r"""() => {
  const root = document.querySelector('#trust_pagelet_lcdb');
  const cache = window.TrustUI?.getComp('trust_pagelet_lcdb')?._dataparamCaches;
  if (!root || !cache) throw Error('待办组件数据尚未就绪');
  const items = [...root.querySelectorAll('._dataitem_')].filter(el => el.getClientRects().length).map(el => {
    const key = el.getAttribute('paramcacheid');
    const data = cache[key]; const content = data?.msgContent;
    if (!content?.taskId || !data?.tcmpUrl) throw Error('待办缺少任务编号或打开地址');
    return {task_id: String(content.taskId), title: content.PROC_TITLE || el.querySelector('.title')?.getAttribute('title') || '',
      process: content.PROC_NAME || '', node: content.ACTIVITY_NAME || '', time: data.sendDate || '',
      open_url: data.tcmpUrl, row_key: key};
  });
  const raw = root.querySelector('#trust_pagelet_lcdb-itemnumber')?.value || root.querySelector('.hd-num-con')?.textContent;
  const total = raw?.trim() && /^\d+$/.test(raw.trim()) ? Number(raw) : null;
  const pager = root.querySelector('#trust_pagelet_lcdb-footer .layui-laypage');
  const currentText = pager?.querySelector('.layui-laypage-curr em:last-child')?.textContent?.trim();
  const page = currentText && /^\d+$/.test(currentText) ? Number(currentText) : null;
  const prev = pager?.querySelector('a.layui-laypage-prev');
  const next = pager?.querySelector('a.layui-laypage-next');
  const enabledPage = link => {
    if (!link || link.classList.contains('layui-disabled')) return null;
    if (!/^\d+$/.test(link.getAttribute('data-page') || '')) throw Error('待办分页目标无效，无法确认列表完整性');
    return Number(link.getAttribute('data-page'));
  };
  return {total, page, has_pager: !!pager, prev_page: enabledPage(prev), next_page: enabledPage(next), items};
}"""

CLOSE_TAB = r"""taskId => {
  const active = [...document.querySelectorAll('#tab-con li.active')];
  if (active.length !== 1 || active[0].getAttribute('tabid') !== 'MSG_' + taskId)
    return {closed: false, reason: '指定任务不是当前打开的核心系统详情子页'};
  const tab = active[0];
  const url = new URL(tab.getAttribute('url') || '', location.href);
  const ids = url.searchParams.getAll('taskId');
  if (tab.getAttribute('title') !== '待办事宜处理' || url.origin !== location.origin
      || url.pathname !== '/amcs/bpm/client/mw/open' || ids.length !== 1 || ids[0] !== taskId)
    return {closed: false, reason: '详情标签地址与任务编号不匹配'};
  const controls = tab.querySelectorAll('span.h-tab-close');
  if (controls.length !== 1 || !controls[0].getClientRects().length
      || ['hidden', 'collapse'].includes(getComputedStyle(controls[0]).visibility))
    return {closed: false, reason: '详情子页关闭按钮不可见或不唯一'};
  controls[0].click();
  return {closed: true};
}"""

UNLOCK_STATE = r"""() => {
  const visible = el => {
    const rect = el.getBoundingClientRect();
    const style = getComputedStyle(el);
    return rect.width > 0 && rect.height > 0 && style.display !== 'none'
      && style.visibility === 'visible';
  };
  const dialogs = [...document.querySelectorAll('.h_floatdiv.m-message-positon')].filter(visible);
  if (!dialogs.length) return {ready: false, clear: true};
  if (dialogs.length !== 1) return {ready: false, clear: false};
  const dialog = dialogs[0];
  const title = dialog.querySelector('.m-message-title,.h_floatdiv-title')?.textContent?.trim();
  const fields = [...dialog.querySelectorAll('input[type="password"][name="pwd"]')].filter(visible);
  const confirms = [...dialog.querySelectorAll('button')].filter(el =>
    visible(el) && el.textContent.trim() === '确定');
  return {ready: title === '当前会话已经失效,屏幕已锁定,请激活!'
    && fields.length === 1 && confirms.length === 1, clear: false};
}"""


class PendingReader:
    MAX_PAGE_STEPS = 100

    def __init__(self, browser, config, log, page_url=None):
        self.browser, self.config, self.log = browser, config, log
        self.page_url = page_url

    def _widget(self):
        found = []
        for context in self.browser.browser.contexts:
            for page in context.pages:
                if self.page_url and page.url != self.page_url:
                    continue
                for frame in page.frames:
                    try:
                        widget = frame.locator(WIDGET)
                        if widget.count() == 1 and widget.is_visible():
                            found.append((page, frame))
                    except Exception:
                        continue
        if len(found) != 1:
            raise ValueError(f'发现 {len(found)} 个待办列表，请打开核心系统待办首页；多个首页时用 --page-url 指定完整地址')
        return found[0]

    @staticmethod
    def _has_page(snapshot, direction):
        return snapshot.get(f'{direction}_page') is not None

    def _navigate_page(self, frame, snapshot, direction):
        if direction not in ('prev', 'next') or not snapshot.get('has_pager') or snapshot.get('page') is None:
            raise ValueError('待办分页状态无法确认，已停止翻页')
        target = snapshot.get(f'{direction}_page')
        step = -1 if direction == 'prev' else 1
        if target != snapshot['page'] + step:
            raise ValueError('待办分页目标与当前页码不连续，已停止翻页')

        selector = f'{WIDGET} #trust_pagelet_lcdb-footer .layui-laypage-{direction}'
        link = frame.locator(selector)
        if link.count() != 1 or not link.is_visible():
            raise ValueError('待办分页控件不可见或不唯一，已停止翻页')
        classes = (link.get_attribute('class') or '').split()
        if 'layui-disabled' in classes or link.get_attribute('data-page') != str(target):
            raise ValueError('待办分页控件状态已变化，已停止翻页')

        old_ids = [item['task_id'] for item in snapshot['items']]
        link.click(timeout=5000)
        try:
            frame.wait_for_function(
                """state => {
                  const root = document.querySelector('#trust_pagelet_lcdb');
                  const current = root?.querySelector('#trust_pagelet_lcdb-footer .layui-laypage-curr em:last-child')
                    ?.textContent?.trim();
                  const keys = [...(root?.querySelectorAll('._dataitem_') || [])]
                    .filter(el => el.getClientRects().length)
                    .map(el => el.getAttribute('paramcacheid'));
                  const cache = window.TrustUI?.getComp('trust_pagelet_lcdb')?._dataparamCaches;
                  const rowsReady = keys.every(key => cache?.[key]?.msgContent?.taskId && cache?.[key]?.tcmpUrl);
                  const ids = keys.map(key => String(cache?.[key]?.msgContent?.taskId));
                  return current === String(state.page)
                    && keys.length > 0
                    && JSON.stringify(ids) !== JSON.stringify(state.oldIds)
                    && rowsReady;
                }""",
                arg={'page': target, 'oldIds': old_ids},
                timeout=5000,
            )
        except Exception as exc:
            raise ValueError(f'待办分页后未到达第 {target} 页，已停止读取') from exc
        updated = frame.evaluate(SNAPSHOT)
        if updated.get('page') != target:
            raise ValueError(f'待办分页状态与目标第 {target} 页不一致，已停止读取')
        return updated

    def _first_page(self, frame):
        snapshot = frame.evaluate(SNAPSHOT)
        if not snapshot.get('has_pager'):
            return snapshot
        for _ in range(self.MAX_PAGE_STEPS):
            if snapshot.get('page') is None:
                raise ValueError('待办分页控件缺少当前页码，已停止读取')
            if snapshot['page'] == 1:
                if self._has_page(snapshot, 'prev'):
                    raise ValueError('待办第一页的上一页状态异常，已停止读取')
                return snapshot
            if not self._has_page(snapshot, 'prev'):
                raise ValueError('待办分页无法返回第一页，已停止读取')
            snapshot = self._navigate_page(frame, snapshot, 'prev')
        raise ValueError('待办分页超过安全读取上限，已停止读取')

    def _find_task(self, frame, task_id):
        snapshot = self._first_page(frame)
        for _ in range(self.MAX_PAGE_STEPS):
            ids = [item['task_id'] for item in snapshot['items']]
            if len(ids) != len(set(ids)):
                raise ValueError('同一任务在当前页出现多次，无法唯一定位，请刷新待办列表')
            matches = [item for item in snapshot['items'] if item['task_id'] == task_id]
            if len(matches) == 1:
                return matches[0]
            if len(matches) > 1:
                raise ValueError('同一任务在当前页出现多次，无法唯一定位，请刷新待办列表')
            if not self._has_page(snapshot, 'next'):
                self._first_page(frame)
                return None
            snapshot = self._navigate_page(frame, snapshot, 'next')
        raise ValueError('待办分页超过安全读取上限，已停止读取')

    def list_tasks(self):
        _, frame = self._widget()
        snapshot = self._first_page(frame)
        total = snapshot['total']
        items, seen = [], set()
        pages_read = 0
        has_pager = snapshot.get('has_pager', False)
        try:
            while True:
                pages_read += 1
                if pages_read > self.MAX_PAGE_STEPS:
                    raise ValueError('待办分页超过安全读取上限，已停止读取')
                if snapshot['total'] != total:
                    raise ValueError('翻页期间待办总数发生变化，请刷新后重试')
                page_ids = [item['task_id'] for item in snapshot['items']]
                if len(page_ids) != len(set(page_ids)):
                    raise ValueError('同一任务在当前页出现多次，无法唯一定位，请刷新待办列表')
                for item in snapshot['items']:
                    if item['task_id'] in seen:
                        raise ValueError('同一任务出现在多个待办页，无法确认列表完整性')
                    seen.add(item['task_id'])
                    items.append(item)
                if not self._has_page(snapshot, 'next'):
                    break
                snapshot = self._navigate_page(frame, snapshot, 'next')
        except Exception:
            try:
                self._first_page(frame)
            except Exception as exc:
                self.log(f'读取失败后无法恢复待办第一页: {exc}', 'warn')
            raise
        else:
            self._first_page(frame)

        complete = total is not None and len(items) == total
        if total is None and has_pager and not self._has_page(snapshot, 'next'):
            complete = True
        result = {'total': total, 'items': items}
        result['visible_count'] = len(items)
        result['pages_read'] = pages_read
        result['complete'] = complete
        result['list_url'] = frame.url
        result['warning'] = '' if complete else '无法确认全部待办均已读取：分页未结束或读取数量与系统总数不一致'
        for item in result['items']:
            item.pop('row_key')
        return result

    def close_task(self, task_id):
        if not task_id.isdecimal():
            raise ValueError('任务编号必须为数字，请先列出待办并使用 task_id')
        matches = []
        for context in self.browser.browser.contexts:
            for page in context.pages:
                if self.page_url and page.url != self.page_url:
                    continue
                parsed = urlsplit(page.url)
                if parsed.scheme not in ('http', 'https') or parsed.path != '/amcs/index.htm':
                    continue
                try:
                    home_count = page.locator('iframe#homepage_iframe').count()
                    tab_count = page.locator(f'#tab-con li.active[tabid="MSG_{task_id}"]').count()
                except Exception:
                    continue
                if home_count != 1:
                    continue
                if tab_count > 1:
                    raise ValueError('发现多个匹配的内部详情标签，未关闭任何页面')
                if tab_count == 1:
                    matches.append(page)
        if len(matches) != 1:
            raise ValueError('未找到唯一且处于当前激活状态的指定任务详情子页，未关闭任何页面')

        page = matches[0]
        try:
            result = page.evaluate(CLOSE_TAB, task_id)
        except Exception as exc:
            raise ValueError('详情子页关闭控件检查失败，未确认关闭') from exc
        if not result.get('closed'):
            raise ValueError(result.get('reason', '详情子页未关闭'))
        try:
            page.wait_for_function(
                """taskId => ![...document.querySelectorAll('#tab-con li')]
                  .some(tab => tab.getAttribute('tabid') === 'MSG_' + taskId)""",
                arg=task_id,
                timeout=5000,
            )
        except Exception as exc:
            raise ValueError('已触发关闭按钮，但未确认详情子页关闭') from exc
        return {'task_id': task_id, 'closed': True,
                'note': '仅关闭匹配的核心系统内部详情标签；未执行审批或登记。'}

    def unlock_session(self, password):
        if not isinstance(password, str) or not password or '\x00' in password:
            raise ValueError('解锁密码不能为空或包含无效字符')
        matches = []
        for context in self.browser.browser.contexts:
            for page in context.pages:
                if self.page_url and page.url != self.page_url:
                    continue
                parsed = urlsplit(page.url)
                if parsed.scheme not in ('http', 'https') or parsed.path != '/amcs/index.htm':
                    continue
                try:
                    if page.locator('iframe#homepage_iframe').count() != 1:
                        continue
                    if page.evaluate(UNLOCK_STATE).get('ready'):
                        matches.append(page)
                except Exception:
                    continue
        if len(matches) != 1:
            raise ValueError('未找到唯一的核心系统会话锁屏弹窗，未提交密码')

        page = matches[0]
        dialog = page.locator('.h_floatdiv.m-message-positon').filter(visible=True)
        field = dialog.locator('input[type="password"][name="pwd"]').filter(visible=True)
        confirm = dialog.get_by_role('button', name='确定', exact=True).filter(visible=True)
        try:
            if dialog.count() != 1 or field.count() != 1 or confirm.count() != 1:
                raise ValueError('锁屏表单已变化')
            field.fill(password, timeout=3000)
            if not page.evaluate(UNLOCK_STATE).get('ready'):
                raise ValueError('锁屏表单已变化')
            confirm.click(timeout=3000)
            deadline = time.monotonic() + 10
            while time.monotonic() < deadline:
                if (urlsplit(page.url).path == '/amcs/index.htm'
                        and page.locator('iframe#homepage_iframe').count() == 1
                        and page.evaluate(UNLOCK_STATE).get('clear')):
                    page.wait_for_timeout(300)
                    if page.evaluate(UNLOCK_STATE).get('clear'):
                        break
                page.wait_for_timeout(100)
            else:
                raise ValueError('锁屏弹窗仍在显示')
        except Exception:
            try:
                field.fill('', timeout=1000)
            except Exception:
                pass
            raise ValueError('解锁未确认成功；请在浏览器检查会话状态，命令不会重试') from None
        try:
            page.evaluate("""() => {
              for (const dialog of document.querySelectorAll('.h_floatdiv.m-message-positon')) {
                const title = dialog.querySelector('.m-message-title,.h_floatdiv-title')?.textContent?.trim();
                if (title === '当前会话已经失效,屏幕已锁定,请激活!') {
                  for (const field of dialog.querySelectorAll('input[type="password"][name="pwd"]'))
                    field.value = '';
                }
              }
            }""")
        except Exception:
            pass
        return {'unlocked': True, 'evidence': '核心系统锁屏弹窗已消失',
                'note': '仅执行一次会话解锁；未审批、未登记。'}

    @staticmethod
    def _task_frame(frame, task_id, origin):
        current = frame
        matched = False
        while current:
            parsed = urlsplit(current.url)
            if parsed.scheme in ('http', 'https') and (parsed.scheme, parsed.netloc) != origin:
                return False
            ids = parse_qs(parsed.query).get('taskId')
            if ids and ids != [task_id]:
                return False
            if current.parent_frame and not current.frame_element().is_visible():
                return False
            if (parsed.scheme, parsed.netloc) == origin and ids == [task_id]:
                matched = True
            current = current.parent_frame
        return matched

    def view_task(self, task_id, system='old', timeout=20):
        if not task_id.isdecimal():
            raise ValueError('任务编号必须为数字，请先列出待办并使用 task_id')
        page, frame = self._widget()
        item = self._find_task(frame, task_id)
        if item is None:
            raise ValueError('指定任务不在待办列表的任何分页中；不会按相似标题打开')
        expected = urlsplit(urljoin(frame.url, item['open_url']))
        origin_url = urlsplit(frame.url)
        origin = (origin_url.scheme, origin_url.netloc)
        if origin_url.scheme not in ('http', 'https') or (expected.scheme, expected.netloc) != origin or parse_qs(expected.query).get('taskId') != [task_id]:
            raise ValueError('待办打开地址与本系统或任务编号不匹配，已停止')
        row = frame.locator(f'{WIDGET} ._dataitem_[paramcacheid={json.dumps(item["row_key"])}]').filter(visible=True)
        if row.count() != 1:
            raise ValueError('待办行已变化，请重新查询')
        # Native handler preserves internal tab/delegation behavior; never invent a URL.
        row.click(timeout=5000)
        deadline = time.monotonic() + timeout
        target = None
        while time.monotonic() < deadline:
            if page.locator('input[name="clientUserId"]').filter(visible=True).count():
                raise ValueError('系统要求选择委托人，请在浏览器中确认后重新查看；工具不会代选身份')
            candidates = []
            for candidate_page in page.context.pages:
                for candidate in candidate_page.frames:
                    try:
                        if not self._task_frame(candidate, task_id, origin):
                            continue
                        if candidate.parent_frame and not candidate.frame_element().is_visible():
                            continue
                        selector = 'input#subject' if system == 'new' else self.config.get('approval', {}).get('approve_button_selector', '')
                        if selector and candidate.locator(selector).filter(visible=True).count() == 1:
                            candidates.append(candidate)
                    except Exception:
                        continue
            if len(candidates) > 1:
                raise ValueError('发现多个匹配的详情页，请关闭重复详情后重试')
            if len(candidates) == 1:
                target = candidates[0]
                break
            page.wait_for_timeout(100)
        if target is None:
            raise ValueError('未找到任务编号匹配且已就绪的详情页，未执行审批；请检查委托人弹窗、页面加载或选择器')
        helper = ApprovalHelper(self.browser, self.config, log_callback=self.log, oa_type=system)
        # Keep fallback extraction inside the verified task, not the portal's other tabs.
        helper.main_page = target
        records = helper.extract_current_page(target)
        if not any(str(record.get('事项名称', '')).strip() for record in records):
            raise ValueError('详情页未提取到事项名称，不能把空数据当作项目概况')
        if not self._task_frame(target, task_id, origin):
            raise ValueError('提取期间页面任务发生变化，结果已丢弃')
        self.detail_frame, self.portal_page, self.origin = target, page, origin
        return {'task_id': task_id, 'title': item['title'], 'system': system,
                'records': records, 'read_only': True,
                'note': '仅返回现有规则提取的字段；未读取附件全文，未审批、未登记。打开页面可能产生已读记录。'}
