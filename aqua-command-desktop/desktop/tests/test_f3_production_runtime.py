"""Passive SQLite stage evidence must never imply a remote read or delivery."""
import sqlite3
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from f3_runtime import RuntimeEvidence, read_snapshot
from opcua_storage import DurableStorage


class TestF3RuntimeEvidence(unittest.TestCase):
    def setUp(self):
        profile = tempfile.TemporaryDirectory()
        self.addCleanup(profile.cleanup)
        self.path = Path(profile.name) / "state.db"
        self.storage = DurableStorage(self.path)

    def insert_observation(self):
        with sqlite3.connect(self.path) as conn:
            conn.execute("INSERT INTO tag_observations(tag_name, quality, arrival_timestamp) VALUES ('LAB.Level', 'GOOD', datetime('now'))")

    def test_missing_database_is_not_created(self):
        missing = self.path.parent / "absent.db"
        self.assertFalse(read_snapshot(missing)["available"])
        self.assertFalse(missing.exists())

    def test_initial_history_emits_no_pulses_new_commit_emits_one_finite_pulse(self):
        self.insert_observation()
        model = RuntimeEvidence()
        model.accept(read_snapshot(self.path), now=10)
        self.assertEqual(model.active(now=10), [])
        self.insert_observation()
        model.accept(read_snapshot(self.path), now=11)
        self.assertEqual([p["stage"] for p in model.active(now=11.2)], ["storage"])
        self.assertEqual(model.active(now=13), [])
        self.assertEqual(model.snapshot["counts"]["storage"], 2)

    def test_failed_or_missing_snapshot_clears_pulses_and_never_replays_history(self):
        model = RuntimeEvidence()
        model.accept(read_snapshot(self.path), now=0)
        self.insert_observation()
        model.accept(read_snapshot(self.path), now=1)
        self.assertTrue(model.active(now=1))
        model.accept({"available": False, "error": "locked"}, now=1.1)
        self.assertEqual(model.active(now=1.1), [])
        model.accept(read_snapshot(self.path), now=2)
        self.assertEqual(model.active(now=2), [])

    def test_stale_and_disconnected_read_never_emits_success_pulse(self):
        model = RuntimeEvidence()
        model.emit_read("a", "read-1", connected=True, fresh=False, now=1)
        model.emit_read("a", "read-2", connected=False, fresh=True, now=1)
        self.assertEqual(model.active(now=1), [])
        model.emit_read("a", "read-3", connected=True, fresh=True, now=1)
        self.assertEqual(len(model.active(now=1)), 1)
        model.clear_source("a")
        self.assertEqual(model.active(now=1), [])

    def test_mock_success_is_labelled_synthetic_and_payload_secrets_are_not_exposed(self):
        with sqlite3.connect(self.path) as conn:
            conn.execute("INSERT INTO task_events(event_id, task_id, task_name, tag_name, trigger_type, severity, created_at) VALUES ('e', 't', 'Test', 'LAB.Level', 'above', 'INFO', datetime('now'))")
            conn.execute("INSERT INTO notification_outbox(outbox_id, event_id, channel, payload, created_at) VALUES ('o', 'e', 'mock_relay', '{\"bot_token\": \"private\"}', datetime('now'))")
            conn.execute("INSERT INTO delivery_attempts(outbox_id, attempt_time, status, http_status, response_body) VALUES ('o', datetime('now'), 'SUCCESS', 200, '{\"ok\":true}')")
        snapshot = read_snapshot(self.path)
        self.assertEqual(snapshot["delivery_state"], "SYNTHETIC_DEMO")
        self.assertNotIn("private", repr(snapshot))
        self.assertNotIn("response_body", repr(snapshot))
        self.assertEqual(snapshot["origin"], "UNBOUND_LOCAL_RUNTIME")


if __name__ == "__main__":
    unittest.main()
