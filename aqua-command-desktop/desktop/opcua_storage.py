#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
opcua_storage.py — Durable SQLite Storage Engine for AQUA COMMAND
Handles WAL-mode persistent storage for Tag Observations, Task Events,
Task Runtime States, and Notification Outbox with Crash Recovery.

Strict Invariants:
- Thread-safe connection handling using connection-per-thread or lock.
- WAL journal mode for low latency concurrent reads & writes.
- Deduplicated task events linked to transactional notification outbox.
- Disk full and retention limit protections.
"""

import os
import sys
import json
import uuid
import sqlite3
import threading
import logging
from pathlib import Path
from typing import Dict, Any, List, Optional, Tuple
from datetime import datetime, timezone, timedelta
from dataclasses import dataclass, field

logger = logging.getLogger("aqua.storage")


@dataclass
class StoredObservation:
    tag_name: str
    value: Any
    unit: str
    quality: str
    raw_status: int = 0
    source_timestamp: Optional[str] = None
    server_timestamp: Optional[str] = None
    arrival_timestamp: Optional[str] = None


@dataclass
class TaskEvent:
    event_id: str
    task_id: str
    task_name: str
    tag_name: str
    trigger_type: str
    trigger_value: Any
    threshold_value: Any
    description: str
    severity: str = "INFO"  # INFO, WARNING, CRITICAL
    created_at: Optional[str] = None


@dataclass
class TaskRuntimeState:
    task_id: str
    active_state: int = 0  # 0: normal, 1: triggered/active
    consecutive_samples: int = 0
    last_evaluated_value: Optional[float] = None
    last_evaluated_quality: Optional[str] = None
    last_evaluated_at: Optional[str] = None
    last_triggered_at: Optional[str] = None


@dataclass
class OutboxItem:
    outbox_id: str
    event_id: str
    channel: str
    recipient: Optional[str]
    payload: Dict[str, Any]
    status: str  # PENDING, SENDING, SENT, FAILED
    retry_count: int = 0
    max_retries: int = 5
    next_retry_at: Optional[str] = None
    created_at: Optional[str] = None
    sent_at: Optional[str] = None
    last_error: Optional[str] = None


class DurableStorage:
    """SQLite Durable Storage Manager with WAL Mode and Outbox Persistence."""

    def __init__(self, db_path: Path, max_db_size_bytes: int = 100 * 1024 * 1024):
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self.max_db_size_bytes = max_db_size_bytes
        self._lock = threading.Lock()
        self.disk_full_flag = False
        self._init_db()

    def _get_connection(self) -> sqlite3.Connection:
        conn = sqlite3.connect(
            str(self.db_path),
            timeout=10.0,
            check_same_thread=False
        )
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self):
        with self._lock:
            conn = self._get_connection()
            try:
                # Enable WAL mode for high performance concurrent operations
                conn.execute("PRAGMA journal_mode = WAL;")
                conn.execute("PRAGMA synchronous = NORMAL;")
                conn.execute("PRAGMA foreign_keys = ON;")

                conn.executescript("""
                CREATE TABLE IF NOT EXISTS tag_observations (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    tag_name TEXT NOT NULL,
                    value REAL,
                    value_raw TEXT,
                    unit TEXT,
                    quality TEXT NOT NULL,
                    raw_status INTEGER,
                    source_timestamp TEXT,
                    server_timestamp TEXT,
                    arrival_timestamp TEXT NOT NULL
                );

                CREATE INDEX IF NOT EXISTS idx_obs_tag_time
                ON tag_observations(tag_name, arrival_timestamp);

                CREATE TABLE IF NOT EXISTS task_events (
                    event_id TEXT PRIMARY KEY,
                    task_id TEXT NOT NULL,
                    task_name TEXT NOT NULL,
                    tag_name TEXT NOT NULL,
                    trigger_type TEXT NOT NULL,
                    trigger_value REAL,
                    threshold_value REAL,
                    description TEXT,
                    severity TEXT NOT NULL,
                    created_at TEXT NOT NULL
                );

                CREATE INDEX IF NOT EXISTS idx_events_task_time
                ON task_events(task_id, created_at);

                CREATE TABLE IF NOT EXISTS task_runtime_state (
                    task_id TEXT PRIMARY KEY,
                    active_state INTEGER NOT NULL DEFAULT 0,
                    consecutive_samples INTEGER NOT NULL DEFAULT 0,
                    last_evaluated_value REAL,
                    last_evaluated_quality TEXT,
                    last_evaluated_at TEXT,
                    last_triggered_at TEXT
                );

                CREATE TABLE IF NOT EXISTS notification_outbox (
                    outbox_id TEXT PRIMARY KEY,
                    event_id TEXT NOT NULL,
                    channel TEXT NOT NULL,
                    recipient TEXT,
                    payload TEXT NOT NULL,
                    status TEXT NOT NULL DEFAULT 'PENDING',
                    retry_count INTEGER NOT NULL DEFAULT 0,
                    max_retries INTEGER NOT NULL DEFAULT 5,
                    next_retry_at TEXT,
                    created_at TEXT NOT NULL,
                    sent_at TEXT,
                    last_error TEXT,
                    FOREIGN KEY (event_id) REFERENCES task_events(event_id) ON DELETE CASCADE
                );

                CREATE INDEX IF NOT EXISTS idx_outbox_status_retry
                ON notification_outbox(status, next_retry_at);

                CREATE TABLE IF NOT EXISTS delivery_attempts (
                    attempt_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    outbox_id TEXT NOT NULL,
                    attempt_time TEXT NOT NULL,
                    status TEXT NOT NULL,
                    http_status INTEGER,
                    response_body TEXT,
                    error_message TEXT,
                    FOREIGN KEY (outbox_id) REFERENCES notification_outbox(outbox_id) ON DELETE CASCADE
                );
                """)
                conn.commit()
            finally:
                conn.close()

    def record_observations(self, observations: List[StoredObservation]) -> int:
        """Atomically stores a batch of tag observations."""
        if not observations:
            return 0
        if self.is_db_full():
            logger.warning("Database size limit exceeded (%d bytes). Skipping observation write.", self.max_db_size_bytes)
            self.disk_full_flag = True
            return 0

        now_iso = datetime.now(timezone.utc).isoformat()
        records = []
        for obs in observations:
            v_real = None
            if isinstance(obs.value, (int, float)) and not isinstance(obs.value, bool):
                v_real = float(obs.value)
            elif isinstance(obs.value, bool):
                v_real = 1.0 if obs.value else 0.0
            records.append((
                obs.tag_name,
                v_real,
                str(obs.value),
                obs.unit or "",
                obs.quality,
                obs.raw_status,
                obs.source_timestamp or now_iso,
                obs.server_timestamp or now_iso,
                obs.arrival_timestamp or now_iso
            ))

        with self._lock:
            conn = self._get_connection()
            try:
                conn.executemany("""
                INSERT INTO tag_observations (
                    tag_name, value, value_raw, unit, quality, raw_status,
                    source_timestamp, server_timestamp, arrival_timestamp
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, records)
                conn.commit()
                self.disk_full_flag = False
                return len(records)
            except sqlite3.OperationalError as e:
                if "disk is full" in str(e).lower():
                    self.disk_full_flag = True
                    logger.error("SQLite OperationalError: disk is full")
                    return 0
                raise
            finally:
                conn.close()

    def record_event_and_enqueue_outbox(
        self,
        event: TaskEvent,
        outbox_channels: List[Tuple[str, Optional[str], Dict[str, Any]]]
    ) -> bool:
        """Atomically saves a triggered TaskEvent and enqueues corresponding outbox items."""
        now_iso = datetime.now(timezone.utc).isoformat()
        if not event.created_at:
            event.created_at = now_iso

        v_real = None
        if isinstance(event.trigger_value, (int, float)) and not isinstance(event.trigger_value, bool):
            v_real = float(event.trigger_value)
        elif isinstance(event.trigger_value, bool):
            v_real = 1.0 if event.trigger_value else 0.0

        th_real = None
        if isinstance(event.threshold_value, (int, float)) and not isinstance(event.threshold_value, bool):
            th_real = float(event.threshold_value)

        outbox_rows = []
        for channel, recipient, payload in outbox_channels:
            outbox_id = f"out_{uuid.uuid4().hex[:12]}"
            payload_json = json.dumps(payload, ensure_ascii=False)
            outbox_rows.append((
                outbox_id,
                event.event_id,
                channel,
                recipient or "",
                payload_json,
                "PENDING",
                0,
                5,
                now_iso,
                now_iso
            ))

        with self._lock:
            conn = self._get_connection()
            try:
                conn.execute("BEGIN TRANSACTION;")
                conn.execute("""
                INSERT INTO task_events (
                    event_id, task_id, task_name, tag_name, trigger_type,
                    trigger_value, threshold_value, description, severity, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    event.event_id,
                    event.task_id,
                    event.task_name,
                    event.tag_name,
                    event.trigger_type,
                    v_real,
                    th_real,
                    event.description,
                    event.severity,
                    event.created_at
                ))

                if outbox_rows:
                    conn.executemany("""
                    INSERT INTO notification_outbox (
                        outbox_id, event_id, channel, recipient, payload,
                        status, retry_count, max_retries, next_retry_at, created_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """, outbox_rows)

                conn.commit()
                return True
            except Exception as e:
                conn.rollback()
                logger.error("Failed atomic event & outbox commit: %s", e)
                return False
            finally:
                conn.close()

    def get_runtime_state(self, task_id: str) -> Optional[TaskRuntimeState]:
        with self._lock:
            conn = self._get_connection()
            try:
                row = conn.execute(
                    "SELECT * FROM task_runtime_state WHERE task_id = ?",
                    (task_id,)
                ).fetchone()
                if not row:
                    return None
                return TaskRuntimeState(
                    task_id=row["task_id"],
                    active_state=row["active_state"],
                    consecutive_samples=row["consecutive_samples"],
                    last_evaluated_value=row["last_evaluated_value"],
                    last_evaluated_quality=row["last_evaluated_quality"],
                    last_evaluated_at=row["last_evaluated_at"],
                    last_triggered_at=row["last_triggered_at"]
                )
            finally:
                conn.close()

    def save_runtime_state(self, state: TaskRuntimeState):
        with self._lock:
            conn = self._get_connection()
            try:
                conn.execute("""
                INSERT INTO task_runtime_state (
                    task_id, active_state, consecutive_samples,
                    last_evaluated_value, last_evaluated_quality,
                    last_evaluated_at, last_triggered_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(task_id) DO UPDATE SET
                    active_state=excluded.active_state,
                    consecutive_samples=excluded.consecutive_samples,
                    last_evaluated_value=excluded.last_evaluated_value,
                    last_evaluated_quality=excluded.last_evaluated_quality,
                    last_evaluated_at=excluded.last_evaluated_at,
                    last_triggered_at=excluded.last_triggered_at
                """, (
                    state.task_id,
                    state.active_state,
                    state.consecutive_samples,
                    state.last_evaluated_value,
                    state.last_evaluated_quality,
                    state.last_evaluated_at,
                    state.last_triggered_at
                ))
                conn.commit()
            finally:
                conn.close()

    def get_pending_outbox_items(self, limit: int = 20) -> List[OutboxItem]:
        now_iso = datetime.now(timezone.utc).isoformat()
        items = []
        with self._lock:
            conn = self._get_connection()
            try:
                rows = conn.execute("""
                SELECT * FROM notification_outbox
                WHERE status = 'PENDING' AND (next_retry_at IS NULL OR next_retry_at <= ?)
                ORDER BY created_at ASC
                LIMIT ?
                """, (now_iso, limit)).fetchall()
                for r in rows:
                    items.append(OutboxItem(
                        outbox_id=r["outbox_id"],
                        event_id=r["event_id"],
                        channel=r["channel"],
                        recipient=r["recipient"],
                        payload=json.loads(r["payload"]) if r["payload"] else {},
                        status=r["status"],
                        retry_count=r["retry_count"],
                        max_retries=r["max_retries"],
                        next_retry_at=r["next_retry_at"],
                        created_at=r["created_at"],
                        sent_at=r["sent_at"],
                        last_error=r["last_error"]
                    ))
            finally:
                conn.close()
        return items

    def mark_outbox_sending(self, outbox_id: str):
        with self._lock:
            conn = self._get_connection()
            try:
                conn.execute(
                    "UPDATE notification_outbox SET status = 'SENDING' WHERE outbox_id = ?",
                    (outbox_id,)
                )
                conn.commit()
            finally:
                conn.close()

    def mark_outbox_sent(self, outbox_id: str):
        now_iso = datetime.now(timezone.utc).isoformat()
        with self._lock:
            conn = self._get_connection()
            try:
                conn.execute(
                    "UPDATE notification_outbox SET status = 'SENT', sent_at = ?, last_error = NULL WHERE outbox_id = ?",
                    (now_iso, outbox_id)
                )
                conn.commit()
            finally:
                conn.close()

    def mark_outbox_retry(self, outbox_id: str, error_msg: str, backoff_seconds: float):
        now = datetime.now(timezone.utc)
        next_try = (now + timedelta(seconds=backoff_seconds)).isoformat()
        with self._lock:
            conn = self._get_connection()
            try:
                row = conn.execute(
                    "SELECT retry_count, max_retries FROM notification_outbox WHERE outbox_id = ?",
                    (outbox_id,)
                ).fetchone()
                if row:
                    retries = row["retry_count"] + 1
                    status = "FAILED" if retries >= row["max_retries"] else "PENDING"
                    conn.execute("""
                    UPDATE notification_outbox
                    SET status = ?, retry_count = ?, next_retry_at = ?, last_error = ?
                    WHERE outbox_id = ?
                    """, (status, retries, next_try, error_msg[:255], outbox_id))
                    conn.commit()
            finally:
                conn.close()

    def record_delivery_attempt(
        self,
        outbox_id: str,
        status: str,
        http_status: Optional[int] = None,
        response_body: Optional[str] = None,
        error_message: Optional[str] = None
    ):
        now_iso = datetime.now(timezone.utc).isoformat()
        with self._lock:
            conn = self._get_connection()
            try:
                conn.execute("""
                INSERT INTO delivery_attempts (
                    outbox_id, attempt_time, status, http_status, response_body, error_message
                ) VALUES (?, ?, ?, ?, ?, ?)
                """, (
                    outbox_id,
                    now_iso,
                    status,
                    http_status,
                    response_body[:255] if response_body else None,
                    error_message[:255] if error_message else None
                ))
                conn.commit()
            finally:
                conn.close()

    def recover_uncommitted_outbox(self) -> int:
        """Recovers any items stuck in 'SENDING' state after an unexpected process crash."""
        with self._lock:
            conn = self._get_connection()
            try:
                cur = conn.execute(
                    "UPDATE notification_outbox SET status = 'PENDING' WHERE status = 'SENDING'"
                )
                conn.commit()
                recovered = cur.rowcount
                if recovered > 0:
                    logger.info("Outbox Recovery: Restored %d uncommitted 'SENDING' items to 'PENDING'", recovered)
                return recovered
            finally:
                conn.close()

    def cleanup_retention(self, retention_days: int = 7) -> int:
        """Removes observations older than retention period."""
        cutoff = (datetime.now(timezone.utc) - timedelta(days=retention_days)).isoformat()
        with self._lock:
            conn = self._get_connection()
            try:
                cur = conn.execute(
                    "DELETE FROM tag_observations WHERE arrival_timestamp < ?",
                    (cutoff,)
                )
                conn.commit()
                deleted = cur.rowcount
                if deleted > 0:
                    logger.info("Retention Cleanup: Purged %d observations older than %d days", deleted, retention_days)
                return deleted
            finally:
                conn.close()

    def get_recent_observations(self, tag_name: Optional[str] = None, limit: int = 50) -> List[StoredObservation]:
        with self._lock:
            conn = self._get_connection()
            try:
                if tag_name:
                    cursor = conn.execute(
                        "SELECT tag_name, value, unit, quality, raw_status, source_timestamp, server_timestamp, arrival_timestamp "
                        "FROM tag_observations WHERE tag_name = ? ORDER BY id DESC LIMIT ?",
                        (tag_name, limit)
                    )
                else:
                    cursor = conn.execute(
                        "SELECT tag_name, value, unit, quality, raw_status, source_timestamp, server_timestamp, arrival_timestamp "
                        "FROM tag_observations ORDER BY id DESC LIMIT ?",
                        (limit,)
                    )
                rows = cursor.fetchall()
                results = []
                for r in rows:
                    results.append(StoredObservation(
                        tag_name=r["tag_name"],
                        value=r["value"],
                        unit=r["unit"],
                        quality=r["quality"],
                        raw_status=r["raw_status"],
                        source_timestamp=r["source_timestamp"],
                        server_timestamp=r["server_timestamp"],
                        arrival_timestamp=r["arrival_timestamp"]
                    ))
                return results
            finally:
                conn.close()

    def get_task_events(self, task_id: Optional[str] = None, limit: int = 50) -> List[TaskEvent]:
        with self._lock:
            conn = self._get_connection()
            try:
                if task_id:
                    cursor = conn.execute(
                        "SELECT event_id, task_id, task_name, tag_name, trigger_type, trigger_value, threshold_value, description, severity, created_at "
                        "FROM task_events WHERE task_id = ? ORDER BY created_at DESC LIMIT ?",
                        (task_id, limit)
                    )
                else:
                    cursor = conn.execute(
                        "SELECT event_id, task_id, task_name, tag_name, trigger_type, trigger_value, threshold_value, description, severity, created_at "
                        "FROM task_events ORDER BY created_at DESC LIMIT ?",
                        (limit,)
                    )
                rows = cursor.fetchall()
                results = []
                for r in rows:
                    results.append(TaskEvent(
                        event_id=r["event_id"],
                        task_id=r["task_id"],
                        task_name=r["task_name"],
                        tag_name=r["tag_name"],
                        trigger_type=r["trigger_type"],
                        trigger_value=r["trigger_value"],
                        threshold_value=r["threshold_value"],
                        description=r["description"],
                        severity=r["severity"],
                        created_at=r["created_at"]
                    ))
                return results
            finally:
                conn.close()

    def is_db_full(self) -> bool:
        if not self.db_path.is_file():
            return False
        return self.db_path.stat().st_size >= self.max_db_size_bytes

    def get_stats(self) -> Dict[str, Any]:
        with self._lock:
            conn = self._get_connection()
            try:
                obs_cnt = conn.execute("SELECT COUNT(*) FROM tag_observations").fetchone()[0]
                evt_cnt = conn.execute("SELECT COUNT(*) FROM task_events").fetchone()[0]
                out_pending = conn.execute("SELECT COUNT(*) FROM notification_outbox WHERE status = 'PENDING'").fetchone()[0]
                out_sent = conn.execute("SELECT COUNT(*) FROM notification_outbox WHERE status = 'SENT'").fetchone()[0]
                out_failed = conn.execute("SELECT COUNT(*) FROM notification_outbox WHERE status = 'FAILED'").fetchone()[0]
                size_b = self.db_path.stat().st_size if self.db_path.is_file() else 0
                return {
                    "observations_count": obs_cnt,
                    "events_count": evt_cnt,
                    "outbox_pending": out_pending,
                    "outbox_sent": out_sent,
                    "outbox_failed": out_failed,
                    "db_size_bytes": size_b,
                    "is_full": size_b >= self.max_db_size_bytes
                }
            finally:
                conn.close()
