"""Manual F3 access through the existing asyncua reader and PKI implementation."""
import asyncio
import time
from datetime import datetime, timezone

from cryptography.hazmat.primitives import serialization

try:
    from . import opcua_reader as secure_reader
    from .opcua_store import ObservableStateStore, Quality
    from .f3_evidence import endpoint_target
except ImportError:
    import opcua_reader as secure_reader
    from opcua_store import ObservableStateStore, Quality
    from f3_evidence import endpoint_target


class ValidationReceipt:
    """Observe the existing validator's result without modifying its decision."""
    def __init__(self, pki):
        self.pki = pki
        self.result = None

    def __getattr__(self, name):
        return getattr(self.pki, name)

    def validate_server_certificate(self, *args, **kwargs):
        self.result = self.pki.validate_server_certificate(*args, **kwargs)
        return self.result


class ReadReceiptStore(ObservableStateStore):
    def __init__(self):
        super().__init__()
        self.received = False

    def update_from_datavalue(self, *args, **kwargs):
        self.received = True
        return super().update_from_datavalue(*args, **kwargs)


class SecureF3OpcUa:
    def __init__(self, mapper, pki, config_dir):
        self.mapper, self.pki, self.config_dir = mapper, pki, config_dir

    def readiness(self, device, options, *, require_mapping=False):
        _, _, error = endpoint_target(device)
        if error:
            return error
        if not secure_reader.HAS_ASYNCUA or self.pki is None:
            return "Existing OPC UA/PKI implementation is unavailable"
        if options.get("sec_policy") != "Basic256Sha256":
            return "F3 requires explicitly configured Basic256Sha256 / SignAndEncrypt"
        if options.get("auth_mode", "Anonymous") not in ("Anonymous", "Username"):
            return "Unsupported authentication mode"
        if options.get("auth_mode") == "Username" and not options.get("username"):
            return "Configure credentials for this exact endpoint in F6"
        if require_mapping and (self.mapper is None or not self.mapper.is_allowed(device.get("test_tag", ""))):
            return "Read refused: select a verified NodeId mapping in F6"
        return None

    @staticmethod
    def result():
        return {"timestamp": datetime.now(timezone.utc).isoformat(), "checked_at": time.time(),
                "opcua_state": "NOT_TESTED", "session_state": "DISCONNECTED",
                "certificate_trust": "NOT_TESTED", "security_status": "NOT_TESTED",
                "session_verified": False, "read_success": False, "last_error": None}

    @staticmethod
    def certificate_result(result, receipt):
        validation = receipt.result
        if validation is not None:
            result["certificate_trust"] = "TRUSTED" if validation["valid"] else validation.get("status_code", "REJECTED")
            result["certificate_reason"] = validation.get("error")
            result["certificate_thumbprint"] = validation.get("cert_info", {}).get("thumbprint")
            if not validation["valid"]:
                result["opcua_state"] = "CERTIFICATE_UNTRUSTED"
                result["last_error"] = validation.get("error") or result["certificate_trust"]

    @staticmethod
    def failure(result, error, password=""):
        message = str(error) or type(error).__name__
        message = message.replace(password, "[redacted]") if password else message
        result["last_error"] = message
        result["opcua_state"] = 'TIMEOUT' if isinstance(error, TimeoutError) or 'Timeout' in message else "AUTH_FAILED" if "BadUser" in message or "BadIdentity" in message else "ERROR"

    def probe_sync(self, device, options, on_session_open=None):
        """Open one trusted session and close it; never start monitoring or read tags."""
        result = self.result()
        error = self.readiness(device, options)
        if error:
            result.update(opcua_state="NOT_CONFIGURED", last_error=error)
            return result
        receipt = ValidationReceipt(self.pki)

        async def probe():
            host, _, _ = endpoint_target(device)
            client = secure_reader.Client(device["endpoint_url"], timeout=4.0)
            client.application_uri = receipt.DEFAULT_APP_URI
            cert_path, key_path = receipt.ensure_client_certificate()
            await client.set_security_string(f"Basic256Sha256,SignAndEncrypt,{cert_path},{key_path}")
            certificate = getattr(client.security_policy, "peer_certificate", None)
            if not certificate:
                raise PermissionError("Server certificate missing; secure session refused")
            der = certificate if isinstance(certificate, bytes) else certificate.public_bytes(serialization.Encoding.DER)
            validation = receipt.validate_server_certificate(cert_bytes=der, expected_host=host, check_trust_store=True)
            if not validation["valid"]:
                raise PermissionError(validation.get("status_code", "Certificate rejected"))
            if options.get("auth_mode") == "Username":
                client.set_user(options["username"])
                client.set_password(options.get("password", ""))
            async with client:
                result.update(session_state="CONNECTED", session_verified=True,
                              opcua_state="CONNECTED", security_status="Basic256Sha256 / SignAndEncrypt",
                              last_session_success=datetime.now(timezone.utc).isoformat())
                self.certificate_result(result, receipt)
                if on_session_open:
                    on_session_open(dict(result))
            result.update(session_state="DISCONNECTED", opcua_state="DISCONNECTED")

        try:
            asyncio.run(probe())
        except Exception as error:
            self.failure(result, error, options.get("password", ""))
        self.certificate_result(result, receipt)
        result["session_state"] = "DISCONNECTED"
        result["checked_at"] = time.time()
        return result

    def read_sync(self, device, options):
        """Use ManualOpcUaReader unchanged, with an F3-local observation store."""
        result = self.result()
        error = self.readiness(device, options, require_mapping=True)
        if error:
            result.update(opcua_state="NOT_CONFIGURED", last_error=error)
            return result
        receipt = ValidationReceipt(self.pki)
        store = ReadReceiptStore()
        reader = secure_reader.ManualOpcUaReader(self.mapper, store, self.config_dir, pki=receipt)
        try:
            obs = reader.read_tag_once_sync(
                tag_name=device["test_tag"], endpoint_url=device["endpoint_url"],
                sec_policy="Basic256Sha256", auth_mode=options.get("auth_mode", "Anonymous"),
                username=options.get("username", ""), password=options.get("password", ""), timeout=4.0)
            quality = obs.quality
            if store.received and quality == Quality.GOOD and obs.is_stale(15.0):
                quality = Quality.STALE
            result.update(value=obs.value, quality=quality, tag_name=obs.tag_name,
                          node_id=obs.node_id, raw_status=obs.raw_status_name,
                          source_timestamp=obs.source_time.isoformat() if obs.source_time else None,
                          server_timestamp=obs.server_time.isoformat() if obs.server_time else None,
                          arrival_timestamp=obs.arrival_time.isoformat() if obs.arrival_time else None,
                          read_success=store.received, session_verified=store.received)
            if store.received:
                result.update(opcua_state="READ_VERIFIED", last_session_success=result["timestamp"],
                              security_status="Basic256Sha256 / SignAndEncrypt")
            else:
                self.failure(result, obs.raw_status_name, options.get("password", ""))
        except Exception as error:
            self.failure(result, error, options.get("password", ""))
        self.certificate_result(result, receipt)
        result["checked_at"] = time.time()
        return result
