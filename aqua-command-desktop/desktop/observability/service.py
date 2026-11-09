"""Optional Unix-socket projection and passive host sampling, independent of core workers."""
import copy
import json
import os
import stat
import threading
import time
from collections import deque
from pathlib import Path

from .adapter import graph
from .contract import fresh, iso, timestamp
from .metrics import HostMetrics
from .transport import UnixServer


class ProjectionService:
    def __init__(self, path, token, contract, history, *, interval=5):
        if len(token) < 32:
            raise ValueError("A private bearer token is required")
        self.path, self.token, self.contract, self.history = Path(path), token, contract, history
        self.interval = interval
        self.lock = threading.Lock()
        self.snapshot = None
        self.metrics = deque(maxlen=720)
        self.stop_event = threading.Event()
        self.server = None
        self.threads = []
        self.socket_identity = None

    def publish(self, snapshot):
        # Freeze only JSON-compatible sanitized data; no owner references cross threads.
        frozen = json.loads(json.dumps(snapshot, allow_nan=False))
        with self.lock:
            self.snapshot = frozen

    def current(self, *, now=None):
        now = time.time() if now is None else now
        with self.lock:
            value = copy.deepcopy(self.snapshot)
        if value is None:
            return {"state": "NO_DATA", "stream": "RUNTIME", "devices": [], "tags": [],
                    "worker": {}, "probes": [], "refresh_events": [], "captured_at": None}
        producer_stale = not fresh(value["captured_at"], now, self.contract.ttl)
        if producer_stale:
            value["state"] = "STALE"
            value["worker"]["state"] = "STALE"
        for row in value["devices"]:
            observed = row.get("last_read_success") if row["connection_status"] == "READ_VERIFIED" else None
            observed = observed or row.get("observed_at")
            observed_state = row["connection_status"] in ("READ_VERIFIED", "OPC_UA_CONNECTED", "TCP_CONNECTED", "REACHABLE", "ERROR")
            if producer_stale or observed_state and "observed_at" in row and not fresh(observed, now, row.get("stale_after", self.contract.ttl)):
                row.update(connection_status="STALE", data_quality="STALE", session_state="UNKNOWN", tcp_status="STALE", last_read_success=None)
        for row in value["tags"]:
            expired = "arrival_timestamp" in row and (not fresh(row["arrival_timestamp"], now, row.get("stale_after", self.contract.ttl)) or
                not fresh(row.get("source_timestamp") or row["arrival_timestamp"], now, row.get("stale_after", self.contract.ttl)))
            if producer_stale or row["quality"] in ("GOOD", "UNCERTAIN") and expired:
                row.update(quality="STALE", value=None, session_state="UNKNOWN")
        return value

    def payload(self, path, params):
        prefix = "/v1/runtime/"
        if not path.startswith(prefix):
            raise KeyError(path)
        name = path[len(prefix):]
        known = {"health", "snapshot", "graph", "devices", "tags", "worker", "probes", "refresh",
                 "host", "host-history", "interfaces", "history", "events", "outbox", "attempts"}
        if name not in known:
            raise KeyError(path)
        if name in {"history", "events", "outbox", "attempts"}:
            history = self.history.read(params.get("window", "1h"), params.get("tag_id"),
                                        start_ms=params.get("from"), end_ms=params.get("to"))
            return dict(history, data=history["observations" if name == "history" else name])
        current = self.current()
        base = {"state": current["state"], "stream": "RUNTIME", "captured_at": current["captured_at"]}
        if name == "snapshot":
            return current
        if name == "health":
            return dict(base, listener="UP", authentication="REQUIRED", methods=["GET"])
        if name == "graph":
            if current["state"] == "NO_DATA":
                return dict(base, nodes=[], edges=[])
            topology = graph(current["devices"], current["tags"], self.history.read(), timestamp(current["captured_at"]) or 0)
            if current["state"] == "STALE":
                for row in topology["nodes"]:
                    row.update(mainStat="STALE", display_state="STALE", display_quality="STALE", color="#f0c36d")
                for row in topology["edges"]:
                    row.update(mainStat="STALE", color="#68768a")
            return dict(base, **topology)
        if name in {"host", "host-history", "interfaces"}:
            with self.lock:
                history = copy.deepcopy(list(self.metrics))
            latest = history[-1] if history else None
            if latest and not fresh(latest["timestamp"], time.time(), self.contract.ttl):
                latest = None
            data = history if name == "host-history" else latest.get("interfaces", []) if name == "interfaces" and latest else [latest] if latest else []
            return {"state": latest["state"] if latest else "NO_DATA", "stream": "RUNTIME", "data": data}
        data = [current["worker"]] if name == "worker" and current["worker"] else current.get("refresh_events" if name == "refresh" else name, [])
        return dict(base, data=data)

    def _sample_host(self):
        try:
            sampler = HostMetrics(self.contract)
            while not self.stop_event.is_set():
                result = sampler.sample()
                with self.lock:
                    self.metrics.append(result)
                self.stop_event.wait(self.interval)
        except Exception:
            # Optional metrics failure cannot propagate into monitoring or UI.
            pass

    def start(self):
        self.path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        parent = self.path.parent.stat()
        if parent.st_uid != os.getuid() or stat.S_IMODE(parent.st_mode) & 0o077:
            raise PermissionError("Projection directory must be private and owned")
        if os.path.lexists(self.path):
            raise FileExistsError("Projection socket already exists")
        try:
            self.server = UnixServer(self.path, self.token, self.payload)
            os.chmod(self.path, 0o600)
            self.socket_identity = self.path.stat().st_ino
            for target, kwargs in ((self.server.serve_forever, {"poll_interval": 0.1}), (self._sample_host, {})):
                thread = threading.Thread(target=target, kwargs=kwargs, daemon=True, name="Aqua-Observability")
                thread.start()
                self.threads.append(thread)
        except Exception:
            if self.server:
                self.server.server_close()
            raise

    def stop(self):
        self.stop_event.set()
        if self.server:
            self.server.shutdown()
            self.server.server_close()
        for thread in self.threads:
            thread.join(timeout=1)
        if self.socket_identity and self.path.exists() and self.path.stat().st_ino == self.socket_identity:
            self.path.unlink()
