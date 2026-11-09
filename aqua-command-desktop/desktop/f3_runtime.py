"""Read existing runtime evidence without starting workers or writing their state."""
import sqlite3
import time
from contextlib import closing
from pathlib import Path


TABLES = {"storage": "tag_observations", "task": "task_events",
          "outbox": "notification_outbox", "delivery": "delivery_attempts"}


def read_snapshot(db_path):
    snapshot = {"available": False, "origin": "UNBOUND_LOCAL_RUNTIME", "error": None}
    if not db_path:
        return dict(snapshot, error="Runtime database not available")
    path = Path(db_path)
    try:
        if not path.is_file():
            return dict(snapshot, error="Runtime database not available")
        stat = path.stat()
        started = time.monotonic()
        with closing(sqlite3.connect(path.resolve().as_uri() + "?mode=ro", uri=True, timeout=0.15)) as conn:
            conn.execute("PRAGMA query_only=ON")
            conn.set_progress_handler(lambda: int(time.monotonic() - started > 0.25), 2000)
            conn.execute("BEGIN")
            counts, marks = {}, {}
            for stage, table in TABLES.items():
                counts[stage], marks[stage] = conn.execute(
                    f"SELECT COUNT(*), COALESCE(MAX(rowid), 0) FROM {table}").fetchone()
            statuses = dict(conn.execute("SELECT status, COUNT(*) FROM notification_outbox GROUP BY status"))
            evaluation = conn.execute("SELECT MAX(last_evaluated_at) FROM task_runtime_state").fetchone()[0]
            delivery = conn.execute(
                "SELECT a.attempt_id, a.attempt_time, a.status, a.http_status, o.channel "
                "FROM delivery_attempts a JOIN notification_outbox o USING(outbox_id) "
                "ORDER BY a.attempt_id DESC LIMIT 1").fetchone()
        snapshot.update(available=True, counts=counts, marks=marks, outbox=statuses,
                        last_evaluation=evaluation, checked_at=time.time(),
                        db_identity=(stat.st_dev, stat.st_ino),
                        delivery_state="SYNTHETIC_DEMO" if delivery and delivery[4] == "mock_relay" else "RECORDED_UNVERIFIED" if delivery else "NOT_TESTED",
                        last_delivery={"id": delivery[0], "time": delivery[1], "status": delivery[2],
                                       "http_status": delivery[3], "channel": delivery[4]} if delivery else None)
    except (OSError, sqlite3.Error) as error:
        snapshot["error"] = f"Read-only runtime snapshot unavailable: {type(error).__name__}"
    return snapshot


class RuntimeEvidence:
    """Finite pulses from new observed events. Configuration and carrier emit none."""
    def __init__(self):
        self.snapshot = {"available": False}
        self.pulses = []
        self.baseline = None

    def accept(self, snapshot, *, now=None):
        now = time.monotonic() if now is None else now
        self.snapshot = snapshot
        if not snapshot.get("available"):
            self.pulses.clear()
            self.baseline = None
            return
        if self.baseline and self.baseline.get("db_identity") == snapshot.get("db_identity"):
            for stage, mark in snapshot["marks"].items():
                if mark > self.baseline["marks"].get(stage, mark):
                    self.pulses.append({"stage": stage, "event_id": f"{stage}:{mark}",
                                        "started": now, "source": "OBSERVED_LOCAL"})
        self.baseline = snapshot
        self.pulses = self.active(now=now)[-64:]

    def emit_read(self, source, event_id, *, connected, fresh, now=None):
        if connected and fresh:
            self.pulses.append({"stage": "read", "event_id": event_id, "source": source,
                                "started": time.monotonic() if now is None else now})
            self.pulses = self.pulses[-64:]

    def clear_source(self, source):
        self.pulses = [item for item in self.pulses if item["source"] != source]

    def active(self, *, now=None):
        now = time.monotonic() if now is None else now
        return [dict(item, progress=(now - item["started"]) / 1.2)
                for item in self.pulses if 0 <= now - item["started"] < 1.2]
