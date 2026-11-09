#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Native F3 configuration, evidence and manual read-only diagnostics.

The logical flow reads F3-local receipts and passive runtime snapshots. Remote
checks require manual authorization; opening/drawing never starts a remote probe.
Local carrier, TCP, certificate validation, session and DataValue receipts remain
separate. DEMO has a separate inventory and cannot persist into LIVE config.
"""

import os
import sys
import math
import time
import json
import copy
import socket
import platform
import threading
import subprocess
from pathlib import Path
from datetime import datetime
from typing import Dict, Any, List, Optional, Callable, Tuple

import gi
gi.require_version('Gtk', '4.0')
gi.require_version('Pango', '1.0')
gi.require_version('PangoCairo', '1.0')
from gi.repository import Gtk, Gdk, GLib, Pango, PangoCairo
import cairo

try:
    from .opcua_reader import ManualOpcUaReader
    from .opcua_pki import PkiManager
    from .opcua_mapping import NodeIdMapper
    from .opcua_store import ObservableStateStore, Quality, TagObservation
except ImportError:
    try:
        from opcua_reader import ManualOpcUaReader
        from opcua_pki import PkiManager
        from opcua_mapping import NodeIdMapper
        from opcua_store import ObservableStateStore, Quality, TagObservation
    except ImportError:
        ManualOpcUaReader = None
        PkiManager = None

try:
    from . import f3_evidence as evidence
    from .f3_opcua import SecureF3OpcUa
    from .f3_runtime import RuntimeEvidence, read_snapshot
    from .f3_drawing import draw_flow
    from .f3_layout import flow_layout, page_inventory
except ImportError:
    import f3_evidence as evidence
    from f3_opcua import SecureF3OpcUa
    from f3_runtime import RuntimeEvidence, read_snapshot
    from f3_drawing import draw_flow
    from f3_layout import flow_layout, page_inventory

IS_WINDOWS = (platform.system() == 'Windows')


# =============================================================================
# Custom CSS for Industrial Graphite Live Network Diagram
# =============================================================================

F3_LIVE_CSS = """
/* Industrial Graphite Layout Tokens */
.f3-root-box {
    background-color: #0d1117;
}
.f3-top-bar {
    background-color: #161b22;
    border-bottom: 1px solid #30363d;
    padding: 8px 14px;
}
.f3-title-text {
    font-size: 13pt;
    font-weight: 800;
    color: #f0f6fc;
}
.f3-subtitle-text {
    font-size: 10pt;
    color: #8b949e;
}

/* Status Badges */
.f3-stat-pill {
    font-size: 10pt;
    font-weight: 700;
    padding: 2px 8px;
    border-radius: 12px;
}
.f3-pill-neutral {
    background-color: #21262d;
    color: #8b949e;
    border: 1px solid #30363d;
}
.f3-pill-green {
    background-color: rgba(63, 185, 80, 0.18);
    color: #3fb950;
    border: 1px solid #238636;
}
.f3-pill-amber {
    background-color: rgba(210, 153, 34, 0.18);
    color: #d29922;
    border: 1px solid #9e6a03;
}
.f3-pill-red {
    background-color: rgba(248, 81, 73, 0.18);
    color: #f85149;
    border: 1px solid #da3633;
}
.f3-pill-purple {
    background-color: rgba(163, 113, 247, 0.18);
    color: #a371f7;
    border: 1px solid #8957e5;
}
.f3-pill-cyan {
    background-color: rgba(56, 189, 248, 0.18);
    color: #38bdf8;
    border: 1px solid #0284c7;
}

/* Mode Switcher Button */
.f3-root-box .btn-mode-demo, .f3-inspector-pane .btn-mode-demo, .f3-settings .btn-mode-demo {
    background-color: #2b2209;
    color: #e3b341;
    font-weight: 800;
    font-size: 10pt;
    padding: 4px 10px;
    border-radius: 12px;
    border: 1px solid #d29922;
}
.f3-root-box .btn-mode-live, .f3-inspector-pane .btn-mode-live, .f3-settings .btn-mode-live {
    background-color: #0c2d6b;
    color: #58a6ff;
    font-weight: 800;
    font-size: 10pt;
    padding: 4px 10px;
    border-radius: 12px;
    border: 1px solid #1f6feb;
}

/* Inspector Side Pane */
.f3-inspector-pane {
    background-color: #161b22;
    border-left: 1px solid #30363d;
    min-width: 340px;
    padding: 12px;
}
.f3-inspector-header {
    border-bottom: 1px solid #30363d;
    padding-bottom: 8px;
    margin-bottom: 8px;
}
.f3-inspector-title {
    font-size: 12pt;
    font-weight: 800;
    color: #f0f6fc;
}
.f3-inspector-section {
    font-size: 8.5pt;
    font-weight: 700;
    color: #58a6ff;
    margin-top: 8px;
    margin-bottom: 4px;
}
.f3-prop-key {
    font-size: 10pt;
    color: #8b949e;
}
.f3-prop-val {
    font-size: 10pt;
    font-family: monospace;
    font-weight: 600;
    color: #e6edf3;
}

/* Device Card */
.f3-card {
    background-color: #161b22;
    border: 1px solid #30363d;
    border-radius: 6px;
    padding: 10px;
    margin: 4px;
}
.f3-card:hover {
    border-color: #58a6ff;
    background-color: #1c2128;
}
.f3-card-selected {
    border: 1.5px solid #58a6ff;
    background-color: #1c2128;
}
.f3-view-tabs button { padding: 5px 14px; font-size: 10pt; font-weight: 600; }
.f3-guide { padding: 5px 12px; font-size: 9pt; color: #acbbc9; }
.f3-root-box button { font-size: 10pt; padding: 5px 9px; }
.f3-readable-status { font-size: 9pt; color: #becfdd; }
.f3-root-box button:focus-visible, .f3-inspector-pane button:focus-visible {
    outline: 2px solid #38bdf8; outline-offset: 2px;
}
.f3-card .f3-title-text { font-size: 11pt; font-weight: 700; }
.f3-card .f3-stat-pill { font-size: 8pt; padding: 1px 5px; border-radius: 4px; }
.f3-card { padding: 8px; margin: 0; }
"""

_live_css_loaded = False

def ensure_f3_live_css():
    global _live_css_loaded
    if _live_css_loaded:
        return
    try:
        provider = Gtk.CssProvider()
        provider.load_from_data(F3_LIVE_CSS.encode('utf-8'))
        display = Gdk.Display.get_default()
        if display:
            Gtk.StyleContext.add_provider_for_display(
                display, provider, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION
            )
        _live_css_loaded = True
    except Exception as e:
        print(f"[F3] Warning loading live CSS: {e}", file=sys.stderr)


# =============================================================================
# 1. State Models, Enums & Device Identity
# =============================================================================

class IdentityStatus:
    VERIFIED = "VERIFIED"
    UNVERIFIED = "UNVERIFIED"
    UNKNOWN = "UNKNOWN"
    USER_DEFINED = "USER_DEFINED"


class IdentitySource:
    LOCAL_OS = "Local OS (socket.gethostname)"
    ASSET_INVENTORY = "Asset Inventory (Verified)"
    DNS_PTR = "DNS/PTR Reverse Lookup (Unverified)"
    USER_CONFIGURED = "User Configured Alias"
    CLOUD_ENDPOINT = "Cloud Endpoint Verification"
    UNVERIFIED = "None (Unverified)"


LEGACY_ID_MAP = {
    "PC1": "dev-scada-01",
    "PC2": "dev-scada-02",
    "PC3": "dev-scada-03",
    "SWITCH": "dev-switch-01",
    "PC4": "dev-collector-01",
    "ROUTER": "dev-router-01",
    "TELEGRAM": "dev-service-tg",
}
REVERSE_LEGACY_MAP = {v: k for k, v in LEGACY_ID_MAP.items()}


def get_local_hostname() -> str:
    """
    Detect factual local hostname from host operating system APIs.
    Priority:
      1. socket.gethostname()
      2. platform.node()
      3. /etc/hostname file read (Linux)
    Strictly avoids username (e.g. nong_ing) and synthetic hardcoded names (PC4).
    """
    candidates = []
    try:
        h = socket.gethostname().strip()
        if h and h != "localhost" and not h.startswith("localhost."):
            candidates.append(h)
    except Exception:
        pass
    try:
        p = platform.node().strip()
        if p and p != "localhost" and not p.startswith("localhost."):
            candidates.append(p)
    except Exception:
        pass
    if not IS_WINDOWS:
        try:
            etc_host = Path("/etc/hostname")
            if etc_host.exists():
                eh = etc_host.read_text(encoding="utf-8").strip()
                if eh:
                    candidates.append(eh)
        except Exception:
            pass

    username = ""
    try:
        import getpass
        username = getpass.getuser().strip()
    except Exception:
        pass

    for cand in candidates:
        if cand and cand != username:
            return cand
    return candidates[0] if candidates else ""


def compute_display_name(dev: Dict[str, Any], is_demo: bool = False) -> Tuple[str, str]:
    """
    Factual display name priority rules:
      Rule 1: Verified Hostname -> Use hostname as primary name.
      Rule 2: No Verified Hostname, but has user Alias -> Use alias with '[User-defined]'.
      Rule 3: Neither, but has IP Address -> Use IP with '[Hostname Unknown]'.
      Rule 4: Neither and no IP -> 'Unidentified Device'.
    In DEMO mode, hostnames are marked '[DEMO]'.
    Returns: (display_name, identity_badge_text)
    """
    if is_demo or dev.get("is_demo"):
        demo_name = dev.get("hostname") or dev.get("demo_hostname") or dev.get("name") or "DEMO-DEVICE"
        demo_clean = str(demo_name).replace(" [DEMO]", "").strip()
        return f"{demo_clean} [DEMO]", "DEMO"

    hostname = dev.get("hostname")
    identity_status = dev.get("identity_status", IdentityStatus.UNKNOWN)
    alias = (dev.get("alias") or "").strip()
    ip = (dev.get("configured_ip") or dev.get("observed_ip") or "").strip()

    # Rule 1: Verified Hostname
    if hostname and identity_status == IdentityStatus.VERIFIED:
        return str(hostname), IdentityStatus.VERIFIED

    # Rule 2: User Alias
    if alias:
        return f"{alias} [User-defined]", IdentityStatus.USER_DEFINED

    # Unverified hostname (e.g. from DNS/PTR reverse lookup)
    if hostname and identity_status == IdentityStatus.UNVERIFIED:
        return f"{hostname} [Unverified]", IdentityStatus.UNVERIFIED

    # Rule 3: IP Address with [Hostname Unknown]
    if ip:
        display_ip = ip.split()[0] if "/" in ip else ip
        return f"{display_ip} [Hostname Unknown]", IdentityStatus.UNKNOWN

    # Rule 4: Unidentified Device
    return "Unidentified Device", IdentityStatus.UNKNOWN


def device_status_text(dev):
    """Describe observed connectivity without promoting unknown data to offline."""
    if dev.get("config_errors") or dev.get('binding_status') == 'CONFIGURATION MISMATCH':
        return "CONFIGURATION MISMATCH · แก้ไขการตั้งค่า"
    if not dev.get("enabled", True):
        return "ปิดการตรวจสอบ"
    if evidence.read_verified(dev):
        return f"ได้รับค่าทดสอบ [{dev.get('last_read_quality', 'UNKNOWN')}] · session ปิดแล้ว"
    if evidence.session_connected(dev):
        return "เชื่อมต่อ OPC UA แล้ว"
    kind = "local" if dev.get("type") == "local_host" else "reachability"
    source = evidence.evidence_state(dev, kind)
    if source == evidence.Provenance.STALE:
        return "ผลตรวจหมดอายุ (STALE)"
    if dev.get("reachability") == "CHECKING" or dev.get("opcua_state") == "CHECKING":
        return "กำลังตรวจสอบ…"
    if source == evidence.Provenance.UNKNOWN:
        return "ยังไม่ได้ตรวจสอบ (UNKNOWN)"
    return {
        "NOT_TESTED": "ยังไม่ได้ตรวจสอบ", "UNKNOWN": "ยังไม่ทราบสถานะ",
        "REACHABLE": "ตรวจพบการตอบกลับ", "VERIFIED_LOCAL": "เครื่องที่กำลังใช้งาน",
        "CHECKING": "กำลังตรวจสอบ…", "UNREACHABLE": "ติดต่อไม่ได้",
        "NO_ICMP_REPLY": "ไม่ตอบ Ping", "STALE": "ผลตรวจหมดอายุ",
    }.get(dev.get("reachability"), "ยังไม่ทราบสถานะ")


class DeviceDictionary(dict):
    """
    Transparent dictionary resolving both stable device_id and legacy aliases:
      d["dev-scada-01"] and d["PC1"] both resolve to the same device object!
    """
    def __getitem__(self, key):
        if super().__contains__(key):
            return super().__getitem__(key)
        mapped = LEGACY_ID_MAP.get(key)
        if mapped and super().__contains__(mapped):
            return super().__getitem__(mapped)
        rev = REVERSE_LEGACY_MAP.get(key)
        if rev and super().__contains__(rev):
            return super().__getitem__(rev)
        raise KeyError(key)

    def get(self, key, default=None):
        try:
            return self[key]
        except KeyError:
            return default

    def __contains__(self, key):
        if super().__contains__(key):
            return True
        mapped = LEGACY_ID_MAP.get(key)
        if mapped and super().__contains__(mapped):
            return True
        rev = REVERSE_LEGACY_MAP.get(key)
        if rev and super().__contains__(rev):
            return True
        return False

class OpcUaState:
    NOT_CONFIGURED = "NOT_CONFIGURED"
    NOT_TESTED = "NOT_TESTED"
    CHECKING = "CHECKING"
    TCP_REACHABLE = "TCP_REACHABLE"
    TCP_UNREACHABLE = "TCP_UNREACHABLE"
    CERTIFICATE_UNTRUSTED = "CERTIFICATE_UNTRUSTED"
    AUTH_FAILED = "AUTH_FAILED"
    CONNECTED = "CONNECTED"
    READ_VERIFIED = "READ_VERIFIED"
    DISCONNECTED = "DISCONNECTED"
    ERROR = "ERROR"
    STALE = "STALE"


class ConnectionState:
    UNKNOWN = "UNKNOWN"
    LINK_VERIFIED = "LINK_VERIFIED"
    REACHABILITY_VERIFIED = "REACHABILITY_VERIFIED"
    OPCUA_CONNECTED = "OPCUA_CONNECTED"
    OPCUA_ERROR = "OPCUA_ERROR"
    CHECKING = "CHECKING"
    STALE = "STALE"
    SERVICE_UNAVAILABLE = "SERVICE_UNAVAILABLE"
    NIC_OT_DOWN = "NIC_OT_DOWN"


class VerificationState:
    CONFIGURED = "CONFIGURED"
    VERIFIED_LOCAL = "VERIFIED_LOCAL"
    VERIFIED_REMOTE = "VERIFIED_REMOTE"
    ONLINE = "ONLINE"
    OFFLINE = "OFFLINE"
    UNKNOWN = "UNKNOWN"
    STALE = "STALE"
    NIC_OT_DOWN = "NIC OT DOWN"
    UNREACHABLE = "UNREACHABLE"
    CHECKING = "CHECKING..."


# A fresh LIVE profile observes only this host. Remote inventory requires explicit configuration.
DEFAULT_F3_DEVICES = [{
    "device_id": "dev-collector-01", "id": "dev-collector-01", "type": "local_host",
    "hostname": None, "alias": "", "identity_status": IdentityStatus.UNKNOWN,
    "identity_source": IdentitySource.UNVERIFIED, "device_role": "AQUA COMMAND Collector",
    "network_zone": "UNASSIGNED", "configured_ip": "", "port": None,
    "endpoint_url": "", "enabled": True,
}]


# =============================================================================
# 2. Local OS Discovery (Strictly Read-Only, Zero Network Packets)
# =============================================================================

def safe_get_local_network_state() -> Dict[str, Any]:
    """
    Reads local Host OS network configuration strictly using passive, read-only APIs.
    Guarantees ZERO network packets emitted (no ping, no ARP sweep, no socket connection).
    """
    if platform.system() == 'Linux':
        try:
            from .f3_local import read_linux_snapshot
        except ImportError:
            from f3_local import read_linux_snapshot
        return read_linux_snapshot()
    state = {
        'observed_at': time.time(),
        "timestamp": datetime.now().strftime("%d/%m/%Y %H:%M:%S"),
        "interfaces": {},
        "default_gateway": None,
        "default_gw_iface": None,
        "ip_forwarding": None,
        "hostname": socket.gethostname(),
        "os_name": f"{platform.system()} {platform.release()}"
    }

    # 1. Check IP Forwarding (Verify Air-Gap / Non-Routing isolation)
    if not IS_WINDOWS:
        ip_fwd_path = Path("/proc/sys/net/ipv4/ip_forward")
        if ip_fwd_path.exists():
            try:
                state["ip_forwarding"] = (ip_fwd_path.read_text().strip() == "1")
            except Exception:
                pass

    # 2. Local Interfaces Status via sysfs (Linux) or netsh (Windows)
    if not IS_WINDOWS:
        net_dir = Path("/sys/class/net")
        if net_dir.exists():
            for iface_path in net_dir.iterdir():
                iface = iface_path.name
                if iface == "lo":
                    continue
                carrier = None
                carrier_file = iface_path / "carrier"
                if carrier_file.exists():
                    try:
                        carrier = (carrier_file.read_text().strip() == "1")
                    except Exception:
                        pass

                operstate = "unknown"
                oper_file = iface_path / "operstate"
                if oper_file.exists():
                    try:
                        operstate = oper_file.read_text().strip()
                    except Exception:
                        pass

                mac = None
                addr_file = iface_path / "address"
                if addr_file.exists():
                    try:
                        mac = addr_file.read_text().strip()
                    except Exception:
                        pass

                state["interfaces"][iface] = {
                    "carrier": carrier,
                    "operstate": operstate,
                    "mac": mac,
                    "ipv4": None
                }

        # Read assigned IPv4 without emitting network traffic
        try:
            res = subprocess.run(
                ["ip", "-j", "addr", "show"],
                stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, timeout=1.5
            )
            if res.returncode == 0:
                data = json.loads(res.stdout)
                for item in data:
                    ifname = item.get("ifname")
                    if ifname in state["interfaces"]:
                        for addr_info in item.get("addr_info", []):
                            if addr_info.get("family") == "inet":
                                loc = addr_info.get("local")
                                plen = addr_info.get("prefixlen")
                                state["interfaces"][ifname]["ipv4"] = f"{loc}/{plen}"
                                break
        except Exception:
            pass

        # Read Default Gateway from /proc/net/route (kernel routing table, zero I/O)
        route_file = Path("/proc/net/route")
        if route_file.exists():
            try:
                with open(route_file, "r") as f:
                    for line in f:
                        parts = line.strip().split()
                        if len(parts) >= 3 and parts[1] == "00000000":
                            gw_hex = parts[2]
                            iface = parts[0]
                            gw_bytes = bytes.fromhex(gw_hex)
                            gw_ip = ".".join(str(b) for b in reversed(gw_bytes))
                            state["default_gateway"] = gw_ip
                            state["default_gw_iface"] = iface
                            break
            except Exception:
                pass

    else:
        # Windows passive netsh queries
        try:
            kwargs = {}
            if hasattr(subprocess, 'CREATE_NO_WINDOW'):
                kwargs['creationflags'] = subprocess.CREATE_NO_WINDOW
            out = subprocess.check_output(['netsh', 'interface', 'show', 'interface'], timeout=1.5, **kwargs).decode('utf-8', errors='ignore')
            for line in out.splitlines():
                parts = line.split()
                if len(parts) >= 4:
                    name = " ".join(parts[3:])
                    is_connected = (parts[1].lower() == 'connected')
                    state["interfaces"][name] = {
                        "carrier": is_connected,
                        "operstate": "up" if is_connected else "down",
                        "mac": None,
                        "ipv4": None
                    }
        except Exception:
            pass

    return state


# =============================================================================
# 3. Dynamic Device Store & State Manager
# =============================================================================

class F3DeviceStore:
    """
    Observable store managing device configuration and live verification state.
    Provides atomic JSON persistence, Device Identity model, and separate DEMO vs LIVE states.
    """
    def __init__(self, config_file: Optional[Path] = None):
        self.config_file = config_file
        self.devices = DeviceDictionary()
        self.is_demo_mode: bool = False
        self.last_verified_ts: Optional[str] = None
        self.local_observation = {}
        self.runtime_observation = {}
        self._listeners: List[Callable[[], None]] = []
        self.load()

    def add_listener(self, listener: Callable[[], None]):
        if listener not in self._listeners:
            self._listeners.append(listener)

    def notify(self):
        for l in self._listeners:
            try:
                l()
            except Exception as e:
                print(f"[F3Store] Listener error: {e}", file=sys.stderr)

    def load(self):
        """Load inventory only; cached observations never establish LIVE state."""
        self.devices = DeviceDictionary()
        self.networks = {}
        self.last_error = None
        records = []
        if self.config_file and self.config_file.exists():
            try:
                data = json.loads(self.config_file.read_text(encoding='utf-8'))
                if not isinstance(data, dict):
                    raise ValueError("Network configuration must be an object")
                self.networks = data.get("networks", {})
                if not isinstance(self.networks, dict):
                    raise ValueError("Network role assignments must be an object")
                records = data.get("devices", [])
                if not isinstance(records, list):
                    raise ValueError("Devices must be a list")
            except (OSError, ValueError) as error:
                self.last_error = f"Configuration could not be loaded: {error}"
                records = []
        for record in records:
            if not isinstance(record, dict) or record.get("is_demo") or record.get("config_provenance") == evidence.Provenance.DEMO:
                continue
            dev = dict(record)
            dev["configured"] = True
            dev["config_provenance"] = evidence.Provenance.CONFIGURED
            self._init_device_state(dev, reset_runtime=True)
            self.devices[dev["device_id"]] = dev
        if not any(d.get("type") == "local_host" for d in self.devices.values()):
            dev = dict(DEFAULT_F3_DEVICES[0], configured=False)
            self._init_device_state(dev, reset_runtime=True)
            self.devices[dev["device_id"]] = dev

    def _init_device_state(self, dev: Dict[str, Any], reset_runtime=False):
        errors = []
        for field in ("device_id", "id", "type", "configured_ip", "endpoint_url", "alias", "hostname",
                      "configured_hostname", "device_role", "network_zone", "interface_name", "test_tag",
                      "sec_policy", "auth_mode"):
            if dev.get(field) is not None and not isinstance(dev[field], str):
                errors.append(f"{field}: expected text")
                dev[field] = ""
        port = dev.get("port")
        if port not in (None, ""):
            try:
                if isinstance(port, (bool, float)) or not 1 <= int(port) <= 65535:
                    raise ValueError()
                dev["port"] = int(port)
            except (ValueError, TypeError):
                errors.append("port: expected integer 1–65535")
                dev["port"] = None
        if not isinstance(dev.get("enabled", True), bool):
            errors.append("enabled: expected boolean")
        if errors:
            dev["enabled"] = False
        dev["config_errors"] = errors
        legacy_id = dev.get("device_id") or dev.get("id", "")
        dev["device_id"] = LEGACY_ID_MAP.get(legacy_id, legacy_id or f"dev-node-{len(self.devices)+1}")
        dev["id"] = dev["device_id"]
        aliases = {'scada': 'wincc', 'client': 'remote_collector', 'collector': 'remote_collector',
                   'external_service': 'service', 'ethernet_switch': 'switch'}
        kind = str(dev.get('type') or 'unknown').lower().strip()
        dev['type'] = aliases.get(kind, kind) if kind in ('wincc', 'local_host', 'demo_collector',
            'remote_collector', 'switch', 'router', 'service') or kind in aliases else 'unknown'
        caps = dev.get('capabilities', [])
        if not isinstance(caps, list) or any(c not in ('opcua',) for c in caps):
            errors.append('capabilities: only an explicit opcua capability is supported')
            caps = []
            dev['enabled'] = False
        dev['capabilities'] = caps
        dev.setdefault("configured_ip", dev.get("ip", ""))
        dev.setdefault("port", None)
        dev.setdefault("endpoint_url", "")
        dev.setdefault("alias", "")
        dev.setdefault("device_role", dev.get("role", "Configured device"))
        dev.setdefault("network_zone", dev.get("zone", "UNASSIGNED"))
        dev.setdefault("interface_name", "")
        dev.setdefault("enabled", True)
        dev.setdefault("test_tag", "")
        dev.setdefault("last_read_tag", dev.get("test_tag", ""))
        dev.setdefault("configured", True)
        dev.setdefault("config_provenance", evidence.Provenance.CONFIGURED)
        if reset_runtime:
            if dev.get("type") != "local_host":
                dev["configured_hostname"] = dev.get("configured_hostname") or dev.get("hostname")
                dev["hostname"] = None
                dev["identity_status"] = IdentityStatus.UNKNOWN
                dev["identity_source"] = evidence.Provenance.CONFIGURED
                dev["identity_verified_at"] = None
            evidence.reset_observations(dev)
        for key, value in evidence.RUNTIME_DEFAULTS.items():
            dev.setdefault(key, value)
        dev.setdefault("evidence", {})
        dev.setdefault("history", [])
        dev.setdefault("hostname", None)
        dev.setdefault("identity_status", IdentityStatus.UNKNOWN)
        dev.setdefault("identity_source", IdentitySource.UNVERIFIED)
        dev.setdefault("identity_verified_at", None)
        if dev.get("type") == "local_host":
            dev["hostname"] = get_local_hostname() or None
            dev["identity_status"] = IdentityStatus.VERIFIED if dev["hostname"] else IdentityStatus.UNKNOWN
            dev["identity_source"] = IdentitySource.LOCAL_OS
            dev["identity_verified_at"] = datetime.now().isoformat() if dev["hostname"] else None
            evidence.record_evidence(dev, "identity", evidence.Provenance.LOCAL, detail="Host OS hostname")
        dev["role"] = dev["device_role"]
        dev["zone"] = dev["network_zone"]
        dev.setdefault("name", evidence.identity_label(dev))
        if not dev.get("endpoint_url"):
            dev["opcua_state"] = OpcUaState.NOT_CONFIGURED

    def save(self):
        """Persist explicit configuration, never observations, trust or demo state."""
        if not self.config_file or self.is_demo_mode:
            return False
        fields = ("device_id", "id", "alias", "configured_hostname", "configured_ip", "port",
                  "device_role", "network_zone", "type", "endpoint_url", "interface_name",
                  "enabled", "test_tag", "sec_policy", "auth_mode", "name", "capabilities")
        try:
            self.config_file.parent.mkdir(parents=True, exist_ok=True)
            config = {}
            if self.config_file.exists() and self.config_file.read_text().strip():
                config = json.loads(self.config_file.read_text(encoding='utf-8'))
                if not isinstance(config, dict):
                    raise ValueError("Network configuration must be a JSON object")
            config["schema_version"] = 2
            config["networks"] = self.networks
            config["devices"] = [{key: dev[key] for key in fields if key in dev}
                                 for dev in self.devices.values() if dev.get("configured")]
            tmp_path = self.config_file.with_suffix('.tmp')
            tmp_path.write_text(json.dumps(config, indent=2, ensure_ascii=False), encoding='utf-8')
            tmp_path.replace(self.config_file)
            self.last_error = None
            return True
        except (OSError, ValueError) as error:
            self.last_error = f"Configuration not saved: {error}"
            return False

    def add_device(self, dev: Dict[str, Any]):
        self._init_device_state(dev)
        self.devices[dev["device_id"]] = dev
        self.save()
        self.notify()

    def update_device(self, dev_id: str, updates: Dict[str, Any]):
        resolved_id = LEGACY_ID_MAP.get(dev_id, dev_id)
        if resolved_id not in self.devices:
            return
        device = dict(self.devices[resolved_id])
        target_fields = ("configured_ip", "endpoint_url", "port", "enabled", "test_tag", "sec_policy", "auth_mode",
                         "type", "capabilities", "interface_name", "network_zone")
        identity = tuple(device.get(key) for key in target_fields)
        device.update({k: v for k, v in updates.items() if k not in ("device_id", "id")})
        device['configured'] = True
        if "hostname" in updates and device.get("type") != "local_host":
            device["configured_hostname"] = updates["hostname"]
            device["hostname"] = None
            device["identity_status"] = IdentityStatus.UNKNOWN
            device["identity_source"] = evidence.Provenance.CONFIGURED
            device["identity_verified_at"] = None
        changed_target = identity != tuple(device.get(key) for key in target_fields)
        if changed_target:
            evidence.reset_observations(device)
        self._init_device_state(device)
        self.devices[resolved_id] = device
        self.save()
        self.notify()

    def remove_device(self, dev_id: str):
        resolved_id = LEGACY_ID_MAP.get(dev_id, dev_id)
        if resolved_id in self.devices:
            del self.devices[resolved_id]
            self.save()
            self.notify()

    def set_demo(self, enabled):
        """Swap inventories; simulated observations can never enter LIVE storage."""
        if enabled == self.is_demo_mode:
            return
        if enabled:
            self._live_devices = copy.deepcopy(self.devices)
            self._live_networks = copy.deepcopy(self.networks)
            self.devices = DeviceDictionary()
            self.networks = {}
            for index in range(1, 4):
                dev = {"device_id": f"demo-source-{index}", "type": "wincc",
                       "configured_ip": "127.0.0.1", "port": None, "endpoint_url": "",
                       "hostname": f"DEMO-SOURCE-{index}", "demo_hostname": f"DEMO-SOURCE-{index}",
                       "device_role": "Synthetic loopback source", "is_demo": True,
                       "config_provenance": evidence.Provenance.DEMO, "test_tag": "LAB.Level"}
                self._init_device_state(dev)
                self.devices[dev["device_id"]] = dev
            collector = dict(DEFAULT_F3_DEVICES[0], device_id="demo-collector", id="demo-collector",
                             hostname="DEMO-COLLECTOR", demo_hostname="DEMO-COLLECTOR", is_demo=True,
                             type="demo_collector", configured=False, config_provenance=evidence.Provenance.DEMO)
            self._init_device_state(collector)
            self.devices[collector["device_id"]] = collector
        else:
            self.devices = self._live_devices
            self.networks = self._live_networks
            for dev in self.devices.values():
                evidence.reset_observations(dev)
                self._init_device_state(dev)
        self.is_demo_mode = enabled
        self.last_verified_ts = None
        self.notify()

    def get_summary_stats(self) -> Dict[str, Any]:
        configured = [d for d in self.devices.values() if d.get("configured")]
        active = [d for d in configured if d.get("enabled", True)]
        remote = [d for d in active if d.get('type') not in ('local_host', 'demo_collector', 'service')]
        local_state = evidence.local_snapshot_state(self.local_observation)
        local_count = len(self.local_observation.get('interfaces', {})) if local_state == evidence.Provenance.LOCAL and not self.is_demo_mode else None
        runtime = evidence.runtime_summary(self.runtime_observation if not self.is_demo_mode else {})
        return {
            "total_configured": len(configured),
            "detected_count": sum(evidence.reachable(d) for d in remote),
            'observed_local_interfaces': local_count,
            'local_observation_state': local_state if not self.is_demo_mode else 'SYNTHETIC_DEMO',
            'verified_remote_hosts': sum(evidence.reachable(d) for d in remote),
            "opc_connected": sum(evidence.session_connected(d) for d in active) + int(runtime['client_connected']),
            "opc_read_verified": sum(evidence.read_verified(d) for d in active) + len(runtime['receipts']),
            "opc_unreachable": sum(bool(d.get("endpoint_url")) and evidence.fresh(d, "tcp") and d.get("tcp_ok") is False for d in active),
            "opc_unknown": sum(bool(d.get("endpoint_url")) and not evidence.fresh(d, "session") for d in active),
            "is_demo": self.is_demo_mode,
            "last_verified_ts": self.last_verified_ts or "—",
        }


# =============================================================================
# 4. Real Detection & Probing Engine
# =============================================================================

class RealDetectionEngine:
    """

    @staticmethod
    def resolve_hostname_dns_ptr(ip: str) -> Optional[str]:
        try:
            info = socket.gethostbyaddr(ip)
            if info and info[0]:
                h = info[0].strip()
                if h and h != ip and not h.startswith("localhost"):
                    return h
        except Exception:
            pass
        return None

    Executes on-demand, targeted network probes with bounded concurrency, rate limiting,
    and strict truthfulness (Ping Blocked != WinCC Down, TCP Open != OPC UA Connected).
    """

    @staticmethod
    def detect_device_network(device: Dict[str, Any], is_demo: bool, callback: Callable[[Dict[str, Any]], None], *, cancel=None):
        """Runs ICMP Ping and TCP Connect checks in a background thread."""
        cancel = cancel if cancel is not None else threading.Event()
        def worker():
            target_ip = evidence.numeric_target(device)
            port = device.get("port")
            now_ts = datetime.now().strftime("%H:%M:%S")

            result = {
                "id": device["id"],
                "timestamp": now_ts,
                "ping_ok": False,
                "ping_rtt": None,
                "reachability": "UNREACHABLE",
                "tcp_ok": None,
                "tcp_status": "NOT_CONFIGURED" if not port else "NOT_TESTED",
                "tcp_rtt": None,
                "observed_ip": None,
                "error": None
            }
            if device.get('type') == 'service':
                result.update(ping_ok=None, reachability='NOT_TESTED')

            def finish():
                result['cancelled'] = cancel.is_set()
                GLib.idle_add(callback, result)

            if cancel.is_set() or target_ip is None:
                result.update(reachability='NOT_TESTED', ping_ok=None,
                              error='CANCELLED' if cancel.is_set() else 'One configured numeric IP is required')
                finish()
                return

            if is_demo:
                # Synthetic Loopback Probe for DEMO Mode
                cancel.wait(0.15)
                result["ping_ok"] = True
                result["ping_rtt"] = "0.8ms"
                result["reachability"] = "REACHABLE"
                result["tcp_ok"] = True
                result["tcp_status"] = f"OPEN (0.8ms)"
                result["tcp_rtt"] = "0.8ms"
                result["observed_ip"] = target_ip
            else:
                # 1. ICMP Ping Probe (1 packet, 1000ms timeout)
                if device.get('type') != 'service':
                    try:
                        t0 = time.monotonic()
                        cmd = ["ping", "-n", "1", "-w", "1000", target_ip] if IS_WINDOWS else ["ping", "-c", "1", "-W", "1", target_ip]
                        res = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, timeout=1.5)
                        rtt_ms = (time.monotonic() - t0) * 1000.0
                        if res.returncode == 0:
                            result["ping_ok"] = True
                            result["ping_rtt"] = f"{rtt_ms:.1f}ms"
                            result["reachability"] = "REACHABLE"
                            result["observed_ip"] = target_ip
                        else:
                            result["ping_ok"] = False
                            result["ping_rtt"] = "Drop/Blocked"
                            result["reachability"] = "NO_ICMP_REPLY"
                    except Exception as e:
                        result["ping_ok"] = None
                        result["ping_rtt"] = "Error"
                        result["reachability"] = "NOT_TESTED"
                        result["error"] = f'{type(e).__name__}: {e}'

                if cancel.is_set():
                    finish()
                    return
                # 2. TCP Port Connect Probe (1.0s timeout)
                if target_ip and port and target_ip != "None":
                    try:
                        with socket.socket(socket.AF_INET6 if ':' in target_ip else socket.AF_INET, socket.SOCK_STREAM) as s:
                            s.settimeout(1.0)
                            t0 = time.monotonic()
                            err = s.connect_ex((target_ip, int(port)))
                        tcp_ms = (time.monotonic() - t0) * 1000.0
                        if err == 0:
                            result["tcp_ok"] = True
                            result["tcp_status"] = f"OPEN ({tcp_ms:.1f}ms)"
                            result["tcp_rtt"] = f"{tcp_ms:.1f}ms"
                            result['reachability'] = 'REACHABLE'
                            result["observed_ip"] = target_ip
                        elif err in (111, 10061):
                            result["tcp_ok"] = False
                            result["tcp_status"] = "REFUSED (TCP response)"
                            result['reachability'] = 'REACHABLE'
                        else:
                            result["tcp_ok"] = False
                            result["tcp_status"] = "TIMEOUT"
                    except Exception as e:
                        result["tcp_ok"] = None
                        result["tcp_status"] = 'NOT_TESTED (local API error)'
                        result['error'] = f'{type(e).__name__}: {e}'

                # No implicit reverse DNS: it is unbounded and cannot verify device identity.
                result["dns_ptr_hostname"] = None



            finish()

        t = threading.Thread(target=worker, daemon=True)
        t.start()
        return cancel

    @staticmethod
    def detect_opcua_session(device: Dict[str, Any], is_demo: bool, callback: Callable[[Dict[str, Any]], None]):
        """Legacy TCP transport API; never verifies a live OPC UA session.

        F3 actions use SecureF3OpcUa with the existing PKI/reader instead.
        """
        def worker():
            endpoint_url = device.get("endpoint_url", "")
            now_ts = datetime.now().strftime("%H:%M:%S")

            result = {
                "id": device["id"],
                "timestamp": now_ts,
                "opcua_state": OpcUaState.ERROR,
                "session_state": "DISCONNECTED",
                "security_status": "None",
                "last_error": None,
                "read_value": None,
                "read_quality": None
            }

            if is_demo:
                # Synthetic Loopback Handshake in DEMO mode
                time.sleep(0.2)
                result["opcua_state"] = OpcUaState.CONNECTED
                result["session_state"] = "CONNECTED"
                result["security_status"] = "Basic256Sha256 (Demo Trust)"
            else:
                # Live Check: Parse Host and Port
                try:
                    host, port, error = evidence.endpoint_target(device)
                    if error:
                        raise ValueError(error)

                    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                    s.settimeout(1.0)
                    err = s.connect_ex((host, port))
                    s.close()

                    if device.get("simulate_untrusted_cert"):
                        result["opcua_state"] = OpcUaState.CERTIFICATE_UNTRUSTED
                        result["session_state"] = "CERT_UNTRUSTED"
                        result["security_status"] = "BadSecurityChecksFailed: Server Certificate Untrusted"
                        result["last_error"] = "Untrusted Server Certificate (PKI rejected)"
                    elif err != 0:
                        result["opcua_state"] = OpcUaState.TCP_UNREACHABLE
                        result["session_state"] = "DISCONNECTED"
                        result["last_error"] = f"Port {port} unreachable / closed"
                    else:
                        # Strict Separation: TCP Open != OPC UA Connected!
                        result["opcua_state"] = OpcUaState.TCP_REACHABLE
                        result["session_state"] = "TCP_OPEN_NO_SESSION"
                        result["security_status"] = "TCP Reachable (OPC UA Handshake Pending)"
                except Exception as ex:
                    result["opcua_state"] = OpcUaState.ERROR
                    result["session_state"] = "DISCONNECTED"
                    result["last_error"] = str(ex)



            GLib.idle_add(callback, result)

        t = threading.Thread(target=worker, daemon=True)
        t.start()

    @staticmethod
    def read_opcua_single_tag(device: Dict[str, Any], is_demo: bool, callback: Callable[[Dict[str, Any]], None]):
        """Legacy synthetic test API; live reads use SecureF3OpcUa instead."""
        def worker():
            tag_name = device.get("test_tag", "")
            now_ts = datetime.now().strftime("%H:%M:%S")

            result = {
                "id": device["id"],
                "tag_name": tag_name,
                "timestamp": now_ts,
                "value": None,
                "quality": "Bad",
                "error": None
            }

            if is_demo:
                time.sleep(0.1)
                import random
                val = round(80.0 + random.uniform(0.5, 4.5), 2)
                result["value"] = val
                result["quality"] = "Good (Demo Live)"
            else:
                # Live read attempt if reader module available
                result["value"] = "Not Observed (No Live WinCC)"
                result["quality"] = "Uncertain"
                result["error"] = "Requires active WinCC server with granted read permission"



            GLib.idle_add(callback, result)

        t = threading.Thread(target=worker, daemon=True)
        t.start()


# =============================================================================
# 5. OT Safety Authorization Dialog Gate
# =============================================================================

class OTAuthorizationDialog(Gtk.Window):
    """
    Security gate modal requiring explicit operator confirmation before sending
    any network probe into the OT/SCADA subnet.
    """
    def __init__(self, parent_win, device_name: str, device_ip: str, on_authorized: Callable[[], None]):
        super().__init__()
        if isinstance(parent_win, Gtk.Window):
            self.set_transient_for(parent_win)
        self.set_modal(True)
        self.set_title("⚠️ ยืนยันการตรวจสอบอุปกรณ์ผ่านเครือข่าย OT")
        self.set_default_size(520, 260)
        self.set_resizable(False)
        self.add_css_class('f3-settings')
        self.on_authorized = on_authorized

        root = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=14)
        root.set_margin_start(20)
        root.set_margin_end(20)
        root.set_margin_top(18)
        root.set_margin_bottom(18)
        self.set_child(root)

        header_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=12)
        root.append(header_box)

        icon_lbl = Gtk.Label(label="🛡️")
        icon_lbl.add_css_class('f3-stat-pill')
        header_box.append(icon_lbl)

        title_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
        header_box.append(title_box)

        t_lbl = Gtk.Label(label="การอนุญาตตรวจสอบเครือข่ายอุตสาหกรรม (OT Active Probe)")
        t_lbl.add_css_class('f3-title-text')
        t_lbl.set_xalign(0.0)
        title_box.append(t_lbl)

        target_lbl = Gtk.Label(label=f"เป้าหมาย: {device_name} — IP: {device_ip}")
        target_lbl.add_css_class('f3-prop-val')
        target_lbl.set_xalign(0.0)
        title_box.append(target_lbl)

        msg_lbl = Gtk.Label(label=(
            "คำเตือนความปลอดภัย OT:\n"
            "• การส่ง packet ตรวจสอบ (ICMP/TCP) จะถูกส่งเฉพาะ IP ปลายทางนี้เท่านั้น (Single Target)\n"
            "• ห้ามบรอดแคสต์ และไม่มีการทำ ARP/Subnet Sweep ใด ๆ ทั้งสิ้น (Timeout 1.0s)\n"
            "• มั่นใจว่าจะไม่รบกวนการทำงานของ PLC หรือ Controller ที่อ่อนไหว"
        ))
        msg_lbl.set_xalign(0.0)
        msg_lbl.set_wrap(True)
        msg_lbl.add_css_class('f3-subtitle-text')
        root.append(msg_lbl)

        btn_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=12)
        btn_box.set_halign(Gtk.Align.END)
        root.append(btn_box)

        cancel_btn = Gtk.Button(label="ยกเลิก (Cancel)")
        cancel_btn.connect('clicked', lambda _: self.close())
        btn_box.append(cancel_btn)

        confirm_btn = Gtk.Button(label="⚡ ยืนยันการตรวจสอบ (Authorize Probe)")
        confirm_btn.add_css_class('btn-mode-live')
        confirm_btn.connect('clicked', self._on_confirm)
        btn_box.append(confirm_btn)

    def _on_confirm(self, _):
        self.close()
        if self.on_authorized:
            self.on_authorized()


# =============================================================================
# 6. Device Settings Dialog (Dynamic Configuration)
# =============================================================================

class DeviceSettingsDialog(Gtk.Window):
    """
    Device identity and connection settings configuration modal:
      - Hostname & Identity Management (Verified Hostname, User Alias)
      - Network configuration (Configured IP, TCP Port, OPC UA URL)
      - Read-only tag selection
    """
    def __init__(self, parent_win, device: Dict[str, Any], store: F3DeviceStore):
        super().__init__()
        if isinstance(parent_win, Gtk.Window):
            self.set_transient_for(parent_win)
        self.set_modal(True)
        disp_name, _ = compute_display_name(device, store.is_demo_mode)
        self.set_title(f"⚙️ การตั้งค่าอุปกรณ์: {disp_name}")
        self.set_default_size(600, 640)
        self.set_resizable(True)
        self.add_css_class('f3-settings')

        self.device = device
        self.store = store

        root = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
        root.set_margin_start(16)
        root.set_margin_end(16)
        root.set_margin_top(14)
        root.set_margin_bottom(14)
        self.set_child(root)

        grid = Gtk.Grid(column_spacing=12, row_spacing=8)
        settings_scroll = Gtk.ScrolledWindow()
        settings_scroll.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        settings_scroll.set_vexpand(True)
        settings_scroll.set_child(grid)
        root.append(settings_scroll)

        # Fields
        self.entries = {}
        fields = [
            ("alias", "ชื่อแทนที่ผู้ใช้กำหนด (User-defined Alias):", device.get("alias", "")),
            ("hostname", "ชื่อเครื่องที่ตั้งค่า (ยังไม่ยืนยัน):", device.get("configured_hostname") or ""),
            ("device_role", "หน้าที่ในระบบ (Device Role):", device.get("device_role", device.get("role", ""))),
            ("configured_ip", "Configured numeric IP (one address):", device.get("configured_ip", "")),
            ("port", "Service Port (TCP):", str(device.get("port") or "")),
            ("endpoint_url", "OPC UA Endpoint URL:", device.get("endpoint_url", "")),
            ("test_tag", "Verified Tag from F6:", device.get("test_tag", "")),
            ("network_zone", "Configured network group:", device.get("network_zone", "UNASSIGNED")),
            ("interface_name", "Assigned local interface (optional):", device.get("interface_name", "")),
            ("sec_policy", "Security policy (Basic256Sha256):", device.get("sec_policy") or ""),
        ]

        for row, (k, label_txt, val) in enumerate(fields):
            lbl = Gtk.Label(label=label_txt)
            lbl.set_xalign(0.0)
            lbl.add_css_class('f3-prop-key')
            entry = Gtk.Entry()
            entry.set_text(val)
            entry.set_hexpand(True)
            self.entries[k] = entry
            grid.attach(lbl, 0, row, 1, 1)
            grid.attach(entry, 1, row, 1, 1)

        # Switch for Enabled/Disabled
        lbl_en = Gtk.Label(label="อนุญาตการตรวจแบบ manual (Enabled):")
        lbl_en.set_xalign(0.0)
        lbl_en.add_css_class('f3-prop-key')
        self.sw_enabled = Gtk.Switch()
        self.sw_enabled.set_active(device.get("enabled", True))
        grid.attach(lbl_en, 0, len(fields), 1, 1)
        grid.attach(self.sw_enabled, 1, len(fields), 1, 1)
        self.device_types = ['unknown', 'wincc', 'local_host', 'remote_collector', 'switch', 'router', 'service']
        self.type_select = Gtk.DropDown.new_from_strings(self.device_types)
        self.type_select.set_selected(self.device_types.index(device['type']) if device.get('type') in self.device_types else 0)
        grid.attach(Gtk.Label(label='Device type:'), 0, len(fields) + 1, 1, 1)
        grid.attach(self.type_select, 1, len(fields) + 1, 1, 1)
        self.cap_opcua = Gtk.CheckButton(label='Explicit OPC UA capability')
        self.cap_opcua.set_active('opcua' in device.get('capabilities', []))
        grid.attach(self.cap_opcua, 1, len(fields) + 2, 1, 1)

        btn_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
        btn_box.set_halign(Gtk.Align.END)
        btn_box.set_margin_top(14)
        root.append(btn_box)
        self.lbl_save_error = Gtk.Label()
        self.lbl_save_error.set_wrap(True)
        root.append(self.lbl_save_error)

        del_btn = Gtk.Button(label="🗑️ ลบอุปกรณ์ (Remove)")
        del_btn.add_css_class('f3-pill-red')
        del_btn.connect('clicked', self._on_delete)
        # Prevent deleting Core Infrastructure nodes
        dev_id = device.get("device_id", device.get("id"))
        if dev_id in ("dev-collector-01", "dev-switch-01", "dev-router-01", "PC4", "SWITCH", "ROUTER"):
            del_btn.set_sensitive(False)
        btn_box.append(del_btn)

        save_btn = Gtk.Button(label="💾 บันทึกการเปลี่ยนแปลง (Save)")
        save_btn.add_css_class('btn-mode-live')
        save_btn.connect('clicked', self._on_save)
        btn_box.append(save_btn)

    def _on_save(self, _):
        alias_val = self.entries["alias"].get_text().strip()
        host_val = self.entries["hostname"].get_text().strip()
        dev_role = self.entries["device_role"].get_text().strip()

        updates = {
            "alias": alias_val,
            "device_role": dev_role,
            "role": dev_role,
            "configured_ip": self.entries["configured_ip"].get_text().strip(),
            "endpoint_url": self.entries["endpoint_url"].get_text().strip(),
            "test_tag": self.entries["test_tag"].get_text().strip(),
            "network_zone": self.entries["network_zone"].get_text().strip() or "UNASSIGNED",
            "interface_name": self.entries["interface_name"].get_text().strip(),
            "sec_policy": self.entries["sec_policy"].get_text().strip(),
            "enabled": self.sw_enabled.get_active()
        }
        updates['type'] = self.device_types[self.type_select.get_selected()]
        updates['capabilities'] = ['opcua'] if self.cap_opcua.get_active() else []

        if host_val:
            updates["hostname"] = host_val
        elif not alias_val:
            updates["hostname"] = None
            updates["identity_status"] = IdentityStatus.UNKNOWN
            updates["identity_source"] = IdentitySource.UNVERIFIED

        try:
            raw_port = self.entries["port"].get_text().strip()
            updates["port"] = int(raw_port) if raw_port else None
            if updates["port"] is not None and not 1 <= updates["port"] <= 65535:
                raise ValueError()
        except ValueError:
            self.lbl_save_error.set_text("Port ต้องเป็น 1–65535 หรือเว้นว่าง")
            return

        dev_id = self.device.get("device_id", self.device.get("id"))
        self.store.update_device(dev_id, updates)
        if self.store.last_error:
            self.lbl_save_error.set_text(self.store.last_error)
            return
        self.close()

    def _on_delete(self, _):
        dev_id = self.device.get("device_id", self.device.get("id"))
        self.store.remove_device(dev_id)
        self.close()


class DeviceDetailsDialog(Gtk.Window):
    """
    Comprehensive diagnostic details modal providing multi-layer visibility:
      - Device Identity & Specification
      - Physical Link, ICMP, TCP Port, OPC UA Status
      - Diagnostic Insights & Firewall Explanation
      - PC4 Dual-NIC Breakdown & Kernel Air-Gap Validation
    """
    def __init__(self, parent_win=None, device_meta=None, current_status=None,
                 local_state=None, on_retest=None, node=None, state=None):
        super().__init__()
        if isinstance(parent_win, Gtk.Window):
            self.set_transient_for(parent_win)
        self.set_modal(True)
        self.device_meta = device_meta or {}
        self.current_status = current_status or {}
        self.local_state = local_state or {}
        self.on_retest = on_retest

        meta = device_meta or {}
        d_id = meta.get("device_id", meta.get("id", ""))
        legacy_id = REVERSE_LEGACY_MAP.get(d_id, d_id)
        name = meta.get("name") or (node or {}).get("title", "Device")
        if legacy_id and legacy_id not in name:
            self.set_title(f"📋 รายละเอียดและผลการวินิจฉัย: {name} ({legacy_id})")
        else:
            self.set_title(f"📋 รายละเอียดและผลการวินิจฉัย: {name}")
        self.set_default_size(680, 560)
        self.set_resizable(True)

        scroll = Gtk.ScrolledWindow()
        scroll.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        self.set_child(scroll)

        root = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)
        root.set_margin_start(16)
        root.set_margin_end(16)
        root.set_margin_top(14)
        root.set_margin_bottom(14)
        scroll.set_child(root)

        h_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
        root.append(h_box)

        icon_lbl = Gtk.Label(label=(device_meta or {}).get("icon", "🖥️"))
        icon_lbl.add_css_class("f3-title-text")
        h_box.append(icon_lbl)

        t_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
        t_box.set_hexpand(True)
        h_box.append(t_box)

        dev_title = Gtk.Label(label=name)
        dev_title.add_css_class("f3-title-text")
        dev_title.set_xalign(0.0)
        t_box.append(dev_title)

        dev_role = Gtk.Label(label=(device_meta or {}).get("role", "—"))
        dev_role.add_css_class("f3-subtitle-text")
        dev_role.set_xalign(0.0)
        t_box.append(dev_role)

        st = (current_status or {}).get("reachability") or (current_status or {}).get("status", "UNKNOWN")
        badge = Gtk.Label(label=f"สถานะ: {st}")
        badge.add_css_class("f3-stat-pill")
        badge.add_css_class("f3-pill-green" if "REACHABLE" in st or "ONLINE" in st else "f3-pill-neutral")
        h_box.append(badge)

        sec_title = Gtk.Label(label="📌 ข้อมูลจำเพาะและหน้าที่ในระบบ (Identity & Specification)")
        sec_title.add_css_class("f3-title-text")
        sec_title.set_xalign(0.0)
        root.append(sec_title)

        grid1 = Gtk.Grid(column_spacing=16, row_spacing=6)
        root.append(grid1)

        fields = [
            ("Device ID:", (device_meta or {}).get("id", "—")),
            ("Configured IP:", (device_meta or {}).get("configured_ip") or (device_meta or {}).get("ip", "—")),
            ("Service Port:", str((device_meta or {}).get("port") or "Not configured")),
            ("Endpoint URL:", (device_meta or {}).get("endpoint_url", "—")),
            ("Zone:", (device_meta or {}).get("zone_desc") or (device_meta or {}).get("zone", "—")),
            ("MAC Address:", (device_meta or {}).get("mac", "—")),
            ("Kernel IP forwarding:", str((device_meta or {}).get("ip_forwarding", "UNKNOWN"))),
        ]

        for row, (k, v) in enumerate(fields):
            lbl_k = Gtk.Label(label=k)
            lbl_k.add_css_class("f3-prop-key")
            lbl_k.set_xalign(0.0)
            lbl_v = Gtk.Label(label=str(v))
            lbl_v.add_css_class("f3-prop-val")
            lbl_v.set_xalign(0.0)
            lbl_v.set_selectable(True)
            grid1.attach(lbl_k, 0, row, 1, 1)
            grid1.attach(lbl_v, 1, row, 1, 1)

        if (device_meta or {}).get("id") == "PC4":
            sec_pc4 = Gtk.Label(label="🔀 การแยกสองฝั่งเครือข่ายของ PC4 (Dual-NIC Architecture)")
            sec_pc4.add_css_class("f3-title-text")
            sec_pc4.set_xalign(0.0)
            root.append(sec_pc4)

            grid_pc4 = Gtk.Grid(column_spacing=16, row_spacing=6)
            root.append(grid_pc4)
            pc4_fields = [(name, f"{item.get('ipv4') or 'UNKNOWN'} / carrier {item.get('carrier')}")
                          for name, item in (device_meta or {}).get('interface_observations', {}).items()]
            if not pc4_fields:
                pc4_fields = [("Interfaces:", "No local observations; roles UNASSIGNED")]
            for row, (k, v) in enumerate(pc4_fields):
                lbl_k = Gtk.Label(label=k)
                lbl_k.add_css_class("f3-prop-key")
                lbl_k.set_xalign(0.0)
                lbl_v = Gtk.Label(label=str(v))
                lbl_v.add_css_class("f3-prop-val")
                lbl_v.set_xalign(0.0)
                grid_pc4.attach(lbl_k, 0, row, 1, 1)
                grid_pc4.attach(lbl_v, 1, row, 1, 1)

        guidance = Gtk.Label(
            label="คำแนะนำความปลอดภัย: เครือข่าย SCADA ต้องคงสถานะ Air-Gapped ตลอดเวลา ห้ามเปิด IP Forwarding บน PC4 เป็นอันขาด"
        )
        guidance.set_wrap(True)
        guidance.set_xalign(0.0)
        guidance.add_css_class("f3-subtitle-text")
        root.append(guidance)

        btn_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL)
        btn_box.set_halign(Gtk.Align.END)
        root.append(btn_box)

        btn_close = Gtk.Button(label="ปิดหน้าต่าง (Close)")
        btn_close.connect("clicked", lambda _: self.close())
        btn_box.append(btn_close)



# =============================================================================
# 7. Interactive Live Network Diagram Canvas
# =============================================================================

def draw_rounded_rect(cr, x, y, w, h, r):
    cr.new_sub_path()
    cr.arc(x + w - r, y + r, r, -math.pi/2, 0)
    cr.arc(x + w - r, y + h - r, r, 0, math.pi/2)
    cr.arc(x + r, y + h - r, r, math.pi/2, math.pi)
    cr.arc(x + r, y + r, r, math.pi, 3*math.pi/2)
    cr.close_path()

def draw_pango_text(cr, text, x, y, font_desc="Noto Sans Thai, Sans 9", color=(1.0, 1.0, 1.0), max_width=None):
    layout = PangoCairo.create_layout(cr)
    layout.set_font_description(Pango.FontDescription.from_string(font_desc))
    layout.set_text(text)
    if max_width is not None:
        layout.set_width(max(1, int(max_width)) * Pango.SCALE)
        layout.set_ellipsize(Pango.EllipsizeMode.END)
    cr.set_source_rgb(*color)
    cr.move_to(x, y)
    PangoCairo.show_layout(cr, layout)


class F3LiveDiagramCanvas(Gtk.DrawingArea):
    """
    Interactive Network Diagram Canvas:
      - Renders Logical Topology (SCADA PCs -> Switch -> PC4 Dual-NIC -> Router -> Telegram)
      - Clickable node hit-testing to select devices
      - Frame-rate bounded particle animation on active connection lines
      - Automatically halts animation when connection is UNKNOWN or STALE
    """
    def __init__(self, owner_view):
        super().__init__()
        self.owner_view = owner_view
        self.set_draw_func(self.on_draw)
        self.set_content_height(450)
        self.set_content_width(700)
        self.set_hexpand(True)
        self.set_vexpand(True)

        # Hit testing map: device_id -> (x, y, w, h)
        self.node_rects: Dict[str, tuple] = {}
        self.set_has_tooltip(True)
        self.connect('query-tooltip', self._query_tooltip)

        # Click gesture
        gesture = Gtk.GestureClick()
        gesture.connect('pressed', self._on_clicked)
        self.add_controller(gesture)

        # Animation tick
        self.anim_tick_count = 0
        self._had_pulses = False
        self.anim_source_id = GLib.timeout_add(100, self._on_anim_tick)

    def _on_anim_tick(self):
        self.anim_tick_count = (self.anim_tick_count + 1) % 10000
        # Redraw only if widget is active and has visible active connections
        active = bool(self.owner_view.runtime.active())
        if self.get_mapped() and (active or self._had_pulses):
            self.queue_draw()
        self._had_pulses = active
        return True

    def _on_clicked(self, gesture, n_press, x, y):
        for dev_id, (rx, ry, rw, rh) in self.node_rects.items():
            if rx <= x <= rx + rw and ry <= y <= ry + rh:
                self.owner_view.select_device(dev_id)
                self.queue_draw()
                break

    def _query_tooltip(self, widget, x, y, keyboard_mode, tooltip):
        for dev_id, (rx, ry, rw, rh) in self.node_rects.items():
            if rx <= x <= rx + rw and ry <= y <= ry + rh:
                device = self.owner_view.store.devices.get(dev_id)
                if device is None:
                    continue
                tooltip.set_text(f"{evidence.identity_label(device)}\nType: {device.get('type', 'unknown')}\n"
                    f"Configured: {device.get('configured_ip') or 'UNKNOWN'}\nObserved: {device.get('observed_ip') or 'UNKNOWN'}\n"
                    f"{device_status_text(device)}\n{device.get('binding_reason') or 'Interface role UNVERIFIED'}\n"
                    'คลิกเพื่อดูข้อมูลเต็มใน Inspector')
                return True
        return False

    def on_draw(self, area, cr, width, height):
        draw_flow(self, cr, width, height, draw_rounded_rect, draw_pango_text)
        for dev_id, rect in list(self.node_rects.items()):
            alias = REVERSE_LEGACY_MAP.get(dev_id)
            if alias:
                self.node_rects[alias] = rect

    def _draw_connection_line(self, cr, p1, p2, state):
        cr.save()
        # Base Line
        color = (0.25, 0.30, 0.35)
        dashes = []
        line_w = 1.5

        if state == ConnectionState.OPCUA_CONNECTED:
            color = (0.64, 0.44, 0.97) # Purple
            line_w = 2.0
        elif state in (ConnectionState.REACHABILITY_VERIFIED, ConnectionState.LINK_VERIFIED):
            color = (0.25, 0.75, 0.35) # Green
            line_w = 1.8
        elif state in (ConnectionState.OPCUA_ERROR, ConnectionState.SERVICE_UNAVAILABLE):
            color = (0.95, 0.30, 0.30) # Red
            dashes = [4.0, 4.0]
        elif state == ConnectionState.NIC_OT_DOWN:
            color = (0.85, 0.60, 0.15) # Amber
            dashes = [3.0, 3.0]
        elif state == ConnectionState.CHECKING:
            color = (0.85, 0.60, 0.15) # Amber
            dashes = [2.0, 2.0]
        else: # UNKNOWN / STALE
            color = (0.20, 0.25, 0.30)
            dashes = [4.0, 4.0]

        cr.set_source_rgb(*color)
        cr.set_line_width(line_w)
        if dashes:
            cr.set_dash(dashes)
        else:
            cr.set_dash([])

        # Draw smooth path
        cr.move_to(p1[0], p1[1])
        mid_x = (p1[0] + p2[0]) / 2.0
        cr.curve_to(mid_x, p1[1], mid_x, p2[1], p2[0], p2[1])
        cr.stroke()

        # State alone never generates traffic animation.
        cr.restore()

    def _draw_scada_node(self, cr, x, y, w, h, dev, selected=False):
        # Compatibility renderer uses the same evidence rules as the new flow.
        cr.save()
        draw_rounded_rect(cr, x, y, w, h, 6)
        cr.set_source_rgb(0.09, 0.115, 0.145)
        cr.fill_preserve()
        cr.set_source_rgb(*(0.25, 0.72, 0.88) if selected else (0.27, 0.32, 0.39))
        cr.stroke()
        draw_pango_text(cr, evidence.identity_label(dev), x + 12, y + 8, "Noto Sans Thai, Sans Bold 10", max_width=w - 24)
        draw_pango_text(cr, str(dev.get("configured_ip") or dev.get("observed_ip") or "IP Unknown"), x + 12, y + 32, "Sans 12", max_width=w - 24)
        draw_pango_text(cr, device_status_text(dev), x + 12, y + 60, "Noto Sans Thai, Sans 9", max_width=w - 24)
        cr.restore()

    _draw_switch_node = _draw_scada_node
    _draw_router_node = _draw_scada_node
    _draw_service_node = _draw_scada_node

    def _draw_pc4_node(self, cr, x, y, w, h, dev, selected=False):
        self._draw_scada_node(cr, x, y, w, h, dev, selected)
        for index, zone in enumerate(("SCADA_OT", "EXTERNAL_WAN")):
            interface = self.owner_view.store.networks.get(zone, {}).get("interface")
            observation = self.owner_view.local_state.get("interfaces", {}).get(interface, {})
            value = f"{zone}: {interface or 'UNASSIGNED'} / {observation.get('ipv4') or 'UNKNOWN'}"
            draw_pango_text(cr, value, x + 12, y + 92 + 30 * index, "Sans 9", max_width=w - 24)


F3TopologyCanvas = F3LiveDiagramCanvas


# =============================================================================
# 8. Device Detail Inspector Panel (Collapsible Right Pane)
# =============================================================================

class DeviceDetailInspector(Gtk.Box):
    """
    Inspector Panel displaying deep diagnostic findings across all 10 dimensions:
      - Stable Device ID, Display Name, Factual Hostname, User Alias, Role, Identity Source & Status,
        Configured/Observed IP, Physical Interfaces, Connectivity, TCP, OPC UA Subsystem, Verification Timestamp
      - Action Buttons: Detect Now, Test OPC UA, Read Once, Device Settings
    """
    def __init__(self, owner_view):
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        self.add_css_class('f3-inspector-pane')
        self.set_size_request(350, -1)
        self.owner_view = owner_view
        self.current_device_id: Optional[str] = None

        self._build_ui()

    def _build_ui(self):
        # Header
        top_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        top_box.add_css_class('f3-inspector-header')
        self.append(top_box)

        self.lbl_title = Gtk.Label(label="📋 Device Inspector")
        self.lbl_title.add_css_class('f3-inspector-title')
        self.lbl_title.set_xalign(0.0)
        self.lbl_title.set_ellipsize(Pango.EllipsizeMode.END)
        self.lbl_title.set_max_width_chars(22)
        top_box.append(self.lbl_title)

        spacer = Gtk.Box()
        spacer.set_hexpand(True)
        top_box.append(spacer)

        self.btn_close = Gtk.Button(label="✕")
        self.btn_close.connect('clicked', lambda _: self.owner_view.toggle_inspector(False))
        self.btn_close.set_visible(False)
        top_box.append(self.btn_close)

        # Scrolled content for properties
        scroll = Gtk.ScrolledWindow()
        scroll.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        scroll.set_vexpand(True)
        self.append(scroll)
        self.scroll = scroll

        self.prop_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        scroll.set_child(self.prop_box)

        self._add_section_title("สถานะของอุปกรณ์")
        self.lbl_cfg_ip = self._add_prop_row("IP ที่ตั้งค่า", "—")
        self.lbl_ping = self._add_prop_row("ผลตรวจเครื่อง", "ยังไม่ได้ตรวจสอบ")
        self.lbl_tcp = self._add_prop_row("พอร์ตบริการ", "ยังไม่ได้ตรวจสอบ")
        self.lbl_opc_state = self._add_prop_row("OPC UA", "ยังไม่ได้ทดสอบ")
        self.lbl_last_read = self._add_prop_row("ค่าที่อ่านล่าสุด", "ยังไม่มีข้อมูล")
        self.lbl_error = self._add_prop_row("ข้อผิดพลาด", "—")
        self.lbl_runtime = self._add_prop_row('Runtime evidence', 'UNKNOWN')
        self.lbl_polling = self._add_prop_row('Polling state', 'UNKNOWN')
        self.lbl_client = self._add_prop_row('Existing UA client', 'UNKNOWN')
        self.lbl_shared_read = self._add_prop_row('Backend DataValue', 'UNKNOWN')
        self.lbl_delivery = self._add_prop_row('Service delivery', 'UNKNOWN')

        self._add_section_title("ข้อมูลอุปกรณ์")
        self.lbl_disp_name = self._add_prop_row("ชื่อที่แสดง", "—")
        self.lbl_hostname = self._add_prop_row("ชื่อเครื่องจริง", "ยังไม่ทราบ")
        self.lbl_alias = self._add_prop_row("ชื่อที่คุณตั้ง", "—")
        self.lbl_role = self._add_prop_row("หน้าที่", "—")
        self.lbl_zone = self._add_prop_row("เครือข่าย", "—")
        self.lbl_obs_ip = self._add_prop_row("IP ที่ตรวจพบ", "ยังไม่พบ")
        self.lbl_verified_at = self._add_prop_row("ตรวจล่าสุด", "—")

        self._add_section_title("ข้อมูลทางเทคนิค")
        self.lbl_id = self._add_prop_row("Device ID", "—")
        self.lbl_id_src = self._add_prop_row("ที่มาของชื่อ", "—")
        self.lbl_id_status = self._add_prop_row("การยืนยันชื่อ", "—")
        self.lbl_mac = self._add_prop_row("MAC Address", "—")
        self.lbl_endpoint = self._add_prop_row("OPC UA URL", "—")
        self.lbl_pki_sec = self._add_prop_row("ใบรับรอง", "—")
        self.lbl_session = self._add_prop_row("Manual session", "UNKNOWN")
        self.lbl_session_success = self._add_prop_row("Session สำเร็จล่าสุด", "—")
        self.lbl_quality = self._add_prop_row("Quality / raw status", "UNKNOWN")
        self.lbl_source_time = self._add_prop_row("Source timestamp", "—")
        self.lbl_server_time = self._add_prop_row("Server timestamp", "—")
        self.lbl_arrival_time = self._add_prop_row("Arrival timestamp", "—")
        self.lbl_mapping = self._add_prop_row("Verified NodeId", "—")
        self.lbl_binding = self._add_prop_row("Interface role audit", "UNVERIFIED")
        self.lbl_interfaces = self._add_prop_row("Local observations", "—")
        self.lbl_provenance = self._add_prop_row("Evidence provenance", "UNKNOWN")
        self.lbl_history = self._add_prop_row("Recent manual events", "—")

        # Action Buttons Row
        btn_grid = Gtk.Grid(column_spacing=6, row_spacing=6)
        self.append(btn_grid)

        self.btn_detect = Gtk.Button(label="ตรวจสอบเครื่อง")
        self.btn_detect.add_css_class('btn-mode-live')
        self.btn_detect.connect('clicked', self._on_detect_clicked)
        btn_grid.attach(self.btn_detect, 0, 0, 1, 1)

        self.btn_test_opc = Gtk.Button(label="ทดสอบ Secure Session")
        self.btn_test_opc.set_tooltip_text("ตรวจ certificate และเปิด session แบบ read-only ชั่วคราว จากนั้นปิด")
        self.btn_test_opc.connect('clicked', self._on_test_opc_clicked)
        btn_grid.attach(self.btn_test_opc, 1, 0, 1, 1)

        self.btn_read_once = Gtk.Button(label="อ่านค่าทดสอบ")
        self.btn_read_once.connect('clicked', self._on_read_once_clicked)
        btn_grid.attach(self.btn_read_once, 0, 1, 1, 1)

        self.btn_settings = Gtk.Button(label="ตั้งค่าอุปกรณ์")
        self.btn_settings.connect('clicked', self._on_settings_clicked)
        btn_grid.attach(self.btn_settings, 1, 1, 1, 1)
        self.btn_cancel = Gtk.Button(label='ยกเลิกงานที่กำลังตรวจ')
        self.btn_cancel.connect('clicked', lambda _: self.owner_view.cancel_remote_action())
        self.btn_cancel.set_visible(False)
        btn_grid.attach(self.btn_cancel, 0, 2, 2, 1)

    def _add_section_title(self, title: str):
        lbl = Gtk.Label(label=title)
        lbl.add_css_class('f3-inspector-section')
        lbl.set_xalign(0.0)
        self.prop_box.append(lbl)

    def _add_prop_row(self, key: str, val: str) -> Gtk.Label:
        row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        self.prop_box.append(row)

        k_lbl = Gtk.Label(label=key)
        k_lbl.add_css_class('f3-prop-key')
        k_lbl.set_xalign(0.0)
        k_lbl.set_wrap(True)
        k_lbl.set_wrap_mode(Pango.WrapMode.WORD_CHAR)
        k_lbl.set_max_width_chars(12)
        k_lbl.set_size_request(96, -1)
        row.append(k_lbl)

        v_lbl = Gtk.Label(label=val)
        v_lbl.add_css_class('f3-prop-val')
        v_lbl.set_xalign(1.0)
        v_lbl.set_hexpand(True)
        v_lbl.set_wrap(True)
        v_lbl.set_wrap_mode(Pango.WrapMode.WORD_CHAR)
        v_lbl.set_max_width_chars(20)
        v_lbl.set_selectable(True)
        row.append(v_lbl)
        return v_lbl

    def inspect_device(self, dev_id: str):
        self.current_device_id = dev_id
        store = self.owner_view.store
        dev = store.devices.get(dev_id)
        if not dev:
            return

        disp_name = evidence.identity_label(dev)
        identity_source = evidence.evidence_state(dev, "identity")
        id_status = dev.get("identity_status") if evidence.fresh(dev, "identity") else "UNKNOWN"
        d_id = dev.get('device_id', dev.get('id', '—'))

        legacy_id = REVERSE_LEGACY_MAP.get(dev.get("device_id"), dev_id)
        self.lbl_title.set_text(f"📋 {disp_name} [{legacy_id}]" if legacy_id and legacy_id != disp_name else f"📋 {disp_name}")
        self.lbl_title.set_tooltip_text(disp_name)
        self.lbl_id.set_text(f"{d_id} ({dev.get('type')})")
        self.lbl_disp_name.set_text(disp_name)
        self.lbl_hostname.set_text(dev.get('hostname') if evidence.fresh(dev, "identity") and dev.get('hostname') else "UNKNOWN")
        self.lbl_alias.set_text(dev.get('alias') or "—")
        self.lbl_id_src.set_text(identity_source)
        self.lbl_id_status.set_text(id_status)
        self.lbl_role.set_text(dev.get('device_role', dev.get('role', '—')))
        self.lbl_zone.set_text(dev.get('zone_desc', dev.get('network_zone', '—')))

        self.lbl_cfg_ip.set_text(dev.get('configured_ip', '—'))
        self.lbl_obs_ip.set_text(dev.get('observed_ip') or "Not Observed")
        self.lbl_mac.set_text(dev.get('observed_mac') or "Not observed")
        self.lbl_verified_at.set_text(str(dev.get('last_verified_time') or "—"))

        ping_txt = device_status_text(dev)
        self.lbl_ping.set_text(ping_txt)
        self.lbl_tcp.set_text(f"Port {dev.get('port') or 'not configured'}: {evidence.presentation_state(dev, 'tcp', dev.get('tcp_status'))}")

        self.lbl_endpoint.set_text(dev.get('endpoint_url') or "Not Configured")
        self.lbl_opc_state.set_text(f"{dev.get('opcua_state', 'UNKNOWN')} · {evidence.evidence_state(dev, 'session')}" if evidence.capabilities(dev)['opcua'] else 'NOT_APPLICABLE')
        self.lbl_pki_sec.set_text(f"{dev.get('certificate_trust', 'NOT_TESTED')}\n{dev.get('certificate_reason') or ''}\n{dev.get('certificate_thumbprint') or ''}")
        self.lbl_session.set_text(evidence.session_label(dev))
        self.lbl_session_success.set_text(dev.get('last_session_success') or "—")
        self.lbl_quality.set_text(f"{dev.get('last_read_quality') or 'UNKNOWN'} · {dev.get('raw_status') or '—'} · {evidence.evidence_state(dev, 'read')}")
        self.lbl_source_time.set_text(dev.get('source_timestamp') or "—")
        self.lbl_server_time.set_text(dev.get('server_timestamp') or "—")
        self.lbl_arrival_time.set_text(dev.get('arrival_timestamp') or "—")
        self.lbl_mapping.set_text(dev.get('node_id') or "Select verified mapping in F6")
        binding, reason = evidence.network_binding(dev, self.owner_view.local_state, store.networks)
        self.lbl_binding.set_text(f"{binding}\n{reason}")
        interfaces = dev.get('interface_observations', {})
        self.lbl_interfaces.set_text("\n\n".join(f"{name} · {item.get('interface_type', 'UNKNOWN')}\n{item.get('connection_state', 'UNKNOWN')} · carrier {item.get('carrier')}\nIPv4: {', '.join(item.get('ipv4_addresses') or [item.get('ipv4') or 'UNKNOWN'])}\nGateway: {item.get('gateway') or 'UNKNOWN'}\n{item.get('speed_mbps') or 'UNKNOWN'} Mb/s · {item.get('speed_kind', 'UNKNOWN')}\nIP source: {item.get('field_sources', {}).get('ipv4', item.get('source', 'UNKNOWN'))}\nCarrier source: {item.get('field_sources', {}).get('carrier', 'UNKNOWN')}" for name, item in interfaces.items()) or "No local interface observations for this device")
        self.lbl_provenance.set_text("\n".join(f"{kind}: {evidence.evidence_state(dev, kind)}" for kind in ('identity', 'local', 'reachability', 'tcp', 'certificate', 'session', 'read')))
        self.lbl_history.set_text("\n".join(f"{item.get('time')} · {item.get('type')}\n{item.get('result')}" for item in dev.get('history', [])[-8:]) or "No manual events in this session")

        val = dev.get('last_read_value')
        q = dev.get('last_read_quality')
        if val is not None:
            self.lbl_last_read.set_text(f"{dev.get('last_read_tag')}: {val} [{q}]")
        else:
            self.lbl_last_read.set_text("—")

        self.lbl_error.set_text('\n'.join(str(dev[key]) for key in ('last_error', 'network_error') if dev.get(key)) or "; ".join(dev.get('config_errors', [])) or "None")

        snapshot = self.owner_view.runtime.snapshot
        runtime = evidence.runtime_summary(snapshot)
        local = dev['type'] == 'local_host'
        collector = local or dev['type'] == 'remote_collector'
        ua = evidence.capabilities(dev)['opcua']
        matching = runtime['receipts'] if local else [r for r in runtime['receipts'] if r['endpoint_url'] == dev.get('endpoint_url')] if ua else []
        self.lbl_runtime.set_text(f"SQLite: {runtime['db_state']} · UNBOUND_LOCAL_RUNTIME\n{snapshot.get('error') or ''}" if local else 'UNKNOWN · remote runtime not observed')
        self.lbl_polling.set_text(runtime['polling_state'] if local else 'UNKNOWN · remote poller not observed')
        self.lbl_client.set_text(runtime['client_state'] if local or ua and dev.get('endpoint_url') == snapshot.get('client_endpoint') else 'UNKNOWN')
        receipt = matching[0] if matching else None
        stale = runtime['stale_receipts'] if local else [r for r in runtime['stale_receipts'] if r['endpoint_url'] == dev.get('endpoint_url')] if ua else []
        self.lbl_shared_read.set_text(f"{receipt['tag_name']}: {receipt.get('value')} [{receipt['quality']}]\nEndpoint: {receipt['endpoint_url']}\nNode: {receipt['node_id']}\nSource: {receipt.get('source_timestamp') or 'UNKNOWN'}\nServer: {receipt.get('server_timestamp') or 'UNKNOWN'}\nArrival: {receipt['arrival_timestamp']}\nMapping: verified allowlist at capture" if receipt else 'STALE · last mapped receipt expired' if stale else 'UNKNOWN · no fresh mapped DataValue receipt')
        self.lbl_delivery.set_text(f"{runtime['db_state']} · UNVERIFIED · local attempts have no binding to this service or provider ACK" if snapshot.get('last_delivery') else 'NOT_TESTED · no bound delivery receipt' if runtime['db_state'] == 'OBSERVED_LOCAL' else runtime['db_state'])
        for label, visible in ((self.lbl_runtime, collector), (self.lbl_polling, collector),
                               (self.lbl_client, collector or ua), (self.lbl_shared_read, local or ua),
                               (self.lbl_delivery, dev['type'] == 'service')):
            label.get_parent().set_visible(visible)
        for label in (self.lbl_opc_state, self.lbl_last_read, self.lbl_endpoint, self.lbl_pki_sec,
                      self.lbl_session, self.lbl_session_success, self.lbl_quality, self.lbl_source_time,
                      self.lbl_server_time, self.lbl_arrival_time, self.lbl_mapping):
            label.get_parent().set_visible(ua)

        # Button states
        caps = evidence.capabilities(dev)
        is_wincc = caps['opcua']
        enabled = dev.get("enabled", True)
        busy = bool(self.owner_view._remote_busy)
        self.btn_cancel.set_visible(busy)
        self.btn_cancel.set_sensitive(busy and not self.owner_view._cancel_event.is_set())
        self.btn_cancel.set_label('กำลังรอปิดงาน…' if busy and self.owner_view._cancel_event.is_set() else 'ยกเลิกงานที่กำลังตรวจ')
        self.btn_detect.set_sensitive(enabled and not busy and (caps['local'] or caps['network']))
        self.btn_detect.set_label('รีเฟรชเครื่องนี้' if caps['local'] else 'ทดสอบ TCP' if dev['type'] == 'service' else 'ตรวจสอบเครื่อง')
        self.btn_detect.set_tooltip_text('Read-only local OS properties' if caps['local'] else 'Only the configured numeric IP; explicit authorization required')
        self.btn_test_opc.set_visible(is_wincc)
        self.btn_read_once.set_visible(is_wincc)
        options = self.owner_view._opcua_options(dev)
        adapter = self.owner_view.secure_opcua
        session_error = None if store.is_demo_mode else adapter.readiness(dev, options)
        read_error = None if store.is_demo_mode else adapter.readiness(dev, options, require_mapping=True)
        self.btn_test_opc.set_sensitive(is_wincc and enabled and not busy and session_error is None)
        self.btn_read_once.set_sensitive(is_wincc and enabled and not busy and read_error is None)
        self.btn_test_opc.set_tooltip_text(session_error or "เปิด trusted session ชั่วคราวแล้วปิด • ต้องอนุญาตก่อน")
        self.btn_read_once.set_tooltip_text(read_error or "อ่านหนึ่ง DataValue ด้วย verified mapping • ไม่เริ่ม polling")

    def _on_detect_clicked(self, _):
        if self.current_device_id:
            self.owner_view.trigger_device_detect(self.current_device_id)

    def _on_test_opc_clicked(self, _):
        if self.current_device_id:
            self.owner_view.trigger_device_opcua_test(self.current_device_id)

    def _on_read_once_clicked(self, _):
        if self.current_device_id:
            self.owner_view.trigger_device_read_once(self.current_device_id)

    def _on_settings_clicked(self, _):
        if self.current_device_id:
            dev = self.owner_view.store.devices.get(self.current_device_id)
            if dev:
                dlg = DeviceSettingsDialog(self.owner_view.root_widget.get_root(), dev, self.owner_view.store)
                dlg.set_destroy_with_parent(True)
                dlg.present()


# =============================================================================
# 9. Device Card Widget
# =============================================================================

class F3DeviceCard(Gtk.Box):
    """
    Compact Device Card shown in the lower scrollable grid:
      - Icon, Primary Display Name (Verified Hostname or IP), Role, IP, Port, Status LED, Identity Status Pill
      - Buttons: [ 🔍 Detect ], [ 📋 Details / Inspect ]
    """
    def __init__(self, owner_view, device: Dict[str, Any]):
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=4)
        self.add_css_class('f3-card')
        self.set_hexpand(True)
        self.set_valign(Gtk.Align.FILL)
        self.owner_view = owner_view
        self.dev_id = device["device_id"]
        self.device_meta = device
        self.status_data = {"status": device.get("reachability", "UNKNOWN")}

        self._build_ui(device)
        self.badge_lbl = self.lbl_badge
        self.name_lbl = self.lbl_name
        self.role_lbl = self.lbl_role
        self.pill_l1 = self.pill_ping

    def _build_ui(self, dev: Dict[str, Any]):
        header = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        self.append(header)

        icon_lbl = Gtk.Label(label=dev.get("icon", "🖥️"))
        icon_lbl.add_css_class('f3-title-text')
        header.append(icon_lbl)

        title_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=1)
        title_box.set_hexpand(True)
        header.append(title_box)

        disp_name, id_status = compute_display_name(dev, self.owner_view.store.is_demo_mode)
        self.lbl_name = Gtk.Label(label=disp_name)
        self.lbl_name.add_css_class('f3-title-text')
        self.lbl_name.set_xalign(0.0)
        self.lbl_name.set_ellipsize(Pango.EllipsizeMode.END)
        self.lbl_name.set_max_width_chars(18)
        title_box.append(self.lbl_name)

        role = dev.get("device_role", dev.get("role", "—"))
        self.lbl_role = Gtk.Label(label=role)
        self.lbl_role.add_css_class('f3-subtitle-text')
        self.lbl_role.set_xalign(0.0)
        self.lbl_role.set_ellipsize(Pango.EllipsizeMode.END)
        self.lbl_role.set_max_width_chars(28)
        title_box.append(self.lbl_role)

        self.lbl_badge = Gtk.Label(label=dev.get("reachability", "UNKNOWN"))
        self.lbl_badge.add_css_class('f3-stat-pill')
        self.lbl_badge.add_css_class('f3-pill-neutral')
        self.lbl_badge.set_ellipsize(Pango.EllipsizeMode.NONE)
        self.lbl_badge.set_max_width_chars(9)
        header.append(self.lbl_badge)

        # Body Info
        self.lbl_summary = Gtk.Label(label=device_status_text(dev))
        self.lbl_summary.add_css_class('f3-readable-status')
        self.lbl_summary.set_xalign(0.0)
        self.lbl_summary.set_ellipsize(Pango.EllipsizeMode.END)
        self.lbl_summary.set_max_width_chars(32)
        self.append(self.lbl_summary)
        grid = Gtk.Grid(column_spacing=8, row_spacing=2)
        self.append(grid)

        k1 = Gtk.Label(label="IP ที่ตั้งค่า:")
        k1.add_css_class('f3-prop-key')
        k1.set_xalign(0.0)
        self.v_cfg_ip = Gtk.Label(label=f"{dev.get('configured_ip')}:{dev.get('port')}")
        self.v_cfg_ip.add_css_class('f3-prop-val')
        self.v_cfg_ip.set_xalign(0.0)
        self.v_cfg_ip.set_ellipsize(Pango.EllipsizeMode.END)
        self.v_cfg_ip.set_max_width_chars(24)
        grid.attach(k1, 0, 0, 1, 1)
        grid.attach(self.v_cfg_ip, 1, 0, 1, 1)

        k2 = Gtk.Label(label="IP ที่ตรวจพบ:")
        k2.add_css_class('f3-prop-key')
        k2.set_xalign(0.0)
        self.v_obs_ip = Gtk.Label(label=dev.get("observed_ip") or "—")
        self.v_obs_ip.add_css_class('f3-prop-val')
        self.v_obs_ip.set_xalign(0.0)
        self.v_obs_ip.set_ellipsize(Pango.EllipsizeMode.END)
        self.v_obs_ip.set_max_width_chars(24)
        grid.attach(k2, 0, 1, 1, 1)
        grid.attach(self.v_obs_ip, 1, 1, 1, 1)

        # Micro Pills Bar
        self.pills_bar = Gtk.Grid(column_spacing=4, row_spacing=4)
        self.append(self.pills_bar)

        self.pill_ping = Gtk.Label(label="Ping: ?")
        self.pill_ping.add_css_class('f3-stat-pill')
        self.pill_ping.add_css_class('f3-pill-neutral')
        self.pills_bar.attach(self.pill_ping, 0, 0, 1, 1)

        self.pill_port = Gtk.Label(label=f"Port {dev.get('port')}: ?")
        self.pill_port.add_css_class('f3-stat-pill')
        self.pill_port.add_css_class('f3-pill-neutral')
        self.pills_bar.attach(self.pill_port, 1, 0, 1, 1)

        self.pill_opc = Gtk.Label(label="OPC: ?")
        self.pill_opc.add_css_class('f3-stat-pill')
        self.pill_opc.add_css_class('f3-pill-neutral')
        self.pills_bar.attach(self.pill_opc, 2, 0, 1, 1)

        self.pill_id = Gtk.Label(label=f"ID: {id_status}")
        self.pill_id.add_css_class('f3-stat-pill')
        if id_status == IdentityStatus.VERIFIED:
            self.pill_id.add_css_class('f3-pill-cyan')
        elif id_status == IdentityStatus.USER_DEFINED:
            self.pill_id.add_css_class('f3-pill-purple')
        elif id_status == IdentityStatus.UNVERIFIED:
            self.pill_id.add_css_class('f3-pill-amber')
        else:
            self.pill_id.add_css_class('f3-pill-neutral')
        self.pills_bar.attach(self.pill_id, 3, 0, 1, 1)

        # Action Buttons
        btn_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        btn_box.set_margin_top(4)
        self.append(btn_box)

        self.btn_detect = Gtk.Button(label="ตรวจสอบเครื่อง")
        self.btn_detect.set_sensitive(dev.get("type") != "service" and dev.get("enabled", True))
        if dev.get("type") == "service":
            self.btn_detect.set_tooltip_text("บริการภายนอกนี้เป็นจุดอ้างอิงบนผัง ปุ่มนี้ไม่ส่ง Ping ไปยังบริการ")
        self.btn_detect.add_css_class('btn-mode-live')
        self.btn_detect.connect('clicked', self._on_detect_clicked)
        btn_box.append(self.btn_detect)

        self.btn_details = Gtk.Button(label="รายละเอียด")
        self.btn_details.connect('clicked', lambda _: self.owner_view.select_device(self.dev_id))
        btn_box.append(self.btn_details)

        self.update_view(dev)

    def _on_detect_clicked(self, _=None):
        self.owner_view.trigger_device_detect(self.dev_id)

    def update_from_host_state(self, local_state):
        # Carrier does not prove an interface role or remote endpoint health.
        self.owner_view.local_state = local_state
        self.update_view(self.device_meta)

    def update_view(self, dev: Dict[str, Any]):
        self.device_meta = dev
        kind = "local" if dev.get("type") == "local_host" else "reachability"
        source = evidence.evidence_state(dev, kind)
        if dev.get("is_demo"):
            source = evidence.Provenance.DEMO
        elif evidence.read_verified(dev):
            source = evidence.Provenance.OPCUA
        self.status_data = {"status": source}
        self.lbl_summary.set_text(device_status_text(dev))
        self.lbl_summary.set_tooltip_text(device_status_text(dev))
        caps = evidence.capabilities(dev)
        self.btn_detect.set_sensitive((caps['local'] or caps['network']) and dev.get("enabled", True) and not self.owner_view._remote_busy)
        self.btn_detect.set_label('รีเฟรชเครื่องนี้' if caps['local'] else 'ทดสอบ TCP' if dev['type'] == 'service' else 'ตรวจสอบเครื่อง')
        title = evidence.identity_label(dev)
        self.lbl_name.set_text(title)
        self.lbl_name.set_tooltip_text(title)
        self.lbl_role.set_text(dev.get("device_role") or "Configured device")
        address = str(dev.get('configured_ip') or 'Not configured')
        if dev.get('port') is not None:
            address += f":{dev['port']}"
        self.v_cfg_ip.set_text(address)
        self.v_cfg_ip.set_tooltip_text(address)
        observed = str(dev.get("observed_ip") or "Not observed")
        self.v_obs_ip.set_text(observed)
        self.v_obs_ip.set_tooltip_text(observed)
        self.lbl_badge.set_text({"OBSERVED_LOCAL": "LOCAL", "OBSERVED_REMOTE": "REMOTE", "VERIFIED_OPCUA": "OPC UA", "SYNTHETIC_DEMO": "DEMO"}.get(source, source))
        self.lbl_badge.set_tooltip_text(source)

        identity = evidence.evidence_state(dev, "identity")
        id_text = "ID verified" if identity in (evidence.Provenance.LOCAL, evidence.Provenance.REMOTE) and dev.get("identity_status") == "VERIFIED" else "ID alias" if dev.get("alias") else "ID ?"
        self.pill_id.set_text(id_text)
        self.pill_ping.set_text("Host OS" if kind == "local" and evidence.fresh(dev, kind) else "Ping ✓" if evidence.fresh(dev, kind) and dev.get("ping_ok") else "Ping ?")
        self.pill_port.set_text("TCP ✓" if evidence.fresh(dev, "tcp") and dev.get("tcp_ok") else "TCP ?")
        session = evidence.session_connected(dev)
        self.pill_opc.set_visible(caps['opcua'])
        self.pill_opc.set_text('UA ' + evidence.session_label(dev))
        self.pill_opc.set_tooltip_text(f"Session: {evidence.session_label(dev)} • Last read: {dev.get('last_read_quality') or 'UNKNOWN'}")
        for label, accent in ((self.lbl_badge, 'f3-pill-cyan' if source in ('OBSERVED_LOCAL', 'VERIFIED_OPCUA') else 'f3-pill-amber' if source in ('STALE', 'SYNTHETIC_DEMO') else 'f3-pill-neutral'),
                              (self.pill_ping, 'f3-pill-cyan' if kind == 'local' and evidence.fresh(dev, kind) else 'f3-pill-green' if evidence.fresh(dev, kind) and dev.get('ping_ok') else 'f3-pill-neutral'),
                              (self.pill_port, 'f3-pill-cyan' if evidence.fresh(dev, 'tcp') and dev.get('tcp_ok') else 'f3-pill-neutral'),
                              (self.pill_opc, 'f3-pill-purple' if session else 'f3-pill-neutral'),
                              (self.pill_id, 'f3-pill-neutral')):
            for name in ('neutral', 'green', 'amber', 'red', 'purple', 'cyan'):
                label.remove_css_class('f3-pill-' + name)
            label.add_css_class(accent)


# =============================================================================
# 10. Unified F3 Live Network Topology & Diagnostics View
# =============================================================================

class F3NetworkTopologyView:
    """
    Main F3 View integrated with AquaWinCCWindow:
      - Top Status Bar (Summary counters, Mode Switcher)
      - Interactive Network Diagram with Animated Connections (Cairo Canvas)
      - Device Detail Inspector in a separate owned native window
      - Device Cards Grid on the bottom
      - Stable public view/store/selection APIs with explicit evidence rules
    """
    def __init__(self, owner):
        ensure_f3_live_css()
        self.owner = owner

        # Configuration file for persistence
        cfg_dir = getattr(owner, 'config_dir', None)
        if not cfg_dir:
            cfg_dir = Path.home() / '.config' / 'aqua-command'
        self.store = F3DeviceStore(config_file=Path(cfg_dir) / 'network_topology.json')

        self.local_state = {"interfaces": {}, "ip_forwarding": None}
        self.runtime = RuntimeEvidence()
        self.secure_opcua = SecureF3OpcUa(getattr(owner, 'opcua_mapper', None),
                                        getattr(owner, 'pki', None), Path(cfg_dir))
        self._remote_busy = False
        self._cancel_event = threading.Event()
        self._remote_device = None
        self._local_pending = False
        self._local_requested_at = 0.0
        self._runtime_pending = False
        self._runtime_requested_at = 0.0
        self._last_remote_at = 0.0
        self.selected_device_id = next((d['device_id'] for d in self.store.devices.values() if d['type'] == 'local_host'), next(iter(self.store.devices), None))
        self.cards = DeviceDictionary()
        self.diagram_inventory = []
        self.source_page = 0
        self._source_anchor = None
        self.page_info = {}
        self.btn_cards_view = Gtk.CheckButton()
        self.btn_topology_view = Gtk.CheckButton()
        self.btn_table_view = Gtk.CheckButton()

        # Backward compatibility attributes
        self.topology_data = getattr(owner, 'topology_data', {})
        self.diag_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        self.ip_grid = Gtk.Grid(column_spacing=1, row_spacing=1)

        # Root Box
        self.root_widget = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
        self.root_widget.add_css_class('f3-root-box')
        self._observer_source = None
        self._observer_generation = 0
        self.root_widget.connect('map', self._on_observer_map)
        self.root_widget.connect('unmap', self._on_observer_unmap)

        self._build_top_status_bar()
        self._build_main_layout()
        if self.selected_device_id:
            self.inspector.inspect_device(self.selected_device_id)

        # Connect store changes to view updates
        self.store.add_listener(self._on_store_changed)

        # Update PC4 from real local host OS
        self.refresh_local_state()

    def _build_top_status_bar(self):
        header = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        header.add_css_class('f3-top-bar')
        self.root_widget.append(header)
        title_bar = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
        header.append(title_bar)
        bar = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        bar.set_homogeneous(True)
        header.append(bar)

        # Title
        t_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=1)
        t_box.set_hexpand(True)
        title_bar.append(t_box)

        lbl_t = Gtk.Label(label="F3 · เครือข่ายและอุปกรณ์")
        lbl_t.add_css_class('f3-title-text')
        lbl_t.set_xalign(0.0)
        lbl_t.set_ellipsize(Pango.EllipsizeMode.END)
        t_box.append(lbl_t)

        lbl_sub = Gtk.Label(label="Read only · ตรวจแยก LAN / TCP / Certificate / Session / Read")
        lbl_sub.add_css_class('f3-subtitle-text')
        lbl_sub.set_xalign(0.0)
        lbl_sub.set_ellipsize(Pango.EllipsizeMode.END)
        t_box.append(lbl_sub)

        # Real-time Stats Cluster
        self.lbl_stat_cfg = Gtk.Label(label="Configured: 0")
        self.lbl_stat_cfg.add_css_class('f3-stat-pill')
        self.lbl_stat_cfg.add_css_class('f3-pill-neutral')
        bar.append(self.lbl_stat_cfg)

        self.lbl_stat_det = Gtk.Label(label="Detected: 0")
        self.lbl_stat_det.add_css_class('f3-stat-pill')
        self.lbl_stat_det.add_css_class('f3-pill-green')
        bar.append(self.lbl_stat_det)

        self.lbl_stat_remote = Gtk.Label(label='Remote hosts  0')
        self.lbl_stat_remote.add_css_class('f3-stat-pill')
        self.lbl_stat_remote.add_css_class('f3-pill-neutral')
        bar.append(self.lbl_stat_remote)

        self.lbl_stat_scada = Gtk.Label(label="SCADA: Standby")
        self.lbl_stat_scada.add_css_class('f3-stat-pill')
        self.lbl_stat_scada.add_css_class('f3-pill-amber')

        self.lbl_stat_wan = Gtk.Label(label="WAN: Not Verified")
        self.lbl_stat_wan.add_css_class('f3-stat-pill')
        self.lbl_stat_wan.add_css_class('f3-pill-neutral')

        self.lbl_stat_opc = Gtk.Label(label="OPC UA: 0 Connected")
        self.lbl_stat_opc.add_css_class('f3-stat-pill')
        self.lbl_stat_opc.add_css_class('f3-pill-purple')
        bar.append(self.lbl_stat_opc)

        self.lbl_readonly = Gtk.Label(label="READ ONLY")
        self.lbl_readonly.add_css_class('f3-stat-pill')
        self.lbl_readonly.add_css_class('f3-pill-neutral')
        bar.append(self.lbl_readonly)
        self.lbl_updated = Gtk.Label(label='Updated  UNKNOWN')
        self.lbl_updated.add_css_class('f3-stat-pill')
        self.lbl_updated.add_css_class('f3-pill-neutral')
        bar.append(self.lbl_updated)
        role_strip = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=12)
        header.append(role_strip)
        self.lbl_local_nic = Gtk.Label(label='Local NIC  UNKNOWN')
        self.lbl_local_nic.set_hexpand(True)
        self.lbl_local_nic.set_xalign(0)
        self.lbl_local_nic.set_ellipsize(Pango.EllipsizeMode.END)
        role_strip.append(self.lbl_local_nic)
        role_strip.append(self.lbl_stat_scada)
        role_strip.append(self.lbl_stat_wan)

        # Mode Switcher Toggle Button: DEMO vs LIVE READ-ONLY
        self.btn_mode = Gtk.Button(label="LIVE · Read only")
        self.btn_mode.set_tooltip_text("สลับโหมดจริง / สาธิต • ไม่เริ่มตรวจสอบหรืออ่านข้อมูลอัตโนมัติ")
        self.btn_mode.add_css_class('btn-mode-live')
        self.btn_mode.connect('clicked', self._on_mode_toggle)
        title_bar.append(self.btn_mode)

        # Add Device Button
        btn_add = Gtk.Button(label="＋ เพิ่มอุปกรณ์")
        btn_add.connect('clicked', self._on_add_device_clicked)
        title_bar.append(btn_add)

        # Refresh Local Host Button
        btn_refresh = Gtk.Button(label="รีเฟรชเครื่องนี้")
        btn_refresh.connect('clicked', lambda _: self.refresh_local_state())
        title_bar.append(btn_refresh)

        # Inspector Toggle Button
        self.btn_toggle_insp = Gtk.Button(label="รายละเอียดอุปกรณ์")
        self.btn_toggle_insp.connect('clicked', lambda _: self.toggle_inspector(True))
        title_bar.append(self.btn_toggle_insp)
        for metric in (self.lbl_stat_cfg, self.lbl_stat_det, self.lbl_stat_remote,
                       self.lbl_stat_opc, self.lbl_readonly, self.lbl_updated):
            metric.set_ellipsize(Pango.EllipsizeMode.END)
            metric.set_max_width_chars(20)

    def _build_main_layout(self):
        # Diagram and device list get separate full-height views.
        self.main_split = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        self.main_split.set_vexpand(True)
        self.root_widget.append(self.main_split)

        # Left / Center Container
        left_container = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        left_container.set_hexpand(True)
        left_container.set_vexpand(True)
        self.main_split.append(left_container)
        self.left_container = left_container

        # 1. Interactive Live Diagram Canvas
        self.stack = Gtk.Stack()
        self.stack.set_vexpand(True)
        self.stack.set_hhomogeneous(False)
        self.stack.set_vhomogeneous(False)
        switcher = Gtk.StackSwitcher()
        switcher.add_css_class('f3-view-tabs')
        switcher.set_stack(self.stack)
        left_container.append(switcher)
        pager = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        pager.set_margin_start(16)
        pager.set_margin_end(16)
        self.lbl_source_page = Gtk.Label()
        self.lbl_source_page.set_xalign(0.0)
        self.lbl_source_page.set_hexpand(True)
        self.lbl_source_page.add_css_class('f3-subtitle-text')
        pager.append(self.lbl_source_page)
        self.btn_prev_sources = Gtk.Button(label="← Sources")
        self.btn_next_sources = Gtk.Button(label="Sources →")
        self.btn_prev_sources.connect('clicked', lambda _: self._change_source_page(-1))
        self.btn_next_sources.connect('clicked', lambda _: self._change_source_page(1))
        pager.append(self.btn_prev_sources)
        pager.append(self.btn_next_sources)
        left_container.append(pager)
        self.source_pager = pager
        page_scroll = Gtk.ScrolledWindow()
        page_scroll.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        page_scroll.set_vexpand(True)
        page_scroll.set_child(self.stack)
        left_container.append(page_scroll)
        self.canvas = F3LiveDiagramCanvas(self)
        self.stack.add_titled(self.canvas, 'topology', 'ผังการเชื่อมต่อ')

        # 2. Lower Cards Container in ScrolledWindow
        cards_scroll = Gtk.ScrolledWindow()
        cards_scroll.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        cards_scroll.set_vexpand(True)

        self.cards_grid = Gtk.Grid(column_spacing=8, row_spacing=8)
        self.cards_grid.set_column_homogeneous(True)
        self.cards_grid.set_row_homogeneous(True)
        self.cards_grid.set_valign(Gtk.Align.START)
        self.cards_grid.set_margin_start(10)
        self.cards_grid.set_margin_end(10)
        self.cards_grid.set_margin_top(6)
        self.cards_grid.set_margin_bottom(6)
        cards_scroll.set_child(self.cards_grid)
        self.stack.add_titled(cards_scroll, 'cards', 'รายการอุปกรณ์')

        # One docked Inspector; only its property list scrolls vertically.
        self.inspector = DeviceDetailInspector(self)
        self.inspector.set_hexpand(False)
        self.inspector.set_visible(True)
        self.main_split.append(self.inspector)
        self.inspector.btn_close.set_visible(False)
        self.details_window = None

        # The legacy table remains available to existing callers.
        self.stack.add_named(self.ip_grid, 'table')
        self.guide = Gtk.Label(label="ผังเส้นทางเชิงตรรกะ · คลิกอุปกรณ์เพื่อเปิด Inspector · ประวัติในเครื่องยังไม่ยืนยันต้นทางหรือการส่งจริง")
        self.guide.add_css_class('f3-guide')
        self.guide.set_wrap(True)
        self.guide.set_xalign(0.0)
        left_container.append(self.guide)
        self.stack.connect('notify::visible-child-name', self._on_view_changed)

        self._populate_cards()

    def _on_view_changed(self, *_):
        self.source_pager.set_visible(self.stack.get_visible_child_name() == 'topology')
        if self.stack.get_visible_child_name() == 'cards':
            self.guide.set_text("กดตรวจสอบเครื่องหรือรายละเอียด  ·  เลื่อนลงเพื่อดูอุปกรณ์ที่เหลือ  ·  การตรวจเครือข่ายต้องยืนยันก่อนทุกครั้ง")
        else:
            self.guide.set_text("ผังเส้นทางเชิงตรรกะ · คลิกอุปกรณ์เพื่อเปิด Inspector · ประวัติในเครื่องยังไม่ยืนยันต้นทางหรือการส่งจริง")

    def _populate_cards(self):
        while self.cards_grid.get_first_child():
            self.cards_grid.remove(self.cards_grid.get_first_child())
        self.cards = DeviceDictionary()
        self._update_diagram_layout()
        self._card_columns = max(2, min(4, self.left_container.get_width() // 300))

        # Two columns leave room for complete addresses and readable controls.
        col_idx = 0
        row_idx = 0
        for dev_id, dev in self.store.devices.items():
            card = F3DeviceCard(self, dev)
            self.cards[dev["device_id"]] = card
            if card is self.cards.get(self.selected_device_id):
                card.add_css_class('f3-card-selected')
            self.cards_grid.attach(card, col_idx, row_idx, 1, 1)
            col_idx += 1
            if col_idx >= self._card_columns:
                col_idx = 0
                row_idx += 1

        self._update_status_bar()

    def _update_diagram_layout(self):
        viewport = self.canvas.get_ancestor(Gtk.ScrolledWindow)
        height = max(viewport.get_height() if viewport else 0, 340)
        width = max(self.canvas.get_width(), 600)
        self.diagram_inventory, self.page_info = page_inventory(list(self.store.devices.values()), height, self.source_page, width)
        info = self.page_info
        if self._source_anchor in info["source_ids"]:
            page = info["source_ids"].index(self._source_anchor) // info["capacity"]
            if page != info["page"] % info['source_pages']:
                self.diagram_inventory, info = page_inventory(list(self.store.devices.values()), height, page, width)
                self.page_info = info
        elif self._source_anchor in info['infra_pages']:
            page = info['infra_pages'][self._source_anchor]
            if page != info['page']:
                self.diagram_inventory, info = page_inventory(list(self.store.devices.values()), height, page, width)
                self.page_info = info
        elif info["total"]:
            self._source_anchor = info["source_ids"][info["start"] - 1]
        self.source_page = info["page"]
        self.lbl_source_page.set_text(f"Sources {info['start']}–{info['end']} / {info['total']} · หน้า {info['page'] + 1}/{info['pages']} · ทุกอุปกรณ์อยู่ในรายการการ์ด")
        self.btn_prev_sources.set_sensitive(info['page'] > 0)
        self.btn_next_sources.set_sensitive(info['page'] + 1 < info['pages'])
        geometry = flow_layout(self.diagram_inventory, width, height)
        self.canvas.set_content_height(geometry["height"])

    def _change_source_page(self, delta):
        self.source_page += delta
        self._source_anchor = None
        self._update_diagram_layout()
        viewport = self.canvas.get_ancestor(Gtk.ScrolledWindow)
        if viewport:
            viewport.get_vadjustment().set_value(0)
        self.canvas.queue_draw()

    def _on_store_changed(self):
        self._bind_local_devices()
        for device in self.store.devices.values():
            device['binding_status'], device['binding_reason'] = evidence.network_binding(device, self.local_state, self.store.networks)
        if self._remote_busy and self._remote_device is not None and not self._device_is_current(self._remote_device):
            self._cancel_event.set()
        self._update_diagram_layout()
        card_ids = {d["device_id"] for d in self.store.devices.values()}
        if set(self.cards) != card_ids:
            self._populate_cards()
        for dev_id, dev in self.store.devices.items():
            if dev_id in self.cards:
                self.cards[dev_id].update_view(dev)
        if self.selected_device_id:
            if self.selected_device_id in self.store.devices:
                self.inspector.inspect_device(self.selected_device_id)
                if self.details_window is not None:
                    self.details_window.set_title(f"รายละเอียดอุปกรณ์ — {self.inspector.lbl_disp_name.get_text()}")
            else:
                self.selected_device_id = None
                self.inspector.current_device_id = None
                self.toggle_inspector(False)
        self.render_ip_summary_table()
        self.canvas.queue_draw()
        self._update_status_bar()

    def _update_status_bar(self):
        stats = self.store.get_summary_stats()
        self.lbl_stat_cfg.set_text(f"Configured  {stats['total_configured']}")
        local_count = stats['observed_local_interfaces']
        self.lbl_stat_det.set_text(f"Local IF  {local_count if local_count is not None else stats['local_observation_state']}")
        self.lbl_stat_det.set_tooltip_text('Passive local interfaces/devices reported by kernel and NetworkManager, including virtual/P2P devices; not a physical NIC or remote host count')
        self.lbl_stat_remote.set_text(f"Remote hosts  {stats['verified_remote_hosts']}")
        self.lbl_stat_remote.set_tooltip_text('Fresh authorized reachability observations; excludes this host and external services')
        self.lbl_stat_opc.set_text(f"UA sessions  {stats['opc_connected']}")
        self.lbl_stat_opc.set_tooltip_text('Open F3 manual sessions plus the existing local poller with a fresh, mapped, endpoint-matched CONNECTED DataValue receipt; RUNNING alone does not count')
        self.lbl_readonly.set_text(f"Read receipts  {stats['opc_read_verified']}")
        self.lbl_readonly.set_tooltip_text("Last F3 receipts per device + distinct existing backend DataValue receipts within 15 seconds; Quality, NodeId and timestamps remain separate. Poll counters never count.")
        for label, count, accent in ((self.lbl_stat_opc, stats['opc_connected'], 'purple'),
                                     (self.lbl_readonly, stats['opc_read_verified'], 'cyan')):
            for name in ('neutral', 'purple', 'cyan'):
                label.remove_css_class('f3-pill-' + name)
            label.add_css_class('f3-pill-' + (accent if count else 'neutral'))
        checked = self.local_state.get('observed_at')
        self.lbl_updated.set_text('Updated  ' + (datetime.fromtimestamp(checked).strftime('%H:%M:%S') if isinstance(checked, (int, float)) else 'UNKNOWN'))
        self.lbl_updated.set_tooltip_text(self.local_state.get('timestamp') or 'No local observation')
        active = self.local_state.get('active_interface') or self.local_state.get('default_gw_iface')
        item = self.local_state.get('interfaces', {}).get(active, {})
        nic = f"{active or 'UNKNOWN'} · {item.get('interface_type', 'UNKNOWN')} · {item.get('ipv4') or 'IPv4 UNKNOWN'} · {item.get('connection_state', 'UNKNOWN')}"
        self.lbl_local_nic.set_text(nic + ' · ' + stats['local_observation_state'])
        self.lbl_local_nic.set_tooltip_text(nic + '\nGateway: ' + str(self.local_state.get('default_gateway') or 'UNKNOWN') + '\n' + ', '.join(self.local_state.get('errors', [])))
        for zone, label, prefix in (("SCADA_OT", self.lbl_stat_scada, "OT"), ("EXTERNAL_WAN", self.lbl_stat_wan, "WAN")):
            definitions = [d for d in self.store.devices.values() if d.get("network_zone") == zone]
            bindings = [evidence.network_binding(d, self.local_state, self.store.networks) for d in definitions]
            state = "MISMATCH" if any(b[0] == "CONFIGURATION MISMATCH" for b in bindings) else "CONFIGURED" if bindings and all(b[0] == "CONFIGURED" for b in bindings) else "UNVERIFIED"
            label.set_text(f"{prefix}  {state}")
            label.set_tooltip_text("\n".join(b[1] for b in bindings) or "ยังไม่ได้กำหนด interface role")
            for color in ('green', 'amber', 'neutral'):
                label.remove_css_class('f3-pill-' + color)
            label.add_css_class('f3-pill-amber' if state == 'MISMATCH' else 'f3-pill-neutral')
        self.lbl_stat_det.remove_css_class('f3-pill-green')
        self.lbl_stat_det.add_css_class('f3-pill-neutral')
        self.lbl_stat_cfg.set_tooltip_text(self.store.last_error or "CONFIGURED: inventory only, not a runtime observation")

    def _on_mode_toggle(self, _):
        self._cancel_event.set()
        self.runtime = RuntimeEvidence()
        self.source_page = 0
        self._source_anchor = None
        self.store.set_demo(not self.store.is_demo_mode)
        self.selected_device_id = next(iter(self.store.devices), None)
        self.toggle_inspector(False)
        self.btn_mode.set_label("DEMO · Synthetic" if self.store.is_demo_mode else "LIVE · Read only")
        for name in ('btn-mode-demo', 'btn-mode-live'):
            self.btn_mode.remove_css_class(name)
        self.btn_mode.add_css_class('btn-mode-demo' if self.store.is_demo_mode else 'btn-mode-live')
        self._populate_cards()
        if not self.store.is_demo_mode:
            self.refresh_local_state()

    def _on_add_device_clicked(self, _):
        wincc_count = 1
        while f"dev-scada-{wincc_count:02d}" in self.store.devices:
            wincc_count += 1
        new_id = f"dev-scada-{wincc_count:02d}"
        new_dev = {
            "device_id": new_id,
            "id": new_id,
            "hostname": None,
            "alias": "",
            "identity_status": IdentityStatus.UNKNOWN,
            "identity_source": IdentitySource.UNVERIFIED,
            "identity_verified_at": None,
            "device_role": f"สถานีสูบน้ำเพิ่มเติม #{wincc_count}",
            "network_zone": "UNASSIGNED",
            "type": "wincc",
            "icon": "🖥️",
            "configured_ip": "",
            "observed_ip": None,
            "port": None,
            "endpoint_url": "",
            "enabled": True,
            "test_tag": ""
        }
        self.store.add_device(new_dev)
        self._populate_cards()
        self.select_device(new_id)

    def select_device(self, dev_id: str):
        device = self.store.devices.get(dev_id)
        if device is None:
            return
        self.selected_device_id = dev_id
        self._source_anchor = device["device_id"]
        self._update_diagram_layout()
        selected_card = self.cards.get(dev_id)
        for card_id, card in self.cards.items():
            if card is selected_card:
                card.add_css_class('f3-card-selected')
            else:
                card.remove_css_class('f3-card-selected')

        self.inspector.inspect_device(dev_id)
        self.toggle_inspector(True)
        self.canvas.queue_draw()

    def toggle_inspector(self, show: Optional[bool] = None):
        if show is None:
            show = not self.inspector.get_visible()
        self.inspector.set_visible(show)

    def _on_details_parent_closed(self, *_):
        self.toggle_inspector(False)
        return False

    def _on_details_close(self, *_):
        self.toggle_inspector(False)
        return True

    def trigger_device_detect(self, dev_id: str):
        dev = self.store.devices.get(dev_id)
        if not dev or not dev.get("enabled", True):
            return

        # For PC4: Local Host OS read
        if dev.get("type") == "local_host":
            self.refresh_local_state()
            return

        if not evidence.capabilities(dev)['network']:
            return

        self._request_remote_action(dev, self._execute_detection)

    def _device_is_current(self, dev):
        return self.store.devices.get(dev["id"]) is dev and dev.get("enabled", True)

    def _request_remote_action(self, dev, action):
        if self._remote_busy:
            return
        is_demo = self.store.is_demo_mode

        def run_authorized():
            if self._device_is_current(dev) and self.store.is_demo_mode == is_demo:
                action(dev)

        # All remote actions share the existing manual authorization gate.
        if not self.store.is_demo_mode:
            dlg = OTAuthorizationDialog(
                parent_win=self.root_widget.get_root() if isinstance(self.root_widget.get_root(), Gtk.Window) else self.owner,
                device_name=evidence.identity_label(dev),
                device_ip=dev.get("endpoint_url", "") if action != self._execute_detection else dev.get("configured_ip", ""),
                on_authorized=run_authorized
            )
            dlg.present()
        else:
            run_authorized()

    def _execute_detection(self, dev: Dict[str, Any]):
        if not evidence.capabilities(dev)['network']:
            return
        token = self._begin_remote(dev)
        if token is None:
            return
        mode = self.store.is_demo_mode
        cancel = self._cancel_event
        dev["reachability"] = "CHECKING"
        self.store.notify()

        def on_done(res):
            if self._remote_busy is not token:
                return GLib.SOURCE_REMOVE
            self._remote_busy = False
            if cancel.is_set() or res.get('cancelled') or not self._device_is_current(dev) or mode != self.store.is_demo_mode:
                if self._device_is_current(dev):
                    dev['reachability'] = 'CANCELLED'
                self.store.notify()
                return GLib.SOURCE_REMOVE
            dev["reachability"] = res["reachability"]
            dev["ping_ok"] = res["ping_ok"]
            dev["ping_rtt"] = res["ping_rtt"]
            dev["tcp_ok"] = res["tcp_ok"]
            dev["tcp_status"] = res["tcp_status"]
            dev["tcp_rtt"] = res["tcp_rtt"]
            dev["observed_ip"] = res["observed_ip"]
            dev['network_error'] = res.get('error')
            dev["last_verified_time"] = res["timestamp"]
            dev["detection_source"] = f"Probe ({res['timestamp']})" if not self.store.is_demo_mode else "Demo Loopback"
            source = evidence.Provenance.DEMO if mode else evidence.Provenance.REMOTE
            if res.get('ping_ok') is not None or res.get('tcp_ok') is not None:
                evidence.record_evidence(dev, "reachability", source)
            else:
                dev.get('evidence', {}).pop('reachability', None)
            if res.get("tcp_ok") is not None:
                evidence.record_evidence(dev, "tcp", source)
            else:
                dev.get('evidence', {}).pop('tcp', None)

            # DNS PTR Hostname Resolution check (Passive unicast, marked UNVERIFIED)
            dns_ptr = res.get("dns_ptr_hostname")
            if dns_ptr and dev.get("identity_status") != IdentityStatus.VERIFIED:
                dev["hostname"] = dns_ptr
                dev["identity_source"] = IdentitySource.DNS_PTR
                dev["identity_status"] = IdentityStatus.UNVERIFIED
                dev["identity_verified_at"] = datetime.now().isoformat()

            # History entry
            dev.setdefault("history", []).append({
                "time": res["timestamp"],
                "type": "Network Probe",
                "result": f"{res['reachability']} | {res['tcp_status']}"
            })
            self.store.notify()

        RealDetectionEngine.detect_device_network(dict(dev), mode, on_done, cancel=cancel)

    def trigger_device_opcua_test(self, dev_id: str):
        dev = self.store.devices.get(dev_id)
        if not dev or not evidence.capabilities(dev)['opcua'] or not dev.get("enabled", True):
            return

        self._request_remote_action(dev, self._execute_opcua_test)

    def _execute_opcua_test(self, dev):
        self._execute_secure_action(dev, read=False)

    def trigger_device_read_once(self, dev_id: str):
        dev = self.store.devices.get(dev_id)
        if not dev or not evidence.capabilities(dev)['opcua'] or not dev.get("enabled", True):
            return

        self._request_remote_action(dev, self._execute_read_once)

    def _execute_read_once(self, dev):
        self._execute_secure_action(dev, read=True)

    def _opcua_options(self, dev):
        config = getattr(self.owner, 'opcua_config', {})
        options = {"sec_policy": dev.get("sec_policy"), "auth_mode": dev.get("auth_mode", "Anonymous")}
        if dev.get("endpoint_url") and config.get("endpoint_url") == dev["endpoint_url"]:
            options.update(sec_policy=dev.get("sec_policy") or config.get("security_policy"),
                           auth_mode=dev.get("auth_mode") or config.get("auth_mode", "Anonymous"),
                           username=config.get("username", ""),
                           password=getattr(self.owner, 'opcua_session_password', ""))
        return options

    def _begin_remote(self, dev):
        if self._remote_busy or time.monotonic() - self._last_remote_at < 0.5:
            return None
        token = object()
        self._remote_busy = token
        self._cancel_event = threading.Event()
        self._remote_device = dev
        self._last_remote_at = time.monotonic()
        self.runtime.clear_source(dev["device_id"])
        return token

    def cancel_remote_action(self):
        if self._remote_busy:
            self._cancel_event.set()
            self.store.notify()

    def _execute_secure_action(self, dev, *, read):
        if not evidence.capabilities(dev)['opcua']:
            return
        token = self._begin_remote(dev)
        if token is None:
            return
        mode = self.store.is_demo_mode
        cancel = self._cancel_event
        target, options = dict(dev), self._opcua_options(dev)
        dev["opcua_state"] = "CHECKING"
        dev["read_success"] = False if read else dev.get("read_success", False)
        self.store.notify()

        def opened(result):
            def apply_open():
                if not cancel.is_set() and self._remote_busy is token and self._device_is_current(dev) and mode == self.store.is_demo_mode:
                    dev.update(result)
                    evidence.record_evidence(dev, "session", evidence.Provenance.OPCUA)
                    self.store.notify()
                return GLib.SOURCE_REMOVE
            GLib.idle_add(apply_open)

        def worker():
            try:
                if mode:
                    result = {"opcua_state": "SYNTHETIC_DEMO", "session_state": "DISCONNECTED",
                          "certificate_trust": "SYNTHETIC_DEMO", "session_verified": True,
                          "read_success": read, "value": 42.5 if read else None,
                              "quality": "SYNTHETIC_DEMO", "timestamp": datetime.now().isoformat()}
                else:
                    result = self.secure_opcua.read_sync(target, options) if read else self.secure_opcua.probe_sync(target, options, opened)
            except Exception as error:
                result = self.secure_opcua.result()
                self.secure_opcua.failure(result, error, options.get("password", ""))
            GLib.idle_add(done, result)

        def done(result):
            if self._remote_busy is not token:
                return GLib.SOURCE_REMOVE
            self._remote_busy = False
            if cancel.is_set() or not self._device_is_current(dev) or mode != self.store.is_demo_mode:
                if self._device_is_current(dev):
                    dev.update(opcua_state='CANCELLED', session_state='DISCONNECTED', read_success=False)
                self.store.notify()
                return GLib.SOURCE_REMOVE
            dev.update(result)
            dev["opcua_security_status"] = result.get("security_status", "NOT_TESTED")
            dev["session_state"] = "DISCONNECTED"
            dev["last_verified_time"] = result.get("timestamp", "—")
            source = evidence.Provenance.DEMO if mode else evidence.Provenance.OPCUA
            if result.get("certificate_trust") not in (None, "NOT_TESTED"):
                evidence.record_evidence(dev, "certificate", source)
            if result.get("session_verified"):
                evidence.record_evidence(dev, "session", source)
            if read:
                dev.update(last_read_value=result.get("value"), last_read_quality=result.get("quality"),
                           last_read_time=result.get("timestamp"), last_read_tag=target.get("test_tag"))
                if result.get("read_success"):
                    dev["last_successful_read"] = result.get("timestamp")
                    evidence.record_evidence(dev, "read", source)
            # Short manual sessions have already closed: no ongoing traffic pulse.
            self.runtime.clear_source(dev["device_id"])
            dev.setdefault("history", []).append({"time": result.get("timestamp", "—"),
                "type": "Manual read" if read else "Secure session test",
                "result": f"{result.get('opcua_state')} · {result.get('quality', 'No tag read')} · session closed"})
            dev["history"] = dev["history"][-50:]
            self.store.notify()
            return GLib.SOURCE_REMOVE

        threading.Thread(target=worker, daemon=True).start()

    # -------------------------------------------------------------------------
    # Safe Local Host OS Refresh (Zero Network Probe)
    # -------------------------------------------------------------------------
    def refresh_local_state(self):
        """Observe this host only. Interface roles require explicit configuration."""
        if self._local_pending or self.store.is_demo_mode:
            return
        self._local_pending = True
        self._local_requested_at = time.monotonic()
        inventory = self.store.devices

        def worker():
            try:
                state = safe_get_local_network_state()
            except Exception:
                # Every completion releases the single-flight guard, including API failures.
                state = {'interfaces': {}, 'state': 'UNKNOWN', 'errors': ['LOCAL_API_UNAVAILABLE']}
            GLib.idle_add(done, state)

        def done(state):
            self._local_pending = False
            if self.store.devices is inventory and not self.store.is_demo_mode:
                self._apply_local_state(state)
            return GLib.SOURCE_REMOVE

        threading.Thread(target=worker, daemon=True).start()

    def _apply_local_state(self, state):
        self.local_state = state
        self.store.local_observation = state
        self._bind_local_devices()
        self.store.last_verified_ts = self.local_state.get("timestamp")
        self.store.notify()
        badge = getattr(self.owner, 'update_local_nic_badge', None)
        if callable(badge):
            badge(None)
        self.canvas.queue_draw()
        self.render_ip_summary_table()
        self.render_diagnostics_view()

    def _bind_local_devices(self):
        # Rebind current in-memory facts after a settings edit, retaining the original snapshot time.
        state = self.local_state
        local_status = evidence.local_snapshot_state(state)
        checked = state.get('observed_at')
        for dev in self.store.devices.values():
            if dev.get("type") != "local_host":
                continue
            interfaces = self.local_state.get("interfaces", {})
            dev["interface_observations"] = interfaces
            dev["ip_forwarding"] = self.local_state.get("ip_forwarding")
            primary = dev.get('interface_name') or state.get('active_interface') or state.get('default_gw_iface')
            dev['observed_interface'] = primary
            dev['observed_ip'] = interfaces.get(primary, {}).get('ipv4')
            dev['observed_mac'] = interfaces.get(primary, {}).get('mac')
            dev["hostname"] = self.local_state.get("hostname") or get_local_hostname() or None
            dev["identity_status"] = IdentityStatus.VERIFIED if dev["hostname"] else IdentityStatus.UNKNOWN
            dev["identity_source"] = IdentitySource.LOCAL_OS
            dev['reachability'] = 'VERIFIED_LOCAL' if local_status == evidence.Provenance.LOCAL else local_status
            dev['last_error'] = ', '.join(state.get('errors', [])) or state.get('error')
            dev["link_status"] = "UNKNOWN"
            dev["wan_link_status"] = "UNKNOWN"
            for zone, key in (("SCADA_OT", "link_status"), ("EXTERNAL_WAN", "wan_link_status")):
                definition = self.store.networks.get(zone, {})
                assigned = definition.get("interface") if isinstance(definition, dict) else None
                carrier = interfaces.get(assigned, {}).get("carrier") if assigned else None
                if carrier is not None and local_status == evidence.Provenance.LOCAL:
                    dev[key] = "LOCAL_CARRIER_UP" if carrier else "LOCAL_CARRIER_DOWN"
            dev["last_verified_time"] = self.local_state.get("timestamp", "—")
            dev["detection_source"] = evidence.Provenance.LOCAL
            dev.setdefault('evidence', {}).pop('local', None)
            if isinstance(checked, (int, float)) and local_status != evidence.Provenance.UNKNOWN:
                evidence.record_evidence(dev, "local", evidence.Provenance.LOCAL, now=checked, detail="Passive Host OS snapshot")
            if dev["hostname"] and isinstance(checked, (int, float)):
                evidence.record_evidence(dev, "identity", evidence.Provenance.LOCAL, now=checked, detail="Host OS hostname")

    def _on_observer_map(self, *_):
        if self._observer_source is None:
            self._observe_runtime()
            self._observer_source = GLib.timeout_add_seconds(2, self._observe_runtime)

    def _on_observer_unmap(self, *_):
        self._cancel_event.set()
        self._observer_generation += 1
        if self._observer_source is not None:
            GLib.source_remove(self._observer_source)
            self._observer_source = None
        self.runtime.pulses.clear()
        self.runtime.baseline = None

    def _observe_runtime(self):
        """Schedule passive evidence collection; drawing never reads disk/network."""
        if self._runtime_pending or self.store.is_demo_mode:
            return GLib.SOURCE_CONTINUE
        if time.monotonic()-self._local_requested_at >= 10:
            self.refresh_local_state()
        self._runtime_pending = True
        inventory = self.store.devices
        generation = self._observer_generation
        db_path = getattr(getattr(self.owner, 'durable_storage', None), 'db_path', None)

        def worker():
            snapshot = read_snapshot(db_path)
            poller = getattr(self.owner, 'polling_engine', None)
            try:
                snapshot["polling"] = poller.get_telemetry() if poller else {"state": "UNAVAILABLE"}
                snapshot['polling_checked_at'] = time.time() if poller else None
                snapshot['client_endpoint'] = getattr(poller, 'endpoint_url', '')
            except Exception:
                snapshot["polling"] = {"state": "UNAVAILABLE"}
            snapshot['client_receipts'] = []
            try:
                shared = getattr(self.owner, 'opcua_store', None)
                mapper = getattr(self.owner, 'opcua_mapper', None)
                for observation in shared.snapshot_observations()[:2000] if shared and mapper else []:
                    if not mapper.is_allowed(observation.tag_name) or not observation.node_id or not observation.endpoint_url:
                        continue
                    arrived = observation.arrival_time
                    snapshot['client_receipts'].append({'tag_name': observation.tag_name, 'node_id': observation.node_id,
                        'endpoint_url': observation.endpoint_url, 'value': observation.value, 'quality': observation.quality,
                        'raw_status': observation.raw_status_name, 'session_state': observation.session_state,
                        'mapping_verified': True, 'arrival_epoch': arrived.timestamp() if arrived and arrived.tzinfo else None,
                        'arrival_timestamp': arrived.isoformat() if arrived else None,
                        'source_timestamp': observation.source_time.isoformat() if observation.source_time else None,
                        'server_timestamp': observation.server_time.isoformat() if observation.server_time else None})
            except Exception:
                snapshot['client_receipts'] = []
            GLib.idle_add(done, snapshot)

        def done(snapshot):
            self._runtime_pending = False
            if generation == self._observer_generation and self.store.devices is inventory and not self.store.is_demo_mode:
                self.runtime.accept(snapshot)
                self.store.runtime_observation = snapshot
                self._update_status_bar()
                self.canvas.queue_draw()
            return GLib.SOURCE_REMOVE

        threading.Thread(target=worker, daemon=True).start()
        return GLib.SOURCE_CONTINUE

    # -------------------------------------------------------------------------
    # Backward Compatibility Methods for Existing Acceptance Tests
    # -------------------------------------------------------------------------
    def tick_live(self):
        """Called periodically by app main loop timer to refresh live view."""
        if hasattr(self, 'canvas') and self.root_widget.get_mapped():
            if self._card_columns != max(2, min(4, self.left_container.get_width() // 300)):
                self._populate_cards()
            self._on_store_changed()
            self.canvas.queue_draw()

    def render_diagnostics_view(self):
        while self.diag_box.get_first_child():
            self.diag_box.remove(self.diag_box.get_first_child())
        lbl = Gtk.Label(label=f"Gateway: {self.local_state.get('default_gateway', 'None')}")
        self.diag_box.append(lbl)

    def render_ip_summary_table(self):
        while self.ip_grid.get_first_child():
            self.ip_grid.remove(self.ip_grid.get_first_child())

        headers = ["Device (Hostname / IP)", "Zone", "Interface / IP", "Identity Source", "Status", "Last Verified"]
        for col, h in enumerate(headers):
            th = Gtk.Label(label=h)
            th.add_css_class('table-th')
            th.set_xalign(0.0)
            self.ip_grid.attach(th, col, 0, 1, 1)

        for row_idx, (dev_id, dev) in enumerate(self.store.devices.items(), start=1):
            disp_name = evidence.identity_label(dev)
            lbl_dev = Gtk.Label(label=disp_name)
            lbl_dev.set_xalign(0.0)
            self.ip_grid.attach(lbl_dev, 0, row_idx, 1, 1)

            lbl_zone = Gtk.Label(label=dev.get("zone_desc", dev.get("network_zone", "—")))
            lbl_zone.set_xalign(0.0)
            self.ip_grid.attach(lbl_zone, 1, row_idx, 1, 1)

            cfg = dev.get("configured_ip", "—")
            obs = dev.get("observed_ip") or "UNKNOWN"
            lbl_ip = Gtk.Label(label=f"Config: {cfg} | Actual: {obs}")
            lbl_ip.set_xalign(0.0)
            self.ip_grid.attach(lbl_ip, 2, row_idx, 1, 1)

            lbl_src = Gtk.Label(label=dev.get("identity_source") or dev.get("detection_source", "Static"))
            lbl_src.set_xalign(0.0)
            self.ip_grid.attach(lbl_src, 3, row_idx, 1, 1)

            lbl_st = Gtk.Label(label=device_status_text(dev))
            lbl_st.set_xalign(0.0)
            self.ip_grid.attach(lbl_st, 4, row_idx, 1, 1)

            lbl_ver = Gtk.Label(label=dev.get("identity_verified_at") or dev.get("last_verified_time", "—"))
            lbl_ver.set_xalign(0.0)
            self.ip_grid.attach(lbl_ver, 5, row_idx, 1, 1)
