"""Sanitized point-in-time contracts. No I/O, GTK or industrial dependencies."""
import hashlib
import hmac
import math
from datetime import datetime, timezone

try:
    from .. import f3_evidence as evidence
except ImportError:
    import f3_evidence as evidence


def timestamp(value):
    try:
        if isinstance(value, str):
            value = datetime.fromisoformat(value.replace("Z", "+00:00"))
        if isinstance(value, datetime):
            value = value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value
            return value.timestamp()
        if isinstance(value, (int, float)) and math.isfinite(value):
            return float(value)
    except (ValueError, OverflowError, OSError):
        pass
    return None


def iso(value):
    epoch = timestamp(value)
    try:
        return datetime.fromtimestamp(epoch, timezone.utc).isoformat() if epoch is not None else None
    except (ValueError, OverflowError, OSError):
        return None


def fresh(value, now, ttl):
    epoch = timestamp(value)
    return epoch is not None and -1 <= now - epoch <= ttl


def scalar(value):
    # Strings/objects may contain sensitive payloads; numeric/bool telemetry only.
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)) and math.isfinite(value):
        return value
    return None


def quality(value):
    value = str(value or "NOT_OBSERVED").upper()
    return value if value in {"GOOD", "BAD", "UNCERTAIN", "STALE", "DISCONNECTED", "NOT_OBSERVED"} else "NOT_OBSERVED"


class Contract:
    def __init__(self, key, *, ttl=15.0):
        if not isinstance(key, bytes) or len(key) < 32:
            raise ValueError("Projection requires a private key of at least 32 bytes")
        self.key, self.ttl = key, ttl

    def identity(self, kind, raw):
        digest = hmac.new(self.key, (kind + "\0" + str(raw)).encode(), hashlib.sha256).hexdigest()[:20]
        return kind + "-" + digest

    def device(self, dev, now):
        ident = self.identity("device", dev.get("device_id", ""))
        kinds = ("read", "session", "tcp", "reachability", "local", "identity", "certificate")
        states = {kind: evidence.evidence_state(dev, kind, now=now) for kind in kinds}
        for kind in kinds:
            item = dev.get("evidence", {}).get(kind, {})
            if timestamp(item.get("checked_at")) is None:
                states[kind] = "UNKNOWN"
            if kind in evidence.OPCUA_KINDS and evidence.endpoint_target(dev)[2]:
                states[kind] = "UNKNOWN"
        valid = lambda kind: states[kind] not in ("UNKNOWN", "STALE", "SYNTHETIC_DEMO")
        read_ok = valid("read") and dev.get("read_success") is True
        q = quality(dev.get("last_read_quality") or dev.get("quality")) if read_ok else "NOT_OBSERVED"
        if states["read"] == "STALE":
            q = "STALE"
        connected = valid("session") and dev.get("session_state") == "CONNECTED"
        tcp = dev.get("tcp_ok") if valid("tcp") else None
        reach = valid("reachability") and dev.get("reachability") == "REACHABLE"
        local = valid("local") and dev.get("reachability") == "VERIFIED_LOCAL"
        state = "READ_VERIFIED" if read_ok and q == "GOOD" else "OPC_UA_CONNECTED" if connected else "TCP_CONNECTED" if tcp is True else "REACHABLE" if reach or local else None
        if read_ok and q in ("BAD", "UNCERTAIN"):
            state = "ERROR"
        if state is None:
            state = "ERROR" if tcp is False else "STALE" if "STALE" in states.values() else "CONFIGURED" if dev.get("configured_ip") or dev.get("endpoint_url") else "UNKNOWN"
        times = [timestamp(dev.get("evidence", {}).get(k, {}).get("checked_at")) for k in kinds if valid(k)]
        observed = max((t for t in times if t is not None), default=None)
        return {
            "device_id": ident, "alias": "Device " + ident[-6:],
            "verified_hostname": None, "configured_ip": None, "observed_ip": None,
            "target_ref": self.identity("target", dev.get("endpoint_url") or dev.get("configured_ip")) if dev.get("endpoint_url") or dev.get("configured_ip") else None,
            "configured_endpoint": "REDACTED" if dev.get("endpoint_url") else None,
            "connection_status": state, "identity_source": states["identity"],
            "observed_at": iso(observed), "stale_after": self.ttl,
            "tcp_status": "TCP_CONNECTED" if tcp is True else "ERROR" if tcp is False else states["tcp"],
            "certificate_status": str(dev.get("certificate_trust")) if valid("certificate") and dev.get("certificate_trust") in ("TRUSTED", "UNTRUSTED", "EXPIRED", "NOT_APPLICABLE") else states["certificate"],
            "session_state": "CONNECTED" if connected else "CLOSED" if valid("session") and dev.get("session_state") == "CLOSED" else "UNKNOWN",
            "last_read_success": iso(dev.get("last_successful_read") or dev.get("last_read_time")) if read_ok else None,
            "data_quality": q, "timestamp": iso(observed),
            "provenance": "VERIFIED_OPCUA" if read_ok else "OBSERVED_LOCAL" if local else "OBSERVED_REMOTE" if reach or tcp is not None else state,
            "privacy": "OPAQUE_IDS", "kind": "OPC_UA_SOURCE" if dev.get("endpoint_url") else "LOCAL_HOST" if dev.get("type") == "local_host" else "NETWORK_DEVICE",
        }

    def tag(self, obs, targets, now):
        endpoint = getattr(obs, "endpoint_url", None)
        valid_target = isinstance(endpoint, str) and not evidence.endpoint_target({"endpoint_url": endpoint})[2]
        device = targets.get(endpoint) if valid_target else None
        session = getattr(obs, "session_state", "UNKNOWN")
        q = quality(obs.quality)
        if q in ("GOOD", "UNCERTAIN") and (not fresh(obs.arrival_time, now, self.ttl) or not fresh(obs.source_time or obs.arrival_time, now, self.ttl)):
            q = "STALE"
        return {
            "tag_id": self.identity("tag", obs.tag_name),
            "device_id": self.identity("device", device) if device else None,
            "value": scalar(obs.value) if q == "GOOD" and device else None,
            "data_type": "boolean" if isinstance(obs.value, bool) else "number" if scalar(obs.value) is not None else "unsupported",
            "engineering_unit": obs.unit if obs.unit in ("", "%", "m", "mm", "cm", "bar", "kPa", "MPa", "°C", "C", "Hz", "A", "V", "kW", "m3/h", "m³/h", "s") else "",
            "quality": q, "source_timestamp": iso(obs.source_time),
            "arrival_timestamp": iso(obs.arrival_time),
            "session_state": session if isinstance(session, str) and session in ("CONNECTED", "CLOSED", "DISCONNECTED", "ERROR", "UNKNOWN") else "UNKNOWN",
            "provenance": "VERIFIED_OPCUA" if device else "UNBOUND_LOCAL_RUNTIME",
            "stale_after": self.ttl,
        }
