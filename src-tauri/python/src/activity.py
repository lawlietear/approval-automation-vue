"""Machine-local activity journal. Recovery never invokes approval code."""
from contextlib import contextmanager
from datetime import datetime
import hashlib
import json
import os
from pathlib import Path
import sqlite3
import uuid


CHANNELS = ('Obsidian', '企业微信')


class Activity:
    def __init__(self, config_path):
        self.path = Path(config_path).with_name('activity.sqlite3')
        with self.connect() as db:
            db.execute('CREATE TABLE IF NOT EXISTS activity (id TEXT PRIMARY KEY, created TEXT, payload TEXT)')

    @contextmanager
    def connect(self):
        db = sqlite3.connect(self.path, timeout=5)
        try:
            with db:
                yield db
        finally:
            db.close()

    @contextmanager
    def lock(self):
        # All runner entry points share this OS lock, including manual recovery.
        with self.path.with_suffix('.lock').open('a+b') as handle:
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
                raise ValueError('已有审批、补登或诊断在运行，请稍后重试') from exc
            try:
                yield
            finally:
                handle.seek(0)
                if os.name == 'nt':
                    msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
                else:
                    fcntl.flock(handle, fcntl.LOCK_UN)

    def save(self, item):
        item['revision'] = uuid.uuid4().hex
        with self.connect() as db:
            db.execute('INSERT OR REPLACE INTO activity VALUES (?, ?, ?)',
                       (item['id'], item['created'], json.dumps(item, ensure_ascii=False)))

    def begin(self, system, department='', task_id=''):
        item = dict(id=uuid.uuid4().hex, created=datetime.now().astimezone().isoformat(),
                    system=system, department=department, task_id=task_id, approval='unknown',
                    note='审批运行中或曾被中断，结果需核实；不要重复审批。', records=[])
        self.save(item)
        return item

    def get(self, item_id):
        with self.connect() as db:
            row = db.execute('SELECT payload FROM activity WHERE id=?', (item_id,)).fetchone()
        if not row:
            raise ValueError('处理记录不存在，请刷新')
        return json.loads(row[0])

    def recent(self, offset=0):
        with self.connect() as db:
            rows = db.execute('SELECT payload FROM activity ORDER BY created DESC, id DESC LIMIT 21 OFFSET ?',
                              (max(0, offset),)).fetchall()
        return {'items': [json.loads(row[0]) for row in rows[:20]], 'has_more': len(rows) > 20}

    @staticmethod
    def destination(registration, channel):
        target = registration.webhook.url if channel == '企业微信' else os.path.normcase(
            os.path.abspath(registration.settings.get('obsidian_directory', '')))
        return hashlib.sha256(target.encode('utf-8')).hexdigest()

    def add_records(self, item, records, registration):
        for data in records:
            states = {}
            for channel, key in (('Obsidian', 'obsidian_enabled'), ('企业微信', 'wechat_enabled')):
                states[channel] = dict(state='pending' if registration.settings[key] else 'disabled',
                                       detail='', attempts=0, target=self.destination(registration, channel))
            item['records'].append(dict(data=dict(data), channels=states))
        self.save(item)

    def send(self, item, index, channel, registration):
        entry = item['records'][index]
        state = entry['channels'][channel]
        if state['state'] not in ('pending', 'failed'):
            raise ValueError('该通道已完成、已关闭或结果待核实，禁止重复发送')
        if state['target'] != self.destination(registration, channel):
            raise ValueError('登记目标已变更；请恢复原链接或目录后补登，避免写错位置')
        state.update(state='sending', detail='请求已开始；如发生中断，先核实目标中是否已登记。',
                     attempts=state['attempts'] + 1)
        self.save(item)  # Persist uncertainty BEFORE any external side effect.
        outcome = registration.send_channel(entry['data'], channel, item['created'])
        state.update(outcome)
        self.save(item)
        label = {'success': '成功', 'failed': '未完成', 'unknown': '结果待核实'}.get(state['state'], '结果待核实')
        registration.log(f"{channel}登记{label}" + (f"：{state['detail']}" if state['detail'] else ''),
                         'info' if state['state'] == 'success' else 'error')
        return state['state'] == 'success'

    def submit_record(self, item, index, registration):
        result = {}
        for channel in CHANNELS:
            state = item['records'][index]['channels'][channel]['state']
            if state == 'disabled':
                continue
            result[channel] = self.send(item, index, channel, registration)
        return result

    def recover(self, item_id, index, channel, revision, action, registration=None):
        item = self.get(item_id)
        if item['revision'] != revision:
            raise ValueError('记录已变化，请刷新后重新核实')
        if channel not in CHANNELS or index < 0 or index >= len(item['records']):
            raise ValueError('登记通道或记录序号无效')
        state = item['records'][index]['channels'][channel]
        if state['target'] != self.destination(registration, channel):
            raise ValueError('登记目标已变更，请恢复原目标后核实或补登')
        if action == 'retry':
            if item['approval'] not in ('confirmed', 'flow_returned'):
                raise ValueError('审批结果未确认，不允许补登')
            self.send(item, index, channel, registration)
        elif action in ('received', 'absent'):
            if state['state'] not in ('unknown', 'sending'):
                raise ValueError('仅待核实通道可以人工确认，请刷新')
            state.update(state='success' if action == 'received' else 'failed',
                         detail='用户已核实目标中存在此记录' if action == 'received' else '用户已核实目标中没有此记录，可单独补登',
                         resolved_at=datetime.now().astimezone().isoformat())
            self.save(item)
        else:
            raise ValueError('不支持的处理动作')
        return item
