import tempfile
import unittest
from contextlib import closing
from pathlib import Path

from opcua_storage import DurableStorage, StoredObservation
from task_engine import TaskEngine


class TaskAlertAtomicityTests(unittest.TestCase):
    def test_failed_outbox_insert_does_not_advance_task_or_report_an_event(self):
        with tempfile.TemporaryDirectory() as private:
            storage = DurableStorage(Path(private) / "lab.db")
            engine = TaskEngine(storage)
            engine.load_tasks([{"id": "lab", "tags": ["LAB.TAG"], "threshold": 5, "recipient": "test"}])
            observations = {"LAB.TAG": StoredObservation("LAB.TAG", 9, "", "GOOD")}
            with closing(storage._get_connection()) as conn:
                conn.execute("""CREATE TRIGGER reject_lab_job BEFORE INSERT ON notification_outbox
                    BEGIN SELECT RAISE(ABORT, 'test outbox failure'); END""")
                conn.commit()

            self.assertEqual(engine.evaluate_observations(observations), [])
            self.assertIsNone(storage.get_runtime_state("lab"))
            self.assertEqual(storage.get_stats()["events_count"], 0)
            self.assertEqual(storage.get_pending_outbox_items(), [])

            with closing(storage._get_connection()) as conn:
                conn.execute("DROP TRIGGER reject_lab_job")
                conn.commit()
            event, = engine.evaluate_observations(observations)
            self.assertEqual(storage.get_stats()["events_count"], 1)
            self.assertEqual(storage.get_pending_outbox_items()[0].event_id, event.event_id)
            self.assertEqual(storage.get_runtime_state("lab").active_state, 1)
            self.assertEqual(engine.evaluate_observations(observations), [])
