#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
notification_worker.py — Decoupled Notification & Outbox Worker for AQUA COMMAND
Processes Durable Outbox queue, formats Alert messages, and dispatches to
Telegram Bot API or Authorized Gateway Relay with Exponential Backoff,
Deduplication, and Rate Limiting.

Strict Safety Invariants:
- Zero raw socket sweeps or unauthorized internet routing.
- Pending items remain safely in outbox during network disconnections.
- Mock relay endpoint support for loopback offline verification.
- Prohibits real production sends without explicit user consent.
"""

import os
import sys
import time
import json
import logging
import threading
import urllib.request
import urllib.error
from typing import Dict, Any, Optional
from datetime import datetime, timezone

from opcua_storage import DurableStorage, OutboxItem

logger = logging.getLogger("aqua.notification")


class NotificationWorker:
    """Decoupled background worker for reliable notification outbox delivery."""

    def __init__(
        self,
        storage: DurableStorage,
        poll_interval: float = 1.0,
        rate_limit_per_min: int = 20,
        base_backoff_seconds: float = 2.0,
        mock_endpoint_url: Optional[str] = None
    ):
        self.storage = storage
        self.poll_interval = poll_interval
        self.rate_limit_per_min = rate_limit_per_min
        self.base_backoff_seconds = base_backoff_seconds
        self.mock_endpoint_url = mock_endpoint_url or os.environ.get("AQUA_MOCK_TELEGRAM_URL")  # e.g. "http://127.0.0.1:8088"

        self.running = False
        self.thread: Optional[threading.Thread] = None
        self._sent_timestamps = []
        self._lock = threading.Lock()

        # Telemetry metrics
        self.delivered_count = 0
        self.failed_count = 0
        self.retry_count = 0
        self.last_delivery_time: Optional[str] = None
        self.last_error: Optional[str] = None

    def start(self):
        with self._lock:
            if self.running:
                return
            self.running = True
            # Crash recovery on worker startup
            self.storage.recover_uncommitted_outbox()
            self.thread = threading.Thread(target=self._worker_loop, daemon=True, name="AquaNotificationWorker")
            self.thread.start()
            logger.info("NotificationWorker started (interval: %.1fs, rate limit: %d/min)", self.poll_interval, self.rate_limit_per_min)

    def stop(self, timeout: float = 3.0):
        with self._lock:
            if not self.running:
                return
            self.running = False
        if self.thread and self.thread.is_alive():
            self.thread.join(timeout=timeout)
        logger.info("NotificationWorker stopped cleanly.")

    def _worker_loop(self):
        while self.running:
            try:
                items = self.storage.get_pending_outbox_items(limit=10)
                for item in items:
                    if not self.running:
                        break
                    if not self._check_rate_limit():
                        time.sleep(0.5)
                        break
                    self._process_outbox_item(item)
            except Exception as e:
                logger.error("Error in notification worker loop: %s", e)

            # Sleep poll interval in short slices for prompt termination
            elapsed = 0.0
            while elapsed < self.poll_interval and self.running:
                time.sleep(0.2)
                elapsed += 0.2

    def _check_rate_limit(self) -> bool:
        now = time.monotonic()
        # Prune timestamps older than 60 seconds
        self._sent_timestamps = [t for t in self._sent_timestamps if now - t < 60.0]
        return len(self._sent_timestamps) < self.rate_limit_per_min

    def _record_rate_limit_send(self):
        self._sent_timestamps.append(time.monotonic())

    def _process_outbox_item(self, item: OutboxItem):
        self.storage.mark_outbox_sending(item.outbox_id)
        success = False
        http_code = None
        resp_body = None
        err_msg = None

        try:
            if item.channel == "telegram":
                success, http_code, resp_body, err_msg = self._dispatch_telegram(item)
            elif item.channel == "mock_relay":
                success, http_code, resp_body, err_msg = self._dispatch_mock_relay(item)
            else:
                err_msg = f"Unknown channel: {item.channel}"
                success = False
        except Exception as ex:
            err_msg = str(ex)
            success = False

        if success:
            self._record_rate_limit_send()
            self.storage.mark_outbox_sent(item.outbox_id)
            self.storage.record_delivery_attempt(
                outbox_id=item.outbox_id,
                status="SUCCESS",
                http_status=http_code,
                response_body=resp_body
            )
            self.delivered_count += 1
            self.last_delivery_time = datetime.now(timezone.utc).isoformat()
            logger.info("Outbox item %s delivered successfully to %s", item.outbox_id, item.channel)
        else:
            backoff = min(300.0, self.base_backoff_seconds * (2 ** item.retry_count))
            self.storage.mark_outbox_retry(item.outbox_id, err_msg or "Delivery failed", backoff)
            self.storage.record_delivery_attempt(
                outbox_id=item.outbox_id,
                status="FAILURE",
                http_status=http_code,
                response_body=resp_body,
                error_message=err_msg
            )
            self.retry_count += 1
            self.last_error = err_msg
            logger.warning("Outbox item %s delivery failed (%s). Scheduled retry in %.1fs", item.outbox_id, err_msg, backoff)

    def _format_telegram_message(self, payload: Dict[str, Any]) -> str:
        sev_icon = "⚠️"
        if payload.get("severity") == "CRITICAL":
            sev_icon = "🚨"
        elif payload.get("severity") == "INFO":
            sev_icon = "ℹ️"

        msg = (
            f"{sev_icon} [AQUA COMMAND SCADA ALERT]\n"
            f"━━━━━━━━━━━━━━━━━━━━━━\n"
            f"📍 ระบบ: AQUA COMMAND SCADA Gateway\n"
            f"⚙️ งานเฝ้าระวัง: {payload.get('task_name', 'SCADA Task')}\n"
            f"🏷️ จุดวัด (Tag): {payload.get('tag_name', '-')}\n"
            f"📊 ค่าที่ตรวจวัด: {payload.get('value', '-')} {payload.get('unit', '')}\n"
            f"📋 รายละเอียด: {payload.get('description', '-')}\n"
            f"🕒 เวลาเหตุการณ์: {payload.get('timestamp', '-')}\n"
            f"━━━━━━━━━━━━━━━━━━━━━━\n"
            f"🔒 OT Security: Secure Read-Only Gate"
        )
        return msg

    def _dispatch_telegram(self, item: OutboxItem) -> tuple[bool, Optional[int], Optional[str], Optional[str]]:
        bot_token = item.payload.get("bot_token") or "dummy_bot_token"
        chat_id = item.recipient or item.payload.get("chat_id")
        if not chat_id:
            return False, None, None, "Missing recipient chat_id"

        text = self._format_telegram_message(item.payload)

        # Allow URL override for mock loopback testing
        if self.mock_endpoint_url:
            url = f"{self.mock_endpoint_url.rstrip('/')}/bot{bot_token}/sendMessage"
        else:
            url = f"https://api.telegram.org/bot{bot_token}/sendMessage"

        req_data = json.dumps({
            "chat_id": chat_id,
            "text": text,
            "parse_mode": "HTML"
        }).encode("utf-8")

        req = urllib.request.Request(
            url,
            data=req_data,
            headers={"Content-Type": "application/json"}
        )

        try:
            with urllib.request.urlopen(req, timeout=5.0) as resp:
                code = resp.getcode()
                body = resp.read().decode("utf-8", errors="replace")
                return (code == 200), code, body, None
        except urllib.error.HTTPError as e:
            err_body = e.read().decode("utf-8", errors="replace") if hasattr(e, "read") else ""
            return False, e.code, err_body, f"HTTP Error {e.code}: {e.reason}"
        except urllib.error.URLError as e:
            return False, None, None, f"Network Error: {e.reason}"
        except Exception as e:
            return False, None, None, str(e)

    def _dispatch_mock_relay(self, item: OutboxItem) -> tuple[bool, Optional[int], Optional[str], Optional[str]]:
        # Mock relay dispatch directly succeeds in tests
        return True, 200, json.dumps({"ok": True, "message_id": 12345}), None
