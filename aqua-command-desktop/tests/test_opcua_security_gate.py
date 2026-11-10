#!/usr/bin/env python3
"""
Test suite for SEC-04 OPC UA Security Gate Hardening.
Tests positive and negative paths for:
- SecurityPolicy normalization and strict allowlist enforcement
- Rejection of plaintext credentials over unencrypted channels (None / #None)
- Prevention of security downgrade
- Fail-closed X.509 PKI certificate validation (missing, expired, untrusted)
- Preflight check rejection of invalid policies
"""

import asyncio
import sys
import unittest
from pathlib import Path
from unittest.mock import MagicMock, AsyncMock, patch

# Ensure paths
desktop_dir = Path(__file__).resolve().parent.parent / "desktop"
if str(desktop_dir) not in sys.path:
    sys.path.insert(0, str(desktop_dir))

from opcua_polling_engine import OpcUaPollingEngine
from opcua_reader import ManualOpcUaReader
from opcua_mapping import NodeIdMapper
from opcua_store import ObservableStateStore
from opcua_storage import DurableStorage
from opcua_pki import PkiManager
from task_engine import TaskEngine
from opcua_policy import (
    normalize_security_policy,
    assert_secure_channel_for_auth,
    POLICY_NONE,
    POLICY_BASIC256SHA256,
    URI_POLICY_NONE,
    URI_POLICY_BASIC256SHA256,
)


class TestOpcUaSecurityGate(unittest.TestCase):
    def setUp(self):
        self.mapper = MagicMock(spec=NodeIdMapper)
        self.store = MagicMock(spec=ObservableStateStore)
        self.storage = MagicMock(spec=DurableStorage)
        self.task_engine = MagicMock(spec=TaskEngine)
        self.task_engine.get_required_tags.return_value = ["Tag1"]
        self.pki = MagicMock(spec=PkiManager)
        self.pki.DEFAULT_APP_URI = "urn:aquacmd:client"

    def test_opcua_reader_has_serialization_imported(self):
        """Verifies that serialization is imported in opcua_reader module (no NameError)."""
        import opcua_reader
        self.assertTrue(hasattr(opcua_reader, "serialization"), "serialization must be imported in opcua_reader")
        from cryptography.hazmat.primitives import serialization
        self.assertIs(opcua_reader.serialization, serialization)

    def test_policy_normalization_allowlist(self):
        """Positive test: Valid short names and full OPC UA URIs normalize to canonical policy names."""
        self.assertEqual(normalize_security_policy("None"), POLICY_NONE)
        self.assertEqual(normalize_security_policy("none"), POLICY_NONE)
        self.assertEqual(normalize_security_policy(URI_POLICY_NONE), POLICY_NONE)
        self.assertEqual(normalize_security_policy("Basic256Sha256"), POLICY_BASIC256SHA256)
        self.assertEqual(normalize_security_policy("basic256sha256"), POLICY_BASIC256SHA256)
        self.assertEqual(normalize_security_policy(URI_POLICY_BASIC256SHA256), POLICY_BASIC256SHA256)

    def test_policy_normalization_rejects_unsupported_or_malformed(self):
        """Negative test: Malformed, unrecognized, or deprecated policies fail closed with ValueError."""
        invalid_policies = [
            "",
            "   ",
            None,
            123,
            "Basic128Rsa15",  # Insecure / deprecated
            "Basic256",        # SHA-1 deprecated
            "Aes128_Sha256_RsaOaep",
            "InsecureCustomPolicy",
            "http://opcfoundation.org/UA/SecurityPolicy#Invalid",
        ]
        for p in invalid_policies:
            with self.assertRaises(ValueError, msg=f"Should reject invalid policy: {p}"):
                normalize_security_policy(p)

    def test_polling_engine_rejects_username_on_none_policy(self):
        """Negative test: Username authentication on SecurityPolicy=None must fail-closed with PermissionError."""
        engine = OpcUaPollingEngine(
            mapper=self.mapper,
            store=self.store,
            storage=self.storage,
            task_engine=self.task_engine,
            pki=self.pki
        )
        engine.endpoint_url = "opc.tcp://127.0.0.1:4840"
        engine.sec_policy = "None"
        engine.auth_mode = "Username"
        engine.username = "admin"
        engine.password = "secretpassword"

        loop = asyncio.new_event_loop()
        try:
            with self.assertRaises(PermissionError) as ctx:
                loop.run_until_complete(engine._create_and_connect_client())
            self.assertIn("Plaintext username/password is strictly forbidden", str(ctx.exception))
        finally:
            loop.close()

    def test_polling_engine_rejects_username_on_uri_none_policy(self):
        """Negative test: Username authentication on full URI SecurityPolicy#None must also fail-closed."""
        engine = OpcUaPollingEngine(
            mapper=self.mapper,
            store=self.store,
            storage=self.storage,
            task_engine=self.task_engine,
            pki=self.pki
        )
        engine.endpoint_url = "opc.tcp://127.0.0.1:4840"
        engine.sec_policy = URI_POLICY_NONE
        engine.auth_mode = "Username"
        engine.username = "admin"
        engine.password = "secretpassword"

        loop = asyncio.new_event_loop()
        try:
            with self.assertRaises(PermissionError) as ctx:
                loop.run_until_complete(engine._create_and_connect_client())
            self.assertIn("Plaintext username/password is strictly forbidden", str(ctx.exception))
        finally:
            loop.close()

    def test_reader_rejects_username_on_none_policy(self):
        """Negative test: ManualOpcUaReader rejects Username on SecurityPolicy=None."""
        reader = ManualOpcUaReader(mapper=self.mapper, store=self.store, pki=self.pki)
        obs = reader.read_tag_once_sync(
            tag_name="TestTag",
            endpoint_url="opc.tcp://127.0.0.1:4840",
            sec_policy="None",
            auth_mode="Username",
            username="admin",
            password="secretpassword"
        )
        self.assertEqual(obs.quality, "BAD")
        self.assertEqual(obs.raw_status_name, "BadSecurityChecksFailed")

    def test_reader_rejects_username_on_uri_none_policy(self):
        """Negative test: ManualOpcUaReader rejects Username on URI SecurityPolicy#None."""
        reader = ManualOpcUaReader(mapper=self.mapper, store=self.store, pki=self.pki)
        obs = reader.read_tag_once_sync(
            tag_name="TestTag",
            endpoint_url="opc.tcp://127.0.0.1:4840",
            sec_policy=URI_POLICY_NONE,
            auth_mode="Username",
            username="admin",
            password="secretpassword"
        )
        self.assertEqual(obs.quality, "BAD")
        self.assertEqual(obs.raw_status_name, "BadSecurityChecksFailed")

    def test_reader_rejects_invalid_policy_string(self):
        """Negative test: ManualOpcUaReader rejects unknown / invalid policy string fail-closed."""
        reader = ManualOpcUaReader(mapper=self.mapper, store=self.store, pki=self.pki)
        obs = reader.read_tag_once_sync(
            tag_name="TestTag",
            endpoint_url="opc.tcp://127.0.0.1:4840",
            sec_policy="Basic128Rsa15",
            auth_mode="Anonymous"
        )
        self.assertEqual(obs.quality, "BAD")
        self.assertEqual(obs.raw_status_name, "BadSecurityChecksFailed")

    def test_polling_engine_preflight_validates_policy(self):
        """Verifies run_preflight_checks rejects invalid policies and accepts allowed policies."""
        engine = OpcUaPollingEngine(
            mapper=self.mapper, store=self.store, storage=self.storage,
            task_engine=self.task_engine, pki=self.pki
        )
        ok_valid, _ = engine.run_preflight_checks("opc.tcp://127.0.0.1:4840", "None")
        self.assertTrue(ok_valid)

        ok_invalid, reason = engine.run_preflight_checks("opc.tcp://127.0.0.1:4840", "Deprecated_Policy")
        self.assertFalse(ok_invalid)
        self.assertIn("SEC-04", reason)

    def test_polling_engine_start_monitoring_rejects_insecure_combination(self):
        """Verifies start_monitoring rejects Username on SecurityPolicy None."""
        engine = OpcUaPollingEngine(
            mapper=self.mapper, store=self.store, storage=self.storage,
            task_engine=self.task_engine, pki=self.pki
        )
        ok, reason = engine.start_monitoring(
            endpoint_url="opc.tcp://127.0.0.1:4840",
            sec_policy="None",
            auth_mode="Username",
            username="admin",
            password="pwd"
        )
        self.assertFalse(ok)
        self.assertIn("Plaintext username/password is strictly forbidden", reason)

    def test_polling_engine_allows_anonymous_on_none_policy(self):
        """Positive test: Anonymous authentication on SecurityPolicy=None is permitted to proceed."""
        engine = OpcUaPollingEngine(
            mapper=self.mapper,
            store=self.store,
            storage=self.storage,
            task_engine=self.task_engine,
            pki=self.pki
        )
        engine.endpoint_url = "opc.tcp://127.0.0.1:4840"
        engine.sec_policy = "None"
        engine.auth_mode = "Anonymous"

        loop = asyncio.new_event_loop()
        try:
            with patch("opcua_polling_engine.Client") as MockClient:
                mock_inst = MagicMock()
                mock_inst.connect = AsyncMock()
                MockClient.return_value = mock_inst

                client = loop.run_until_complete(engine._create_and_connect_client())
                self.assertIs(client, mock_inst)
                mock_inst.connect.assert_called_once()
        finally:
            loop.close()

    def test_polling_engine_fails_closed_when_server_cert_missing_in_basic256(self):
        """Negative test: In Basic256Sha256 mode, if server certificate is missing, fail-closed."""
        engine = OpcUaPollingEngine(
            mapper=self.mapper,
            store=self.store,
            storage=self.storage,
            task_engine=self.task_engine,
            pki=self.pki
        )
        engine.endpoint_url = "opc.tcp://127.0.0.1:4840"
        engine.sec_policy = "Basic256Sha256"
        engine.auth_mode = "Anonymous"

        loop = asyncio.new_event_loop()
        try:
            with patch("opcua_polling_engine.Client") as MockClient:
                mock_inst = MagicMock()
                mock_inst.set_security_string = AsyncMock()
                mock_inst.security_policy.peer_certificate = None
                MockClient.return_value = mock_inst

                # Mock PKI ensure_client_certificate
                self.pki.ensure_client_certificate = MagicMock(return_value=("client.crt", "client.key"))

                with self.assertRaises(PermissionError) as ctx:
                    loop.run_until_complete(engine._create_and_connect_client())
                self.assertIn("Server certificate missing", str(ctx.exception))
        finally:
            loop.close()

    def test_polling_engine_fails_closed_when_server_cert_untrusted_or_expired(self):
        """Negative test: Server certificate failing trust/expiration check must fail-closed."""
        engine = OpcUaPollingEngine(
            mapper=self.mapper,
            store=self.store,
            storage=self.storage,
            task_engine=self.task_engine,
            pki=self.pki
        )
        engine.endpoint_url = "opc.tcp://127.0.0.1:4840"
        engine.sec_policy = "Basic256Sha256"
        engine.auth_mode = "Anonymous"

        # Mock invalid cert validation result
        self.pki.validate_server_certificate.return_value = {
            "valid": False,
            "status_code": "BadCertificateUntrusted",
            "error": "Untrusted server certificate in test"
        }

        loop = asyncio.new_event_loop()
        try:
            with patch("opcua_polling_engine.Client") as MockClient:
                mock_inst = MagicMock()
                mock_inst.set_security_string = AsyncMock()
                mock_inst.security_policy.peer_certificate = b"MOCK_CERT_BYTES"
                MockClient.return_value = mock_inst

                self.pki.ensure_client_certificate = MagicMock(return_value=("client.crt", "client.key"))

                with self.assertRaises(PermissionError) as ctx:
                    loop.run_until_complete(engine._create_and_connect_client())
                self.assertIn("BadCertificateUntrusted", str(ctx.exception))
        finally:
            loop.close()


if __name__ == "__main__":
    unittest.main()
