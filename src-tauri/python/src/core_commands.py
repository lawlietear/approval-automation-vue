"""Confirmed, single-task core approvals; durable attempts are never auto-retried."""
from contextlib import contextmanager
import hashlib
import json
import os
from pathlib import Path
import sqlite3
import time
import uuid
from urllib.parse import urlsplit

from .approver import ApprovalHelper


def fingerprint(value):
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True).encode('utf-8')).hexdigest()


class CoreCommands:
    def __init__(self, reader, registration, configuration, directory=None):
        self.reader, self.registration = reader, registration
        self.configuration = fingerprint(configuration)
        self.directory = Path(directory) if directory else Path(os.environ['LOCALAPPDATA']) / 'com.yourcompany.approvaltool' / 'LocalCommands'
        self.directory.mkdir(parents=True, exist_ok=True)
        self.db_path = self.directory / 'approvals.sqlite3'
        with self.connect() as db:
            db.execute('CREATE TABLE IF NOT EXISTS reviews (token TEXT PRIMARY KEY, created REAL, task TEXT, origin TEXT, config TEXT, snapshot TEXT)')
            db.execute('CREATE TABLE IF NOT EXISTS attempts (origin TEXT, task TEXT, result TEXT, PRIMARY KEY(origin, task))')

    @contextmanager
    def connect(self):
        db = sqlite3.connect(self.db_path, timeout=2)
        try:
            with db:
                yield db
        finally:
            db.close()

    @contextmanager
    def lock(self):
        # OS lock is released on process exit; the durable attempt still blocks retries.
        with (self.directory / 'command.lock').open('a+b') as handle:
            if handle.tell() == 0:
                handle.write(b'0')
                handle.flush()
            handle.seek(0)
            try:
                if os.name == 'nt':
                    import msvcrt
                    msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
                else:
                    import fcntl
                    fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except OSError as exc:
                raise ValueError('另一个本地命令正在运行，请勿并发操作浏览器') from exc
            try:
                yield
            finally:
                handle.seek(0)
                if os.name == 'nt':
                    msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
                else:
                    fcntl.flock(handle, fcntl.LOCK_UN)

    @staticmethod
    def snapshot(result):
        return {key: result[key] for key in ('task_id', 'title', 'system', 'records')}

    def review(self, task_id):
        result = self.reader.view_task(task_id, 'old')
        token = uuid.uuid4().hex
        origin = '://'.join(self.reader.origin)
        with self.connect() as db:
            db.execute('INSERT INTO reviews VALUES (?, ?, ?, ?, ?, ?)',
                       (token, time.time(), task_id, origin, self.configuration,
                        json.dumps(self.snapshot(result), ensure_ascii=False, sort_keys=True)))
        return dict(result, review_token=token, review_expires_in=900)

    def get_review(self, task_id, token):
        with self.connect() as db:
            row = db.execute('SELECT created, task, origin, config, snapshot FROM reviews WHERE token=?', (token,)).fetchone()
        if not row or row[1] != task_id:
            raise ValueError('查看凭证不存在或不属于指定任务，请重新 view')
        return row

    def status(self, task_id, token):
        review = self.get_review(task_id, token)
        with self.connect() as db:
            row = db.execute('SELECT result FROM attempts WHERE origin=? AND task=?', (review[2], task_id)).fetchone()
        return json.loads(row[0]) if row else {'task_id': task_id, 'approval': 'not_started', 'registration': []}

    def save(self, origin, task_id, result, create=False):
        with self.connect() as db:
            payload = json.dumps(result, ensure_ascii=False)
            if create:
                try:
                    db.execute('INSERT INTO attempts VALUES (?, ?, ?)', (origin, task_id, payload))
                except sqlite3.IntegrityError as exc:
                    raise ValueError('该任务已有审批尝试记录，禁止重复审批；请使用 status 核实') from exc
            else:
                db.execute('UPDATE attempts SET result=? WHERE origin=? AND task=?', (payload, origin, task_id))

    def guard(self, task_id):
        reader = self.reader
        if not reader._task_frame(reader.detail_frame, task_id, reader.origin):
            raise ValueError('当前详情任务已变化，停止后续操作')
        page = reader.portal_page
        if urlsplit(page.url).path != '/amcs/index.htm' or reader.detail_frame.page != page:
            raise ValueError('审批命令仅支持核心首页内的已核验详情标签')
        valid = page.evaluate("""id => {
          const tabs = [...document.querySelectorAll('#tab-con li.active')];
          if (tabs.length !== 1 || tabs[0].getAttribute('tabid') !== 'MSG_' + id
              || tabs[0].getAttribute('title') !== '待办事宜处理') return false;
          const url = new URL(tabs[0].getAttribute('url') || '', location.href);
          return url.origin === location.origin && url.pathname === '/amcs/bpm/client/mw/open'
            && JSON.stringify(url.searchParams.getAll('taskId')) === JSON.stringify([id]);
        }""", task_id)
        if not valid:
            raise ValueError('当前激活的核心详情标签与任务编号不匹配')
        for frame in page.frames:
            if frame.locator('input[name="clientUserId"]').filter(visible=True).count():
                raise ValueError('检测到委托身份选择，停止自动操作')

    def verify_removed(self, task_id):
        page = self.reader.portal_page
        # A fresh complete list is required; a stale tab disappearing is not success.
        page.reload(wait_until='domcontentloaded', timeout=15000)
        self.reader.page_url = page.url
        deadline = time.monotonic() + 15
        while time.monotonic() < deadline:
            try:
                result = self.reader.list_tasks()
                if result['complete']:
                    if any(item['task_id'] == task_id for item in result['items']):
                        return False
                    return True
            except Exception:
                pass
            page.wait_for_timeout(250)
        return False

    def approve(self, task_id, token, confirmed_task_id, quantity='1', business_type=''):
        if confirmed_task_id != task_id or not task_id:
            raise ValueError('必须以 --confirm-task-id 再次明确确认同一个任务编号')
        if str(quantity) not in [str(n) for n in range(1, 11)]:
            raise ValueError('数量必须在 1 到 10 之间')
        review = self.get_review(task_id, token)
        if self.status(task_id, token)['approval'] != 'not_started':
            raise ValueError('该任务已有审批尝试记录，禁止重复审批；请使用 status 核实')
        if time.time() - review[0] > 900 or review[3] != self.configuration:
            raise ValueError('查看凭证已过期或配置已变化，请重新 view 并确认')
        cfg = self.reader.config.get('approval', {})
        if not cfg.get('approve_button_selector') or not cfg.get('final_confirm_button_selector'):
            raise ValueError('缺少同意或最终确认选择器，不能执行命令审批')
        self.registration.validate()
        current = self.reader.view_task(task_id, 'old')
        if '://'.join(self.reader.origin) != review[2] or self.snapshot(current) != json.loads(review[4]):
            raise ValueError('任务来源或已查看字段发生变化，请重新 view 并确认')
        self.guard(task_id)
        frame = self.reader.detail_frame
        button = frame.locator(cfg['approve_button_selector']).filter(visible=True)
        if button.count() != 1 or not button.is_enabled():
            raise ValueError('任务不处于唯一可审批状态')
        records = [dict(record) for record in current['records']]
        for record in records:
            record['数量'] = str(quantity)
            if business_type:
                record['业务类型'] = business_type
        result = {'task_id': task_id, 'approval': 'unknown', 'registration': [], 'records': records,
                  'note': '审批尝试已开始；若进程中断，禁止重试，请人工核实。'}
        self.save(review[2], task_id, result, create=True)
        try:
            helper = ApprovalHelper(self.reader.browser, self.reader.config, log_callback=self.reader.log, oa_type='old')
            helper.main_page = frame
            helper.dialog_page = self.reader.portal_page
            # Extracted fields must remain scoped to the task; global dialogs are used only for clicking.
            helper._process_detail(frame, action_guard=lambda: self.guard(task_id), expected_records=current['records'])
            if not self.verify_removed(task_id):
                raise RuntimeError('未能从刷新后的完整待办确认任务消失，不登记、不自动重试')
            result.update(approval='confirmed', evidence='fresh_complete_pending_list_absent',
                          note='最终确认点击完成且刷新后的完整待办无此任务；不是后台审批回执。')
            self.save(review[2], task_id, result)
            for index, record in enumerate(records):
                result['registration'].append({'index': index, 'channels': self.registration.submit(record)})
                self.save(review[2], task_id, result)
            result['registration_complete'] = len(result['registration']) == len(records) and all(
                all(item['channels'].values()) for item in result['registration'])
        except Exception as exc:
            result['error'] = str(exc)
        self.save(review[2], task_id, result)
        return result
