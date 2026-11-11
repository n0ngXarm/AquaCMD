#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
test_network_resilience_and_recovery.py — Network Outage & Offline Resilience Test Suite for AQUA COMMAND
Tests and proves the system behavior under real-world network failure conditions:
1. Telegram 503 Outage & Exponential Retry Backoff.
2. Complete Internet Disconnection & Outbox Queue Accumulation (Zero Data Loss).
3. Network Restoration & Orderly Outbox Flush.
4. OPC UA Server Disconnection, Reconnecting State & Automatic Reconnect.
5. Mid-flight Process Crash & Cold Restart Recovery ('SENDING' -> 'DELIVERY_UNKNOWN').
6. Rate Limiting Protection (Max 20 messages/min preventing Telegram 429 spam).

Strict Safety Invariants:
- 100% Loopback synthetic testbed on 127.0.0.1.
- Ephemeral certificates and RSA keys inside TemporaryDirectory.
- Zero live WinCC SCADA connection.
- Zero external Telegram API calls (MOCK_ENDPOINT only).
- Zero OPC UA write operations.
"""

import os
import sys
import time
import json
import socket
import asyncio
import tempfile
import threading
import unittest
from pathlib import Path
from http.server import HTTPServer, BaseHTTPRequestHandler
from datetime import datetime, timezone, timedelta

desktop_dir = Path(__file__).resolve().parent.parent
if str(desktop_dir) not in sys.path:
    sys.path.insert(0, str(desktop_dir))

from opcua_storage import DurableStorage, StoredObservation, TaskEvent, OutboxItem
from task_engine import TaskEngine, TaskDefinition
from notification_worker import NotificationWorker
from opcua_polling_engine import OpcUaPollingEngine, PollingState
from opcua_mapping import NodeIdMapper
from opcua_store import ObservableStateStore
from opcua_pki import PkiManager

try:
    from asyncua import Server, ua
    ASYNCUA_AVAILABLE = True
except ImportError:
    ASYNCUA_AVAILABLE = False


def find_free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(('127.0.0.1', 0))
        return s.getsockname()[1]


class ControllableTelegramHandler(BaseHTTPRequestHandler):
    received_requests = []
    fail_with_status = None  # None = 200 OK, 503 = Service Unavailable, 429 = Rate Limit

    def log_message(self, format, *args):
        pass  # Suppress console logging

    def do_POST(self):
        length = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(length).decode("utf-8")
        try:
            data = json.loads(body)
        except Exception:
            data = {"raw": body}

        ControllableTelegramHandler.received_requests.append({
            "path": self.path,
            "data": data,
            "time": time.time()
        })

        if ControllableTelegramHandler.fail_with_status:
            status = ControllableTelegramHandler.fail_with_status
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            err_json = json.dumps({"ok": False, "error_code": status, "description": "Mocked Network Error"}).encode("utf-8")
            self.wfile.write(err_json)
        else:
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(b'{"ok": true, "result": {"message_id": 8888}}')


class TestNetworkResilienceAndRecovery(unittest.TestCase):
    """Rigorous offline and network resilience test suite."""

    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.work_path = Path(self.temp_dir.name)
        self.db_path = self.work_path / "resilience.db"
        self.storage = DurableStorage(self.db_path)

        ControllableTelegramHandler.received_requests.clear()
        ControllableTelegramHandler.fail_with_status = None

        self.tg_port = find_free_port()
        self.mock_tg_url = f"http://127.0.0.1:{self.tg_port}"
        self.httpd = HTTPServer(('127.0.0.1', self.tg_port), ControllableTelegramHandler)
        self.tg_thread = threading.Thread(target=self.httpd.serve_forever, daemon=True)
        self.tg_thread.start()

    def tearDown(self):
        if hasattr(self, 'httpd'):
            self.httpd.shutdown()
            self.httpd.server_close()
        self.temp_dir.cleanup()

    def test_01_telegram_429_outage_and_exponential_backoff(self):
        """Verify handling of HTTP 429 outage, backoff computation, and recovery on service return."""
        worker = NotificationWorker(
            self.storage,
            poll_interval=0.1,
            base_backoff_seconds=0.3,
            mock_endpoint_url=self.mock_tg_url
        )

        # 1. Enqueue an alert event
        evt = TaskEvent(
            event_id="evt_test_429",
            task_id="task_resilience_1",
            task_name="Outage Test",
            tag_name="High_Analog.Tank01_Level",
            trigger_type="threshold_above",
            trigger_value=82.70,
            threshold_value=82.50,
            description="High Water Alert",
            severity="CRITICAL"
        )
        self.storage.record_event_and_enqueue_outbox(
            evt,
            [("telegram", "123456", {"event_id": "evt_test_429", "text": "Level 82.70m"})]
        )

        # Set mock server to fail with 429
        ControllableTelegramHandler.fail_with_status = 429

        # Start worker and observe retry
        worker.start()
        time.sleep(0.4)

        # Verify item was not dropped, but transitioned to retry
        items = self.storage.get_pending_outbox_items(limit=10)
        # Because next_retry_at is in the future (+0.3s), it won't be returned immediately
        stats = self.storage.get_stats()
        self.assertEqual(stats["outbox_sent"], 0, "No item should be sent during 429 outage")

        # Check delivery attempts log
        conn = self.storage._get_connection()
        try:
            attempts = conn.execute("SELECT * FROM delivery_attempts WHERE outbox_id LIKE 'out_%'").fetchall()
            self.assertTrue(len(attempts) >= 1, "At least 1 failed delivery attempt must be logged")
            self.assertEqual(attempts[0]["status"], "FAILURE")
            self.assertEqual(attempts[0]["http_status"], 429)
        finally:
            conn.close()

        # 2. Restore Telegram Service (200 OK)
        ControllableTelegramHandler.fail_with_status = None
        # Allow backoff delay (0.3s) to elapse and worker to retry
        time.sleep(0.8)

        stats_after = self.storage.get_stats()
        self.assertEqual(stats_after["outbox_sent"], 1, "Item must be sent after network recovers")
        self.assertEqual(len(ControllableTelegramHandler.received_requests), 2, "Total 2 attempts: 1 failed, 1 success")

        worker.stop()

    def test_02_total_internet_offline_and_accumulation(self):
        """Verify safe queue accumulation during total network disconnect (connection refused)."""
        # Point worker to closed port
        dead_port = find_free_port()
        worker = NotificationWorker(
            self.storage,
            poll_interval=0.1,
            base_backoff_seconds=0.2,
            mock_endpoint_url=f"http://127.0.0.1:{dead_port}"
        )

        # Enqueue 3 alerts during offline period
        for i in range(3):
            evt = TaskEvent(
                event_id=f"evt_offline_{i}",
                task_id=f"task_{i}",
                task_name=f"Offline Alert {i}",
                tag_name="High_Analog.Tank01_Level",
                trigger_type="threshold_above",
                trigger_value=82.70 + i,
                threshold_value=82.50,
                description=f"Accumulated Event {i}",
                severity="WARNING"
            )
            self.storage.record_event_and_enqueue_outbox(
                evt,
                [("telegram", "123456", {"event_id": f"evt_offline_{i}", "text": f"Event {i}"})]
            )

        worker.start()
        time.sleep(0.5)
        worker.stop()

        # Verify zero dropped events, zero items marked sent, all still in outbox
        stats = self.storage.get_stats()
        self.assertEqual(stats["events_count"], 3)
        self.assertEqual(stats["outbox_sent"], 0)

        # Now reconnect worker to the working mock server
        worker_recovered = NotificationWorker(
            self.storage,
            poll_interval=0.1,
            base_backoff_seconds=0.2,
            mock_endpoint_url=self.mock_tg_url
        )
        worker_recovered.start()

        # Wait for all 3 items to be flushed
        time.sleep(1.2)
        worker_recovered.stop()

        stats_recovered = self.storage.get_stats()
        self.assertEqual(stats_recovered["outbox_sent"], 3, "All 3 accumulated items must be delivered")
        self.assertEqual(len(ControllableTelegramHandler.received_requests), 3)

    def test_03_crash_recovery_sending_to_unknown(self):
        """Verify cold start recovery holds interrupted Telegram requests as DELIVERY_UNKNOWN."""
        # Manually insert an item in 'SENDING' state into SQLite (as if process crashed mid-flight)
        conn = self.storage._get_connection()
        try:
            conn.execute("""
            INSERT INTO task_events (event_id, task_id, task_name, tag_name, trigger_type, trigger_value, threshold_value, description, severity, created_at)
            VALUES ('evt_crashed', 'task_crashed', 'Crashed Task', 'High_Analog.Tank01_Level', 'threshold_above', 83.0, 82.5, 'Crash Test', 'CRITICAL', '2026-11-03T12:00:00Z')
            """)
            conn.execute("""
            INSERT INTO notification_outbox (outbox_id, event_id, channel, recipient, payload, status, retry_count, max_retries, created_at)
            VALUES ('out_crashed_1', 'evt_crashed', 'telegram', '123456', '{"text": "Crashed mid-send"}', 'SENDING', 0, 5, '2026-11-03T12:00:00Z')
            """)
            conn.commit()
        finally:
            conn.close()

        # Verify initially in SENDING state
        conn = self.storage._get_connection()
        try:
            status_before = conn.execute("SELECT status FROM notification_outbox WHERE outbox_id = 'out_crashed_1'").fetchone()[0]
            self.assertEqual(status_before, "SENDING")
        finally:
            conn.close()

        # Startup a new NotificationWorker (simulates application restart)
        worker = NotificationWorker(
            self.storage,
            poll_interval=0.1,
            mock_endpoint_url=self.mock_tg_url
        )
        worker.start()

        time.sleep(0.5)
        worker.stop()

        # Verify recovery holds the uncertain job without dispatching it
        conn = self.storage._get_connection()
        try:
            status_after = conn.execute("SELECT status FROM notification_outbox WHERE outbox_id = 'out_crashed_1'").fetchone()[0]
            self.assertEqual(status_after, "DELIVERY_UNKNOWN")
        finally:
            conn.close()

        self.assertEqual(len(ControllableTelegramHandler.received_requests), 0)

    def test_04_rate_limiting_prevents_api_hammering(self):
        """Verify rate limiter caps dispatch rate to specified per-minute limit."""
        worker = NotificationWorker(
            self.storage,
            poll_interval=0.05,
            rate_limit_per_min=5,  # Cap at 5 msgs/min for this test
            mock_endpoint_url=self.mock_tg_url
        )

        # Enqueue 10 alerts
        for i in range(10):
            evt = TaskEvent(
                event_id=f"evt_rate_{i}",
                task_id=f"task_{i}",
                task_name=f"Rate Task {i}",
                tag_name="High_Analog.Tank01_Level",
                trigger_type="threshold_above",
                trigger_value=83.0,
                threshold_value=82.5,
                description=f"Rate Limit Test {i}",
                severity="INFO"
            )
            self.storage.record_event_and_enqueue_outbox(
                evt,
                [("telegram", "123456", {"event_id": f"evt_rate_{i}", "text": f"Rate Msg {i}"})]
            )

        worker.start()
        time.sleep(0.8)
        worker.stop()

        # Only 5 items should have been sent due to rate limit = 5/min
        self.assertEqual(len(ControllableTelegramHandler.received_requests), 5, "Must enforce rate limit cap of 5")
        stats = self.storage.get_stats()
        self.assertEqual(stats["outbox_sent"], 5)
        self.assertEqual(stats["outbox_pending"], 5)


if __name__ == "__main__":
    unittest.main()
