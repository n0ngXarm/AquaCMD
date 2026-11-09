import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from collector.probe_once import EvidenceStore
from tools.sim.f3_demo_delivery import DeliveryError, finish_delivery, queue_example, send_message


class DemoTaskGroupTest(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.store = EvidenceStore(Path(temporary.name) / 'demo.db')
        self.addCleanup(self.store.close)
        self.tasks = [
            {'id': 'A', 'name': 'ระดับน้ำ', 'tags': ['DemoWaterLevel'], 'threshold': 70},
            {'id': 'B', 'name': 'เฝ้าระวังถัง', 'tags': ['DemoWaterLevel'], 'threshold': 72},
            {'id': 'C', 'name': 'สัญญาณอื่น', 'tags': ['OtherTag'], 'threshold': 60},
        ]
        self.expected_groups = [{key: task[key] for key in ('id', 'name')} for task in self.tasks[:2]]

    def record_read(self, value):
        detail = {'tag': 'DemoWaterLevel', 'value': value, 'quality': 'Good'}
        return self.store.record_read('127.0.0.1', 'DemoWaterLevel', 'ns=2;s=DemoWaterLevel',
                                      ('ok', None, 0, detail), value, 'Good', source='sim')

    def test_only_matching_task_groups_follow_one_queued_message_and_receipt(self):
        read = self.record_read(73.25)
        message = queue_example(self.store, read, self.tasks, '%')
        self.assertIn('ระดับน้ำ', message)
        self.assertIn('เฝ้าระวังถัง', message)
        self.assertNotIn('สัญญาณอื่น', message)
        self.assertEqual(self.store.connection.execute('SELECT COUNT(*) FROM demo_outbox').fetchone()[0], 1)
        self.tasks[0]['name'] = 'เปลี่ยนชื่อหลังเข้าคิว'
        receipt = finish_delivery(self.store, read['id'], 0, message_id=123)
        self.assertEqual(json.loads(receipt['detail'])['message_id'], 123)
        stages = self.store.connection.execute('SELECT * FROM probe_evidence WHERE id>? ORDER BY id',
                                              (read['id'],)).fetchall()
        self.assertEqual([stage['host'] for stage in stages], ['task', 'outbox', 'relay', 'tg'])
        for stage in stages:
            detail = json.loads(stage['detail'])
            self.assertEqual(detail['read_evidence_id'], read['id'])
            self.assertEqual(detail['task_groups'], self.expected_groups)
            self.assertEqual(stage['source'], 'sim')

    def test_unconfirmed_delivery_keeps_the_queued_groups(self):
        read = self.record_read(73.25)
        queue_example(self.store, read, self.tasks, '%')
        receipt = finish_delivery(self.store, read['id'], 0, error='ไม่มีใบยืนยัน')
        self.assertEqual(receipt['result'], 'ERROR')
        self.assertEqual(json.loads(receipt['detail'])['task_groups'], self.expected_groups)
        self.assertEqual(self.store.connection.execute('SELECT state FROM demo_outbox').fetchone()[0], 'unconfirmed')

    def test_no_threshold_match_does_not_queue(self):
        read = self.record_read(69)
        self.assertIsNone(queue_example(self.store, read, self.tasks, '%'))
        self.assertIsNone(self.store.connection.execute(
            "SELECT name FROM sqlite_master WHERE name='demo_outbox'").fetchone())


class TelegramReceiptTest(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.config = Path(temporary.name) / 'telegram.json'
        self.config.write_text(json.dumps({'enabled': True, 'bot_token': '1:fixture', 'chat_id': '1'}))
        constructor = patch('tools.sim.f3_demo_delivery.http.client.HTTPSConnection')
        self.connection = constructor.start().return_value
        self.addCleanup(constructor.stop)
        self.response = self.connection.getresponse.return_value
        self.response.status = 200

    def test_success_requires_telegram_message_id(self):
        self.response.read.return_value = b'{"ok":true,"result":{"message_id":123}}'
        self.assertEqual(send_message(self.config, '[SIMULATED] sample'), 123)
        self.connection.request.assert_called_once()

    def test_http_success_without_bot_receipt_is_failure(self):
        self.response.read.return_value = b'{"ok":false}'
        with self.assertRaisesRegex(DeliveryError, 'ไม่คืนรหัสข้อความ'):
            send_message(self.config, '[SIMULATED] sample')

    def test_connect_failure_never_posts(self):
        self.connection.connect.side_effect = TimeoutError()
        with self.assertRaisesRegex(DeliveryError, 'ยังไม่ได้ส่งข้อความ'):
            send_message(self.config, '[SIMULATED] sample')
        self.connection.request.assert_not_called()

    def test_response_timeout_does_not_retry(self):
        self.connection.getresponse.side_effect = TimeoutError()
        with self.assertRaisesRegex(DeliveryError, 'อาจส่งถึงแล้ว'):
            send_message(self.config, '[SIMULATED] sample')
        self.connection.request.assert_called_once()
