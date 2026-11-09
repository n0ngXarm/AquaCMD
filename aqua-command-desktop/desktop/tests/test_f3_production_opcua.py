"""Real trusted/rejected OPC UA sessions against an ephemeral loopback server."""
import asyncio
import json
import socket
import sys
import tempfile
import threading
import time
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from asyncua import Server, ua
from f3_opcua import SecureF3OpcUa
from opcua_mapping import NodeIdMapper, TagMapping
from opcua_pki import PkiManager
from test_opcua_security_gate import generate_ephemeral_cert_pair


class TestF3SecureReadPreflight(unittest.TestCase):
    def test_invalid_mapping_policy_and_port_are_refused_without_a_socket(self):
        device = {"endpoint_url": "opc.tcp://127.0.0.1:49327", "port": 49327, "test_tag": "LAB.Unmapped"}
        adapter = SecureF3OpcUa(NodeIdMapper(), object(), Path("/tmp"))
        with patch("opcua_reader.Client") as client:
            result = adapter.read_sync(device, {"sec_policy": "Basic256Sha256"})
            self.assertFalse(result["read_success"])
            self.assertIn("verified NodeId", result["last_error"])
            result = adapter.probe_sync(device, {"sec_policy": "None"})
            self.assertIn("Basic256Sha256", result["last_error"])
            device["port"] = 49328
            result = adapter.probe_sync(device, {"sec_policy": "Basic256Sha256"})
            self.assertIn("MISMATCH", result["last_error"])
            client.assert_not_called()


class TestF3SecureLoopback(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.profile = tempfile.TemporaryDirectory(prefix="aqua-f3-secure-lab-")
        cls.directory = Path(cls.profile.name)
        with socket.socket() as reservation:
            reservation.bind(("127.0.0.1", 0))
            cls.port = reservation.getsockname()[1]
        cls.endpoint = f"opc.tcp://127.0.0.1:{cls.port}/f3-lab/"
        cls.wrong_host_endpoint = f"opc.tcp://127.0.0.2:{cls.port}/f3-wrong-host/"
        cls.application_uri = "urn:aquacmd:f3:synthetic-server"
        der, key, _, _ = generate_ephemeral_cert_pair(cls.application_uri, "127.0.0.1")
        cls.der = der
        (cls.directory / "server.der").write_bytes(der)
        (cls.directory / "server.pem").write_bytes(key)
        cls.loop = asyncio.new_event_loop()
        cls.ready = threading.Event()
        cls.startup_error = None
        cls.thread = threading.Thread(target=cls.run_server, daemon=True)
        cls.thread.start()
        if not cls.ready.wait(10):
            raise RuntimeError("Synthetic OPC UA server startup timed out")
        if cls.startup_error:
            raise cls.startup_error

    @classmethod
    def run_server(cls):
        asyncio.set_event_loop(cls.loop)
        try:
            cls.loop.run_until_complete(cls.start_server())
        except Exception as error:
            cls.startup_error = error
        finally:
            cls.ready.set()
        cls.loop.run_forever()

    @classmethod
    async def start_server(cls):
        cls.server = Server()
        await cls.server.init()
        cls.server.set_endpoint(cls.endpoint)
        await cls.server.set_application_uri(cls.application_uri)
        cls.server.set_security_policy([ua.SecurityPolicyType.Basic256Sha256_SignAndEncrypt])
        await cls.server.load_certificate(cls.directory / "server.der")
        await cls.server.load_private_key(cls.directory / "server.pem")
        namespace = await cls.server.register_namespace("urn:aquacmd:f3:lab")
        await cls.server.nodes.objects.add_variable(ua.NodeId("Level", namespace), "LAB.Level", 42.5)
        await cls.server.start()
        cls.wrong_host_server = Server()
        await cls.wrong_host_server.init()
        cls.wrong_host_server.set_endpoint(cls.wrong_host_endpoint)
        await cls.wrong_host_server.set_application_uri(cls.application_uri)
        cls.wrong_host_server.set_security_policy([ua.SecurityPolicyType.Basic256Sha256_SignAndEncrypt])
        await cls.wrong_host_server.load_certificate(cls.directory / "server.der")
        await cls.wrong_host_server.load_private_key(cls.directory / "server.pem")
        await cls.wrong_host_server.start()

    @classmethod
    def tearDownClass(cls):
        asyncio.run_coroutine_threadsafe(cls.server.stop(), cls.loop).result(5)
        asyncio.run_coroutine_threadsafe(cls.wrong_host_server.stop(), cls.loop).result(5)
        cls.loop.call_soon_threadsafe(cls.loop.stop)
        cls.thread.join(5)
        cls.profile.cleanup()

    def setUp(self):
        profile = tempfile.TemporaryDirectory(prefix="aqua-f3-client-")
        self.addCleanup(profile.cleanup)
        self.pki = PkiManager(Path(profile.name) / "pki")
        self.mapper = NodeIdMapper()
        self.mapper.add_mapping(TagMapping("LAB.Level", "s=Level", "urn:aquacmd:f3:lab", verified=True))
        self.adapter = SecureF3OpcUa(self.mapper, self.pki, Path(profile.name))
        self.device = {"endpoint_url": self.endpoint, "port": self.port, "test_tag": "LAB.Level"}
        self.options = {"sec_policy": "Basic256Sha256", "auth_mode": "Anonymous"}

    def test_trusted_session_is_connected_then_explicitly_closed(self):
        self.pki.trust_certificate(self.der)
        opened = []
        result = self.adapter.probe_sync(self.device, self.options, opened.append)
        self.assertEqual(len(opened), 1, result)
        self.assertEqual(opened[0]["session_state"], "CONNECTED")
        self.assertEqual(result["certificate_trust"], "TRUSTED")
        self.assertEqual(result["session_state"], "DISCONNECTED")
        self.assertTrue(result["session_verified"])
        self.assertFalse(result["read_success"])
        self.assertIsNotNone(result["last_session_success"])

    def test_existing_secure_reader_uses_verified_mapping_and_actual_value(self):
        self.pki.trust_certificate(self.der)
        result = self.adapter.read_sync(self.device, self.options)
        self.assertTrue(result["read_success"], result)
        self.assertEqual(result["quality"], "GOOD")
        self.assertEqual(result["value"], 42.5)
        self.assertIn("s=Level", result["node_id"])
        self.assertEqual(result["certificate_trust"], "TRUSTED")
        self.assertEqual(result["session_state"], "DISCONNECTED")
        self.assertIsNotNone(result["source_timestamp"])

    def test_untrusted_certificate_never_opens_a_session_or_reads(self):
        opened = []
        result = self.adapter.probe_sync(self.device, self.options, opened.append)
        self.assertEqual(opened, [])
        self.assertFalse(result["session_verified"])
        self.assertEqual(result["opcua_state"], "CERTIFICATE_UNTRUSTED")
        self.assertNotEqual(result["certificate_trust"], "TRUSTED")
        result = self.adapter.read_sync(self.device, self.options)
        self.assertFalse(result["read_success"])
        self.assertEqual(result["opcua_state"], "CERTIFICATE_UNTRUSTED")

    def test_trusted_certificate_with_wrong_hostname_is_still_rejected(self):
        self.pki.trust_certificate(self.der)
        # The existing PKI deliberately aliases localhost and 127.0.0.1.
        # A different loopback address is an actual SAN mismatch.
        self.device["endpoint_url"] = self.wrong_host_endpoint
        result = self.adapter.probe_sync(self.device, self.options)
        self.assertFalse(result["session_verified"])
        self.assertIn("HostName", result["certificate_trust"])

    def test_manual_authorization_to_actual_read_to_inspector_end_to_end(self):
        import f3_network as f3
        from gi.repository import GLib
        self.pki.trust_certificate(self.der)
        device = dict(self.device, device_id="loopback", type="wincc", configured_ip="127.0.0.1")
        (self.adapter.config_dir / "network_topology.json").write_text(json.dumps({"devices": [device]}))
        owner = SimpleNamespace(config_dir=self.adapter.config_dir, topology_data={}, opcua_mapper=self.mapper,
            pki=self.pki, opcua_config={"endpoint_url": self.endpoint, "security_policy": "Basic256Sha256", "auth_mode": "Anonymous"})
        view = f3.F3NetworkTopologyView(owner)
        self.addCleanup(GLib.source_remove, view.canvas.anim_source_id)
        with patch("f3_network.OTAuthorizationDialog") as authorization:
            view.trigger_device_read_once("loopback")
            authorization.assert_called_once()
            self.assertEqual(authorization.call_args.kwargs["device_ip"], self.endpoint)
            self.assertFalse(view.store.devices["loopback"]["read_success"])
            authorization.call_args.kwargs["on_authorized"]()
        deadline = time.monotonic() + 8
        context = GLib.MainContext.default()
        while view._remote_busy and time.monotonic() < deadline:
            while context.pending():
                context.iteration(False)
            time.sleep(0.005)
        self.assertFalse(view._remote_busy, "Real F3 read worker did not complete")
        dev = view.store.devices["loopback"]
        self.assertEqual(dev["last_read_value"], 42.5)
        self.assertEqual(dev["last_read_quality"], "GOOD")
        self.assertTrue(f3.evidence.read_verified(dev))
        self.assertFalse(f3.evidence.session_connected(dev))
        self.assertEqual(view.store.get_summary_stats()["opc_read_verified"], 1)
        self.assertEqual(view.store.get_summary_stats()["opc_connected"], 0)
        view.inspector.inspect_device("loopback")
        self.assertIn("42.5", view.inspector.lbl_last_read.get_text())
        self.assertEqual(view.inspector.lbl_session.get_text(), "DISCONNECTED")
        self.assertIn("TRUSTED", view.inspector.lbl_pki_sec.get_text())
