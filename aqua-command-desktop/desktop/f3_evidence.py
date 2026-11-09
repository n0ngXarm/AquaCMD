"""F3-only provenance and freshness rules; no GTK, sockets or runtime writes."""
import ipaddress
import math
import time
from urllib.parse import urlsplit


class Provenance:
    CONFIGURED = "CONFIGURED"
    LOCAL = "OBSERVED_LOCAL"
    REMOTE = "OBSERVED_REMOTE"
    OPCUA = "VERIFIED_OPCUA"
    DEMO = "SYNTHETIC_DEMO"
    UNKNOWN = "UNKNOWN"
    STALE = "STALE"


EVIDENCE_TTL = {"local": 60.0, "reachability": 60.0, "tcp": 60.0,
                "session": 15.0, "read": 15.0, "identity": 300.0}
OPCUA_KINDS = ("session", "read", "certificate")
RUNTIME_DEFAULTS = {
    "observed_ip": None, "reachability": "NOT_TESTED", "link_status": "UNKNOWN",
    "wan_link_status": "UNKNOWN", "ping_ok": None, "ping_rtt": None,
    "tcp_ok": None, "tcp_status": "NOT_TESTED", "tcp_rtt": None,
    "opcua_state": "NOT_TESTED", "opcua_security_status": "NOT_TESTED",
    "certificate_trust": "NOT_TESTED", "session_state": "NOT_TESTED",
    "last_read_value": None, "last_read_quality": None, "last_read_time": None,
    "last_verified_time": "—", "last_checked_epoch": None, "last_error": None,
    'network_error': None,
    "last_successful_read": None, "read_success": False, "source_timestamp": None,
    "server_timestamp": None, "last_session_success": None,
    "certificate_reason": None, "certificate_thumbprint": None, "arrival_timestamp": None,
    "node_id": None, "tag_name": None, "quality": None, "value": None, "raw_status": None,
    "session_verified": False, "security_status": "NOT_TESTED", "checked_at": None,
}


def reset_observations(device):
    device.update(RUNTIME_DEFAULTS)
    device["last_read_tag"] = device.get("test_tag", "")
    device.pop("interface_observations", None)
    device.pop("ip_forwarding", None)
    device["evidence"] = {}
    device["provenance"] = Provenance.UNKNOWN
    device["history"] = []


def record_evidence(device, kind, source, *, now=None, detail=""):
    checked = time.time() if now is None else now
    device.setdefault("evidence", {})[kind] = {
        "source": source, "checked_at": checked, "detail": detail,
        "target": device.get("endpoint_url") if kind in OPCUA_KINDS else device.get("configured_ip"),
    }
    device["last_checked_epoch"] = checked
    device["provenance"] = source


def evidence_state(device, kind, *, now=None):
    item = device.get("evidence", {}).get(kind)
    if not item:
        return Provenance.UNKNOWN
    source = item.get("source", Provenance.UNKNOWN)
    allowed = {Provenance.OPCUA} if kind in OPCUA_KINDS else {Provenance.LOCAL, Provenance.REMOTE}
    if device.get("is_demo"):
        allowed.add(Provenance.DEMO)
    if source not in allowed:
        return Provenance.UNKNOWN
    if source == Provenance.DEMO and not device.get("is_demo"):
        return Provenance.UNKNOWN
    checked = item.get("checked_at")
    if not isinstance(checked, (int, float)):
        return Provenance.UNKNOWN
    age = (time.time() if now is None else now) - checked
    if age < -1 or age > EVIDENCE_TTL.get(kind, 60.0):
        return Provenance.STALE
    expected = device.get("endpoint_url") if kind in OPCUA_KINDS else device.get("configured_ip")
    if item.get("target") != expected:
        return Provenance.STALE
    return source


def fresh(device, kind, *, now=None):
    return evidence_state(device, kind, now=now) not in (Provenance.UNKNOWN, Provenance.STALE)


def reachable(device, *, now=None):
    kind = "local" if device.get("type") == "local_host" else "reachability"
    return fresh(device, kind, now=now) and device.get("reachability") in ("REACHABLE", "VERIFIED_LOCAL")


def session_connected(device, *, now=None):
    return fresh(device, "session", now=now) and device.get("session_state") == "CONNECTED"


def session_label(device):
    if not capabilities(device)['opcua']:
        return 'NOT_APPLICABLE'
    state = evidence_state(device, 'session')
    return state if state in (Provenance.UNKNOWN, Provenance.STALE) else device.get('session_state', 'UNKNOWN')


def numeric_target(device):
    try:
        return str(ipaddress.ip_interface(str(device.get('configured_ip') or '').strip()).ip)
    except ValueError:
        return None


def capabilities(device):
    """One policy for presentation and backend entry points; no implicit ports."""
    kind = device.get('type', 'unknown')
    explicit = device.get('capabilities', [])
    explicit = explicit if isinstance(explicit, list) else []
    opcua = kind == 'wincc' or 'opcua' in explicit
    return {'local': kind == 'local_host', 'opcua': opcua,
            'network': kind != 'local_host' and numeric_target(device) is not None
                and (kind != 'service' or device.get('port') is not None)}


def local_snapshot_state(snapshot, *, now=None):
    checked = snapshot.get('observed_at')
    if not isinstance(checked, (int, float)) or not snapshot.get('interfaces') or snapshot.get('state') == 'UNKNOWN':
        return Provenance.UNKNOWN
    age = (time.time() if now is None else now) - checked
    return Provenance.STALE if age < -1 or age > EVIDENCE_TTL['local'] else Provenance.LOCAL


def runtime_summary(snapshot, *, now=None):
    """Project existing local telemetry and mapped DataValue receipts, never poll counters."""
    now = time.time() if now is None else now

    def age_state(checked):
        if not isinstance(checked, (int, float)) or not math.isfinite(checked):
            return Provenance.UNKNOWN
        return Provenance.LOCAL if -1 <= now-checked <= 15 else Provenance.STALE

    polling_evidence = age_state(snapshot.get('polling_checked_at'))
    polling = snapshot.get('polling', {}).get('state', 'UNKNOWN') if polling_evidence == Provenance.LOCAL else polling_evidence
    receipts, seen = [], set()
    qualified = [row for row in snapshot.get('client_receipts', [])
        if row.get('mapping_verified') is True and row.get('node_id') and row.get('quality')
        and row.get('session_state') in ('CONNECTED', 'CLOSED') and not endpoint_target(row)[2]]
    for row in qualified:
        key = (row['endpoint_url'], row.get('tag_name'), row['node_id'], row.get('arrival_epoch'))
        if key not in seen and age_state(row.get('arrival_epoch')) == Provenance.LOCAL:
            seen.add(key)
            receipts.append(row)
    endpoint = snapshot.get('client_endpoint')
    connected = polling in ('RUNNING', 'PAUSED') and any(
        row['endpoint_url'] == endpoint and row['session_state'] == 'CONNECTED' for row in receipts)
    older = any(row['endpoint_url'] == endpoint and age_state(row.get('arrival_epoch')) == Provenance.STALE for row in qualified)
    client = 'CONNECTED_RECENT_READ' if connected else 'STALE' if older and polling in ('RUNNING', 'PAUSED', 'STALE') else 'UNKNOWN'
    return {'db_state': age_state(snapshot.get('checked_at')) if snapshot.get('available') else 'UNKNOWN',
            'polling_state': polling, 'client_state': client, 'client_connected': connected,
            'stale_receipts': [row for row in qualified if age_state(row.get('arrival_epoch')) == Provenance.STALE],
            'receipts': sorted(receipts, key=lambda row: row['arrival_epoch'], reverse=True)}


def read_verified(device, *, now=None):
    return fresh(device, "read", now=now) and bool(device.get("read_success"))


def endpoint_target(device):
    """Return only an explicitly configured, consistent OPC UA target."""
    if device.get("config_errors"):
        return None, None, "CONFIGURATION MISMATCH: " + "; ".join(device["config_errors"])
    endpoint = str(device.get("endpoint_url") or "").strip()
    if not endpoint:
        return None, None, "Endpoint not configured"
    try:
        parsed = urlsplit(endpoint)
        port = parsed.port
        if parsed.scheme != "opc.tcp" or not parsed.hostname or port is None:
            return None, None, "An opc.tcp endpoint with an explicit port is required"
        if parsed.username or parsed.password or not 1 <= port <= 65535:
            return None, None, "Invalid OPC UA endpoint"
        configured_port = device.get("port")
        if configured_port not in (None, "") and int(configured_port) != port:
            return None, None, "CONFIGURATION MISMATCH: endpoint and configured port differ"
        return parsed.hostname, port, None
    except (ValueError, TypeError):
        return None, None, "Invalid endpoint or port"


def network_binding(device, local_state, networks):
    """Audit explicit assignments. Adapter names/subnets never assign roles."""
    zone = device.get("network_zone")
    definition = networks.get(zone, {})
    if not isinstance(definition, dict):
        return "CONFIGURATION MISMATCH", "Network definition must be an object"
    interface = device.get("interface_name") or definition.get("interface")
    snapshot_status = local_snapshot_state(local_state)
    if (interface or device.get('type') == 'local_host' and device.get('configured_ip')) and snapshot_status != Provenance.LOCAL:
        return 'UNVERIFIED', f'Local interface observation is {snapshot_status}; refresh this host before auditing roles'
    # A local configured address must match this host, independently of its assigned role.
    if device.get('type') == 'local_host' and device.get('configured_ip'):
        target = numeric_target(device)
        if target is None:
            return 'CONFIGURATION MISMATCH', 'Configured local IP must be one numeric address'
        candidates = local_state.get('interfaces', {})
        if interface:
            candidates = {interface: candidates.get(interface, {})}
        addresses = []
        for item in candidates.values():
            for address in item.get('ipv4_addresses') or [item.get('ipv4')]:
                try:
                    addresses.append(str(ipaddress.ip_interface(address).ip))
                except (ValueError, TypeError):
                    continue
        if not addresses:
            return 'UNVERIFIED', 'No local address observation is available for comparison'
        if target not in addresses:
            return 'CONFIGURATION MISMATCH', 'Configured local IP differs from observed local addresses'
    if not interface:
        return "UNVERIFIED", "No network interface role explicitly assigned"
    observed = local_state.get("interfaces", {}).get(interface)
    if observed is None:
        return "CONFIGURATION MISMATCH", f"Assigned interface {interface} is not observed locally"
    address = observed.get("ipv4")
    if not address:
        return "UNVERIFIED", f"No IPv4 address observed on {interface}"
    try:
        actual = ipaddress.ip_interface(address)
        target = str(device.get("configured_ip") or "").split("/")[0]
        if target and device.get("type") == "router":
            try:
                if ipaddress.ip_address(target) not in actual.network:
                    return "CONFIGURATION MISMATCH", f"Configured router is outside {interface} subnet {actual.network}"
            except ValueError:
                return "UNVERIFIED", "Configured router name has no authorized address observation"
        configured_subnet = definition.get("subnet")
        if configured_subnet and actual.ip not in ipaddress.ip_network(configured_subnet, strict=False):
            return "CONFIGURATION MISMATCH", f"Observed {interface} address differs from configured {zone} subnet"
        for other_zone, other in networks.items():
            if other_zone == zone:
                continue
            if not isinstance(other, dict):
                return "CONFIGURATION MISMATCH", f"Invalid definition for {other_zone}"
            if other.get("interface") == interface:
                return "CONFIGURATION MISMATCH", f"{interface} assigned to both {zone} and {other_zone}"
            subnet = other.get("subnet")
            if subnet and actual.network.overlaps(ipaddress.ip_network(subnet, strict=False)):
                return "CONFIGURATION MISMATCH", f"Observed {zone} subnet overlaps configured {other_zone}"
        return "CONFIGURED", f"{interface}: {address}; configured role only, remote physical link unverified"
    except ValueError:
        return "CONFIGURATION MISMATCH", "Invalid observed address or configured subnet"


def presentation_state(device, kind, value):
    source = evidence_state(device, kind)
    if source in (Provenance.UNKNOWN, Provenance.STALE):
        return source
    return str(value or "UNKNOWN")


def identity_label(device):
    """Only observed identities or explicit aliases may replace the IP fallback."""
    if device.get("is_demo"):
        return f"{device.get('demo_hostname') or device.get('hostname') or 'Demo source'} [DEMO]"
    source = evidence_state(device, "identity")
    if device.get("hostname") and source in (Provenance.LOCAL, Provenance.REMOTE):
        if device.get("identity_status") == "VERIFIED":
            return str(device["hostname"])
    alias = str(device.get("alias") or "").strip()
    if alias:
        return f"{alias} [User-defined]"
    address = device.get("configured_ip") or device.get("observed_ip")
    return f"{address} [Hostname Unknown]" if address else "Unidentified Device"
