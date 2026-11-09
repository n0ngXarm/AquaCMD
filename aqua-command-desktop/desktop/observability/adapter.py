"""Capture existing owner objects on the GTK thread; serialize only sanitized fields."""
import time
from collections import Counter, deque
from types import SimpleNamespace

from .contract import evidence, iso, timestamp, fresh, quality

COLORS = {"READ_VERIFIED": "#56d9a2", "OPC_UA_CONNECTED": "#67baf5", "TCP_CONNECTED": "#a3afff",
          "REACHABLE": "#8cc7d9", "STALE": "#f0c36d", "ERROR": "#ed7f85"}


def graph(devices, tags, history, now):
    nodes, edges = [], []
    for row in devices:
        if row["kind"] != "OPC_UA_SOURCE":
            continue
        state = row["connection_status"]
        nodes.append({"id": row["device_id"], "title": row["alias"], "subTitle": "OPC UA source",
            "mainStat": state, "secondaryStat": row["data_quality"], "color": COLORS.get(state, "#91a0b4"),
            "detail__session": row["session_state"], "detail__tcp": row["tcp_status"],
            "detail__certificate": row["certificate_status"], "detail__provenance": row["provenance"],
            "detail__observed_at": row["observed_at"] or "NOT_OBSERVED", "detail__target": row["target_ref"] or "NOT_CONFIGURED"})
        edges.append({"id": "read-" + row["device_id"], "source": row["device_id"], "target": "collector",
            "mainStat": state, "detail__relation": "Logical configured read path; not a physical cable",
            "detail__evidence": "Recent read receipt" if state == "READ_VERIFIED" else "No current verified data flow",
            "color": COLORS[state] if state == "READ_VERIFIED" else "#68768a"})
    fixed = (("collector", "AQUA Collector", "OWNER_RUNNING"),
             ("storage", "SQLite", history.get("state", "UNKNOWN")),
             ("task", "Task Engine", "RECORDED_EVENTS" if history.get("events") else "NO_DATA"),
             ("outbox", "Durable Outbox", "RECORDED_ITEMS" if history.get("outbox") else "NO_DATA"),
             ("relay", "Notification Relay", "UNVERIFIED"))
    for ident, title, state in fixed:
        nodes.append({"id": ident, "title": title, "subTitle": "Logical data flow",
            "mainStat": state, "secondaryStat": "", "color": COLORS.get(state, "#91a0b4"),
            "detail__provenance": "OBSERVED_LOCAL" if ident == "collector" else "UNBOUND_LOCAL_RUNTIME",
            "detail__observed_at": iso(now), "detail__session": "N/A", "detail__tcp": "N/A",
            "detail__certificate": "N/A", "detail__target": "Local owner"})
    for source, target in (("collector", "storage"), ("storage", "task"), ("task", "outbox"), ("outbox", "relay")):
        edges.append({"id": source + "-" + target, "source": source, "target": target,
            "mainStat": "CONFIGURED_PATH", "detail__relation": "Logical pipeline; no source-to-delivery correlation",
            "detail__evidence": "UNVERIFIED", "color": "#68768a"})
    compact = {"CONFIGURED": "CONFIG", "READ_VERIFIED": "READ OK", "OPC_UA_CONNECTED": "SESSION", "TCP_CONNECTED": "TCP",
        "OWNER_RUNNING": "OWNER", "AVAILABLE": "DB OK", "NO_DATA": "NO DATA", "UNVERIFIED": "NO ACK",
        "NOT_OBSERVED": "NO READ", "RECORDED_EVENTS": "EVENTS", "RECORDED_ITEMS": "ITEMS"}
    for node in nodes:
        node["display_state"] = compact.get(node["mainStat"], node["mainStat"])
        node["display_quality"] = compact.get(node["secondaryStat"], node["secondaryStat"])
    return {"nodes": nodes, "edges": edges}


class OwnerProjection:
    def __init__(self, contract):
        self.contract = contract
        self.refresh_events = []
        self.probe_events = deque(maxlen=500)

    def record_refresh(self, catalog_count, *, now=None):
        now = time.time() if now is None else now
        self.refresh_events.append({"timestamp": iso(now), "event_type": "LOCAL_CATALOG_REFRESH",
            "catalog_count": int(catalog_count), "provenance": "OBSERVED_LOCAL", "network_probe": False})
        self.refresh_events = self.refresh_events[-500:]

    def capture(self, owner, *, now=None):
        """Only call on the owner thread. Does not start, stop or query any industrial worker."""
        now = time.time() if now is None else now
        f3 = getattr(owner, "f3_network_view", None)
        store = getattr(f3, "store", None)
        demo = bool(getattr(store, "is_demo_mode", False))
        raw = [d for d in getattr(store, "devices", {}).values() if not d.get("is_demo")] if not demo else []
        telemetry = owner.polling_engine.get_telemetry()
        poll_state = telemetry.get("state", "UNKNOWN")
        active = poll_state in ("RUNNING", "PAUSED", "RECONNECTING")
        entry = getattr(owner, "entry_opc_url", None)
        endpoint = owner.polling_engine.endpoint_url if active else entry.get_text().strip() if entry else ""
        if endpoint and not any(d.get("endpoint_url") == endpoint for d in raw):
            raw.append({"device_id": "shared-opcua-source", "endpoint_url": endpoint, "type": "scada_server"})
        counts = Counter(d.get("endpoint_url") for d in raw if d.get("endpoint_url"))
        targets = {d["endpoint_url"]: d["device_id"] for d in raw if d.get("endpoint_url") and counts[d["endpoint_url"]] == 1}
        devices = [self.contract.device(d, now) for d in raw]
        tags = [self.contract.tag(obs, targets, now) for obs in owner.opcua_store.snapshot_observations()[:2000]]
        known_receipts = {row["receipt_id"] for row in self.probe_events}
        for dev, row in zip(raw, devices):
            for kind in ("reachability", "tcp", "session", "read"):
                item = dev.get("evidence", {}).get(kind, {})
                checked = timestamp(item.get("checked_at"))
                if checked is not None and item.get("source") in ("OBSERVED_REMOTE", "VERIFIED_OPCUA"):
                    receipt_id = self.contract.identity("receipt", (row["device_id"], kind, checked, item.get("target")))
                    if receipt_id not in known_receipts:
                        state = evidence.evidence_state(dev, kind, now=now)
                        if state not in ("UNKNOWN", "STALE", "SYNTHETIC_DEMO"):
                            state = {"reachability": dev.get("reachability") if dev.get("reachability") in ("REACHABLE", "UNREACHABLE") else "UNKNOWN",
                                "tcp": "TCP_CONNECTED" if dev.get("tcp_ok") is True else "ERROR" if dev.get("tcp_ok") is False else "UNKNOWN",
                                "session": row["session_state"],
                                "read": quality(dev.get("last_read_quality")) if dev.get("read_success") is True else "ERROR"}[kind]
                        self.probe_events.append({"receipt_id": receipt_id, "device_id": row["device_id"], "event_type": kind.upper(),
                            "timestamp": iso(checked), "provenance": item["source"], "status": state,
                            "target_ref": self.contract.identity("target", item.get("target")), "new_probe": False})
                        known_receipts.add(receipt_id)
            if row["data_quality"] not in ("NOT_OBSERVED", "STALE") and dev.get("tag_name"):
                receipt = SimpleNamespace(tag_name=dev["tag_name"], value=dev.get("last_read_value"),
                    quality=dev.get("last_read_quality"), source_time=dev.get("source_timestamp"),
                    arrival_time=dev.get("arrival_timestamp") or dev.get("last_read_time"),
                    unit=dev.get("unit", ""), endpoint_url=dev.get("endpoint_url"), session_state="CLOSED")
                tags.append(self.contract.tag(receipt, targets, now))
        by_id = {}
        for tag in sorted(tags, key=lambda t: timestamp(t["arrival_timestamp"]) or 0):
            by_id[tag["tag_id"]] = tag
        tags = list(by_id.values())
        # Actual shared read receipts may enrich the matching source; poll counters never do.
        for row in devices:
            observed = [t for t in tags if t["device_id"] == row["device_id"]]
            latest = max(observed, key=lambda t: timestamp(t["arrival_timestamp"]) or 0, default=None)
            if latest:
                row["data_quality"] = latest["quality"]
                row["last_read_success"] = latest["arrival_timestamp"] if latest["quality"] == "GOOD" else None
                row["observed_at"] = latest["arrival_timestamp"]
                row["provenance"] = latest["provenance"]
                row["connection_status"] = "READ_VERIFIED" if latest["quality"] == "GOOD" else "STALE" if latest["quality"] == "STALE" else "ERROR" if latest["quality"] in ("BAD", "UNCERTAIN", "DISCONNECTED") else "UNKNOWN"
                row["session_state"] = "CONNECTED" if latest["session_state"] == "CONNECTED" and active and poll_state == "RUNNING" and fresh(latest["arrival_timestamp"], now, self.contract.ttl) else "CLOSED" if latest["session_state"] == "CLOSED" else "UNKNOWN"
        worker = {k: telemetry.get(k) for k in ("state", "interval_seconds", "poll_count", "successful_polls",
            "failed_polls", "target_tags_count", "last_poll_duration_ms", "jitter_ms", "reconnect_attempts")}
        return {"stream": "RUNTIME", "captured_at": iso(now), "state": "AVAILABLE",
            "devices": devices, "tags": tags, "worker": worker, "probes": list(self.probe_events),
            "refresh_events": list(self.refresh_events), "synthetic_inventory_excluded": demo,
            "privacy": "OPAQUE_IDS", "stale_after": self.contract.ttl}
