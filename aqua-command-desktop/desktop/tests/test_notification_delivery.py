"""Durable delivery state regression with an isolated loopback HTTP destination."""
import os
import tempfile
import threading
import unittest
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from unittest.mock import patch

from notification_worker import NotificationWorker
from opcua_storage import DurableStorage, TaskEvent


class DeliveryStateTests(unittest.TestCase):
    def setUp(self):
        private = tempfile.TemporaryDirectory()
        self.addCleanup(private.cleanup)
        self.storage = DurableStorage(Path(private.name) / "lab.db")
        self.event = TaskEvent("lab-event", "lab-task", "LAB", "LAB.TAG",
                               "threshold_above", 10.0, 5.0, "LAB synthetic event")
        self.storage.record_event_and_enqueue_outbox(self.event, [("telegram", "123", {})])
        self.item = self.storage.get_pending_outbox_items()[0]

    def test_response_lost_after_request_keeps_job_and_does_not_repeat(self):
        requests = []
        storage = self.storage

        class Sink(BaseHTTPRequestHandler):
            def do_POST(self):
                self.rfile.read(int(self.headers["Content-Length"]))
                with storage._get_connection() as conn:
                    status = conn.execute("SELECT status FROM notification_outbox").fetchone()[0]
                requests.append(status)
                self.close_connection = True

            def log_message(self, *_):
                pass

        with HTTPServer(("127.0.0.1", 0), Sink) as server:
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()
            try:
                worker = NotificationWorker(self.storage, mock_endpoint_url=f"http://127.0.0.1:{server.server_port}")
                worker._process_outbox_item(self.item)
                self.assertEqual(requests, ["SENDING"])
                self.assertEqual(self.storage.get_stats()["outbox_delivery_unknown"], 1)
                self.assertEqual(self.storage.get_pending_outbox_items(), [])
                self.assertEqual(self.storage.recover_uncommitted_outbox(), 0)
                worker._process_outbox_item(self.item)
                self.assertEqual(requests, ["SENDING"])
            finally:
                server.shutdown()
                thread.join()

    def test_restart_holds_interrupted_job_without_losing_id(self):
        self.assertTrue(self.storage.mark_outbox_sending(self.item.outbox_id))
        self.assertEqual(self.storage.recover_uncommitted_outbox(), 1)
        self.assertEqual(self.storage.get_pending_outbox_items(), [])
        with self.storage._get_connection() as conn:
            row = conn.execute("SELECT outbox_id, status FROM notification_outbox").fetchone()
        self.assertEqual(tuple(row), (self.item.outbox_id, "DELIVERY_UNKNOWN"))

    def test_legacy_exhausted_job_is_held_during_recovery(self):
        with self.storage._get_connection() as conn:
            conn.execute("UPDATE notification_outbox SET status='FAILED', retry_count=5")
            conn.commit()
        self.assertEqual(self.storage.recover_uncommitted_outbox(), 1)
        self.assertEqual(self.storage.get_pending_outbox_items(), [])
        self.assertEqual(self.storage.get_stats()["outbox_delivery_unknown"], 1)

    def test_laboratory_default_prevents_external_dispatch(self):
        with patch.dict(os.environ, {}, clear=True):
            worker = NotificationWorker(self.storage)
            with patch.object(worker._opener, "open") as dispatch:
                worker._process_outbox_item(self.item)
                dispatch.assert_not_called()
        with self.storage._get_connection() as conn:
            status = conn.execute("SELECT status FROM notification_outbox").fetchone()[0]
        self.assertEqual(status, "BLOCKED_BY_POLICY")
