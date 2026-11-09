"""Bounded, sanitized SQLite reads. Never initialize or migrate the owning database."""
import sqlite3
import time
from contextlib import closing
from pathlib import Path

from .contract import iso, quality, scalar

WINDOWS = {"1h": 3600, "24h": 86400, "7d": 604800}
UNITS = {"", "%", "m", "mm", "cm", "bar", "kPa", "MPa", "°C", "C", "Hz", "A", "V", "kW", "m3/h", "m³/h", "s"}


class History:
    def __init__(self, path, contract):
        self.path, self.contract = Path(path), contract

    def read(self, window="1h", tag_id=None, *, now=None, start_ms=None, end_ms=None):
        if window not in WINDOWS:
            raise ValueError("Unsupported history window")
        now = time.time() if now is None else now
        start, end = now - WINDOWS[window], now
        if start_ms is not None or end_ms is not None:
            try:
                start, end = int(start_ms) / 1000, int(end_ms) / 1000
            except (TypeError, ValueError, OverflowError) as error:
                raise ValueError("Invalid history range") from error
            if start < 0 or end <= start or end - start > WINDOWS["7d"] or end > now + 1:
                raise ValueError("History range must be in the past and no longer than seven days")
        result = {"state": "NO_DATA", "stream": "RUNTIME", "provenance": "UNBOUND_LOCAL_RUNTIME", "checked_at": iso(now),
                  "window": "CUSTOM" if start_ms is not None else window, "range_start": iso(start), "range_end": iso(end),
                  "observations": [], "events": [], "outbox": [], "attempts": [], "limit": 2000,
                  "coverage": "BOUNDED_RECENT_ROWS"}
        if not self.path.is_file():
            return result
        started = time.monotonic()
        try:
            with closing(sqlite3.connect(self.path.resolve().as_uri() + "?mode=ro", uri=True, timeout=0.1)) as db:
                db.execute("PRAGMA query_only=ON")
                db.set_progress_handler(lambda: int(time.monotonic() - started > 0.3), 1000)
                db.execute("BEGIN")
                bounds = (iso(start), iso(end))
                selected = None
                if tag_id:
                    candidates = db.execute("SELECT DISTINCT tag_name FROM tag_observations "
                        "WHERE julianday(arrival_timestamp) BETWEEN julianday(?) AND julianday(?) LIMIT 2000", bounds)
                    selected = next((name for (name,) in candidates if self.contract.identity("tag", name) == tag_id), None)
                rows = [] if tag_id and selected is None else db.execute(
                    "SELECT tag_name,value,unit,quality,source_timestamp,arrival_timestamp FROM tag_observations "
                    "WHERE julianday(arrival_timestamp) BETWEEN julianday(?) AND julianday(?) " +
                    ("AND tag_name=? " if selected is not None else "") + "ORDER BY id DESC LIMIT 2000",
                    (*bounds, selected) if selected is not None else bounds)
                for name, value, unit, q, source, arrival in rows:
                    ident = self.contract.identity("tag", name)
                    if tag_id and tag_id != ident:
                        continue
                    q = quality(q)
                    result["observations"].append({"tag_id": ident, "value": scalar(value) if q == "GOOD" else None,
                        "unit": unit if unit in UNITS else "", "quality": q, "source_timestamp": iso(source),
                        "timestamp": iso(arrival), "provenance": "UNBOUND_LOCAL_RUNTIME",
                        "series": ident + " [" + (unit if unit in UNITS and unit else "unit not supplied") + "]"})
                result["observations"].sort(key=lambda row: row["timestamp"] or "")
                # Synthetic mock-relay events are not runtime notification evidence.
                events = db.execute(
                    "SELECT event_id,task_id,trigger_type,severity,created_at,trigger_value,threshold_value FROM task_events e "
                    "WHERE julianday(created_at) BETWEEN julianday(?) AND julianday(?) AND NOT EXISTS "
                    "(SELECT 1 FROM notification_outbox o WHERE o.event_id=e.event_id AND o.channel='mock_relay') "
                    "ORDER BY created_at DESC LIMIT 500", bounds)
                for event, task, kind, severity, stamp, value, threshold in events:
                    result["events"].append({"event_id": self.contract.identity("event", event),
                        "task_id": self.contract.identity("task", task), "event_type": kind if kind in
                        {"threshold_high", "threshold_low", "transition_on", "transition_off", "analog_high", "analog_low", "digital_on", "digital_off"} else "RECORDED_EVENT",
                        "severity": severity.upper() if severity.upper() in {"INFO", "WARNING", "CRITICAL", "ERROR"} else "UNKNOWN",
                        "timestamp": iso(stamp), "trigger_value": scalar(value), "threshold_value": scalar(threshold),
                        "acknowledgement_state": "UNVERIFIED", "provenance": "UNBOUND_LOCAL_RUNTIME",
                        "event_marker": 1, "series": self.contract.identity("task", task) + " [unit not recorded]"})
                result["events"].sort(key=lambda row: row["timestamp"] or "")
                outbox = db.execute(
                    "SELECT outbox_id,event_id,status,(SELECT COUNT(*) FROM delivery_attempts a WHERE a.outbox_id=o.outbox_id),"
                    "created_at,sent_at,(SELECT MAX(attempt_time) FROM delivery_attempts a WHERE a.outbox_id=o.outbox_id) FROM notification_outbox o "
                    "WHERE channel!='mock_relay' AND julianday(created_at) BETWEEN julianday(?) AND julianday(?) "
                    "ORDER BY created_at DESC LIMIT 500", bounds)
                for item, event, status, count, created, sent, attempted in outbox:
                    result["outbox"].append({"outbox_id": self.contract.identity("outbox", item),
                        "event_id": self.contract.identity("event", event), "status": status if status in
                        {"PENDING", "SENDING", "SENT", "FAILED", "RETRY"} else "UNKNOWN",
                        "attempt_count": count, "timestamp": iso(created), "last_attempt_at": iso(attempted),
                        "sent_at": iso(sent), "acknowledgement_state": "UNVERIFIED"})
                attempts = db.execute(
                    "SELECT a.attempt_id,a.outbox_id,a.attempt_time,a.status,a.http_status FROM delivery_attempts a "
                    "JOIN notification_outbox o USING(outbox_id) WHERE o.channel!='mock_relay' AND "
                    "julianday(a.attempt_time) BETWEEN julianday(?) AND julianday(?) ORDER BY a.attempt_id DESC LIMIT 500", bounds)
                for ident, item, stamp, status, http in attempts:
                    result["attempts"].append({"attempt_id": self.contract.identity("attempt", ident),
                        "outbox_id": self.contract.identity("outbox", item), "timestamp": iso(stamp),
                        "status": status if status in {"SUCCESS", "FAILED", "SENT", "ERROR", "RETRY"} else "UNKNOWN",
                        "http_status": http if isinstance(http, int) and not isinstance(http, bool) and 100 <= http <= 599 else None,
                        "acknowledgement_state": "UNVERIFIED"})
            result["state"] = "AVAILABLE"
        except (sqlite3.Error, OSError):
            # No raw exception, path, SQL or partial payload crosses the boundary.
            result.update(state="ERROR", observations=[], events=[], outbox=[], attempts=[])
        return result
