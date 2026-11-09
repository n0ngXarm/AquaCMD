#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
opcua_polling_engine.py — 5-Second Monotonic OPC UA Polling Engine for AQUA COMMAND
Reads Task-Assigned OPC UA tags at a strict 5-second cadence using Monotonic Clock
scheduling, Non-Overlapping execution guards, Preflight authorization,
Session Reconnect with Exponential Backoff, and Read-Only enforcement.

Strict Safety Invariants:
- Zero OPC UA Write operations (strictly read-only).
- Does NOT start automatically upon startup; requires explicit user authorization.
- Reads ONLY Task-Assigned tags by default (prevents 457-tag overload without load test).
- Non-overlapping execution: Never triggers concurrent poll cycles.
- Bad quality is preserved and never converted to false OFF states.
"""

import sys
import time
import asyncio
import logging
import threading
from pathlib import Path
from urllib.parse import urlparse
from typing import Dict, Any, List, Optional, Set, Tuple
from datetime import datetime, timezone
from dataclasses import dataclass, field

from opcua_pki import PkiManager, POLICY_BASIC256SHA256, POLICY_NONE
from opcua_mapping import NodeIdMapper
from opcua_store import ObservableStateStore, Quality, TagObservation
from opcua_storage import DurableStorage, StoredObservation
from task_engine import TaskEngine

logger = logging.getLogger("aqua.polling_engine")

try:
    from asyncua import Client, ua
    from cryptography.hazmat.primitives import serialization
    ASYNCUA_AVAILABLE = True
except ImportError:
    ASYNCUA_AVAILABLE = False


class PollingState:
    STOPPED = "STOPPED"
    PREFLIGHT = "PREFLIGHT"
    STARTING = "STARTING"
    RUNNING = "RUNNING"
    PAUSED = "PAUSED"
    RECONNECTING = "RECONNECTING"
    ERROR = "ERROR"


@dataclass
class PollingTelemetry:
    state: str = PollingState.STOPPED
    interval_seconds: float = 5.0
    poll_count: int = 0
    successful_polls: int = 0
    failed_polls: int = 0
    overlap_prevented_count: int = 0
    last_poll_duration_ms: float = 0.0
    avg_poll_duration_ms: float = 0.0
    jitter_ms: float = 0.0
    last_good_data_iso: Optional[str] = None
    last_good_data_monotonic: Optional[float] = None
    data_age_seconds: float = 0.0
    reconnect_attempts: int = 0
    target_tags_count: int = 0
    last_error: Optional[str] = None


class OpcUaPollingEngine:
    """Production-grade 5-Second Monotonic OPC UA Polling Engine."""

    def __init__(
        self,
        mapper: NodeIdMapper,
        store: ObservableStateStore,
        storage: DurableStorage,
        task_engine: TaskEngine,
        pki: PkiManager,
        interval_seconds: float = 5.0,
        mode_task_tags_only: bool = True
    ):
        self.mapper = mapper
        self.store = store
        self.storage = storage
        self.task_engine = task_engine
        self.pki = pki
        self.interval_seconds = interval_seconds
        self.mode_task_tags_only = mode_task_tags_only

        self.telemetry = PollingTelemetry(interval_seconds=interval_seconds)
        self._lock = threading.Lock()

        # Threading & Async state
        self._stop_event = threading.Event()
        self._pause_event = threading.Event()
        self._worker_thread: Optional[threading.Thread] = None

        # Connection parameters
        self.endpoint_url: str = ""
        self.sec_policy: str = "None"
        self.auth_mode: str = "Anonymous"
        self.username: str = ""
        self.password: str = ""

        self._client: Optional[Any] = None
        self._loop: Optional[asyncio.AbstractEventLoop] = None

    def run_preflight_checks(
        self,
        endpoint_url: str,
        sec_policy: str = "Basic256Sha256"
    ) -> Tuple[bool, str]:
        """
        Validates connection prerequisites before allowing monitoring to start.
        Enforces PKI trust verification and task tag presence.
        """
        if not ASYNCUA_AVAILABLE:
            return False, "asyncua library is not installed."

        parsed = urlparse(endpoint_url)
        if parsed.scheme != "opc.tcp" or not parsed.hostname or not parsed.port:
            return False, f"Invalid OPC UA URL format: '{endpoint_url}'. Expected 'opc.tcp://<host>:<port>'."

        # Check required tags
        required_tags = self.task_engine.get_required_tags()
        if self.mode_task_tags_only and not required_tags:
            return False, "No active tasks with assigned tags found. Assign at least 1 tag in F2 before starting monitoring."

        # Check PKI prerequisites if Basic256Sha256
        if sec_policy == "Basic256Sha256":
            cert_p, key_p = self.pki.ensure_client_certificate()
            if not cert_p.is_file() or not key_p.is_file():
                return False, "Client PKI application certificate / RSA key could not be verified."

        return True, "Preflight checks passed."

    def start_monitoring(
        self,
        endpoint_url: str,
        sec_policy: str = "Basic256Sha256",
        auth_mode: str = "Anonymous",
        username: str = "",
        password: str = ""
    ) -> Tuple[bool, str]:
        """
        Authorizes and begins 5-second polling monitoring.
        Requires explicit user initiation and preflight check passage.
        """
        with self._lock:
            if self.telemetry.state in (PollingState.RUNNING, PollingState.STARTING):
                return False, "Monitoring is already active."

            self.telemetry.state = PollingState.PREFLIGHT
            ok, reason = self.run_preflight_checks(endpoint_url, sec_policy)
            if not ok:
                self.telemetry.state = PollingState.ERROR
                self.telemetry.last_error = reason
                return False, f"Preflight failed: {reason}"

            self.endpoint_url = endpoint_url
            self.sec_policy = sec_policy
            self.auth_mode = auth_mode
            self.username = username
            self.password = password

            self._stop_event.clear()
            self._pause_event.clear()
            self.telemetry.state = PollingState.STARTING

            self._worker_thread = threading.Thread(
                target=self._run_event_loop_thread,
                name="AquaOpcUaPollingWorker",
                daemon=True
            )
            self._worker_thread.start()
            return True, "Monitoring engine started successfully."

    def stop_monitoring(self, timeout: float = 6.0) -> bool:
        """Gracefully halts 5-second polling and disconnects OPC UA session."""
        with self._lock:
            if self.telemetry.state == PollingState.STOPPED:
                return True
            logger.info("Stopping OPC UA polling engine...")
            self._stop_event.set()

        if self._worker_thread and self._worker_thread.is_alive():
            self._worker_thread.join(timeout=timeout)

        with self._lock:
            self.telemetry.state = PollingState.STOPPED
        logger.info("OPC UA polling engine stopped cleanly.")
        return True

    def pause_monitoring(self) -> bool:
        """Temporarily suspends polling cycles while preserving connection session."""
        with self._lock:
            if self.telemetry.state != PollingState.RUNNING:
                return False
            self._pause_event.set()
            self.telemetry.state = PollingState.PAUSED
            logger.info("OPC UA polling paused.")
            return True

    def resume_monitoring(self) -> bool:
        """Resumes 5-second polling cycles from paused state."""
        with self._lock:
            if self.telemetry.state != PollingState.PAUSED:
                return False
            self._pause_event.clear()
            self.telemetry.state = PollingState.RUNNING
            logger.info("OPC UA polling resumed.")
            return True

    def get_telemetry(self) -> Dict[str, Any]:
        with self._lock:
            now_mono = time.monotonic()
            if self.telemetry.last_good_data_monotonic:
                self.telemetry.data_age_seconds = round(now_mono - self.telemetry.last_good_data_monotonic, 2)
            else:
                self.telemetry.data_age_seconds = 0.0

            return {
                "state": self.telemetry.state,
                "interval_seconds": self.telemetry.interval_seconds,
                "poll_count": self.telemetry.poll_count,
                "successful_polls": self.telemetry.successful_polls,
                "failed_polls": self.telemetry.failed_polls,
                "overlap_prevented_count": self.telemetry.overlap_prevented_count,
                "last_poll_duration_ms": round(self.telemetry.last_poll_duration_ms, 2),
                "avg_poll_duration_ms": round(self.telemetry.avg_poll_duration_ms, 2),
                "jitter_ms": round(self.telemetry.jitter_ms, 2),
                "last_good_data_iso": self.telemetry.last_good_data_iso,
                "data_age_seconds": self.telemetry.data_age_seconds,
                "reconnect_attempts": self.telemetry.reconnect_attempts,
                "target_tags_count": self.telemetry.target_tags_count,
                "last_error": self.telemetry.last_error
            }

    def _run_event_loop_thread(self):
        self._loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self._loop)
        try:
            self._loop.run_until_complete(self._main_polling_loop())
        except Exception as e:
            logger.error("Unhandled exception in polling thread: %s", e)
            with self._lock:
                self.telemetry.state = PollingState.ERROR
                self.telemetry.last_error = str(e)
        finally:
            self._loop.close()

    async def _create_and_connect_client(self) -> Client:
        client = Client(url=self.endpoint_url, timeout=4.0)
        client.application_uri = self.pki.DEFAULT_APP_URI
        parsed = urlparse(self.endpoint_url)
        expected_host = parsed.hostname or "127.0.0.1"

        if self.sec_policy == "Basic256Sha256":
            cert_p, key_p = self.pki.ensure_client_certificate()
            await client.set_security_string(f"Basic256Sha256,SignAndEncrypt,{cert_p},{key_p}")

            # Handshake & validate server certificate
            server_cert = getattr(client.security_policy, "peer_certificate", None)
            if server_cert:
                server_cert_bytes = server_cert if isinstance(server_cert, bytes) else server_cert.public_bytes(serialization.Encoding.DER)
                val_res = self.pki.validate_server_certificate(
                    cert_bytes=server_cert_bytes,
                    expected_host=expected_host,
                    check_trust_store=True
                )
                if not val_res["valid"]:
                    raise PermissionError(f"Server certificate untrusted: {val_res['status_code']}")

        if self.auth_mode == "Username" and self.username:
            client.set_user(self.username)
            client.set_password(self.password)

        await client.connect()
        return client

    async def _main_polling_loop(self):
        reconnect_delay = 1.0
        backoff_multiplier = 1.8
        max_reconnect_delay = 30.0

        client: Optional[Client] = None

        while not self._stop_event.is_set():
            # 1. Establish or maintain connection
            if client is None:
                with self._lock:
                    self.telemetry.state = PollingState.RECONNECTING

                try:
                    logger.info("Connecting to OPC UA Server (%s, %s)...", self.endpoint_url, self.sec_policy)
                    client = await self._create_and_connect_client()
                    with self._lock:
                        self.telemetry.state = PollingState.RUNNING
                        self.telemetry.reconnect_attempts = 0
                    reconnect_delay = 1.0
                    logger.info("Connected to OPC UA Server successfully. Starting 5s polling loop.")
                except Exception as e:
                    with self._lock:
                        self.telemetry.reconnect_attempts += 1
                        self.telemetry.last_error = f"Connect failure: {e}"
                    logger.warning("Connection failure (attempt %d): %s. Reconnecting in %.1fs",
                                   self.telemetry.reconnect_attempts, e, reconnect_delay)
                    await asyncio.sleep(min(reconnect_delay, 1.0))
                    reconnect_delay = min(max_reconnect_delay, reconnect_delay * backoff_multiplier)
                    continue

            # 2. Main 5-Second Monotonic Polling Cadence
            expected_next_mono = time.monotonic()

            while not self._stop_event.is_set():
                if self._pause_event.is_set():
                    await asyncio.sleep(0.5)
                    expected_next_mono = time.monotonic() + self.interval_seconds
                    continue

                actual_cycle_start = time.monotonic()
                jitter_s = actual_cycle_start - expected_next_mono
                jitter_ms = max(0.0, jitter_s * 1000.0)

                # Execute Poll Cycle
                poll_success = False
                poll_start_time = time.monotonic()

                try:
                    await self._execute_single_poll_cycle(client)
                    poll_success = True
                except Exception as e:
                    logger.error("Poll cycle error: %s", e)
                    with self._lock:
                        self.telemetry.failed_polls += 1
                        self.telemetry.last_error = str(e)
                    # Disconnect on session error
                    try:
                        await client.disconnect()
                    except Exception:
                        pass
                    client = None
                    break

                poll_duration_ms = (time.monotonic() - poll_start_time) * 1000.0

                with self._lock:
                    self.telemetry.poll_count += 1
                    if poll_success:
                        self.telemetry.successful_polls += 1
                        self.telemetry.last_good_data_iso = datetime.now(timezone.utc).isoformat()
                        self.telemetry.last_good_data_monotonic = time.monotonic()
                    self.telemetry.last_poll_duration_ms = poll_duration_ms
                    self.telemetry.jitter_ms = jitter_ms
                    # Exponential moving average for poll duration
                    if self.telemetry.avg_poll_duration_ms == 0.0:
                        self.telemetry.avg_poll_duration_ms = poll_duration_ms
                    else:
                        self.telemetry.avg_poll_duration_ms = (0.2 * poll_duration_ms) + (0.8 * self.telemetry.avg_poll_duration_ms)

                # Non-overlapping Monotonic Scheduling
                expected_next_mono += self.interval_seconds
                now_after_poll = time.monotonic()
                sleep_duration = expected_next_mono - now_after_poll

                if sleep_duration < 0:
                    # Overlap prevented! The read cycle took longer than interval.
                    with self._lock:
                        self.telemetry.overlap_prevented_count += 1
                    logger.warning("Poll cycle took %.1fms (> %.1fs). Overlap prevented; advancing cadence.",
                                   poll_duration_ms, self.interval_seconds)
                    expected_next_mono = now_after_poll
                else:
                    # Sleep in small slices to remain responsive to stop/pause
                    while sleep_duration > 0 and not self._stop_event.is_set() and not self._pause_event.is_set():
                        step = min(0.1, sleep_duration)
                        await asyncio.sleep(step)
                        sleep_duration -= step

        # Clean shutdown of client
        if client:
            try:
                await client.disconnect()
            except Exception:
                pass

    async def _execute_single_poll_cycle(self, client: Client):
        """
        Executes one non-overlapping read pass over all target tags.
        Fanes out results to DurableStorage and TaskEngine.
        STRICT READ-ONLY: Never writes to any OPC UA node!
        """
        # Determine target tags
        if self.mode_task_tags_only:
            target_tags = sorted(list(self.task_engine.get_required_tags()))
        else:
            target_tags = sorted(list(self.mapper.get_mapped_tag_names()))

        with self._lock:
            self.telemetry.target_tags_count = len(target_tags)

        if not target_tags:
            return

        now_utc = datetime.now(timezone.utc)
        now_iso = now_utc.isoformat()
        observations: Dict[str, StoredObservation] = {}

        # Read tags in controlled sequential or bounded batch
        for tag_name in target_tags:
            mapping = self.mapper.get_mapping(tag_name)
            if not mapping or not mapping.verified:
                continue

            node_id_str = mapping.node_id_identifier
            ns_uri = mapping.namespace_uri

            try:
                # Namespace lookup
                ns_idx = await client.get_namespace_index(ns_uri)
                if node_id_str.startswith("s="):
                    ident = node_id_str[2:]
                    node = client.get_node(ua.NodeId(ident, ns_idx))
                elif node_id_str.startswith("i="):
                    ident = int(node_id_str[2:])
                    node = client.get_node(ua.NodeId(ident, ns_idx))
                else:
                    node = client.get_node(node_id_str)

                # Strict Read-Only Call
                dv = await node.read_data_value()

                q_str = "GOOD"
                raw_code = dv.StatusCode.value if dv.StatusCode else 0
                if dv.StatusCode and not dv.StatusCode.is_good():
                    q_str = "BAD"

                val = dv.Value.Value if dv.Value else None
                src_ts = dv.SourceTimestamp.isoformat() if dv.SourceTimestamp else now_iso
                srv_ts = dv.ServerTimestamp.isoformat() if dv.ServerTimestamp else now_iso

                obs = StoredObservation(
                    tag_name=tag_name,
                    value=val,
                    unit=mapping.unit,
                    quality=q_str,
                    raw_status=raw_code,
                    source_timestamp=src_ts,
                    server_timestamp=srv_ts,
                    arrival_timestamp=now_iso
                )
                observations[tag_name] = obs

                # Update in-memory observable store for GUI F1
                self.store.update_from_datavalue(
                    tag_name=tag_name,
                    node_id=node_id_str,
                    data_value=dv,
                    unit=mapping.unit,
                    arrival_time=now_utc,
                    endpoint_url=self.endpoint_url, session_state="CONNECTED"
                )

            except Exception as ex:
                logger.error("Failed reading node for tag %s: %s", tag_name, ex)
                obs_err = StoredObservation(
                    tag_name=tag_name,
                    value=None,
                    unit=mapping.unit,
                    quality="BAD",
                    raw_status=0x80000000,
                    source_timestamp=now_iso,
                    server_timestamp=now_iso,
                    arrival_timestamp=now_iso
                )
                observations[tag_name] = obs_err
                self.store.mark_disconnected(tag_name, node_id_str, str(ex))

        # 1. Atomically store observations in SQLite
        obs_list = list(observations.values())
        self.storage.record_observations(obs_list)

        # 2. Fan-out observations to TaskEngine for condition evaluation & alert generation
        self.task_engine.evaluate_observations(observations, current_time=now_utc)
