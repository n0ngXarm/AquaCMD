#!/usr/bin/env python3
"""
AquaCMD Gate B2 — Manual OPC UA Live Data Reader Module
Executes operator-initiated, non-blocking single-shot reads of verified OPC UA variables.
Strictly Read-Only (no writes, no subscriptions, no background polling).
Enforces explicit allowlists, clean session lifecycle, and GLib main thread safety.
"""

import asyncio
import logging
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional, Callable, Dict, Any

from opcua_mapping import NodeIdMapper, TagMapping
from opcua_store import ObservableStateStore, TagObservation, Quality

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
    """Manages manual single-shot reads of verified OPC UA tags."""

    def __init__(self, mapper: NodeIdMapper, store: ObservableStateStore,
                 config_dir: Optional[Path] = None):
        self.mapper = mapper
        self.store = store
        self.config_dir = config_dir or Path("/home/nong_ing/.gemini/antigravity-cli/brain/b57326e2-8eaf-4e5e-9289-fae9ebec3137/config")
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
        Guarantees clean session setup and teardown.
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

            # 3. Execute Async Reader Loop
            async def _do_read():
                client = Client(url=endpoint_url, timeout=timeout)

                # Configure Security
                if sec_policy == "Basic256Sha256":
                    cert_p = self.config_dir / "client_cert.der"
                    key_p = self.config_dir / "client_key.pem"
                    if not cert_p.exists() or not key_p.exists():
                        raise FileNotFoundError("Certificate or Private Key not found for Basic256Sha256")
                    await client.set_security_string(f"Basic256Sha256,SignAndEncrypt,{cert_p},{key_p}")

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
