import hashlib
import json
import sqlite3
import tempfile
import time
import unittest
from pathlib import Path

from observability.contract import Contract, iso
from observability.history import History
from opcua_storage import DurableStorage


class HistoryTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.path = Path(self.tmp.name) / "owned.db"
        self.owner = DurableStorage(self.path)
        self.now = time.time()
        self.contract = Contract(b"k" * 32)
        self.reader = History(self.path, self.contract)

    def populate(self):
        db = sqlite3.connect(self.path)
        self.addCleanup(db.close)
        with db:
            for q, value, stamp in (("GOOD", 0, self.now), ("BAD", 42, self.now - 1), ("GOOD", 8, self.now - 700000)):
                db.execute("INSERT INTO tag_observations(tag_name,value,unit,quality,arrival_timestamp) VALUES(?,?,?,?,?)",
                           ("PRIVATE_TAG", value, "m", q, iso(stamp)))
            for event, channel in (("real", "telegram"), ("synthetic", "mock_relay")):
                db.execute("INSERT INTO task_events(event_id,task_id,task_name,tag_name,trigger_type,severity,created_at) VALUES(?,?,?,?,?,?,?)",
                           (event, "PRIVATE_TASK", "SECRET_NAME", "PRIVATE_TAG", "threshold_high", "WARNING", iso(self.now)))
                db.execute("INSERT INTO notification_outbox(outbox_id,event_id,channel,recipient,payload,status,created_at) VALUES(?,?,?,?,?,?,?)",
                           (event, event, channel, "SECRET_RECIPIENT", "SECRET_PAYLOAD", "SENT", iso(self.now)))
            for offset in (1, 0):
                db.execute("INSERT INTO delivery_attempts(outbox_id,attempt_time,status,http_status,response_body,error_message) VALUES(?,?,?,?,?,?)",
                           ("real", iso(self.now - offset), "SUCCESS", 200, "SECRET_RESPONSE", "SECRET_ERROR"))

    def test_bounded_sanitized_history_does_not_write_owner(self):
        self.populate()
        before = hashlib.sha256(self.path.read_bytes()).hexdigest()
        result = self.reader.read("7d", now=self.now)
        self.assertEqual(result["stream"], "RUNTIME")
        self.assertEqual(result["state"], "AVAILABLE")
        self.assertEqual(len(result["observations"]), 2)
        self.assertEqual(result["observations"][0]["value"], None)
        self.assertEqual(result["observations"][1]["value"], 0)
        self.assertEqual(result["observations"][1]["provenance"], "UNBOUND_LOCAL_RUNTIME")
        self.assertEqual(len(result["events"]), 1)
        self.assertEqual(len(result["outbox"]), 1)
        self.assertEqual(result["outbox"][0]["acknowledgement_state"], "UNVERIFIED")
        text = json.dumps(result)
        self.assertNotIn("SECRET", text)
        self.assertNotIn("PRIVATE", text)
        self.assertNotIn("synthetic", text)
        self.assertEqual(before, hashlib.sha256(self.path.read_bytes()).hexdigest())

    def test_attempt_count_is_not_retry_count(self):
        self.populate()
        item = self.reader.read(now=self.now)["outbox"][0]
        self.assertEqual(item["attempt_count"], 2)
        self.assertEqual(item["last_attempt_at"], iso(self.now))

    def test_explicit_grafana_range_uses_selected_past_interval(self):
        base = int(self.now)
        with sqlite3.connect(self.path) as db:
            for age, value in ((7200, 12), (0, 99)):
                db.execute("INSERT INTO tag_observations(tag_name,value,unit,quality,arrival_timestamp) VALUES(?,?,?,?,?)",
                    ("PRIVATE_TAG", value, "m", "GOOD", iso(base - age)))
        result = self.reader.read(start_ms=(base - 10800) * 1000, end_ms=(base - 3600) * 1000, now=self.now)
        self.assertEqual([row["value"] for row in result["observations"]], [12])
        self.assertEqual(result["range_start"], iso(base - 10800))
        self.assertEqual(result["range_end"], iso(base - 3600))
        for arguments in ({"start_ms": 1}, {"start_ms": 2, "end_ms": 1},
                {"start_ms": 1, "end_ms": 700000001}, {"start_ms": "bad", "end_ms": 3},
                {"start_ms": base * 1000, "end_ms": (base + 10) * 1000}):
            with self.subTest(arguments=arguments), self.assertRaises(ValueError):
                self.reader.read(now=self.now, **arguments)

    def test_tag_filter_applies_before_observation_limit(self):
        with sqlite3.connect(self.path) as db:
            db.execute("INSERT INTO tag_observations(tag_name,value,unit,quality,arrival_timestamp) VALUES(?,?,?,?,?)",
                ("TARGET_TAG", 42, "m", "GOOD", iso(self.now - 30)))
            db.executemany("INSERT INTO tag_observations(tag_name,value,unit,quality,arrival_timestamp) VALUES(?,?,?,?,?)",
                [("OTHER_TAG", i, "m", "GOOD", iso(self.now - 1)) for i in range(2000)])
        result = self.reader.read(tag_id=self.contract.identity("tag", "TARGET_TAG"), now=self.now)
        self.assertEqual([row["value"] for row in result["observations"]], [42])

    def test_empty_missing_corrupt_and_invalid_window(self):
        self.assertEqual(self.reader.read(now=self.now)["observations"], [])
        absent = Path(self.tmp.name) / "absent.db"
        self.assertEqual(History(absent, self.contract).read()["state"], "NO_DATA")
        self.assertFalse(absent.exists())
        with self.assertRaises(ValueError):
            self.reader.read("all")
        bad = Path(self.tmp.name) / "bad.db"
        bad.write_text("not a SQLite database")
        self.assertEqual(History(bad, self.contract).read()["state"], "ERROR")

    def test_sqlite_dynamic_type_does_not_leak_a_message_in_http_status(self):
        self.populate()
        with sqlite3.connect(self.path) as db:
            db.execute("UPDATE delivery_attempts SET http_status='SECRET_STATUS'")
        result = self.reader.read(now=self.now)
        self.assertNotIn("SECRET", json.dumps(result))
        self.assertTrue(all(row["http_status"] is None for row in result["attempts"]))


if __name__ == "__main__":
    unittest.main()
