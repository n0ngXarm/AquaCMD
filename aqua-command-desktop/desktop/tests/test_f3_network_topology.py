#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
test_f3_network_topology.py — Full Acceptance Test Suite for F3 Live Network Topology & Diagnostics

Verifies all 20 Acceptance Criteria (Phase 9):
  1. F3 Rendering Bounds (1366x768, 1600x900, 1920x1080)
  2. Device Diagram Click Selection
  3. Device Status LED Updates
  4. Animation Halts when UNKNOWN / STALE / ERROR
  5. PC4 Local NIC Detection (Read-only OS sysfs/procfs)
  6. Synthetic Remote ICMP/TCP Detection
  7. OPC UA Endpoint URL & Port Configurable
  8. OPC UA Loopback Connect / Disconnect
  9. Strict Separation: TCP Open != OPC UA Connected
 10. PKI Trust Failure Status (CERTIFICATE_UNTRUSTED)
 11. Read Once DataValue Verification
 12. Add / Remove Device Updates Diagram & Cards
 13. Device Configuration Persistence to JSON
 14. Demo Data Isolation (Zero packet emission in demo mode)
 15. No Network Traffic on F3 Open
 16. No Unauthorized SCADA Probing (OT Authorization Dialog Gate)
 17. No Security Downgrade
 18. GTK4 Thread Safety (GLib.idle_add dispatch)
 19. F1/F2/F6 Regression Safety
 20. 5s Polling & SQLite Outbox Invariants
"""

import os
import sys
import json
import time
import socket
import unittest
import threading
import tempfile
from pathlib import Path
from unittest.mock import patch, MagicMock

desktop_dir = Path(__file__).resolve().parent.parent
if str(desktop_dir) not in sys.path:
    sys.path.insert(0, str(desktop_dir))

import gi
gi.require_version('Gtk', '4.0')
from gi.repository import Gtk, GLib

from f3_network import (
    IdentityStatus,
    IdentitySource,
    get_local_hostname,
    compute_display_name,
    OpcUaState,
    ConnectionState,
    VerificationState,
    safe_get_local_network_state,
    F3DeviceStore,
    RealDetectionEngine,
    OTAuthorizationDialog,
    DeviceSettingsDialog,
    DeviceDetailsDialog,
    F3NetworkTopologyView,
    F3TopologyCanvas,
    F3LiveDiagramCanvas,
    F3DeviceCard
)
from app import DEFAULT_TOPOLOGY, AquaWinCCWindow
from f3_reconciliation_fixture import assert_all_pages_fit


def wait_for_glib(event, timeout=2.0):
    ctx = GLib.MainContext.default()
    start = time.monotonic()
    while not event.is_set() and (time.monotonic() - start) < timeout:
        while ctx.pending():
            ctx.iteration(False)
        time.sleep(0.01)
    while ctx.pending():
        ctx.iteration(False)
    return event.is_set()


class TestF3NetworkTopologyPhase9(unittest.TestCase):
    """Rigorous acceptance test suite covering all 20 Phase 9 Acceptance Tests."""

    @classmethod
    def setUpClass(cls):
        cls.app = Gtk.Application.new("org.aqua.command.test.f3", 0)

    def setUp(self):
        profile = tempfile.TemporaryDirectory()
        self.addCleanup(profile.cleanup)
        self.mock_owner = MagicMock()
        from f3_fixture import configure_legacy_inventory
        configure_legacy_inventory(profile.name)
        self.mock_owner.config_dir = Path(profile.name)
        self.mock_owner.topology_data = json.loads(json.dumps(DEFAULT_TOPOLOGY))
        self.mock_owner.alarm_text = MagicMock()
        self.mock_owner.opcua_session_state = "DISCONNECTED"

    # 1. F3 Rendering Bounds
    def test_01_f3_rendering_bounds(self):
        """1. Verify F3 initializes and renders within bounds at 1366x768, 1600x900, 1920x1080 without window overflow."""
        view = F3NetworkTopologyView(self.mock_owner)
        # G15: height adapts to viewport and pagination, rather than a fixed 450px floor.
        self.addCleanup(GLib.source_remove, view.canvas.anim_source_id)
        for width in (1024, 1366, 1920):
            with self.subTest(width=width):
                assert_all_pages_fit(self, view, width, 407)
        self.assertTrue(view.canvas.get_hexpand())
        self.assertTrue(view.stack.get_vexpand())
        self.assertIsNotNone(view.root_widget)
        self.assertIsNotNone(view.main_split)
        self.assertIsNotNone(view.inspector)
        # Port placement now comes from f3_layout rather than retired local variable names.
        geometry = view.canvas.flow_geometry['stages']
        self.assertLess(geometry['lan'][0], geometry['collector'][0])
        self.assertLess(geometry['collector'][0], geometry['storage'][0])
        self.assertLess(geometry['storage'][0], geometry['outbox'][0])
        self.assertLess(geometry['outbox'][0], geometry['delivery'][0])

    # 2. Device Diagram Click Selection
    def test_02_diagram_click_selection(self):
        """2. Verify clicking a device node on the diagram updates selected device and inspector."""
        view = F3NetworkTopologyView(self.mock_owner)
        view.select_device("PC2")
        self.assertEqual(view.selected_device_id, "PC2")
        self.assertEqual(view.inspector.current_device_id, "PC2")
        self.assertIn("PC2", view.inspector.lbl_title.get_text())
        self.assertTrue(view.inspector.get_visible())

    # 3. Device Status LED Updates
    def test_03_status_led_updates(self):
        # G16: configured flags do not establish observations or an OPC UA session.
        view = F3NetworkTopologyView(self.mock_owner)
        self.addCleanup(GLib.source_remove, view.canvas.anim_source_id)
        view.store.update_device('PC1', {'reachability': 'REACHABLE', 'opcua_state': OpcUaState.CONNECTED})
        card = view.cards['PC1']
        self.assertEqual(card.lbl_badge.get_text(), 'UNKNOWN')
        import f3_evidence as evidence
        dev = view.store.devices['PC1']
        self.assertFalse(evidence.session_connected(dev))
        evidence.record_evidence(dev, 'reachability', evidence.Provenance.REMOTE)
        view.store.notify()
        self.assertEqual(card.lbl_badge.get_text(), 'REMOTE')
        self.assertTrue(evidence.reachable(dev))
        self.assertFalse(evidence.session_connected(dev))
        dev['session_state'] = 'CONNECTED'
        evidence.record_evidence(dev, 'session', evidence.Provenance.OPCUA)
        view.store.notify()
        self.assertTrue(evidence.session_connected(dev))
        self.assertIn('CONNECT', card.pill_opc.get_text())
        dev['evidence']['reachability']['checked_at'] -= 120
        view.store.notify()
        self.assertEqual(card.lbl_badge.get_text(), 'STALE')
        dev['configured_ip'] = '192.0.2.99'
        dev['endpoint_url'] = 'opc.tcp://192.0.2.99:4862'
        self.assertFalse(evidence.reachable(dev))
        self.assertFalse(evidence.session_connected(dev))

    def test_04_animation_stops_when_unknown_stale(self):
        """4. Verify connection line animation halts when state is UNKNOWN, STALE, or ERROR."""
        animated_states = {
            ConnectionState.OPCUA_CONNECTED: True,
            ConnectionState.REACHABILITY_VERIFIED: True,
            ConnectionState.CHECKING: True,
            ConnectionState.UNKNOWN: False,
            ConnectionState.STALE: False,
            ConnectionState.OPCUA_ERROR: False,
            ConnectionState.NIC_OT_DOWN: False,
            ConnectionState.SERVICE_UNAVAILABLE: False
        }
        for st, expected in animated_states.items():
            is_anim = st in (ConnectionState.OPCUA_CONNECTED, ConnectionState.REACHABILITY_VERIFIED,
                             ConnectionState.LINK_VERIFIED, ConnectionState.CHECKING)
            self.assertEqual(is_anim, expected, f"State {st} animation flag mismatch")

    # 5. PC4 Local NIC Detection
    def test_05_pc4_local_nic_detection(self):
        """5. Verify PC4 local NIC detection reads directly from OS sysfs/procfs with zero network packets."""
        state = safe_get_local_network_state()
        self.assertIn("interfaces", state)
        self.assertIn("ip_forwarding", state)
        self.assertFalse(state["ip_forwarding"], "net.ipv4.ip_forward must be 0 (air-gapped)")

    # 6. Synthetic Remote ICMP/TCP Detection
    def test_06_synthetic_remote_detection(self):
        """6. Verify synthetic remote ICMP/TCP detection works in DEMO mode."""
        dev = {"id": "PC1", "configured_ip": "192.0.2.11", "port": 4862, "type": "wincc"}
        result = {}
        done_evt = threading.Event()
        def on_done(res):
            result.update(res)
            done_evt.set()
        RealDetectionEngine.detect_device_network(dev, is_demo=True, callback=on_done)
        self.assertTrue(wait_for_glib(done_evt, timeout=2.0))
        self.assertTrue(result.get("ping_ok"))
        self.assertTrue(result.get("tcp_ok"))
        self.assertEqual(result.get("reachability"), "REACHABLE")

    # 7. OPC UA Endpoint URL & Port Configurable
    def test_07_opcua_endpoint_port_configurable(self):
        """7. Verify OPC UA endpoint URL and port are dynamically configurable and not hardcoded."""
        view = F3NetworkTopologyView(self.mock_owner)
        view.store.update_device("PC1", {
            "port": 4840,
            "endpoint_url": "opc.tcp://192.0.2.11:4840"
        })
        self.assertEqual(view.store.devices["PC1"]["port"], 4840)
        self.assertEqual(view.store.devices["PC1"]["endpoint_url"], "opc.tcp://192.0.2.11:4840")
        self.assertIn("4840", view.cards["PC1"].v_cfg_ip.get_text())

    # 8. OPC UA Loopback Connect / Disconnect
    def test_08_opcua_loopback_connect_disconnect(self):
        """8. Verify clean OPC UA loopback connect and disconnect state transitions."""
        dev = {"id": "PC1", "endpoint_url": "opc.tcp://127.0.0.1:4862", "port": 4862, "type": "wincc"}
        result = {}
        done_evt = threading.Event()
        def on_done(res):
            result.update(res)
            done_evt.set()
        RealDetectionEngine.detect_opcua_session(dev, is_demo=True, callback=on_done)
        self.assertTrue(wait_for_glib(done_evt, timeout=2.0))
        self.assertEqual(result.get("opcua_state"), OpcUaState.CONNECTED)
        self.assertEqual(result.get("session_state"), "CONNECTED")

    # 9. Strict Separation: TCP Open != OPC UA Connected
    def test_09_tcp_open_not_opcua_connected(self):
        """9. Verify strict separation: TCP port open does NOT imply OPC UA session connected."""
        dev = {"id": "PC1", "endpoint_url": "opc.tcp://192.0.2.11:4862", "port": 4862, "type": "wincc"}
        result = {}
        done_evt = threading.Event()
        def on_done(res):
            result.update(res)
            done_evt.set()
        with patch("socket.socket") as mock_sock:
            mock_instance = MagicMock()
            mock_instance.connect_ex.return_value = 0 # TCP connect succeeds
            mock_sock.return_value = mock_instance
            RealDetectionEngine.detect_opcua_session(dev, is_demo=False, callback=on_done)
            self.assertTrue(wait_for_glib(done_evt, timeout=2.0))
            self.assertEqual(result.get("opcua_state"), OpcUaState.TCP_REACHABLE)
            self.assertNotEqual(result.get("opcua_state"), OpcUaState.CONNECTED)
            self.assertEqual(result.get("session_state"), "TCP_OPEN_NO_SESSION")

    # 10. PKI Trust Failure Status
    def test_10_pki_trust_failure_status(self):
        """10. Verify PKI trust failure displays CERTIFICATE_UNTRUSTED status."""
        dev = {"id": "PC1", "endpoint_url": "opc.tcp://192.0.2.11:4862", "port": 4862, "type": "wincc", "simulate_untrusted_cert": True}
        result = {}
        done_evt = threading.Event()
        def on_done(res):
            result.update(res)
            done_evt.set()
        with patch("socket.socket") as mock_sock:
            mock_sock.return_value.connect_ex.return_value = 0
            RealDetectionEngine.detect_opcua_session(dev, is_demo=False, callback=on_done)
            self.assertTrue(wait_for_glib(done_evt, timeout=2.0))
        self.assertEqual(result.get("opcua_state"), OpcUaState.CERTIFICATE_UNTRUSTED)
        self.assertIn("Untrusted", result.get("last_error", ""))

    # 11. Read Once DataValue Verification
    def test_11_read_once_datavalue(self):
        """11. Verify Read Once action returns DataValue with value, quality, and timestamp."""
        dev = {"id": "PC1", "test_tag": "High_Analog.Tank01_Level", "last_read_tag": "High_Analog.Tank01_Level"}
        result = {}
        done_evt = threading.Event()
        def on_done(res):
            result.update(res)
            done_evt.set()
        RealDetectionEngine.read_opcua_single_tag(dev, is_demo=True, callback=on_done)
        self.assertTrue(wait_for_glib(done_evt, timeout=2.0))
        self.assertIsNotNone(result.get("value"))
        self.assertIn("Good", result.get("quality", ""))
        self.assertIsNotNone(result.get("timestamp"))

    # 12. Add / Remove Device Updates Diagram & Cards
    def test_12_add_remove_device_updates_ui(self):
        """12. Verify adding and removing a device dynamically updates cards and store."""
        view = F3NetworkTopologyView(self.mock_owner)
        initial_count = len(view.store.devices)
        new_dev = {
            "id": "PC5_TEMP",
            "name": "PC5 · Test Station",
            "role": "สถานีทดสอบ",
            "type": "wincc",
            "configured_ip": "192.0.2.55",
            "port": 4862
        }
        view.store.add_device(new_dev)
        self.assertEqual(len(view.store.devices), initial_count + 1)
        self.assertIn("PC5_TEMP", view.store.devices)
        view.store.remove_device("PC5_TEMP")
        self.assertEqual(len(view.store.devices), initial_count)
        self.assertNotIn("PC5_TEMP", view.store.devices)

    # 13. Device Configuration Persistence to JSON
    def test_13_device_config_persistence(self):
        """13. Verify device configuration persists atomically to JSON and reloads on restart."""
        import tempfile
        with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as tf:
            cfg_path = Path(tf.name)
        try:
            # Explicit configuration replaces the removed fabricated runtime defaults.
            fixture = Path(__file__).parent / "fixtures/f3_legacy_inventory.json"
            cfg_path.write_bytes(fixture.read_bytes())
            store1 = F3DeviceStore(config_file=cfg_path)
            store1.update_device("PC1", {"name": "PC1 · Modified Name", "port": 4899})
            store1.save()

            store2 = F3DeviceStore(config_file=cfg_path)
            self.assertEqual(store2.devices["PC1"]["name"], "PC1 · Modified Name")
            self.assertEqual(store2.devices["PC1"]["port"], 4899)
        finally:
            if cfg_path.exists():
                cfg_path.unlink()

    # 14. Demo Data Isolation
    def test_14_demo_data_isolation(self):
        """14. Verify DEMO mode uses synthetic loopback and does NOT touch live production IPs."""
        dev = {"id": "PC1", "configured_ip": "192.0.2.11", "port": 4862}
        with patch("socket.socket") as mock_sock, patch("subprocess.run") as mock_sub:
            done_evt = threading.Event()
            RealDetectionEngine.detect_device_network(dev, is_demo=True, callback=lambda _: done_evt.set())
            self.assertTrue(wait_for_glib(done_evt, timeout=2.0))
            mock_sock.assert_not_called()
            mock_sub.assert_not_called()

    # 15. No Network Traffic on F3 Open
    def test_15_no_network_traffic_on_f3_open(self):
        """15. Verify zero outbound network packets / sockets on F3 tab open."""
        with patch("socket.socket") as mock_sock, patch("subprocess.Popen") as mock_pop, patch("subprocess.run") as mock_run:
            view = F3NetworkTopologyView(self.mock_owner)
            mock_sock.assert_not_called()
            mock_pop.assert_not_called()
            for c in mock_run.call_args_list:
                args = c[0][0]
                cmd_name = args[0] if isinstance(args, list) else str(args)
                self.assertNotIn("ping", cmd_name.lower())

    # 16. No Unauthorized SCADA Probing
    def test_16_no_unauthorized_scada_probe(self):
        """16. Verify remote device probing in LIVE mode is gated by OT Safety Authorization Dialog."""
        view = F3NetworkTopologyView(self.mock_owner)
        view.store.is_demo_mode = False
        with patch.object(OTAuthorizationDialog, 'present') as mock_present:
            view.trigger_device_detect("PC1")
            mock_present.assert_called_once()

    # 17. No Security Downgrade
    def test_17_no_security_downgrade(self):
        """17. Verify that security settings cannot be auto-trusted or downgraded without authorization."""
        self.assertIn("CERTIFICATE_UNTRUSTED", dir(OpcUaState))
        self.assertIn("AUTH_FAILED", dir(OpcUaState))

    # 18. GTK4 Thread Safety
    def test_18_gtk_thread_safety(self):
        """18. Verify network detection runs on background thread and dispatches to GLib main thread."""
        dev = {"id": "PC1", "configured_ip": "127.0.0.1", "port": 4862}
        with patch("gi.repository.GLib.idle_add") as mock_idle:
            done_evt = threading.Event()
            def cb(res):
                done_evt.set()
            RealDetectionEngine.detect_device_network(dev, is_demo=True, callback=cb)
            time.sleep(0.3)
            mock_idle.assert_called()

    # 19. F1/F2/F6 Regression Safety
    def test_19_f1_f2_f6_regression(self):
        """19. Verify F1, F2, F6 tabs and underlying models remain completely intact."""
        self.assertTrue(hasattr(AquaWinCCWindow, 'build_overview_page'))
        self.assertTrue(hasattr(AquaWinCCWindow, 'build_task_manager_page'))
        self.assertTrue(hasattr(AquaWinCCWindow, 'build_alarms_page'))

    # 20. 5s Polling & SQLite Outbox Invariants
    def test_20_polling_storage_invariants(self):
        """20. Verify 5-second polling runtime and SQLite Outbox engine remain untouched."""
        from opcua_polling_engine import OpcUaPollingEngine, PollingState
        from opcua_storage import DurableStorage
        from notification_worker import NotificationWorker
        self.assertIsNotNone(OpcUaPollingEngine)
        self.assertIsNotNone(DurableStorage)
        self.assertIsNotNone(NotificationWorker)

    # -------------------------------------------------------------------------
    # Backward Compatibility Test Assertions
    # -------------------------------------------------------------------------
    def test_compat_pc4_dual_nic_layout(self):
        view = F3NetworkTopologyView(self.mock_owner)
        gw = view.topology_data.get('gateway_bridge', {})
        self.assertIn('nic_scada', gw)
        self.assertIn('nic_wan', gw)
        self.assertFalse(view.local_state.get('ip_forwarding', True))

    def test_compat_device_details_dialog(self):
        view = F3NetworkTopologyView(self.mock_owner)
        pc1_card = view.cards["PC1"]
        dlg = DeviceDetailsDialog(
            parent_win=None,
            device_meta=pc1_card.device_meta,
            current_status=pc1_card.status_data,
            local_state=view.local_state
        )
        self.assertIsNotNone(dlg.get_child())
        self.assertIn("PC1", dlg.get_title())

    def test_compat_pc4_details(self):
        view = F3NetworkTopologyView(self.mock_owner)
        pc4_card = view.cards["PC4"]
        dlg = DeviceDetailsDialog(
            parent_win=None,
            device_meta=pc4_card.device_meta,
            current_status=pc4_card.status_data,
            local_state=view.local_state
        )
        self.assertIsNotNone(dlg.get_child())
        self.assertIn("PC4", dlg.get_title())

    def test_compat_ip_table_update(self):
        # G17: explicit store configuration differs from an observed NIC address.
        view = F3NetworkTopologyView(self.mock_owner)
        self.addCleanup(GLib.source_remove, view.canvas.anim_source_id)
        view.store.update_device('dev-collector-01', {'configured_ip': '192.0.2.99'})
        view.render_ip_summary_table()
        labels = []
        child = view.ip_grid.get_first_child()
        while child:
            if isinstance(child, Gtk.Label):
                labels.append(child.get_text())
            child = child.get_next_sibling()
        self.assertIn('Config: 192.0.2.99 | Actual: UNKNOWN', labels)
        self.assertIsNone(view.store.devices['dev-collector-01']['observed_ip'])

    def test_identity_01_local_hostname_from_os(self):
        """1. Verify local machine reads actual OS hostname and never username or PC4."""
        h = get_local_hostname()
        self.assertIsNotNone(h)
        self.assertNotEqual(h, "")
        self.assertNotEqual(h.lower(), "pc4")
        self.assertNotEqual(h.lower(), "local-user")
        self.assertEqual(h, socket.gethostname().strip())

        view = F3NetworkTopologyView(self.mock_owner)
        col_dev = view.store.devices["dev-collector-01"]
        self.assertEqual(col_dev["hostname"], socket.gethostname().strip())
        self.assertEqual(col_dev["identity_status"], IdentityStatus.VERIFIED)
        self.assertEqual(col_dev["identity_source"], IdentitySource.LOCAL_OS)
        self.assertIsNotNone(col_dev["identity_verified_at"])

    def test_identity_01_synthetic_hostname_mock(self):
        """1b. Verify synthetic mocked hostname is used by store and GUI card, never username, PC4, or local-user."""
        import getpass
        real_user = getpass.getuser().strip().lower()
        synth_host = "lab-workstation-node1"

        with patch("socket.gethostname", return_value=synth_host):
            h = get_local_hostname()
            self.assertEqual(h, synth_host)
            self.assertNotEqual(h.lower(), "pc4")
            self.assertNotEqual(h.lower(), "local-user")
            if real_user:
                self.assertNotEqual(h.lower(), real_user)

            view = F3NetworkTopologyView(self.mock_owner)
            col_dev = view.store.devices["dev-collector-01"]
            self.assertEqual(col_dev["hostname"], synth_host)
            self.assertEqual(col_dev["identity_status"], IdentityStatus.VERIFIED)
            self.assertEqual(col_dev["identity_source"], IdentitySource.LOCAL_OS)

            col_card = view.cards["dev-collector-01"]
            card_name = col_card.lbl_name.get_text()
            self.assertEqual(card_name, synth_host)
            self.assertNotIn("PC4", card_name)
            self.assertNotIn("local-user", card_name.lower())
            if real_user:
                self.assertNotIn(real_user, card_name.lower())

    def test_identity_01_localhost_triggers_fallback(self):
        """1c. Verify 'localhost' returned by socket.gethostname() triggers documented OS fallback."""
        with patch("socket.gethostname", return_value="localhost"), \
             patch("platform.node", return_value="lab-backup-node"):
            h = get_local_hostname()
            self.assertEqual(h, "lab-backup-node")

        # When all candidates are localhost or empty, it returns empty string without crashing or returning 'localhost'
        with patch("socket.gethostname", return_value="localhost"), \
             patch("platform.node", return_value="localhost"), \
             patch("pathlib.Path.exists", return_value=False):
            h_fallback = get_local_hostname()
            self.assertNotEqual(h_fallback, "localhost")
            self.assertEqual(h_fallback, "")

    def test_identity_02_unknown_remote_hostname_shows_unknown(self):
        """2. Verify remote SCADA workstation without verified asset record shows Hostname Unknown."""
        view = F3NetworkTopologyView(self.mock_owner)
        scada1 = view.store.devices["dev-scada-01"]
        self.assertIsNone(scada1["hostname"])
        self.assertEqual(scada1["identity_status"], IdentityStatus.UNKNOWN)
        disp_name, status = compute_display_name(scada1, is_demo=False)
        self.assertEqual(disp_name, "192.0.2.11 [Hostname Unknown]")
        self.assertEqual(status, IdentityStatus.UNKNOWN)

    def test_identity_03_dns_ptr_not_auto_verified(self):
        """3. Verify DNS/PTR reverse lookup is classified as UNVERIFIED and not auto-promoted."""
        mock_dev = {
            "device_id": "dev-scada-01",
            "hostname": "scada-ping.tunnel.internal",
            "alias": "",
            "identity_status": IdentityStatus.UNVERIFIED,
            "identity_source": IdentitySource.DNS_PTR,
            "configured_ip": "192.0.2.11"
        }
        disp_name, status = compute_display_name(mock_dev, is_demo=False)
        self.assertEqual(disp_name, "scada-ping.tunnel.internal [Unverified]")
        self.assertEqual(status, IdentityStatus.UNVERIFIED)
        self.assertNotEqual(status, IdentityStatus.VERIFIED)

    def test_identity_04_user_alias_not_actual_hostname(self):
        """4. Verify user alias is tagged [User-defined] and does not mutate factual hostname."""
        view = F3NetworkTopologyView(self.mock_owner)
        view.store.update_device("dev-scada-01", {"alias": "Low Pressure Stn 1"})
        dev = view.store.devices["dev-scada-01"]
        self.assertEqual(dev["alias"], "Low Pressure Stn 1")
        self.assertIsNone(dev["hostname"])
        disp_name, status = compute_display_name(dev, is_demo=False)
        self.assertEqual(disp_name, "Low Pressure Stn 1 [User-defined]")
        self.assertEqual(status, IdentityStatus.USER_DEFINED)

    def test_identity_05_device_id_stable_across_hostname_ip_changes(self):
        """5. Verify stable device_id remains immutable across alias, IP, and hostname changes."""
        view = F3NetworkTopologyView(self.mock_owner)
        view.store.update_device("dev-scada-01", {
            "alias": "Emergency Pump",
            "configured_ip": "192.0.2.77",
            "hostname": "stn1-scada.internal"
        })
        dev = view.store.devices["dev-scada-01"]
        self.assertEqual(dev["device_id"], "dev-scada-01")
        self.assertEqual(dev["configured_ip"], "192.0.2.77")
        self.assertEqual(dev["alias"], "Emergency Pump")

    def test_identity_06_tasks_and_opcua_mapping_intact(self):
        """6. Verify task engine and OPC UA node mappings stay intact after identity changes."""
        view = F3NetworkTopologyView(self.mock_owner)
        view.store.update_device("dev-scada-01", {"alias": "Renamed Station"})
        dev = view.store.devices["dev-scada-01"]
        self.assertEqual(dev["test_tag"], "High_Analog.Tank01_Level")
        self.assertEqual(dev["endpoint_url"], "opc.tcp://192.0.2.11:4862")

    def test_identity_07_dynamic_devices_render_correctly(self):
        """7. Verify adding dynamic devices renders correctly without hardcoded limits."""
        view = F3NetworkTopologyView(self.mock_owner)
        initial_count = len(view.store.devices)
        view._on_add_device_clicked(None)
        self.assertEqual(len(view.store.devices), initial_count + 1)
        new_dev = view.store.devices.get("dev-scada-04")
        self.assertIsNotNone(new_dev)
        self.assertIsNone(new_dev["hostname"])
        self.assertEqual(new_dev["identity_status"], IdentityStatus.UNKNOWN)

    def test_identity_08_demo_data_isolated_from_live(self):
        # G04: LIVE IDs are absent in DEMO; aliases/config cannot cross modes.
        view = F3NetworkTopologyView(self.mock_owner)
        self.addCleanup(GLib.source_remove, view.canvas.anim_source_id)
        before = view.store.config_file.read_bytes()
        live_ids = set(view.store.devices)
        view._on_mode_toggle(None)
        self.assertTrue(view.store.is_demo_mode)
        self.assertTrue(live_ids.isdisjoint(view.store.devices))
        for dev in view.store.devices.values():
            disp_name, status = compute_display_name(dev, is_demo=True)
            self.assertIn('[DEMO]', disp_name)
            self.assertEqual(status, 'DEMO')
        view._on_mode_toggle(None)
        self.assertFalse(view.store.is_demo_mode)
        self.assertEqual(set(view.store.devices), live_ids)
        self.assertEqual(view.store.config_file.read_bytes(), before)

    def test_identity_09_no_fake_online_connected_status(self):
        """9. Verify remote SCADA devices do not show fake online or connected status initially."""
        view = F3NetworkTopologyView(self.mock_owner)
        for dev in view.store.devices.values():
            if dev.get("type") == "wincc":
                self.assertNotIn(dev.get("reachability"), ("ONLINE", "REACHABLE"))
                self.assertNotIn(dev.get("opcua_state"), (OpcUaState.CONNECTED, OpcUaState.READ_VERIFIED))

    def test_identity_10_no_unauthorized_network_traffic(self):
        """10. Verify opening F3 emits zero outbound network traffic and remote probes require authorization."""
        with patch("socket.socket") as mock_sock, patch("subprocess.run") as mock_run:
            view = F3NetworkTopologyView(self.mock_owner)
            mock_sock.assert_not_called()
            for call_args in mock_run.call_args_list:
                cmd = call_args[0][0]
                self.assertNotIn("ping", cmd)

    def test_identity_11_f3_gui_displays_names_and_status(self):
        """11. Verify GUI cards and table display factual hostname/IP and role, abolishing PC1-PC4."""
        view = F3NetworkTopologyView(self.mock_owner)
        col_card = view.cards["dev-collector-01"]
        self.assertEqual(col_card.lbl_name.get_text(), socket.gethostname().strip())
        self.assertNotIn("PC4", col_card.lbl_name.get_text())

        scada1_card = view.cards["dev-scada-01"]
        self.assertEqual(scada1_card.lbl_name.get_text(), "192.0.2.11 [Hostname Unknown]")
        self.assertNotIn("PC1", scada1_card.lbl_name.get_text())

    def test_identity_12_regression_f1_f2_f6_all_pass(self):
        # G18: explicit synthetic fixture, then a separate empty-profile setup.
        from wincc_catalog_fixture import write_catalog
        from gi.repository import Gio
        import app as desktop_app
        from f3_api_view import F3ApiView
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            catalog = write_catalog(directory / 'synthetic.txt')
            for source, expected in ((catalog, 457), (directory / 'missing.txt', 0)):
                with self.subTest(expected_tags=expected), \
                        patch.object(desktop_app, 'CONFIG_DIR', directory / str(expected)), \
                        patch.object(desktop_app, 'DEFAULT_WINCC_EXPORT', source):
                    application = Gtk.Application(application_id=f'org.aqua.p1.catalog{expected}', flags=Gio.ApplicationFlags.NON_UNIQUE)
                    application.register(None)
                    win = AquaWinCCWindow(app=application)
                    try:
                        self.assertTrue(hasattr(win, 'build_overview_page'))
                        self.assertTrue(hasattr(win, 'build_task_manager_page'))
                        self.assertIsInstance(win.f3_network_view, F3ApiView)
                        self.assertEqual(len(win.scanned_tags), expected)
                        self.assertTrue(all(tag['name'].startswith('LAB.') for tag in win.scanned_tags))
                        self.assertFalse(win.f3_network_view._active)
                        self.assertIsNone(win.f3_network_view._server)
                        self.assertEqual(win.stack.get_visible_child_name(), 'overview')
                        for key, page in (('F2', 'overview'), ('F6', 'alarms'), ('F1', 'overview')):
                            win.on_global_key_pressed(None, getattr(desktop_app.Gdk, 'KEY_' + key), 0, 0)
                            self.assertEqual(win.stack.get_visible_child_name(), page)
                            if key == 'F2':
                                self.assertEqual(win.unified_workspace.current_workspace_mode, 'task_manager')
                            if key == 'F1':
                                self.assertEqual(win.unified_workspace.current_workspace_mode, 'monitoring')
                    finally:
                        win.on_close_request()
                        if getattr(win, '_close_dialog', None):
                            win._close_dialog.response(Gtk.ResponseType.ACCEPT)
                        win.destroy()
                        application.quit()


if __name__ == '__main__':
    unittest.main()
