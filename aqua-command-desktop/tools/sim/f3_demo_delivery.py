"""One Telegram test delivery per explicitly started F3 simulation."""
import http.client
import json
import re
import time
from pathlib import Path

from collector.evidence_api import read_connection
from desktop.f3_projection import F3Projection

STAGES = {'task': 'demo_task', 'outbox': 'demo_outbox',
          'relay': 'demo_relay', 'tg': 'demo_telegram'}


class DeliveryError(Exception):
    pass


def send_message(config_path, text):
    try:
        config = json.loads(Path(config_path).read_text())
    except (OSError, ValueError) as error:
        raise DeliveryError('อ่านการตั้งค่า Telegram ใน F6 ไม่ได้') from error
    if not isinstance(config, dict) or config.get('enabled') is not True:
        raise DeliveryError('เปิดใช้งาน Telegram ใน F6 ก่อนทดสอบส่ง')
    token = config.get('bot_token')
    chat = config.get('chat_id')
    if not isinstance(token, str) or not re.fullmatch(r'[0-9]+:[A-Za-z0-9_-]+', token.strip()):
        raise DeliveryError('Bot Token ใน F6 ไม่ถูกต้อง')
    if not isinstance(chat, str) or not chat.strip():
        raise DeliveryError('กรุณาตั้ง Chat ID ใน F6')

    # Direct HTTPS with certificate validation and no redirect or automatic retry.
    connection = http.client.HTTPSConnection('api.telegram.org', timeout=8)
    try:
        try:
            connection.connect()
        except (OSError, http.client.HTTPException) as error:
            raise DeliveryError('เชื่อมต่อ Telegram ไม่สำเร็จ ยังไม่ได้ส่งข้อความ') from error
        connection.request('POST', '/bot' + token.strip() + '/sendMessage',
                           json.dumps({'chat_id': chat.strip(), 'text': text}).encode(),
                           {'Content-Type': 'application/json'})
        response = connection.getresponse()
        if response.status != 200:
            raise DeliveryError(f'Telegram ตอบ HTTP {response.status}')
        body = json.loads(response.read(65536))
    except (OSError, ValueError, http.client.HTTPException) as error:
        raise DeliveryError('ไม่ได้รับใบยืนยันจาก Telegram อาจส่งถึงแล้ว') from error
    finally:
        connection.close()

    result = body.get('result') if isinstance(body, dict) and body.get('ok') is True else None
    message_id = result.get('message_id') if isinstance(result, dict) else None
    if type(message_id) is not int or message_id <= 0:
        raise DeliveryError('Telegram ไม่คืนรหัสข้อความที่ยืนยันได้')
    return message_id


def record_stage(store, node, result, summary, started, read_id, task_groups, message_id=None, *, commit=True):
    detail = {'summary': summary, 'read_evidence_id': read_id, 'task_groups': task_groups}
    if message_id is not None:
        detail['message_id'] = message_id
    return store.record(node, STAGES[node],
                        (result, None if result == 'ok' else summary,
                         (time.monotonic() - started) * 1000, detail), source='sim', commit=commit)


def queue_example(store, read, tasks, unit):
    started = time.monotonic()
    observation = json.loads(read['detail'])
    tag, value = observation.get('tag'), observation.get('value')
    matched = [task for task in tasks
               if tag in task['tags'] and type(value) in (int, float) and value >= task['threshold']]
    if not matched:
        record_stage(store, 'task', 'ERROR', 'ค่าอ่านไม่เข้าเงื่อนไขตัวอย่าง', started, read['id'], [])
        return None
    task_groups = [{'id': task['id'], 'name': task['name']} for task in matched]
    record_stage(store, 'task', 'ok', f'ค่าตัวอย่าง {value:g}{unit} เข้าเงื่อนไขกลุ่ม Task',
                 started, read['id'], task_groups)
    started = time.monotonic()
    criteria = '\n'.join(f"• {task['name']} · เกณฑ์ {task['threshold']:g}{unit}" for task in matched)
    text = (f'[AQUA COMMAND · SIMULATED]\nข้อความทดสอบจากหน้า F3\n'
            f'ระดับน้ำจำลอง {value:g}{unit}\nกลุ่ม Task ที่เข้าเงื่อนไข\n{criteria}')
    with store.connection:
        store.connection.execute('''CREATE TABLE demo_outbox (
            id INTEGER PRIMARY KEY, read_id INTEGER NOT NULL REFERENCES probe_evidence(id),
            message TEXT NOT NULL, state TEXT NOT NULL, telegram_message_id INTEGER,
            task_groups TEXT NOT NULL)''')
        store.connection.execute('INSERT INTO demo_outbox VALUES (1, ?, ?, ?, NULL, ?)',
                                 (read['id'], text, 'queued', json.dumps(task_groups, ensure_ascii=False)))
        record_stage(store, 'outbox', 'ok', 'บันทึก 1 ข้อความลงคิวตัวอย่าง',
                     started, read['id'], task_groups, commit=False)
    return text


def finish_delivery(store, read_id, started, message_id=None, error=None):
    with store.connection:
        queued = store.connection.execute('SELECT task_groups FROM demo_outbox WHERE read_id=? AND state=?',
                                          (read_id, 'queued')).fetchone()
        if queued is None:
            raise ValueError('ไม่พบข้อความจำลองในคิวสำหรับผลอ่านนี้')
        task_groups = json.loads(queued['task_groups'])
        status = 'ok' if message_id is not None else 'ERROR'
        store.connection.execute('UPDATE demo_outbox SET state=?, telegram_message_id=? WHERE read_id=?',
                                 ('sent' if status == 'ok' else 'unconfirmed', message_id, read_id))
        record_stage(store, 'relay', status, 'Telegram Bot API ตอบรับ' if message_id else error,
                     started, read_id, task_groups, message_id, commit=False)
        row = record_stage(store, 'tg', status, f'Telegram ยืนยันข้อความ #{message_id}' if message_id else error,
                           started, read_id, task_groups, message_id, commit=False)
    return row


class DemoProjection(F3Projection):
    def f3_evidence(self):
        snapshot = super().f3_evidence()
        snapshot['demo_delivery'] = True
        with read_connection(self.reader.path) as db:
            for node in snapshot['nodes']:
                method = STAGES.get(node['id'])
                if not method:
                    continue
                node['built'] = True
                row = db.execute('''SELECT * FROM probe_evidence WHERE host=? AND "check"=?
                    AND source='sim' AND id<=? ORDER BY id DESC LIMIT 1''',
                                 (node['id'], method, snapshot['last_event_id'])).fetchone()
                if row:
                    detail = json.loads(row['detail'])
                    node['last'] = {'id': row['id'], 'ok': row['result'] == 'ok', 'ts': row['ts'],
                                    'method': method, 'source': 'sim',
                                    'read_evidence_id': detail.get('read_evidence_id'),
                                    'task_groups': detail.get('task_groups', []),
                                    'detail': f"{detail['summary']} · {row['latency_ms']:.0f} ms"}
        return snapshot
