"""
AquaCMD OPC UA PKI & Certificate Management Subsystem
Security Gate Milestone Implementation

Provides comprehensive X.509 Application Certificate management,
PKI trust store operations, certificate validation with hostname enforcement,
CA chain & CRL revocation verification, and WinCC-compatible rejected/trusted quarantine workflows.
"""

import os
import sys
import socket
import logging
from pathlib import Path
from datetime import datetime, timezone, timedelta
from typing import Optional, Tuple, List, Dict, Any

from cryptography import x509
from cryptography.x509.oid import NameOID, ExtendedKeyUsageOID
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa, padding

logger = logging.getLogger("aquacmd.pki")

DEFAULT_KEY_SIZE = 2048
DEFAULT_VALIDITY_DAYS = 365
DEFAULT_APP_URI = "urn:aquacmd:desktop:client"
DEFAULT_PRODUCT_URI = "urn:aquacmd:desktop:client"
DEFAULT_APP_NAME = "AQUA COMMAND Desktop Companion"

# Supported Modern Security Policies (OPC UA Part 4 / Part 7)
SUPPORTED_POLICIES = {
    "http://opcfoundation.org/UA/SecurityPolicy#Basic256Sha256": "Basic256Sha256",
    "http://opcfoundation.org/UA/SecurityPolicy#Aes128_Sha256_RsaOaep": "Aes128_Sha256_RsaOaep",
    "http://opcfoundation.org/UA/SecurityPolicy#Aes256_Sha256_RsaPss": "Aes256_Sha256_RsaPss",
}

DEPRECATED_POLICIES = {
    "http://opcfoundation.org/UA/SecurityPolicy#Basic256": "Basic256 (Deprecated / SHA-1)",
    "http://opcfoundation.org/UA/SecurityPolicy#Basic128Rsa15": "Basic128Rsa15 (Broken / Insecure)",
}

POLICY_BASIC256SHA256 = "http://opcfoundation.org/UA/SecurityPolicy#Basic256Sha256"
POLICY_NONE = "http://opcfoundation.org/UA/SecurityPolicy#None"
MODE_SIGN_AND_ENCRYPT = "SignAndEncrypt"
MODE_SIGN = "Sign"
MODE_NONE = "None"


class PkiManager:
    """
    Manages the local PKI store for AQUA COMMAND OPC UA Client.
    Follows standard OPC UA directory structure:
      ~/.config/aqua-command/pki/
        own/
          certs/       (client_cert.der, client_cert.pem)
          private/     (client_key.pem - chmod 0600)
        trusted/
          certs/       (trusted server and CA certificates)
        rejected/
          certs/       (quarantined untrusted certificates)
        issuers/
          certs/       (intermediate/root CA certificates)
          crl/         (certificate revocation lists)
    """

    DEFAULT_APP_URI = DEFAULT_APP_URI
    DEFAULT_PRODUCT_URI = DEFAULT_PRODUCT_URI
    DEFAULT_APP_NAME = DEFAULT_APP_NAME

    def __init__(self, pki_dir: Optional[Path] = None):
        if pki_dir is None:
            self.pki_dir = Path.home() / ".config" / "aqua-command" / "pki"
        else:
            self.pki_dir = Path(pki_dir).resolve()

        self.own_certs_dir = self.pki_dir / "own" / "certs"
        self.own_private_dir = self.pki_dir / "own" / "private"
        self.trusted_certs_dir = self.pki_dir / "trusted" / "certs"
        self.rejected_certs_dir = self.pki_dir / "rejected" / "certs"
        self.issuers_certs_dir = self.pki_dir / "issuers" / "certs"
        self.issuers_crl_dir = self.pki_dir / "issuers" / "crl"

        self.client_cert_der = self.own_certs_dir / "client_cert.der"
        self.client_cert_pem = self.own_certs_dir / "client_cert.pem"
        self.client_key_pem = self.own_private_dir / "client_key.pem"

        self._ensure_directories()

    def _ensure_directories(self) -> None:
        """Create PKI directories with secure permissions."""
        for directory in [
            self.own_certs_dir,
            self.trusted_certs_dir,
            self.rejected_certs_dir,
            self.issuers_certs_dir,
            self.issuers_crl_dir,
        ]:
            directory.mkdir(parents=True, exist_ok=True)
            try:
                os.chmod(directory, 0o755)
            except OSError:
                pass

        # Private key directory must strictly be 0700
        self.own_private_dir.mkdir(parents=True, exist_ok=True)
        try:
            os.chmod(self.own_private_dir, 0o700)
        except OSError:
            pass

    def ensure_client_certificate(
        self,
        app_uri: str = DEFAULT_APP_URI,
        common_name: str = DEFAULT_APP_NAME,
        host_name: Optional[str] = None,
        ip_addresses: Optional[List[str]] = None,
        key_size: int = DEFAULT_KEY_SIZE,
        validity_days: int = DEFAULT_VALIDITY_DAYS,
        force_regenerate: bool = False,
    ) -> Tuple[Path, Path]:
        """
        Ensures a valid client application certificate and private key exist.
        If missing or expired or forced, generates a new self-signed X.509 cert.
        Returns: (cert_path_der, key_path_pem)
        """
        needs_gen = force_regenerate

        if not self.client_cert_der.is_file() or not self.client_key_pem.is_file():
            needs_gen = True
        else:
            # Check validity & key match
            try:
                cert = self.load_cert_from_file(self.client_cert_der)
                key = self.load_key_from_file(self.client_key_pem)
                now = datetime.now(timezone.utc)
                if cert.not_valid_before_utc > now or cert.not_valid_after_utc < now:
                    logger.warning("Existing client certificate has expired or is not yet valid. Regenerating.")
                    needs_gen = True
                elif not self.validate_key_pair(cert, key):
                    logger.warning("Existing client private key does not match certificate public key. Regenerating.")
                    needs_gen = True
            except Exception as e:
                logger.warning("Failed to validate existing certificate/key: %s. Regenerating.", e)
                needs_gen = True

        if needs_gen:
            self._generate_client_cert(
                app_uri=app_uri,
                common_name=common_name,
                host_name=host_name,
                ip_addresses=ip_addresses,
                key_size=key_size,
                validity_days=validity_days,
            )

        return self.client_cert_der, self.client_key_pem

    def _generate_client_cert(
        self,
        app_uri: str,
        common_name: str,
        host_name: Optional[str],
        ip_addresses: Optional[List[str]],
        key_size: int,
        validity_days: int,
    ) -> None:
        """Generates RSA private key and self-signed X.509 application certificate."""
        if host_name is None:
            try:
                host_name = socket.gethostname()
            except Exception:
                host_name = "localhost"

        # Generate RSA private key
        private_key = rsa.generate_private_key(
            public_exponent=65537,
            key_size=key_size,
        )

        # Subject & Issuer (Self-signed)
        subject = issuer = x509.Name([
            x509.NameAttribute(NameOID.ORGANIZATION_NAME, "AQUA COMMAND Automation"),
            x509.NameAttribute(NameOID.ORGANIZATIONAL_UNIT_NAME, "SCADA Client"),
            x509.NameAttribute(NameOID.COMMON_NAME, common_name),
        ])

        # Subject Alternative Names (SAN)
        san_items: List[x509.GeneralName] = [
            x509.UniformResourceIdentifier(app_uri),
            x509.DNSName(host_name),
        ]
        if host_name != "localhost":
            san_items.append(x509.DNSName("localhost"))

        # Add IP addresses
        import ipaddress
        if ip_addresses:
            for ip_str in ip_addresses:
                try:
                    san_items.append(x509.IPAddress(ipaddress.ip_address(ip_str)))
                except ValueError:
                    pass
        # Default loopback
        san_items.append(x509.IPAddress(ipaddress.ip_address("127.0.0.1")))

        # Times
        now = datetime.now(timezone.utc)
        not_before = now - timedelta(minutes=5)  # slight clock skew margin
        not_after = now + timedelta(days=validity_days)

        # Build certificate
        builder = (
            x509.CertificateBuilder()
            .subject_name(subject)
            .issuer_name(issuer)
            .public_key(private_key.public_key())
            .serial_number(x509.random_serial_number())
            .not_valid_before(not_before)
            .not_valid_after(not_after)
            .add_extension(
                x509.BasicConstraints(ca=False, path_length=None),
                critical=True,
            )
            .add_extension(
                x509.KeyUsage(
                    digital_signature=True,
                    content_commitment=True,
                    key_encipherment=True,
                    data_encipherment=True,
                    key_agreement=False,
                    key_cert_sign=False,
                    crl_sign=False,
                    encipher_only=False,
                    decipher_only=False,
                ),
                critical=True,
            )
            .add_extension(
                x509.ExtendedKeyUsage([
                    ExtendedKeyUsageOID.CLIENT_AUTH,
                ]),
                critical=False,
            )
            .add_extension(
                x509.SubjectAlternativeName(san_items),
                critical=False,
            )
            .add_extension(
                x509.SubjectKeyIdentifier.from_public_key(private_key.public_key()),
                critical=False,
            )
        )

        certificate = builder.sign(
            private_key=private_key,
            algorithm=hashes.SHA256(),
        )

        # Save private key (strictly chmod 0600)
        key_bytes = private_key.private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.TraditionalOpenSSL,
            encryption_algorithm=serialization.NoEncryption(),
        )
        with open(self.client_key_pem, "wb") as f:
            f.write(key_bytes)
        try:
            os.chmod(self.client_key_pem, 0o600)
        except OSError:
            pass

        # Save certificate in DER format
        der_bytes = certificate.public_bytes(serialization.Encoding.DER)
        with open(self.client_cert_der, "wb") as f:
            f.write(der_bytes)

        # Save certificate in PEM format as well
        pem_bytes = certificate.public_bytes(serialization.Encoding.PEM)
        with open(self.client_cert_pem, "wb") as f:
            f.write(pem_bytes)

        logger.info("Generated new client application certificate: %s", self.client_cert_der)

    @staticmethod
    def load_cert_from_file(cert_path: Path) -> x509.Certificate:
        """Loads an X.509 certificate from either DER or PEM file."""
        data = cert_path.read_bytes()
        try:
            return x509.load_der_x509_certificate(data)
        except Exception:
            return x509.load_pem_x509_certificate(data)

    @staticmethod
    def load_key_from_file(key_path: Path) -> rsa.RSAPrivateKey:
        """Loads an RSA private key from PEM file."""
        data = key_path.read_bytes()
        return serialization.load_pem_private_key(data, password=None)

    @staticmethod
    def validate_key_pair(cert: x509.Certificate, key: rsa.RSAPrivateKey) -> bool:
        """Cryptographically verifies that the private key corresponds to the certificate public key."""
        try:
            pub_key = cert.public_key()
            test_nonce = b"AquaCMD_KeyPair_Verification_Nonce"
            sig = key.sign(test_nonce, padding.PKCS1v15(), hashes.SHA256())
            pub_key.verify(sig, test_nonce, padding.PKCS1v15(), hashes.SHA256())
            return True
        except Exception:
            return False

    @staticmethod
    def cert_thumbprint(cert: x509.Certificate) -> str:
        """Computes SHA-256 fingerprint hex string."""
        return cert.fingerprint(hashes.SHA256()).hex().upper()

    def is_cert_trusted(self, cert: x509.Certificate) -> bool:
        """
        Checks whether the certificate matches any cert in trusted/certs
        by exact public key / fingerprint comparison.
        """
        cert_thumb = self.cert_thumbprint(cert)
        for cert_file in self.trusted_certs_dir.glob("*"):
            if cert_file.is_file() and cert_file.suffix.lower() in [".der", ".pem", ".crt"]:
                try:
                    trusted_cert = self.load_cert_from_file(cert_file)
                    if self.cert_thumbprint(trusted_cert) == cert_thumb:
                        return True
                except Exception:
                    continue
        return False

    def check_crl_revocation(self, cert: x509.Certificate) -> Tuple[bool, Optional[str]]:
        """
        Checks if the certificate serial number is listed in any active CRL in issuers/crl/.
        Returns (is_revoked, reason).
        """
        for crl_file in self.issuers_crl_dir.glob("*"):
            if crl_file.is_file() and crl_file.suffix.lower() in [".crl", ".der", ".pem"]:
                try:
                    data = crl_file.read_bytes()
                    try:
                        crl = x509.load_der_x509_crl(data)
                    except Exception:
                        crl = x509.load_pem_x509_crl(data)

                    # Check if CRL issuer matches cert issuer
                    if crl.issuer == cert.issuer:
                        revoked_entry = crl.get_revoked_certificate_by_serial_number(cert.serial_number)
                        if revoked_entry:
                            rev_date = revoked_entry.revocation_date_utc.isoformat()
                            return True, f"Revoked on {rev_date} (Serial: {hex(cert.serial_number)})"
                except Exception as e:
                    logger.warning("Failed to inspect CRL file %s: %s", crl_file, e)
        return False, None

    def verify_issuer_chain(self, cert: x509.Certificate) -> Tuple[bool, str, Optional[str]]:
        """
        Validates certificate chain against trusted intermediate / root CAs in issuers/certs/.
        Returns (is_valid, status_code, message).
        """
        # If self-signed
        if cert.issuer == cert.subject:
            return True, "Good", "Self-signed certificate"

        # Search issuers/certs/ for matching issuer
        issuer_found = False
        for ca_file in self.issuers_certs_dir.glob("*"):
            if ca_file.is_file() and ca_file.suffix.lower() in [".der", ".pem", ".crt"]:
                try:
                    ca_cert = self.load_cert_from_file(ca_file)
                    if ca_cert.subject == cert.issuer:
                        issuer_found = True
                        # Verify signature of cert using CA public key
                        try:
                            ca_pub = ca_cert.public_key()
                            # Verify signature
                            ca_pub.verify(
                                cert.signature,
                                cert.tbs_certificate_bytes,
                                padding.PKCS1v15(),
                                cert.signature_hash_algorithm,
                            )
                            return True, "Good", f"Verified by CA: {ca_cert.subject.rfc4514_string()}"
                        except Exception:
                            return False, "BadCertificateInvalid", "Certificate signature does not match CA public key (Tampered or Corrupt)"
                except Exception:
                    continue

        if not issuer_found:
            return False, "BadCertificateIssuerUntrusted", f"Issuer '{cert.issuer.rfc4514_string()}' not found in issuers/certs/"

        return True, "Good", None

    def quarantine_rejected_cert(
        self,
        cert_bytes: bytes,
        server_uri: Optional[str] = None,
        reason: str = "Untrusted",
    ) -> Path:
        """
        Saves an untrusted server certificate to rejected/certs with sanitized metadata.
        Returns the path to the quarantined certificate.
        """
        try:
            try:
                cert = x509.load_der_x509_certificate(cert_bytes)
            except Exception:
                cert = x509.load_pem_x509_certificate(cert_bytes)
            thumb = self.cert_thumbprint(cert)[:16]
            clean_uri = "".join(c if c.isalnum() else "_" for c in (server_uri or "server"))[:32]
            filename = f"rejected_{clean_uri}_{thumb}.der"
        except Exception:
            filename = f"rejected_unknown_{int(datetime.now().timestamp())}.der"

        target_path = self.rejected_certs_dir / filename
        with open(target_path, "wb") as f:
            f.write(cert_bytes)

        logger.warning(
            "Quarantined untrusted certificate to: %s (Reason: %s)",
            target_path,
            reason,
        )
        return target_path

    def trust_certificate(self, cert_file_or_bytes: Any) -> Path:
        """
        Explicit operator action: Moves or saves a certificate into trusted/certs.
        NO automatic promotion is ever performed.
        """
        if isinstance(cert_file_or_bytes, Path):
            data = cert_file_or_bytes.read_bytes()
            src_file = cert_file_or_bytes
        elif isinstance(cert_file_or_bytes, bytes):
            data = cert_file_or_bytes
            src_file = None
        else:
            raise ValueError("Expected Path or bytes")

        try:
            cert = x509.load_der_x509_certificate(data)
        except Exception:
            cert = x509.load_pem_x509_certificate(data)

        thumb = self.cert_thumbprint(cert)[:16]
        target_path = self.trusted_certs_dir / f"trusted_{thumb}.der"
        with open(target_path, "wb") as f:
            f.write(cert.public_bytes(serialization.Encoding.DER))

        # If source file was in rejected/, remove it
        if src_file and src_file.parent == self.rejected_certs_dir and src_file.exists():
            try:
                src_file.unlink()
            except OSError:
                pass

        logger.info("Successfully trusted certificate: %s", target_path)
        return target_path

    def validate_server_certificate(
        self,
        cert_bytes: bytes,
        expected_host: str,
        expected_uri: Optional[str] = None,
        expected_thumbprint: Optional[str] = None,
        check_trust_store: bool = True,
    ) -> Dict[str, Any]:
        """
        Comprehensive server certificate validation adhering strictly to OPC UA Part 4.
        Validates:
          1. Parsing & Structure
          2. Validity Period (NotBefore / NotAfter -> BadCertificateTimeInvalid)
          3. Hostname / IP in SAN (-> BadCertificateHostNameInvalid)
          4. ApplicationURI in SAN (-> BadCertificateUriInvalid)
          5. Tamper / Signature Integrity (-> BadCertificateInvalid)
          6. CRL Revocation (-> BadCertificateRevoked)
          7. Issuer Chain Verification (-> BadCertificateIssuerUntrusted)
          8. Unexpected Thumbprint Change Detection (-> BadCertificateUntrusted)
          9. Presence in Trusted Store (-> BadCertificateUntrusted + Quarantine)
        Returns a dict with 'valid': bool, 'status_code': str, 'error': Optional[str], 'cert_info': Dict.
        """
        try:
            try:
                cert = x509.load_der_x509_certificate(cert_bytes)
            except Exception:
                cert = x509.load_pem_x509_certificate(cert_bytes)
        except Exception as e:
            return {
                "valid": False,
                "status_code": "BadCertificateInvalid",
                "error": f"Failed to parse X.509 certificate: {e}",
                "cert_info": {},
            }

        thumb = self.cert_thumbprint(cert)
        now = datetime.now(timezone.utc)

        # Extract Subject Alternative Names
        san_uris: List[str] = []
        san_dns: List[str] = []
        san_ips: List[str] = []
        try:
            san_ext = cert.extensions.get_extension_for_class(x509.SubjectAlternativeName)
            san_uris = san_ext.value.get_values_for_type(x509.UniformResourceIdentifier)
            san_dns = san_ext.value.get_values_for_type(x509.DNSName)
            san_ips = [str(ip) for ip in san_ext.value.get_values_for_type(x509.IPAddress)]
        except x509.ExtensionNotFound:
            pass

        cert_info = {
            "thumbprint": thumb,
            "subject": cert.subject.rfc4514_string(),
            "issuer": cert.issuer.rfc4514_string(),
            "not_before": cert.not_valid_before_utc.isoformat(),
            "not_after": cert.not_valid_after_utc.isoformat(),
            "san_uris": san_uris,
            "san_dns": san_dns,
            "san_ips": san_ips,
        }

        # 1. Check validity period
        if cert.not_valid_before_utc > now:
            return {
                "valid": False,
                "status_code": "BadCertificateTimeInvalid",
                "error": f"Certificate is not valid yet (NotBefore: {cert.not_valid_before_utc.isoformat()})",
                "cert_info": cert_info,
            }
        if cert.not_valid_after_utc < now:
            return {
                "valid": False,
                "status_code": "BadCertificateTimeInvalid",
                "error": f"Certificate has expired (NotAfter: {cert.not_valid_after_utc.isoformat()})",
                "cert_info": cert_info,
            }

        # 2. Check Hostname / IP in SAN
        host_matched = False
        norm_host = expected_host.strip().lower()
        if norm_host in [d.lower() for d in san_dns]:
            host_matched = True
        elif norm_host in san_ips:
            host_matched = True
        elif norm_host in ["127.0.0.1", "localhost"] and ("localhost" in [d.lower() for d in san_dns] or "127.0.0.1" in san_ips):
            host_matched = True

        if not host_matched:
            return {
                "valid": False,
                "status_code": "BadCertificateHostNameInvalid",
                "error": (
                    f"Certificate does not contain expected host '{expected_host}' in SAN "
                    f"(DNS: {san_dns}, IPs: {san_ips})"
                ),
                "cert_info": cert_info,
            }

        # 3. Check Application URI if specified
        if expected_uri and san_uris:
            if expected_uri not in san_uris:
                return {
                    "valid": False,
                    "status_code": "BadCertificateUriInvalid",
                    "error": f"Certificate URI {san_uris} does not match expected {expected_uri}",
                    "cert_info": cert_info,
                }

        # 4. Check CRL Revocation
        is_revoked, rev_reason = self.check_crl_revocation(cert)
        if is_revoked:
            return {
                "valid": False,
                "status_code": "BadCertificateRevoked",
                "error": f"Certificate is revoked: {rev_reason}",
                "cert_info": cert_info,
            }

        # 5. Check CA Issuer Chain (if not self-signed)
        if cert.issuer != cert.subject:
            chain_ok, chain_status, chain_msg = self.verify_issuer_chain(cert)
            if not chain_ok:
                return {
                    "valid": False,
                    "status_code": chain_status,
                    "error": chain_msg,
                    "cert_info": cert_info,
                }

        # 6. Check for Unexpected Server Certificate Thumbprint Change
        if expected_thumbprint and expected_thumbprint.upper() != thumb:
            quarantine_path = self.quarantine_rejected_cert(
                cert_bytes=cert_bytes,
                server_uri=expected_uri or expected_host,
                reason="Server certificate changed unexpectedly",
            )
            return {
                "valid": False,
                "status_code": "BadCertificateUntrusted",
                "error": (
                    f"Server certificate changed unexpectedly! Previous: {expected_thumbprint}, New: {thumb}. "
                    f"Quarantined to: {quarantine_path}. Re-approval required."
                ),
                "cert_info": cert_info,
                "quarantine_path": str(quarantine_path),
            }

        # 7. Check Trust Store
        if check_trust_store:
            if not self.is_cert_trusted(cert):
                quarantine_path = self.quarantine_rejected_cert(
                    cert_bytes=cert_bytes,
                    server_uri=expected_uri or expected_host,
                    reason="Untrusted by client trust store",
                )
                return {
                    "valid": False,
                    "status_code": "BadCertificateUntrusted",
                    "error": (
                        f"Server certificate is untrusted. Quarantined to: {quarantine_path}. "
                        "An administrator must trust this certificate before connection is permitted."
                    ),
                    "cert_info": cert_info,
                    "quarantine_path": str(quarantine_path),
                }

        return {
            "valid": True,
            "status_code": "Good",
            "error": None,
            "cert_info": cert_info,
        }

    @staticmethod
    def validate_security_policy(policy_uri: str, allow_insecure: bool = False) -> Tuple[bool, str, Optional[str]]:
        """
        Validates requested OPC UA Security Policy against Part 4 / Part 7 standards.
        Rejects deprecated or broken algorithms.
        """
        if policy_uri in SUPPORTED_POLICIES:
            return True, "Good", None
        elif policy_uri in DEPRECATED_POLICIES:
            return False, "BadSecurityPolicyRejected", f"Policy '{DEPRECATED_POLICIES[policy_uri]}' is deprecated and insecure."
        elif policy_uri == POLICY_NONE:
            if not allow_insecure:
                return False, "BadSecurityPolicyRejected", "SecurityPolicy#None is prohibited for secure industrial operations."
            return True, "Good", "WARNING: SecurityPolicy#None is active (Insecure Plaintext)"
        else:
            return False, "BadSecurityPolicyRejected", f"Security policy '{policy_uri}' is not supported."
