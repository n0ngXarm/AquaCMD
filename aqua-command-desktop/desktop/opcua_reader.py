#!/usr/bin/env python3
"""
AquaCMD Gate B2 + Security Gate — Manual OPC UA Live Data Reader Module
Executes operator-initiated, non-blocking single-shot reads of verified OPC UA variables.
Strictly Read-Only (no writes, no subscriptions, no background polling).
Enforces explicit allowlists, X.509 PKI certificate validation, clean session lifecycle,
and GLib main thread safety.
"""

import asyncio
import logging
import threading
from urllib.parse import urlparse
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional, Callable, Dict, Any

try:
    from .opcua_mapping import NodeIdMapper, TagMapping
    from .opcua_store import ObservableStateStore, TagObservation, Quality
    from .opcua_pki import PkiManager, SUPPORTED_POLICIES, POLICY_NONE
except ImportError:
    from opcua_mapping import NodeIdMapper, TagMapping
    from opcua_store import ObservableStateStore, TagObservation, Quality
    from opcua_pki import PkiManager, SUPPORTED_POLICIES, POLICY_NONE

logger = logging.getLogger("aquacmd.opcua.reader")

try:
    from asyncua import Client, ua
    HAS_ASYNCUA = True
except ImportError:
    HAS_ASYNCUA = False

try:
    from gi.repository import GLib
    HAS_GLIB = True
except ImportError:
    HAS_GLIB = False


class ManualOpcUaReader:
    """Manages manual single-shot reads of verified OPC UA tags with strict PKI validation."""

    def __init__(self, mapper: NodeIdMapper, store: ObservableStateStore,
                 config_dir: Optional[Path] = None, pki: Optional[PkiManager] = None):
        self.mapper = mapper
        self.store = store
        self.config_dir = config_dir or (Path.home() / ".config" / "aqua-command")
        self.pki = pki or PkiManager(pki_dir=self.config_dir / "pki")
        self._read_lock = threading.Lock()
        self.is_reading = False

    def read_tag_once_async(self, tag_name: str, endpoint_url: str,
                            sec_policy: str = "None", auth_mode: str = "Anonymous",
                            username: str = "", password: str = "",
                            timeout: float = 4.0,
                            callback: Optional[Callable[[TagObservation], None]] = None):
        """
        Spawns a background thread to execute a manual single-shot read.
        Dispatches result to callback on GTK Main Thread via GLib.idle_add.
        """
        def worker():
            obs = self.read_tag_once_sync(
                tag_name=tag_name,
                endpoint_url=endpoint_url,
                sec_policy=sec_policy,
                auth_mode=auth_mode,
                username=username,
                password=password,
                timeout=timeout
            )
            if callback:
                if HAS_GLIB:
                    GLib.idle_add(callback, obs)
                else:
                    callback(obs)

        t = threading.Thread(target=worker, daemon=True, name=f"AquaCMD-Read-{tag_name}")
        t.start()

    def read_tag_once_sync(self, tag_name: str, endpoint_url: str,
                           sec_policy: str = "None", auth_mode: str = "Anonymous",
                           username: str = "", password: str = "",
                           timeout: float = 4.0) -> TagObservation:
        """
        Synchronous execution of single-shot read (called inside worker thread).
        Guarantees clean session setup, PKI certificate validation, and teardown.
        """
        # 1. Concurrency guard: avoid overlapping manual reads
        with self._read_lock:
            self.is_reading = True

        try:
            # 2. Check allowlist
            if not self.mapper.is_allowed(tag_name):
                err_msg = f"Tag '{tag_name}' is not in the verified allowlist (Read Refused)"
                logger.warning(err_msg)
                obs = TagObservation(
                    tag_name=tag_name,
                    value=None,
                    quality=Quality.BAD,
                    arrival_time=datetime.now(timezone.utc),
                    raw_status_name="BadNotAllowed"
                )
                self.store.update_observation(obs)
                return obs

            mapping = self.mapper.get_mapping(tag_name)
            unit = mapping.unit if mapping else ""

            if not HAS_ASYNCUA:
                obs = TagObservation(
                    tag_name=tag_name,
                    value=None,
                    quality=Quality.BAD,
                    arrival_time=datetime.now(timezone.utc),
                    raw_status_name="BadNoLibrary"
                )
                self.store.update_observation(obs)
                return obs

            # 3. Security guardrail: Prohibit plaintext username/password over SecurityPolicy#None
            if auth_mode == "Username" and sec_policy == "None":
                err_msg = "INSECURE_CREDENTIAL_TRANSFER: Username authentication prohibited over SecurityPolicy#None."
                logger.error(err_msg)
                obs = TagObservation(
                    tag_name=tag_name,
                    node_id=mapping.node_id_identifier if mapping else None,
                    value=None,
                    quality=Quality.BAD,
                    arrival_time=datetime.now(timezone.utc),
                    raw_status_name="BadSecurityChecksFailed",
                    unit=unit
                )
                self.store.update_observation(obs)
                return obs

            # 4. Execute Async Reader Loop
            async def _do_read():
                client = Client(url=endpoint_url, timeout=timeout)
                client.application_uri = self.pki.DEFAULT_APP_URI

                parsed = urlparse(endpoint_url)
                expected_host = parsed.hostname or "127.0.0.1"

                # Configure Security
                if sec_policy == "Basic256Sha256":
                    cert_p, key_p = self.pki.ensure_client_certificate()
                    await client.set_security_string(f"Basic256Sha256,SignAndEncrypt,{cert_p},{key_p}")

                    # Validate Server Certificate discovered by set_security_string
                    server_cert = getattr(client.security_policy, "peer_certificate", None)
                    if not server_cert:
                        raise ua.UaStatusCodeError(ua.StatusCodes.BadSecurityChecksFailed)

                    server_cert_bytes = server_cert if isinstance(server_cert, bytes) else server_cert.public_bytes(serialization.Encoding.DER)
                    val_res = self.pki.validate_server_certificate(
                        cert_bytes=server_cert_bytes,
                        expected_host=expected_host,
                        check_trust_store=True,
                    )
                    if not val_res["valid"]:
                        status_code_name = val_res["status_code"]
                        logger.error("Server certificate validation failed: %s (%s)", status_code_name, val_res["error"])
                        status_code = getattr(ua.StatusCodes, status_code_name, ua.StatusCodes.BadCertificateUntrusted)
                        raise ua.UaStatusCodeError(status_code)

                # Configure Authentication
                if auth_mode == "Username":
                    if not username:
                        raise ValueError("Username mode requires valid username")
                    client.set_user(username)
                    client.set_password(password)

                # Connect and Read within context manager (guaranteed session closure)
                async with client:
                    # Dynamically resolve NodeId string using server's current namespace index
                    resolved_ok, node_id_str, resolve_err = await self.mapper.resolve_node_id_string(tag_name, client)
                    if not resolved_ok:
                        raise ValueError(resolve_err)

                    node = client.get_node(node_id_str)
                    # CRITICAL: raise_on_bad_status=False preserves true DataValue without throwing
                    data_value = await node.read_data_value(raise_on_bad_status=False)
                    return node_id_str, data_value

            loop = asyncio.new_event_loop()
            try:
                node_id_str, data_value = loop.run_until_complete(_do_read())
                obs = self.store.update_from_datavalue(tag_name, node_id_str, data_value, unit=unit)
                return obs
            except Exception as ex:
                err_str = str(ex)
                if password and password in err_str:
                    err_str = err_str.replace(password, "******")
                logger.error("Error reading tag %s: %s", tag_name, err_str)
                is_conn_error = isinstance(ex, (ConnectionError, asyncio.TimeoutError)) or (isinstance(ex, OSError) and not isinstance(ex, FileNotFoundError))
                obs = TagObservation(
                    tag_name=tag_name,
                    node_id=mapping.node_id_identifier if mapping else None,
                    value=None,
                    quality=Quality.DISCONNECTED if is_conn_error else Quality.BAD,
                    arrival_time=datetime.now(timezone.utc),
                    raw_status_name=type(ex).__name__,
                    unit=unit
                )
                self.store.update_observation(obs)
                return obs
            finally:
                loop.close()

        finally:
            with self._read_lock:
                self.is_reading = False
