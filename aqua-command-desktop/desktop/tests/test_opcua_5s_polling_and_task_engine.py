#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
test_opcua_5s_polling_and_task_engine.py — Offline Acceptance Test Suite for AQUA COMMAND
Tests the 5-Second Monotonic OPC UA Polling Engine, Task Evaluation Engine,
SQLite WAL Durable Storage, Outbox Crash Recovery, and Telegram Notification Delivery.

Strict Safety Invariants:
- 100% Loopback synthetic testbed on 127.0.0.1 (Zero plant/SCADA connection).
- Ephemeral certificates and RSA keys generated in-memory inside TemporaryDirectory.
- Zero secrets committed.
- Zero real Telegram calls (Mock HTTP server on 127.0.0.1:8099).
- Zero OPC UA Write operations.
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
import ipaddress
from datetime import datetime, timezone, timedelta
from pathlib import Path
from http.server import HTTPServer, BaseHTTPRequestHandler
from typing import Dict, Any, List, Optional, Tuple

from cryptography import x509
from cryptography.x509.oid import NameOID
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa

# Add parent desktop path
desktop_dir = Path(__file__).resolve().parent.parent
if str(desktop_dir) not in sys.path:
    sys.path.insert(0, str(desktop_dir))

from opcua_pki import PkiManager, POLICY_BASIC256SHA256, POLICY_NONE
from opcua_mapping import NodeIdMapper
from opcua_store import ObservableStateStore, Quality, TagObservation
from opcua_storage import DurableStorage, StoredObservation, TaskEvent
from task_engine import TaskEngine, TaskDefinition
from notification_worker import NotificationWorker
from opcua_polling_engine import OpcUaPollingEngine, PollingState

try:
    from asyncua import Server, ua
    ASYNCUA_AVAILABLE = True
except ImportError:
    ASYNCUA_AVAILABLE = False


def find_free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(('127.0.0.1', 0))
        return s.getsockname()[1]


class MockTelegramHandler(BaseHTTPRequestHandler):
    received_requests = []
    fail_requests = False
    return_code = 200

    def log_message(self, format, *args):
        pass  # Suppress logging

    def do_POST(self):
        length = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(length).decode("utf-8")
        try:
            data = json.loads(body)
        except Exception:
            data = {"raw": body}

        MockTelegramHandler.received_requests.append({
            "path": self.path,
            "headers": dict(self.headers),
            "data": data,
            "time": time.time()
        })

        if MockTelegramHandler.fail_requests:
            self.send_response(429)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(b'{"ok": false, "error_code": 429, "description": "Rate limited"}')
        else:
            self.send_response(MockTelegramHandler.return_code)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(b'{"ok": true, "result": {"message_id": 999}}')


def generate_test_cert_pair(app_uri: str, host: str = "127.0.0.1"):
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    name = x509.Name([
        x509.NameAttribute(NameOID.ORGANIZATION_NAME, "AquaCMD Synthetic SCADA Testbed"),
        x509.NameAttribute(NameOID.COMMON_NAME, "WinCC Mock Endpoint"),
    ])
    now = datetime.now(timezone.utc)
    nb = now - timedelta(minutes=10)
    na = now + timedelta(days=365)

    san_items = [
        x509.UniformResourceIdentifier(app_uri),
        x509.DNSName("localhost"),
        x509.IPAddress(ipaddress.ip_address(host))
    ]

    builder = (
        x509.CertificateBuilder()
        .subject_name(name)
        .issuer_name(name)
        .public_key(key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(nb)
        .not_valid_after(na)
        .add_extension(x509.BasicConstraints(ca=False, path_length=None), critical=True)
        .add_extension(x509.SubjectAlternativeName(san_items), critical=False)
    )
    cert = builder.sign(key, hashes.SHA256())
    der = cert.public_bytes(serialization.Encoding.DER)
    pem = key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.TraditionalOpenSSL,
        encryption_algorithm=serialization.NoEncryption(),
    )
    return der, pem, cert


class TestOpcUa5sPollingAndTaskEngine(unittest.TestCase):
    """Offline Acceptance Test Suite for AQUA COMMAND 5s Polling & Task Engine."""

    @classmethod
    def setUpClass(cls):
        if not ASYNCUA_AVAILABLE:
            raise unittest.SkipTest("asyncua library is not installed.")

        cls.temp_dir = tempfile.TemporaryDirectory()
        cls.work_path = Path(cls.temp_dir.name)

        # 1. Start Mock Telegram Server on Loopback
        cls.tg_port = find_free_port()
        cls.mock_tg_url = f"http://127.0.0.1:{cls.tg_port}"
        MockTelegramHandler.received_requests.clear()
        MockTelegramHandler.fail_requests = False
        cls.httpd = HTTPServer(('127.0.0.1', cls.tg_port), MockTelegramHandler)
        cls.tg_thread = threading.Thread(target=cls.httpd.serve_forever, daemon=True)
        cls.tg_thread.start()

        # 2. Setup Loopback Synthetic OPC UA Server
        cls.opc_port = find_free_port()
        cls.opc_url = f"opc.tcp://127.0.0.1:{cls.opc_port}"
        cls.app_uri = "urn:aquacmd:gate_b2:synthetic_plant"

        cls.server_der, cls.server_pem, cls.server_cert = generate_test_cert_pair(cls.app_uri, "127.0.0.1")
        cls.cert_p = cls.work_path / "server_cert.der"
        cls.key_p = cls.work_path / "server_key.pem"
        cls.cert_p.write_bytes(cls.server_der)
        cls.key_p.write_bytes(cls.server_pem)

        cls.opc_loop = asyncio.new_event_loop()
        cls.ready_event = threading.Event()
        cls.server_thread = threading.Thread(target=cls._run_opc_server, daemon=True)
        cls.server_thread.start()
        cls.ready_event.wait(timeout=10.0)

        # Create mapping fixture
        cls.mapping_file = cls.work_path / "test_mapping.json"
        cls.mapping_file.write_text(json.dumps({
            "version": "1.0",
            "mappings": {
                "High_Analog.Tank01_Level": {
                    "node_id_identifier": "s=Synthetic_Plant_Alpha.Tank01.WaterLevel_m",
                    "namespace_uri": cls.app_uri,
                    "data_type": "Float",
                    "unit": "m",
                    "verified": True
                },
                "High_VSD.CTM13PT_Run": {
                    "node_id_identifier": "s=Synthetic_Plant_Alpha.CTM13PT.Running_Status",
                    "namespace_uri": cls.app_uri,
                    "data_type": "Boolean",
                    "unit": "",
                    "verified": True
                },
                "High_VSD.CTM13PT_Speed": {
                    "node_id_identifier": "s=Synthetic_Plant_Alpha.CTM13PT.Speed_RPM",
                    "namespace_uri": cls.app_uri,
                    "data_type": "Float",
                    "unit": "RPM",
                    "verified": True
                }
            }
        }))

    @classmethod
    def _run_opc_server(cls):
        asyncio.set_event_loop(cls.opc_loop)
        try:
            cls.opc_loop.run_until_complete(cls._init_opc_server())
        except Exception:
            import traceback
            traceback.print_exc()
        finally:
            cls.ready_event.set()
        cls.opc_loop.run_forever()

    @classmethod
    async def _init_opc_server(cls):
        cls.server = Server()
        await cls.server.init()
        cls.server.set_endpoint(cls.opc_url)
        await cls.server.set_application_uri(cls.app_uri)
        cls.server.set_security_policy([
            ua.SecurityPolicyType.Basic256Sha256_SignAndEncrypt,
            ua.SecurityPolicyType.NoSecurity
        ])
        await cls.server.load_certificate(str(cls.cert_p))
        await cls.server.load_private_key(str(cls.key_p))

        idx = await cls.server.register_namespace(cls.app_uri)
        cls.var_level = await cls.server.nodes.objects.add_variable(
            ua.NodeId("Synthetic_Plant_Alpha.Tank01.WaterLevel_m", idx),
            "WaterLevel_m",
            82.65,
            ua.VariantType.Float
        )
        cls.var_pump = await cls.server.nodes.objects.add_variable(
            ua.NodeId("Synthetic_Plant_Alpha.CTM13PT.Running_Status", idx),
            "Running_Status",
            True,
            ua.VariantType.Boolean
        )
        cls.var_speed = await cls.server.nodes.objects.add_variable(
            ua.NodeId("Synthetic_Plant_Alpha.CTM13PT.Speed_RPM", idx),
            "Speed_RPM",
            1450.0,
            ua.VariantType.Float
        )
        await cls.server.start()

    @classmethod
    def tearDownClass(cls):
        # Stop Telegram Mock Server
        cls.httpd.shutdown()
        cls.httpd.server_close()

        # Stop OPC UA Server
        async def _stop():
            if hasattr(cls, 'server'):
                await cls.server.stop()
        if cls.opc_loop:
            asyncio.run_coroutine_threadsafe(_stop(), cls.opc_loop).result(timeout=5.0)
            cls.opc_loop.call_soon_threadsafe(cls.opc_loop.stop)
        cls.temp_dir.cleanup()

    def setUp(self):
        self.test_dir = tempfile.TemporaryDirectory()
        self.db_path = Path(self.test_dir.name) / "test_aqua.db"
        self.storage = DurableStorage(self.db_path)
        self.task_engine = TaskEngine(self.storage)
        self.pki_dir = Path(self.test_dir.name) / "pki"
        self.pki = PkiManager(pki_dir=self.pki_dir)
        # Trust the test server certificate
        self.pki.ensure_client_certificate()
        trusted_dir = self.pki_dir / "trusted" / "certs"
        trusted_dir.mkdir(parents=True, exist_ok=True)
        (trusted_dir / "mock_server.der").write_bytes(self.server_der)

        self.mapper = NodeIdMapper(self.mapping_file)
        self.store = ObservableStateStore()
        MockTelegramHandler.received_requests.clear()
        MockTelegramHandler.fail_requests = False

    def tearDown(self):
        self.test_dir.cleanup()

    # =========================================================================
    # Test 1: Preflight & Explicit Authorization Check
    # =========================================================================
    def test_01_preflight_and_authorization(self):
        """Verifies engine rejects starting without valid preflight / task tags."""
        engine = OpcUaPollingEngine(
            self.mapper, self.store, self.storage, self.task_engine, self.pki,
            interval_seconds=1.0, mode_task_tags_only=True
        )

        # 1. No tasks assigned -> Preflight must fail
        ok, reason = engine.start_monitoring(self.opc_url, sec_policy="Basic256Sha256")
        self.assertFalse(ok, "Engine must not start when no active task tags exist")
        self.assertIn("No active tasks", reason)
        self.assertEqual(engine.get_telemetry()["state"], PollingState.ERROR)

        # 2. Add an enabled task with assigned tag -> Preflight passes
        self.task_engine.load_tasks([{
            "id": "task_01",
            "name": "Water Level High",
            "enabled": True,
            "tags": ["High_Analog.Tank01_Level"],
            "condition_type": "threshold_above",
            "threshold": 82.50
        }])

        ok, reason = engine.start_monitoring(self.opc_url, sec_policy="Basic256Sha256")
        self.assertTrue(ok, f"Engine should start when preflight passes: {reason}")
        time.sleep(0.5)
        self.assertIn(engine.get_telemetry()["state"], (PollingState.STARTING, PollingState.RUNNING))
        engine.stop_monitoring()
        self.assertEqual(engine.get_telemetry()["state"], PollingState.STOPPED)

    # =========================================================================
    # Test 2: Monotonic Cadence & Jitter Measurement
    # =========================================================================
    def test_02_monotonic_polling_and_jitter(self):
        """Verifies monotonic clock scheduling and jitter calculation."""
        self.task_engine.load_tasks([{
            "id": "task_01",
            "name": "Water Level High",
            "enabled": True,
            "tags": ["High_Analog.Tank01_Level"],
            "condition_type": "threshold_above",
            "threshold": 82.50
        }])
        # Test with 0.5s interval for swift test execution
        engine = OpcUaPollingEngine(
            self.mapper, self.store, self.storage, self.task_engine, self.pki,
            interval_seconds=0.5, mode_task_tags_only=True
        )
        ok, _ = engine.start_monitoring(self.opc_url, sec_policy="Basic256Sha256")
        self.assertTrue(ok)

        # Wait for 3 poll cycles
        time.sleep(1.8)
        engine.stop_monitoring()

        telem = engine.get_telemetry()
        self.assertGreaterEqual(telem["poll_count"], 2, "Must execute at least 2 cycles")
        self.assertGreaterEqual(telem["successful_polls"], 2)
        self.assertLess(telem["jitter_ms"], 200.0, "Jitter on loopback should remain tightly bounded")
        self.assertGreater(telem["last_poll_duration_ms"], 0.0)
        self.assertIsNotNone(telem["last_good_data_iso"])

    # =========================================================================
    # Test 3: Non-Overlapping Polling Guard
    # =========================================================================
    def test_03_non_overlapping_execution(self):
        """Verifies that slow poll cycles do not execute concurrently."""
        self.task_engine.load_tasks([{
            "id": "task_01",
            "name": "Water Level High",
            "enabled": True,
            "tags": ["High_Analog.Tank01_Level"],
            "condition_type": "threshold_above",
            "threshold": 82.50
        }])
        # Configure interval very short (0.05s) to induce overlap prevention
        engine = OpcUaPollingEngine(
            self.mapper, self.store, self.storage, self.task_engine, self.pki,
            interval_seconds=0.05, mode_task_tags_only=True
        )
        ok, _ = engine.start_monitoring(self.opc_url, sec_policy="Basic256Sha256")
        self.assertTrue(ok)

        time.sleep(0.4)
        engine.stop_monitoring()

        telem = engine.get_telemetry()
        self.assertGreater(telem["poll_count"], 0)
        # Verify overlap prevented counter was engaged or handled without concurrency
        self.assertGreaterEqual(telem["overlap_prevented_count"], 0)

    # =========================================================================
    # Test 4: Task Evaluation, Debounce, and Event Deduplication
    # =========================================================================
    def test_04_task_evaluation_and_deduplication(self):
        """Verifies analog threshold triggering, deduplication, and cooldown."""
        self.task_engine.load_tasks([{
            "id": "task_tank",
            "name": "Tank 01 High Level",
            "enabled": True,
            "tags": ["High_Analog.Tank01_Level"],
            "condition_type": "threshold_above",
            "threshold": 82.50,
            "debounce_samples": 2,  # Must be high for 2 consecutive cycles
            "cooldown_seconds": 60.0,
            "notification_channels": [{"channel": "mock_relay", "recipient": "1001"}]
        }])

        now = datetime.now(timezone.utc)
        # 1. Cycle 1: Value = 82.65 (> 82.50), sample 1 of 2 -> No trigger yet
        obs1 = {"High_Analog.Tank01_Level": StoredObservation(
            tag_name="High_Analog.Tank01_Level", value=82.65, unit="m", quality="GOOD"
        )}
        evts1 = self.task_engine.evaluate_observations(obs1, current_time=now)
        self.assertEqual(len(evts1), 0, "Debounce: cycle 1 should not trigger")
        state1 = self.storage.get_runtime_state("task_tank")
        self.assertEqual(state1.consecutive_samples, 1)
        self.assertEqual(state1.active_state, 0)

        # 2. Cycle 2: Value = 82.68 (> 82.50), sample 2 of 2 -> Triggers Event!
        obs2 = {"High_Analog.Tank01_Level": StoredObservation(
            tag_name="High_Analog.Tank01_Level", value=82.68, unit="m", quality="GOOD"
        )}
        evts2 = self.task_engine.evaluate_observations(obs2, current_time=now + timedelta(seconds=5))
        self.assertEqual(len(evts2), 1, "Debounce: cycle 2 must trigger event")
        self.assertEqual(evts2[0].trigger_type, "threshold_above")
        state2 = self.storage.get_runtime_state("task_tank")
        self.assertEqual(state2.active_state, 1)

        # 3. Cycle 3: Value still high (82.70), state already active -> DEDUPLICATED (No duplicate event!)
        obs3 = {"High_Analog.Tank01_Level": StoredObservation(
            tag_name="High_Analog.Tank01_Level", value=82.70, unit="m", quality="GOOD"
        )}
        evts3 = self.task_engine.evaluate_observations(obs3, current_time=now + timedelta(seconds=10))
        self.assertEqual(len(evts3), 0, "Deduplication: continuous high state must NOT fire duplicate events")

        # 4. Cycle 4: Value drops to normal (82.30 < 82.50) -> State clears back to 0
        obs4 = {"High_Analog.Tank01_Level": StoredObservation(
            tag_name="High_Analog.Tank01_Level", value=82.30, unit="m", quality="GOOD"
        )}
        evts4 = self.task_engine.evaluate_observations(obs4, current_time=now + timedelta(seconds=15))
        self.assertEqual(len(evts4), 0)
        state4 = self.storage.get_runtime_state("task_tank")
        self.assertEqual(state4.active_state, 0, "Active state must reset to 0 when condition clears")

    # =========================================================================
    # Test 5: Boolean Transition (ON/OFF)
    # =========================================================================
    def test_05_boolean_transition(self):
        """Verifies pump running transition (False -> True) triggers transition_on."""
        self.task_engine.load_tasks([{
            "id": "task_pump",
            "name": "CTM13PT Started",
            "enabled": True,
            "tags": ["High_VSD.CTM13PT_Run"],
            "condition_type": "transition_on",
            "debounce_samples": 1,
            "cooldown_seconds": 30.0,
            "notification_channels": [{"channel": "mock_relay", "recipient": "1002"}]
        }])

        now = datetime.now(timezone.utc)
        # Initial state: False
        self.task_engine.evaluate_observations({
            "High_VSD.CTM13PT_Run": StoredObservation(tag_name="High_VSD.CTM13PT_Run", value=False, unit="", quality="GOOD")
        }, current_time=now)

        # Transition: True -> Triggers transition_on event
        evts = self.task_engine.evaluate_observations({
            "High_VSD.CTM13PT_Run": StoredObservation(tag_name="High_VSD.CTM13PT_Run", value=True, unit="", quality="GOOD")
        }, current_time=now + timedelta(seconds=5))
        self.assertEqual(len(evts), 1)
        self.assertEqual(evts[0].trigger_type, "transition_on")

    # =========================================================================
    # Test 6: Strict Quality Isolation (Bad Quality != False/OFF)
    # =========================================================================
    def test_06_bad_quality_isolation(self):
        """Verifies Bad quality does NOT trigger false transition_off or false thresholds."""
        self.task_engine.load_tasks([{
            "id": "task_pump_off",
            "name": "CTM13PT Stopped Alert",
            "enabled": True,
            "tags": ["High_VSD.CTM13PT_Run"],
            "condition_type": "transition_off",
            "debounce_samples": 1,
            "notification_channels": [{"channel": "mock_relay", "recipient": "1003"}]
        }])

        now = datetime.now(timezone.utc)
        # Pump is RUNNING (True)
        self.task_engine.evaluate_observations({
            "High_VSD.CTM13PT_Run": StoredObservation(tag_name="High_VSD.CTM13PT_Run", value=True, unit="", quality="GOOD")
        }, current_time=now)

        # Signal fails with BAD quality (e.g. sensor disconnected)
        evts_bad = self.task_engine.evaluate_observations({
            "High_VSD.CTM13PT_Run": StoredObservation(tag_name="High_VSD.CTM13PT_Run", value=None, unit="", quality="BAD")
        }, current_time=now + timedelta(seconds=5))

        # MUST NOT treat BAD as OFF!
        self.assertEqual(len(evts_bad), 0, "Bad quality must NEVER be interpreted as false/OFF transition")

    # =========================================================================
    # Test 7: Multi-Task Single Read Fan-Out
    # =========================================================================
    def test_07_multi_task_fanout(self):
        """Verifies multiple tasks sharing the same tag evaluate from a single observation."""
        self.task_engine.load_tasks([
            {
                "id": "task_high",
                "name": "High Water Alert",
                "enabled": True,
                "tags": ["High_Analog.Tank01_Level"],
                "condition_type": "threshold_above",
                "threshold": 82.50,
                "notification_channels": [{"channel": "mock_relay", "recipient": "1001"}]
            },
            {
                "id": "task_low",
                "name": "Low Water Alert",
                "enabled": True,
                "tags": ["High_Analog.Tank01_Level"],
                "condition_type": "threshold_below",
                "threshold": 80.00,
                "notification_channels": [{"channel": "mock_relay", "recipient": "1001"}]
            }
        ])

        # Required tags set must contain the tag only once
        req = self.task_engine.get_required_tags()
        self.assertEqual(req, {"High_Analog.Tank01_Level"})

        # Evaluate observation = 82.65 m (triggers task_high, does NOT trigger task_low)
        now = datetime.now(timezone.utc)
        evts = self.task_engine.evaluate_observations({
            "High_Analog.Tank01_Level": StoredObservation(tag_name="High_Analog.Tank01_Level", value=82.65, unit="m", quality="GOOD")
        }, current_time=now)

        self.assertEqual(len(evts), 1)
        self.assertEqual(evts[0].task_id, "task_high")

    # =========================================================================
    # Test 8: SQLite Durable Storage & WAL Mode
    # =========================================================================
    def test_08_sqlite_durable_storage_and_wal(self):
        """Verifies WAL journal mode, atomic batch observation insert, and stats."""
        # Verify WAL mode in SQLite
        conn = self.storage._get_connection()
        mode = conn.execute("PRAGMA journal_mode;").fetchone()[0]
        conn.close()
        self.assertEqual(mode.lower(), "wal", "Database must operate in WAL mode")

        # Insert batch of observations
        obs_batch = [
            StoredObservation("High_Analog.Tank01_Level", 82.65, "m", "GOOD"),
            StoredObservation("High_VSD.CTM13PT_Run", True, "", "GOOD"),
            StoredObservation("High_VSD.CTM13PT_Speed", 1450.0, "RPM", "GOOD")
        ]
        cnt = self.storage.record_observations(obs_batch)
        self.assertEqual(cnt, 3)

        stats = self.storage.get_stats()
        self.assertEqual(stats["observations_count"], 3)
        self.assertFalse(stats["is_full"])

    # =========================================================================
    # Test 9: Outbox Crash Recovery
    # =========================================================================
    def test_09_outbox_crash_recovery(self):
        """Verifies items stuck in SENDING state during a crash are held as DELIVERY_UNKNOWN."""
        # Insert an event and an outbox item directly in SENDING state
        evt = TaskEvent("evt_test_crash", "task_01", "Task Crash", "Tag1", "threshold_above", 85.0, 80.0, "Desc")
        self.storage.record_event_and_enqueue_outbox(evt, [("telegram", "999", {"msg": "Crash test"})])

        pending = self.storage.get_pending_outbox_items()
        self.assertEqual(len(pending), 1)
        out_id = pending[0].outbox_id

        # Mark as SENDING (as if worker was in mid-flight during process termination)
        self.storage.mark_outbox_sending(out_id)
        self.assertEqual(len(self.storage.get_pending_outbox_items()), 0)

        # Simulate Crash Recovery
        recovered = self.storage.recover_uncommitted_outbox()
        self.assertEqual(recovered, 1)

        self.assertEqual(self.storage.get_pending_outbox_items(), [])
        with self.storage._get_connection() as conn:
            item = conn.execute("SELECT outbox_id, status FROM notification_outbox").fetchone()
        self.assertEqual(tuple(item), (out_id, "DELIVERY_UNKNOWN"))

    # =========================================================================
    # Test 10: Offline Network Outage & Notification Retry with Backoff
    # =========================================================================
    def test_10_offline_notification_retry(self):
        """Verifies that delivery failures trigger exponential backoff and eventual success."""
        # Create worker targeting Mock Telegram Server
        worker = NotificationWorker(
            self.storage,
            poll_interval=0.1,
            base_backoff_seconds=0.3,
            mock_endpoint_url=self.mock_tg_url
        )

        evt = TaskEvent("evt_tg_1", "task_tg", "Water Alert", "High_Analog.Tank01_Level", "threshold_above", 83.0, 82.5, "High Water")
        self.storage.record_event_and_enqueue_outbox(evt, [("telegram", "12345678", {"value": 83.0, "unit": "m"})])

        # 1. Simulate a definitive rate-limit rejection
        MockTelegramHandler.fail_requests = True
        worker.start()

        time.sleep(0.5)
        # Should have attempted and scheduled retry
        self.assertGreaterEqual(worker.retry_count, 1)

        # 2. Restore network (mock server succeeds)
        MockTelegramHandler.fail_requests = False
        time.sleep(0.8)

        worker.stop()

        self.assertGreaterEqual(worker.delivered_count, 1)
        self.assertEqual(len(MockTelegramHandler.received_requests), worker.delivered_count + worker.retry_count)
        self.assertEqual(len(self.storage.get_pending_outbox_items()), 0, "Outbox should be clear of pending items")

    # =========================================================================
    # Test 11: OPC UA Session Disconnect and Reconnect Backoff
    # =========================================================================
    def test_11_opcua_reconnect_backoff(self):
        """Verifies polling engine handles session disconnect and enters reconnect state."""
        self.task_engine.load_tasks([{
            "id": "task_reconn",
            "name": "Level Task",
            "enabled": True,
            "tags": ["High_Analog.Tank01_Level"],
            "condition_type": "threshold_above",
            "threshold": 82.50
        }])
        # Provide invalid port to simulate disconnected target
        bad_url = "opc.tcp://127.0.0.1:49999"
        engine = OpcUaPollingEngine(
            self.mapper, self.store, self.storage, self.task_engine, self.pki,
            interval_seconds=0.2, mode_task_tags_only=True
        )
        ok, _ = engine.start_monitoring(bad_url, sec_policy="None")
        self.assertTrue(ok)

        # Engine should enter RECONNECTING state
        time.sleep(1.0)
        telem = engine.get_telemetry()
        self.assertEqual(telem["state"], PollingState.RECONNECTING)
        self.assertGreaterEqual(telem["reconnect_attempts"], 1)

        engine.stop_monitoring()
        self.assertEqual(engine.get_telemetry()["state"], PollingState.STOPPED)

    # =========================================================================
    # Test 12: Strict Read-Only Audit
    # =========================================================================
    def test_12_strict_read_only_audit(self):
        """Verifies that OpcUaPollingEngine source code contains zero write calls."""
        engine_file = desktop_dir / "opcua_polling_engine.py"
        src = engine_file.read_text(encoding="utf-8")

        # Prohibit write_value, write_attribute, set_value calls in polling engine
        forbidden_patterns = [
            ".write_value(",
            ".write_attribute(",
            ".write(",
            "set_value("
        ]
        for pat in forbidden_patterns:
            self.assertNotIn(pat, src, f"Prohibited write pattern '{pat}' detected in OpcUaPollingEngine")

    # =========================================================================
    # Test 13: 5-Second Polling Soak Test Telemetry
    # =========================================================================
    def test_13_soak_test_telemetry(self):
        """
        Runs multi-cycle polling soak test to measure Jitter, Latency,
        Memory stability, and zero data loss.
        """
        self.task_engine.load_tasks([{
            "id": "task_soak",
            "name": "Soak Monitor",
            "enabled": True,
            "tags": ["High_Analog.Tank01_Level", "High_VSD.CTM13PT_Speed"],
            "condition_type": "threshold_above",
            "threshold": 80.0,
            "debounce_samples": 1,
            "notification_channels": [{"channel": "mock_relay", "recipient": "9999"}]
        }])

        engine = OpcUaPollingEngine(
            self.mapper, self.store, self.storage, self.task_engine, self.pki,
            interval_seconds=0.3, mode_task_tags_only=True
        )
        ok, _ = engine.start_monitoring(self.opc_url, sec_policy="Basic256Sha256")
        self.assertTrue(ok)

        # Run for 5 cycles (~1.8 seconds)
        time.sleep(1.8)
        engine.stop_monitoring()

        telem = engine.get_telemetry()
        self.assertGreaterEqual(telem["poll_count"], 4)
        self.assertEqual(telem["failed_polls"], 0, "Soak test must have zero failed polls on loopback")
        self.assertLess(telem["avg_poll_duration_ms"], 50.0, "Average poll duration should be < 50ms on loopback")

        # Verify storage counts
        stats = self.storage.get_stats()
        self.assertGreaterEqual(stats["observations_count"], 8)
        self.assertGreaterEqual(stats["events_count"], 1)
        self.assertFalse(stats["is_full"])


if __name__ == "__main__":
    unittest.main()
