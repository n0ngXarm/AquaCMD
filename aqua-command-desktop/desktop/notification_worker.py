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
import time
import json
import logging
import threading
import urllib.request
import urllib.error
from urllib.parse import urlsplit
from ipaddress import ip_address
from typing import Dict, Any, Optional
from datetime import datetime, timezone

from opcua_storage import DurableStorage, OutboxItem

logger = logging.getLogger("aqua.notification")


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


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
        self.mock_endpoint_url = mock_endpoint_url or os.environ.get("AQUA_MOCK_TELEGRAM_URL")
        self._opener = urllib.request.build_opener(urllib.request.ProxyHandler({}), NoRedirect())

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
            if self.running or (self.thread and self.thread.is_alive()):
                return
            self.storage.recover_uncommitted_outbox()
            self.running = True
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
        if self.thread and self.thread.is_alive():
            logger.warning("NotificationWorker still finishing an in-flight request")
        else:
            logger.info("NotificationWorker stopped")

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
        if not self.storage.mark_outbox_sending(item.outbox_id):
            return
        self._record_rate_limit_send()
        try:
            if item.channel == "telegram":
                status, code, receipt, reason, retry_after = self._dispatch_telegram(item)
            elif item.channel == "mock_relay":
                status, code, receipt, reason, retry_after = "SIMULATED", None, None, "Local simulation only", 0
            else:
                status, code, receipt, reason, retry_after = "FAILED", None, None, "Unknown channel", 0
        except Exception:
            status, code, receipt, reason, retry_after = (
                "DELIVERY_UNKNOWN", None, None, "Delivery acceptance could not be confirmed", 0
            )

        if status == "SENT":
            self.storage.mark_outbox_sent(item.outbox_id)
            self.delivered_count += 1
            self.last_delivery_time = datetime.now(timezone.utc).isoformat()
        elif status == "RETRY_PENDING":
            backoff = max(retry_after, min(300.0, self.base_backoff_seconds * (2 ** item.retry_count)))
            self.storage.mark_outbox_retry(item.outbox_id, reason, backoff)
            self.retry_count += 1
        else:
            self.storage.hold_outbox(item.outbox_id, status, reason)
            self.failed_count += status == "FAILED"
        self.last_error = reason
        self.storage.record_delivery_attempt(
            outbox_id=item.outbox_id,
            status="SUCCESS" if status == "SENT" else "FAILURE" if status == "RETRY_PENDING" else status,
            http_status=code,
            response_body=receipt,
            error_message=reason,
        )

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

    def _dispatch_telegram(self, item: OutboxItem):
        bot_token = item.payload.get("bot_token")
        chat_id = item.recipient or item.payload.get("chat_id")
        if not chat_id:
            return "FAILED", None, None, "Missing recipient chat_id", 0

        if self.mock_endpoint_url:
            try:
                endpoint = urlsplit(self.mock_endpoint_url)
                allowed = (endpoint.scheme == "http" and ip_address(endpoint.hostname).is_loopback
                           and not any((endpoint.username, endpoint.password, endpoint.query, endpoint.fragment)))
            except ValueError:
                allowed = False
            if not allowed:
                return "BLOCKED_BY_POLICY", None, None, "LAB relay requires a loopback HTTP address", 0
            url = f"{self.mock_endpoint_url.rstrip('/')}/bot{bot_token or 'lab-token'}/sendMessage"
        else:
            if os.environ.get("APP_ENV") != "production" or os.environ.get("TELEGRAM_EXTERNAL_DELIVERY_AUTHORIZED") != "true":
                return "BLOCKED_BY_POLICY", None, None, "External Telegram delivery is not authorized", 0
            if not bot_token:
                return "FAILED", None, None, "Missing Telegram bot token", 0
            url = f"https://api.telegram.org/bot{bot_token}/sendMessage"

        request = urllib.request.Request(url, data=json.dumps({
            "chat_id": chat_id, "text": self._format_telegram_message(item.payload), "parse_mode": "HTML",
        }).encode("utf-8"), headers={"Content-Type": "application/json"})
        try:
            with self._opener.open(request, timeout=5.0) as response:
                code = response.getcode()
                result = json.loads(response.read(65536))
                message_id = (result.get("result") or {}).get("message_id")
                if code == 200 and result.get("ok") is True and type(message_id) is int:
                    return "SENT", code, json.dumps({"message_id": message_id}), None, 0
                return "DELIVERY_UNKNOWN", code, None, "Telegram acceptance could not be confirmed", 0
        except urllib.error.HTTPError as error:
            try:
                rejection = json.loads(error.read(65536))
            except (ValueError, OSError):
                rejection = {}
            if isinstance(rejection, dict) and rejection.get("ok") is False and rejection.get("error_code") == error.code:
                if error.code == 429:
                    seconds = (rejection.get("parameters") or {}).get("retry_after")
                    delay = seconds if type(seconds) is int and 0 < seconds <= 86400 else 0
                    return "RETRY_PENDING", error.code, None, "Telegram rate limit", delay
                if 400 <= error.code < 500 and error.code != 408:
                    return "FAILED", error.code, None, f"Telegram rejected the request (HTTP {error.code})", 0
            return "DELIVERY_UNKNOWN", error.code, None, "Telegram acceptance could not be confirmed", 0
        except urllib.error.URLError as error:
            if isinstance(error.reason, ConnectionRefusedError):
                return "RETRY_PENDING", None, None, "Connection refused before dispatch", 0
            return "DELIVERY_UNKNOWN", None, None, "Telegram acceptance could not be confirmed", 0
