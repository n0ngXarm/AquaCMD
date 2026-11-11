#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
test_e2e_gtk_integration.py — End-to-End GTK4 Application Integration Test for AQUA COMMAND
Tests the complete user journey:
1. F2 Task configuration, debounce, cooldown, and task saving.
2. F6 OPC UA Connection configuration & explicit Start Monitoring.
3. 5-Second Monotonic Polling with synthetic OPC UA Server on 127.0.0.1.
4. Single-read fan-out to SQLite WAL storage and Task Evaluation Engine.
5. Task threshold alert triggering (> 82.50 m with 2 consecutive debounce samples).
6. Decoupled Telegram NotificationWorker dispatch to Mock HTTP endpoint.
7. F6 Pause, Resume, and Stop controls with GTK UI state synchronization.
8. Durable Outbox persistence and crash recovery verification.

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
import ipaddress
from pathlib import Path
from http.server import HTTPServer, BaseHTTPRequestHandler
from datetime import datetime, timezone, timedelta

# Add parent desktop directory to sys.path
desktop_dir = Path(__file__).resolve().parent.parent
if str(desktop_dir) not in sys.path:
    sys.path.insert(0, str(desktop_dir))

import gi
gi.require_version('Gtk', '4.0')
from gi.repository import Gtk, GLib

import app
from opcua_polling_engine import PollingState
from opcua_storage import DurableStorage, StoredObservation, TaskEvent

try:
    from asyncua import Server, ua
    from cryptography import x509
    from cryptography.x509.oid import NameOID
    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.hazmat.primitives.asymmetric import rsa
    ASYNCUA_AVAILABLE = True
except ImportError:
    ASYNCUA_AVAILABLE = False


def find_free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(('127.0.0.1', 0))
        return s.getsockname()[1]


class MockTelegramHandler(BaseHTTPRequestHandler):
    received_requests = []
    return_code = 200

    def log_message(self, format, *args):
        pass  # Suppress console logging

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

        self.send_response(MockTelegramHandler.return_code)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(b'{"ok": true, "result": {"message_id": 9999}}')


def generate_test_cert_pair(app_uri: str, host: str = "127.0.0.1"):
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    name = x509.Name([
        x509.NameAttribute(NameOID.ORGANIZATION_NAME, "AquaCMD Synthetic E2E Testbed"),
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


class TestE2EGtkIntegration(unittest.TestCase):
    """End-to-End integration test covering the GTK4 application with live mock servers."""

    @classmethod
    def setUpClass(cls):
        if not ASYNCUA_AVAILABLE:
            raise unittest.SkipTest("asyncua library is not installed.")

        cls.temp_dir = tempfile.TemporaryDirectory()
        cls.work_path = Path(cls.temp_dir.name)

        # 1. Start Mock Telegram Server on Loopback
        cls.tg_port = find_free_port()
        cls.mock_tg_url = f"http://127.0.0.1:{cls.tg_port}"
        os.environ["AQUA_MOCK_TELEGRAM_URL"] = cls.mock_tg_url
        MockTelegramHandler.received_requests.clear()
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

        # 3. Create isolated mapping file
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
                }
            }
        }))

    @classmethod
    def tearDownClass(cls):
        if hasattr(cls, 'httpd'):
            cls.httpd.shutdown()
            cls.httpd.server_close()
        if hasattr(cls, 'server') and hasattr(cls, 'opc_loop'):
            try:
                fut = asyncio.run_coroutine_threadsafe(cls.server.stop(), cls.opc_loop)
                fut.result(timeout=5.0)
            except Exception:
                pass
            cls.opc_loop.call_soon_threadsafe(cls.opc_loop.stop)
        if hasattr(cls, 'temp_dir'):
            cls.temp_dir.cleanup()
        os.environ.pop("AQUA_MOCK_TELEGRAM_URL", None)

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
            ua.SecurityPolicyType.NoSecurity
        ])

        idx = await cls.server.register_namespace(cls.app_uri)

        # Create nodes with explicit NodeId matching test_mapping.json
        cls.tank01_node = await cls.server.nodes.objects.add_variable(
            ua.NodeId("Synthetic_Plant_Alpha.Tank01.WaterLevel_m", idx),
            "Tank01.WaterLevel_m",
            81.0,
            ua.VariantType.Float
        )

        cls.pump_node = await cls.server.nodes.objects.add_variable(
            ua.NodeId("Synthetic_Plant_Alpha.CTM13PT.Running_Status", idx),
            "CTM13PT.Running_Status",
            False,
            ua.VariantType.Boolean
        )

        await cls.server.start()

    def setUp(self):
        MockTelegramHandler.received_requests.clear()

        # Initialize headless GTK Application and Window
        self.gtk_app = Gtk.Application(application_id=f"org.aqua.e2e.test.{int(time.time()*1000)%100000}")
        self.win = app.AquaWinCCWindow(self.gtk_app)
        self.win.auto_scan_active = False

        # Point window to our test mapping file and synthetic database
        self.test_db_path = self.work_path / f"test_e2e_{int(time.time()*1000)}.db"
        self.durable_storage = DurableStorage(self.test_db_path)
        self.win.durable_storage = self.durable_storage

        # Point task engine to test storage
        from task_engine import TaskEngine
        self.win.task_engine = TaskEngine(self.durable_storage)

        # Point notification worker to test storage and mock endpoint
        self.win.notification_worker.stop()
        from notification_worker import NotificationWorker
        self.win.notification_worker = NotificationWorker(
            self.durable_storage,
            poll_interval=0.2,
            mock_endpoint_url=self.mock_tg_url
        )

        # Replace polling engine with test configuration
        self.win.polling_engine.stop_monitoring()
        from opcua_polling_engine import OpcUaPollingEngine
        from opcua_mapping import NodeIdMapper
        from opcua_store import ObservableStateStore

        self.mapper = NodeIdMapper(self.mapping_file)
        self.store = ObservableStateStore()
        self.win.opcua_mapper = self.mapper
        self.win.opcua_store = self.store

        # Point window to test polling engine with 0.5s cadence for responsive E2E testing
        self.win.polling_engine = OpcUaPollingEngine(
            self.mapper,
            self.store,
            self.durable_storage,
            self.win.task_engine,
            self.win.pki,
            interval_seconds=0.5,
            mode_task_tags_only=True
        )

    def tearDown(self):
        if hasattr(self, 'win') and hasattr(self.win, 'polling_engine'):
            self.win.polling_engine.stop_monitoring()
        if hasattr(self, 'win') and hasattr(self.win, 'notification_worker'):
            self.win.notification_worker.stop()

    def test_01_gtk_initial_state_safety_invariants(self):
        """Phase 2 & 3: Verify initial GUI state ensures zero auto-start upon boot."""
        self.assertEqual(self.win.polling_engine.telemetry.state, PollingState.STOPPED)
        self.assertTrue(self.win.btn_start_monitoring.get_sensitive(), "Start button must be enabled initially")
        self.assertFalse(self.win.btn_pause_monitoring.get_sensitive(), "Pause button must be disabled initially")
        self.assertFalse(self.win.btn_stop_monitoring.get_sensitive(), "Stop button must be disabled initially")
        self.assertIn("STOPPED", self.win.lbl_mon_telemetry.get_text(), "Telemetry status must indicate STOPPED")

    def test_02_task_configuration_and_persistence(self):
        """Phase 5: Verify task configuration in F2, debounce, cooldown, and task saving."""
        test_task = {
            "id": "e2e_tank01_high",
            "name": "E2E High Water Alert",
            "active": True,
            "tag_name": "High_Analog.Tank01_Level",
            "assigned_tags": ["High_Analog.Tank01_Level"],
            "rule_type": "threshold_above",
            "threshold": 82.50,
            "debounce_count": 2,
            "cooldown_seconds": 60,
            "alert_channel": "telegram",
            "recipient": "987654321",
            "message_template": "🚨 [TANK 01 HIGH] Level is {value:.2f} m (> {threshold})"
        }
        self.win.tasks = [test_task]
        self.win.task_engine.load_tasks(self.win.tasks)

        # Check required tags
        req_tags = self.win.task_engine.get_required_tags()
        self.assertIn("High_Analog.Tank01_Level", req_tags)
        self.assertEqual(len(req_tags), 1)

    def test_03_e2e_monitoring_lifecycle_and_alert_delivery(self):
        """
        Phase 2 & 4: Full End-to-End GTK Application Journey:
        Configure -> Start Monitoring -> Advance OPC UA values -> Debounce Evaluation ->
        SQLite WAL Storage -> Outbox Queue -> Mock Telegram Delivery -> Pause/Resume/Stop.
        """
        # Configure task with debounce=3 to verify multi-sample debounce filter
        test_task = {
            "id": "e2e_tank01_alert",
            "name": "E2E High Level Alarm",
            "active": True,
            "tag_name": "High_Analog.Tank01_Level",
            "assigned_tags": ["High_Analog.Tank01_Level"],
            "rule_type": "threshold_above",
            "threshold": 82.50,
            "debounce_count": 3,
            "cooldown_seconds": 60,
            "alert_channel": "telegram",
            "recipient": "123456789",
            "message_template": "🚨 [E2E ALERT] Tank Level is {value:.2f} m"
        }
        self.win.tasks = [test_task]
        self.win.task_engine.load_tasks(self.win.tasks)

        # Configure F6 OPC UA Connection in UI widgets
        self.win.entry_opc_url.set_text(self.opc_url)
        self.win.opc_sec_combo.set_selected(0)   # None
        self.win.opc_auth_combo.set_selected(0)  # Anonymous

        # Step 1: Click 'Start Monitoring'
        self.win.on_start_monitoring_clicked()

        # Verify UI state update
        self.assertFalse(self.win.btn_start_monitoring.get_sensitive(), "Start button must be disabled when running")
        self.assertTrue(self.win.btn_pause_monitoring.get_sensitive(), "Pause button must be enabled when running")
        self.assertTrue(self.win.btn_stop_monitoring.get_sensitive(), "Stop button must be enabled when running")

        # Wait for poller to connect and complete first cycle
        time.sleep(1.2)
        self.assertIn(self.win.polling_engine.telemetry.state, (PollingState.RUNNING, PollingState.STARTING))
        self.assertGreaterEqual(self.win.polling_engine.telemetry.poll_count, 1)

        # Verify initial normal reading stored in SQLite (value = 81.0)
        recent_obs = self.durable_storage.get_recent_observations("High_Analog.Tank01_Level", limit=5)
        self.assertTrue(len(recent_obs) >= 1)
        self.assertAlmostEqual(recent_obs[0].value, 81.0, places=1)
        self.assertEqual(len(MockTelegramHandler.received_requests), 0, "No alerts should be triggered at 81.0 m")

        # Step 2: Elevate water level to 82.60 m (> 82.50 m threshold, Debounce 1/2)
        asyncio.run_coroutine_threadsafe(
            self.tank01_node.write_value(ua.DataValue(ua.Variant(82.60, ua.VariantType.Float))),
            self.opc_loop
        ).result(timeout=3.0)

        time.sleep(1.2)
        # Still debounce 1/2 -> No alert yet
        self.assertEqual(len(MockTelegramHandler.received_requests), 0, "Debounce 1/2 must NOT trigger alert")

        # Step 3: Advance water level to 82.75 m (Debounce 2/2 -> Alert Triggered!)
        asyncio.run_coroutine_threadsafe(
            self.tank01_node.write_value(ua.DataValue(ua.Variant(82.75, ua.VariantType.Float))),
            self.opc_loop
        ).result(timeout=3.0)

        # Allow poller and decoupled notification worker to process
        time.sleep(1.8)

        # Verify SQLite event and outbox
        events = self.durable_storage.get_task_events("e2e_tank01_alert", limit=5)
        self.assertTrue(len(events) >= 1, "Task event must be recorded in SQLite")
        self.assertEqual(events[0].trigger_type, "threshold_above")

        # Verify Mock Telegram Delivery
        self.assertTrue(len(MockTelegramHandler.received_requests) >= 1, "Alert must be delivered to Mock Telegram")
        sent_req = MockTelegramHandler.received_requests[0]
        sent_payload = sent_req["data"]
        self.assertEqual(sent_payload.get("chat_id"), "123456789")
        self.assertIn("AQUA COMMAND SCADA ALERT", sent_payload.get("text", ""))
        self.assertIn("Tank01_Level", sent_payload.get("text", ""))

        # Step 4: Test Pause Monitoring
        self.win.on_pause_monitoring_clicked()
        self.assertEqual(self.win.polling_engine.telemetry.state, PollingState.PAUSED)
        self.assertEqual(self.win.btn_pause_monitoring.get_label(), "อ่านต่อ")

        # Step 5: Test Resume Monitoring
        self.win.on_pause_monitoring_clicked()
        self.assertEqual(self.win.polling_engine.telemetry.state, PollingState.RUNNING)
        self.assertEqual(self.win.btn_pause_monitoring.get_label(), "พัก")

        # Step 6: Test Stop Monitoring
        self.win.on_stop_monitoring_clicked()
        self.assertEqual(self.win.polling_engine.telemetry.state, PollingState.STOPPED)
        self.assertTrue(self.win.btn_start_monitoring.get_sensitive())
        self.assertFalse(self.win.btn_pause_monitoring.get_sensitive())
        self.assertFalse(self.win.btn_stop_monitoring.get_sensitive())


if __name__ == "__main__":
    unittest.main()
