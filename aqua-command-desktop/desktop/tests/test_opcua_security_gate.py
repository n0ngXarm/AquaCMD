#!/usr/bin/env python3
"""
test_opcua_security_gate.py — Automated Security Gate Regression Suite for AQUA COMMAND
Validates OPC UA PKI Certificate Management, X.509 Trust Validation, Anti-Downgrade,
and Secure Read-Only Sessions.

Strict Safety Invariants:
- All test certificates and RSA keys generated ephemerally inside TemporaryDirectory.
- Zero secrets, zero credentials, zero production certificates, zero plant IPs committed.
- All network tests constrained 100% to synthetic loopback (127.0.0.1).
"""

import os
import sys
import asyncio
import tempfile
import threading
import unittest
import ipaddress
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Tuple

from cryptography import x509
from cryptography.x509.oid import NameOID, ExtendedKeyUsageOID
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa

# Add parent desktop path
desktop_dir = Path(__file__).resolve().parent.parent
if str(desktop_dir) not in sys.path:
    sys.path.insert(0, str(desktop_dir))

from opcua_pki import (
    PkiManager,
    SUPPORTED_POLICIES,
    POLICY_NONE,
    POLICY_BASIC256SHA256,
    MODE_SIGN_AND_ENCRYPT,
)
from opcua_store import ObservableStateStore, Quality, TagObservation
from opcua_mapping import NodeIdMapper
from opcua_reader import ManualOpcUaReader

# asyncua imports for loopback synthetic tests
try:
    from asyncua import Server, ua
    from asyncua.crypto.permission_rules import User, UserRole
    ASYNCUA_AVAILABLE = True
except ImportError:
    ASYNCUA_AVAILABLE = False


def generate_ephemeral_cert_pair(
    app_uri: str,
    host: str,
    expired: bool = False,
    ca_signer: bool = False
) -> Tuple[bytes, bytes, rsa.RSAPrivateKey, x509.Certificate]:
    """Generates an ephemeral RSA-2048 / SHA-256 certificate pair in memory."""
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    name = x509.Name([
        x509.NameAttribute(NameOID.ORGANIZATION_NAME, "AquaCMD Synthetic SCADA Test"),
        x509.NameAttribute(NameOID.COMMON_NAME, "WinCC Mock Endpoint"),
    ])
    now = datetime.now(timezone.utc)
    if expired:
        nb = now - timedelta(days=30)
        na = now - timedelta(days=1)
    else:
        nb = now - timedelta(minutes=10)
        na = now + timedelta(days=365)

    san_items = [
        x509.UniformResourceIdentifier(app_uri),
        x509.DNSName(host if not host.replace(".", "").isdigit() else "wincc.local"),
    ]
    try:
        san_items.append(x509.IPAddress(ipaddress.ip_address(host)))
    except ValueError:
        pass

    builder = (
        x509.CertificateBuilder()
        .subject_name(name)
        .issuer_name(name)
        .public_key(key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(nb)
        .not_valid_after(na)
        .add_extension(x509.BasicConstraints(ca=ca_signer, path_length=None), critical=True)
        .add_extension(x509.SubjectAlternativeName(san_items), critical=False)
    )
    cert = builder.sign(key, hashes.SHA256())
    der = cert.public_bytes(serialization.Encoding.DER)
    pem = key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.TraditionalOpenSSL,
        encryption_algorithm=serialization.NoEncryption(),
    )
    return der, pem, key, cert


class TestOpcUaSecurityGate(unittest.TestCase):
    """Regression test cases for OPC UA Security Gate."""

    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.pki_dir = Path(self.temp_dir.name) / "pki"
        self.pki = PkiManager(pki_dir=self.pki_dir)

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_01_client_certificate_generation_and_permissions(self):
        """Verifies client app certificate generation, RSA-2048, and 0600 key permissions."""
        cert_p, key_p = self.pki.ensure_client_certificate()
        self.assertTrue(cert_p.is_file(), "Client certificate DER must exist")
        self.assertTrue(key_p.is_file(), "Client private key PEM must exist")

        # Verify filesystem permissions (POSIX: 0600 on key, 0700 on private dir)
        if os.name == "posix":
            key_stat = key_p.stat().st_mode & 0o777
            self.assertEqual(key_stat, 0o600, "Private key must have strict 0600 permissions")
            dir_stat = key_p.parent.stat().st_mode & 0o777
            self.assertEqual(dir_stat, 0o700, "Private directory must have strict 0700 permissions")

        # Verify keypair cryptographic nonce validation
        cert = self.pki.load_cert_from_file(cert_p)
        key = self.pki.load_key_from_file(key_p)
        self.assertTrue(self.pki.validate_key_pair(cert, key), "Keypair must match cryptographically")

    def test_02_trusted_server_certificate_validation(self):
        """Verifies valid server certificate in trusted/certs is accepted."""
        der, _, _, cert = generate_ephemeral_cert_pair("urn:wincc:test_server", "127.0.0.1")
        # Trust the certificate
        self.pki.trust_certificate(der)
        self.assertTrue(self.pki.is_cert_trusted(cert), "Certificate must be trusted after manual promotion")

        res = self.pki.validate_server_certificate(
            cert_bytes=der,
            expected_host="127.0.0.1",
            expected_uri="urn:wincc:test_server",
            check_trust_store=True,
        )
        self.assertTrue(res["valid"], f"Expected valid, got error: {res.get('error')}")
        self.assertEqual(res["status_code"], "Good")
        self.assertIn("thumbprint", res["cert_info"])

    def test_03_unknown_certificate_rejection_and_quarantine(self):
        """Verifies untrusted certificate is rejected with BadCertificateUntrusted and quarantined."""
        der, _, _, cert = generate_ephemeral_cert_pair("urn:wincc:unknown_server", "127.0.0.1")
        res = self.pki.validate_server_certificate(
            cert_bytes=der,
            expected_host="127.0.0.1",
            check_trust_store=True,
        )
        self.assertFalse(res["valid"])
        self.assertEqual(res["status_code"], "BadCertificateUntrusted")
        self.assertIsNotNone(res.get("quarantine_path"))

        q_path = Path(res["quarantine_path"])
        self.assertTrue(q_path.is_file(), "Quarantined certificate file must exist in rejected/certs")
        self.assertEqual(q_path.parent, self.pki.rejected_certs_dir)

    def test_04_expired_certificate_rejection(self):
        """Verifies expired certificate is rejected with BadCertificateTimeInvalid."""
        der, _, _, _ = generate_ephemeral_cert_pair("urn:wincc:expired_server", "127.0.0.1", expired=True)
        res = self.pki.validate_server_certificate(
            cert_bytes=der,
            expected_host="127.0.0.1",
            check_trust_store=False,
        )
        self.assertFalse(res["valid"])
        self.assertEqual(res["status_code"], "BadCertificateTimeInvalid")
        self.assertIn("expired", res["error"])

    def test_05_hostname_and_uri_mismatch_rejection(self):
        """Verifies hostname or ApplicationURI mismatch is rejected."""
        der, _, _, _ = generate_ephemeral_cert_pair("urn:wincc:legit_server", "192.0.2.100")
        # Validate against 10.0.0.1
        res_host = self.pki.validate_server_certificate(
            cert_bytes=der,
            expected_host="10.0.0.1",
            check_trust_store=False,
        )
        self.assertFalse(res_host["valid"])
        self.assertEqual(res_host["status_code"], "BadCertificateHostNameInvalid")

        # Validate against mismatched URI
        res_uri = self.pki.validate_server_certificate(
            cert_bytes=der,
            expected_host="192.0.2.100",
            expected_uri="urn:wincc:different_server",
            check_trust_store=False,
        )
        self.assertFalse(res_uri["valid"])
        self.assertEqual(res_uri["status_code"], "BadCertificateUriInvalid")

    def test_06_certificate_replacement_detected(self):
        """Verifies changed certificate thumbprint for known server is detected and quarantined."""
        der1, _, _, cert1 = generate_ephemeral_cert_pair("urn:wincc:server", "127.0.0.1")
        thumb1 = self.pki.cert_thumbprint(cert1)
        self.pki.trust_certificate(der1)

        # Server changes certificate
        der2, _, _, _ = generate_ephemeral_cert_pair("urn:wincc:server", "127.0.0.1")
        res = self.pki.validate_server_certificate(
            cert_bytes=der2,
            expected_host="127.0.0.1",
            expected_thumbprint=thumb1,
            check_trust_store=True,
        )
        self.assertFalse(res["valid"])
        self.assertEqual(res["status_code"], "BadCertificateUntrusted")
        self.assertIn("changed unexpectedly", res["error"])

    def test_07_no_auto_trust_and_manual_promotion(self):
        """Verifies certificates are never auto-trusted; manual promotion required."""
        der, _, _, cert = generate_ephemeral_cert_pair("urn:wincc:server", "127.0.0.1")
        # Quarantining must NOT trust
        q_path = self.pki.quarantine_rejected_cert(der, "test_server", "Untrusted")
        self.assertFalse(self.pki.is_cert_trusted(cert), "Certificate in rejected/certs must NOT be trusted")

        # Explicit manual operator promotion
        self.pki.trust_certificate(q_path)
        self.assertTrue(self.pki.is_cert_trusted(cert), "Certificate must be trusted after manual promotion")
        self.assertFalse(q_path.exists(), "Source quarantined file must be removed upon promotion")

    def test_08_anti_downgrade_guardrail(self):
        """Verifies username authentication over SecurityPolicy#None is rejected pre-network."""
        store = ObservableStateStore()
        mapping_file = Path(self.temp_dir.name) / "mapping.json"
        mapping_file.write_text("""{
            "mappings": {
                "Allowed.Tag": {
                    "node_id_identifier": "s=Allowed.Tag",
                    "namespace_uri": "urn:test",
                    "data_type": "Float",
                    "verified": true
                }
            }
        }""")
        mapper = NodeIdMapper(mapping_file)
        reader = ManualOpcUaReader(mapper, store, self.pki_dir.parent, pki=self.pki)

        obs = reader.read_tag_once_sync(
            tag_name="Allowed.Tag",
            endpoint_url="opc.tcp://127.0.0.1:4840/none/",
            sec_policy="None",
            auth_mode="Username",
            username="operator",
            password="InsecurePassword",
        )
        self.assertEqual(obs.quality, Quality.BAD)
        self.assertEqual(obs.raw_status_name, "BadSecurityChecksFailed")
        self.assertIsNone(obs.value)

    def test_09_reader_strictly_read_only(self):
        """Verifies ManualOpcUaReader does not expose any write or mutation methods."""
        reader = ManualOpcUaReader(NodeIdMapper(), ObservableStateStore(), self.pki_dir.parent, pki=self.pki)
        self.assertFalse(hasattr(reader, "write_value"), "Reader must not implement write_value")
        self.assertFalse(hasattr(reader, "write_attribute"), "Reader must not implement write_attribute")
        self.assertFalse(hasattr(reader, "create_subscription"), "Reader must not implement background subscription")


@unittest.skipUnless(ASYNCUA_AVAILABLE, "asyncua required for loopback integration test")
class TestOpcUaLoopbackSecurityIntegration(unittest.TestCase):
    """End-to-end loopback integration tests with synthetic servers."""

    @classmethod
    def setUpClass(cls):
        cls.temp_dir = tempfile.TemporaryDirectory()
        cls.pki_dir = Path(cls.temp_dir.name) / "pki"
        cls.pki = PkiManager(pki_dir=cls.pki_dir)

        # Generate server certs
        cls.port_sec = 48590
        cls.port_auth = 48591
        cls.url_sec = f"opc.tcp://127.0.0.1:{cls.port_sec}/aquacmd/test_sec/"
        cls.url_auth = f"opc.tcp://127.0.0.1:{cls.port_auth}/aquacmd/test_auth/"
        cls.uri_sec = "urn:wincc:mock:test_sec"
        cls.uri_auth = "urn:wincc:mock:test_auth"

        der_s, pem_s, _, _ = generate_ephemeral_cert_pair(cls.uri_sec, "127.0.0.1")
        der_a, pem_a, _, _ = generate_ephemeral_cert_pair(cls.uri_auth, "127.0.0.1")

        cls.der_s_p = Path(cls.temp_dir.name) / "srv_sec.der"
        cls.pem_s_p = Path(cls.temp_dir.name) / "srv_sec.pem"
        cls.der_s_p.write_bytes(der_s)
        cls.pem_s_p.write_bytes(pem_s)

        cls.der_a_p = Path(cls.temp_dir.name) / "srv_auth.der"
        cls.pem_a_p = Path(cls.temp_dir.name) / "srv_auth.pem"
        cls.der_a_p.write_bytes(der_a)
        cls.pem_a_p.write_bytes(pem_a)

        # Pre-trust server_sec and server_auth
        cls.pki.trust_certificate(der_s)
        cls.pki.trust_certificate(der_a)

        cls.ready_event = threading.Event()
        cls.loop = asyncio.new_event_loop()
        cls.thread = threading.Thread(target=cls._run_servers, daemon=True)
        cls.thread.start()
        cls.ready_event.wait(timeout=10.0)

    @classmethod
    def _run_servers(cls):
        asyncio.set_event_loop(cls.loop)
        try:
            cls.loop.run_until_complete(cls._init_servers())
        except Exception:
            import traceback
            traceback.print_exc()
        finally:
            cls.ready_event.set()
        cls.loop.run_forever()

    @classmethod
    async def _init_servers(cls):
        cls.server_sec = Server()
        await cls.server_sec.init()
        cls.server_sec.set_endpoint(cls.url_sec)
        await cls.server_sec.set_application_uri(cls.uri_sec)
        cls.server_sec.set_security_policy([ua.SecurityPolicyType.Basic256Sha256_SignAndEncrypt])
        await cls.server_sec.load_certificate(str(cls.der_s_p))
        await cls.server_sec.load_private_key(str(cls.pem_s_p))
        idx = await cls.server_sec.register_namespace("urn:aquacmd:test")
        await cls.server_sec.nodes.objects.add_variable(
            ua.NodeId("Test_Metric", idx), "Test_Metric", 99.4, ua.VariantType.Float
        )
        await cls.server_sec.start()

        cls.server_auth = Server()
        await cls.server_auth.init()
        cls.server_auth.set_endpoint(cls.url_auth)
        await cls.server_auth.set_application_uri(cls.uri_auth)
        cls.server_auth.set_security_policy([ua.SecurityPolicyType.Basic256Sha256_SignAndEncrypt])
        await cls.server_auth.load_certificate(str(cls.der_a_p))
        await cls.server_auth.load_private_key(str(cls.pem_a_p))

        class MockUserManager:
            def get_user(self, iserver, username=None, password=None, certificate=None):
                if username == "admin" and password == "SecretPass123":
                    return User(role=UserRole.User)
                return None

        cls.server_auth.iserver.user_manager = MockUserManager()
        await cls.server_auth.start()

    @classmethod
    def tearDownClass(cls):
        async def _stop():
            if hasattr(cls, 'server_sec'):
                await cls.server_sec.stop()
            if hasattr(cls, 'server_auth'):
                await cls.server_auth.stop()
        if cls.loop:
            asyncio.run_coroutine_threadsafe(_stop(), cls.loop).result(timeout=5.0)
            cls.loop.call_soon_threadsafe(cls.loop.stop)
        cls.temp_dir.cleanup()

    def test_10_f1_read_once_via_secure_channel(self):
        """Verifies F1 single-shot read succeeds over trusted Basic256Sha256 SecureChannel."""
        store = ObservableStateStore()
        # Create minimal mapping
        mapping_file = Path(self.temp_dir.name) / "mapping.json"
        mapping_file.write_text("""{
            "mappings": {
                "Test_Metric": {
                    "namespace_uri": "urn:aquacmd:test",
                    "node_id_identifier": "s=Test_Metric",
                    "data_type": "Float",
                    "unit": "bar",
                    "verified": true
                }
            }
        }""")
        mapper = NodeIdMapper(mapping_file)
        reader = ManualOpcUaReader(mapper, store, self.pki_dir.parent, pki=self.pki)

        obs = reader.read_tag_once_sync(
            tag_name="Test_Metric",
            endpoint_url=self.url_sec,
            sec_policy="Basic256Sha256",
            auth_mode="Anonymous",
            timeout=4.0
        )
        self.assertEqual(obs.quality, Quality.GOOD)
        self.assertAlmostEqual(obs.value, 99.4, places=2)
        self.assertEqual(obs.unit, "bar")

    def test_11_wrong_credentials_rejected_without_leakage(self):
        """Verifies wrong username/password rejected over SecureChannel without secret leakage."""
        from asyncua import Client
        client = Client(url=self.url_auth, timeout=3.0)
        cert_p, key_p = self.pki.ensure_client_certificate()

        async def _test():
            await client.set_security_string(f"Basic256Sha256,SignAndEncrypt,{cert_p},{key_p}")
            client.set_user("admin")
            secret_pass = "INCORRECT_SECRET_PASSWORD"
            client.set_password(secret_pass)
            try:
                async with client:
                    pass
                return False, "Expected BadUserAccessDenied"
            except Exception as e:
                err_str = str(e)
                # Ensure secret password never appears in exception message
                self.assertNotIn(secret_pass, err_str, "Secret password must not leak in error message")
                return True, err_str

        loop = asyncio.new_event_loop()
        try:
            ok, msg = loop.run_until_complete(_test())
            self.assertTrue(ok, f"Expected rejection, got: {msg}")
            self.assertIn("BadUserAccessDenied", msg)
        finally:
            loop.close()


if __name__ == "__main__":
    unittest.main()
