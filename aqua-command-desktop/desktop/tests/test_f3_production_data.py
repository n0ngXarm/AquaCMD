"""Data-integrity regressions for the operator's production F3 contract."""
import json
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import f3_network as f3
from gi.repository import GLib


class TestF3ProductionData(unittest.TestCase):
    def setUp(self):
        self.profile = tempfile.TemporaryDirectory()
        self.addCleanup(self.profile.cleanup)
        self.config = Path(self.profile.name) / "network_topology.json"

    def store(self, devices=None):
        if devices is not None:
            self.config.write_text(json.dumps({"devices": devices}))
        return f3.F3DeviceStore(self.config)

    def remote(self, **extra):
        return dict(device_id="source-a", type="wincc", configured_ip="127.0.0.1",
                    endpoint_url="opc.tcp://127.0.0.1:49327", port=49327, **extra)

    def test_missing_inventory_does_not_invent_remote_devices(self):
        store = self.store()
        self.assertEqual([d for d in store.devices.values() if d.get("type") != "local_host"], [])

    def test_missing_target_and_port_stay_unknown(self):
        store = self.store([{"device_id": "source-a", "type": "wincc"}])
        dev = store.devices["source-a"]
        self.assertFalse(dev.get("configured_ip"), "No default IP may be fabricated")
        self.assertIsNone(dev.get("port"), "No default service port may be fabricated")

    def test_router_configuration_does_not_verify_its_identity(self):
        store = self.store([{"device_id": "dev-router-01", "type": "router",
                             "configured_ip": "127.0.0.2", "hostname": "configured-router"}])
        self.assertNotEqual(store.devices["dev-router-01"]["identity_status"], f3.IdentityStatus.VERIFIED)

    def test_persisted_observations_are_not_current_live_evidence(self):
        store = self.store([self.remote(reachability="REACHABLE", opcua_state="CONNECTED",
                                       session_state="CONNECTED", observed_ip="127.0.0.1")])
        self.assertEqual(store.get_summary_stats()["detected_count"], 0)
        self.assertEqual(store.get_summary_stats()["opc_connected"], 0)
        self.assertIsNone(store.devices["source-a"]["observed_ip"])

    def test_expired_observations_do_not_count_as_reachable(self):
        store = self.store([self.remote()])
        store.devices["source-a"].update(reachability="REACHABLE", last_checked_epoch=0,
                                          provenance="OBSERVED_REMOTE")
        self.assertEqual(store.get_summary_stats()["detected_count"], 0)

    def test_changing_target_invalidates_previous_observations(self):
        store = self.store([self.remote()])
        store.devices["source-a"].update(reachability="REACHABLE", observed_ip="127.0.0.1",
                                          opcua_state="CONNECTED", session_state="CONNECTED")
        store.update_device("source-a", {"configured_ip": "127.0.0.2"})
        self.assertNotEqual(store.devices["source-a"]["reachability"], "REACHABLE")
        self.assertIsNone(store.devices["source-a"]["observed_ip"])

    def test_local_carrier_does_not_assign_ot_or_wan_roles(self):
        self.store([{"device_id": "dev-collector-01", "type": "local_host"}])
        local = {"interfaces": {"wlp2s0": {"carrier": True, "ipv4": "127.0.0.1/8"}},
                 "timestamp": "test", "ip_forwarding": False, "hostname": "loopback-lab"}
        owner = SimpleNamespace(config_dir=Path(self.profile.name), topology_data={})
        with patch("f3_network.safe_get_local_network_state", return_value=local):
            view = f3.F3NetworkTopologyView(owner)
        self.addCleanup(GLib.source_remove, view.canvas.anim_source_id)
        collector = view.store.devices["dev-collector-01"]
        self.assertNotEqual(collector.get("wan_link_status"), "LINK_VERIFIED")
        self.assertNotEqual(collector.get("link_status"), "LINK_VERIFIED")

    def test_demo_inventory_is_isolated_from_live_configuration(self):
        store = self.store([self.remote(alias="Live station")])
        before = self.config.read_bytes()
        store.set_demo(True)
        self.assertNotIn("source-a", store.devices)
        self.assertTrue(all(d.get("is_demo") for d in store.devices.values()))
        store.save()
        self.assertEqual(self.config.read_bytes(), before)
        store.set_demo(False)
        self.assertIn("source-a", store.devices)
        self.assertEqual(store.devices["source-a"]["alias"], "Live station")
        self.assertFalse(any(d.get("is_demo") for d in store.devices.values()))
        self.assertEqual(store.get_summary_stats()["opc_connected"], 0)

    def test_configured_metadata_cannot_be_used_as_observation_evidence(self):
        store = self.store([self.remote()])
        dev = store.devices["source-a"]
        dev["reachability"] = "REACHABLE"
        f3.evidence.record_evidence(dev, "reachability", "CONFIGURED")
        self.assertEqual(store.get_summary_stats()["detected_count"], 0)

    def test_malformed_typed_configuration_is_disabled_and_cannot_crash_the_view(self):
        store = self.store([{"device_id": "malformed", "type": "wincc", "alias": ["unsafe"],
                             "configured_ip": {"bad": 1}, "port": "invalid", "network_zone": 42,
                             "enabled": "yes", "endpoint_url": "opc.tcp://127.0.0.1:49327"}])
        dev = store.devices["malformed"]
        self.assertFalse(dev["enabled"])
        self.assertTrue(dev["config_errors"])
        self.assertIsNotNone(f3.evidence.endpoint_target(dev)[2])
        owner = SimpleNamespace(config_dir=self.config.parent, topology_data={})
        view = f3.F3NetworkTopologyView(owner)
        self.addCleanup(GLib.source_remove, view.canvas.anim_source_id)
        self.assertEqual(view.store.get_summary_stats()["detected_count"], 0)

    def test_invalid_network_definition_is_a_configuration_mismatch(self):
        dev = self.remote(network_zone="SCADA_OT")
        state, reason = f3.evidence.network_binding(dev, {"interfaces": {}}, {"SCADA_OT": "invalid"})
        self.assertEqual(state, "CONFIGURATION MISMATCH")
        self.assertTrue(reason)

    def test_successful_manual_session_close_is_not_an_unreachable_service(self):
        store = self.store([self.remote()])
        dev = store.devices["source-a"]
        dev.update(opcua_state="DISCONNECTED", session_state="DISCONNECTED", session_verified=True)
        f3.evidence.record_evidence(dev, "session", "VERIFIED_OPCUA")
        self.assertEqual(store.get_summary_stats()["opc_unreachable"], 0)
        dev["tcp_ok"] = False
        f3.evidence.record_evidence(dev, "tcp", "OBSERVED_REMOTE")
        self.assertEqual(store.get_summary_stats()["opc_unreachable"], 1)
        dev["evidence"]["tcp"]["checked_at"] = 0
        self.assertEqual(store.get_summary_stats()["opc_unreachable"], 0)


if __name__ == "__main__":
    unittest.main()
