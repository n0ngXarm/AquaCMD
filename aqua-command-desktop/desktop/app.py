
def get_dynamic_plant_groups(scanned_tags):
    """Generates real plant groups dynamically from scanned WinCC tags (Zero Mock)."""
    groups_map = {}
    for t in scanned_tags:
        grp = t.get('group', 'Unassigned')
        if grp not in groups_map:
            groups_map[grp] = []
        groups_map[grp].append(t)

    # Defined plant areas from real WinCC project
    defined_sections = [
        ('High_VSD', '⚡ ปั๊มน้ำแรงดันสูง VSD (High_VSD — ปั๊ม Inverter CTM13PT ถึง CTM17PT)'),
        ('High1_PT1PT', '💧 เซนเซอร์วัดแรงดันน้ำ (High1_PT1PT)'),
        ('High_Analog', '📊 ระบบเครื่องวัดอนาล็อก (High_Analog — Pressure & Flow Transmitters)'),
        ('High_Valve', '🚪 ประตูน้ำและวาล์วไฟฟ้า (High_Valve — Motorized Valves & Penstocks)'),
        ('High_DPM', '⚡ มิเตอร์วัดกำลังไฟฟ้าดิจิทัล (High_DPM — Digital Power Meters)'),
    ]

    result = []
    for grp_key, title in defined_sections:
        tags_in_grp = groups_map.get(grp_key, [])
        if not tags_in_grp:
            continue

        # Extract distinct components
        items = []
        seen = set()
        for t in tags_in_grp:
            raw_name = t['name']
            base_id = raw_name.split('.')[0] if '.' in raw_name else raw_name
            if base_id not in seen:
                seen.add(base_id)
                items.append({
                    'id': base_id,
                    'tag_name': t['name'],
                    'addr': t.get('addr', 'Internal'),
                    'type': t.get('type', 'Real'),
                    'comment': t.get('comment', '') or t['name'],
                    'group': grp_key
                })
            if len(items) >= 6: # Show top 6 distinct equipment assets per group
                break

        result.append({
            'category': title,
            'total_tags': len(tags_in_grp),
            'items': items
        })

    return result


def format_duration(seconds):
    if seconds <= 0:
        return 'ครบกำหนด'
    h = int(seconds // 3600)
    m = int((seconds % 3600) // 60)
    s = int(seconds % 60)
    if h > 0:
        return f'{h} ชม. {m} นาที {s} วิ'
    elif m > 0:
        return f'{m} นาที {s} วิ'
    else:
        return f'{s} วินาที'

#!/usr/bin/env python3
"""
AQUA COMMAND — WinCC V8.1 Industrial SCADA & Task Management Workstation
Designed for Provincial Waterworks Authority, Chiang Mai (การประปาส่วนภูมิภาคสาขาเชียงใหม่)
Umong Water Production Station (สถานีผลิตน้ำอุโมงค์)

Features:
1. Full WinCC V8.1 Tag Scanner (Discovers all 457 tags from Export all.txt / WinCC projects)
2. Task Management (Operators configure custom tasks, cycle times, logging, and notifications)
3. Selective Execution (Only archives and dispatches alerts for active assigned tasks)
4. Clean 2D WinCC V8.1 SCADA layout (High legibility, no 3D canvas, industrial grey theme)
5. 100% Real Host Machine Diagnostics (/proc, loadavg, meminfo, disk, network LAN IP)
6. Rock-solid stability with safe background threads and GLib.idle_add
"""
import os
import sys
import time
import json
import math
import socket
import shutil
import platform
import subprocess
import threading
import concurrent.futures
import asyncio
try:
    from asyncua import Client, Server, ua
    HAS_ASYNCUA = True
except ImportError:
    HAS_ASYNCUA = False

try:
    from .opcua_mapping import NodeIdMapper
    from .opcua_store import ObservableStateStore, Quality
    from .opcua_reader import ManualOpcUaReader
    from .opcua_pki import PkiManager
    from .opcua_storage import DurableStorage, StoredObservation
    from .task_engine import TaskEngine
    from .notification_worker import NotificationWorker
    from .opcua_polling_engine import OpcUaPollingEngine, PollingState
except ImportError:
    from opcua_mapping import NodeIdMapper
    from opcua_store import ObservableStateStore, Quality
    from opcua_reader import ManualOpcUaReader
    from opcua_pki import PkiManager
    from opcua_storage import DurableStorage, StoredObservation
    from task_engine import TaskEngine
    from notification_worker import NotificationWorker
    from opcua_polling_engine import OpcUaPollingEngine, PollingState
import urllib.request
import urllib.error
from urllib.parse import urlparse
from datetime import datetime
from pathlib import Path

import gi
gi.require_version('Gtk', '4.0')
gi.require_version('Pango', '1.0')
gi.require_version('PangoCairo', '1.0')
from gi.repository import Gtk, Gdk, GLib, Pango, PangoCairo
import cairo

USE_UNIFIED_WORKSPACE = True

try:
    from .f1_overview import F1StationExplorerView
    from .f2_tasks import F2TaskManagerView
    from .f3_api_view import F3ApiView
    from .f3_evidence import local_snapshot_state
    from .workspace import AquaUnifiedWorkspaceView
except ImportError:
    from f1_overview import F1StationExplorerView
    from f2_tasks import F2TaskManagerView
    from f3_api_view import F3ApiView
    from f3_evidence import local_snapshot_state
    from workspace import AquaUnifiedWorkspaceView


# ---------------------------------------------------------
# Platform Abstraction & Crash-Resistant Storage (Linux & Windows 11)
# ---------------------------------------------------------
IS_WINDOWS = (sys.platform == 'win32')

if IS_WINDOWS:
    appdata = os.environ.get('APPDATA') or os.environ.get('LOCALAPPDATA')
    CONFIG_DIR = Path(appdata) / 'AquaCommand' if appdata else Path.home() / '.config' / 'aqua-command'
else:
    CONFIG_DIR = Path.home() / '.config' / 'aqua-command'

CONFIG_DIR.mkdir(parents=True, exist_ok=True)
TASKS_CONFIG_FILE = CONFIG_DIR / 'wincc_tasks.json'
TOPOLOGY_CONFIG_FILE = CONFIG_DIR / 'network_topology.json'
TELEGRAM_CONFIG_FILE = CONFIG_DIR / 'telegram_config.json'
OPCUA_CONFIG_FILE = CONFIG_DIR / 'opcua_config.json'

def save_atomic_json(filepath, data):
    """Crash-resistant atomic file save: writes to .tmp before replacing target."""
    p = Path(filepath)
    temp_p = p.with_suffix('.tmp')
    try:
        p.parent.mkdir(parents=True, exist_ok=True)
        with open(temp_p, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
            f.flush()
            os.fsync(f.fileno())
        temp_p.replace(p)
        return True
    except Exception as e:
        print(f"Error atomic saving {filepath}: {e}", file=sys.stderr)
        try:
            if temp_p.exists():
                temp_p.unlink()
        except Exception:
            pass
        return False

MAX_OPCUA_BROWSE_NODES = 500
MAX_OPCUA_BROWSE_DEPTH = 3
OPCUA_BROWSE_TIMEOUT = 5.0

def load_opcua_config():
    if OPCUA_CONFIG_FILE.exists():
        try:
            with open(OPCUA_CONFIG_FILE, 'r', encoding='utf-8') as f:
                data = json.load(f)
                data.pop('password', None)  # Safety: never retain password on disk
                return data
        except Exception:
            pass
    return {
        'endpoint_url': 'opc.tcp://192.168.1.11:4862',
        'security_policy': 'None',
        'auth_mode': 'Anonymous',
        'username': '',
        'status': 'disconnected'
    }

def validate_opcua_endpoint(url):
    """Validates OPC UA Endpoint URL format and scheme."""
    if not url or not isinstance(url, str):
        return False, "กรุณากรอก URL สำหรับเชื่อมต่อ OPC UA"
    url = url.strip()
    if not url.startswith("opc.tcp://"):
        return False, "URL ต้องขึ้นต้นด้วย Scheme 'opc.tcp://' เท่านั้น"
    parsed = urlparse(url)
    if not parsed.hostname:
        return False, "ไม่พบ Hostname หรือ IP Address ใน URL"
    try:
        port = parsed.port
    except ValueError:
        return False, "Port ไม่อยู่ในช่วงที่ถูกต้อง (1-65535)"
    if port is not None and not (1 <= port <= 65535):
        return False, f"Port {port} ไม่ถูกต้อง (ต้องอยู่ระหว่าง 1-65535)"
    return True, url

def save_opcua_config(cfg):
    clean_cfg = dict(cfg)
    clean_cfg.pop('password', None)  # Safety: never save plaintext password to disk
    return save_atomic_json(OPCUA_CONFIG_FILE, clean_cfg)

def load_telegram_config():
    if TELEGRAM_CONFIG_FILE.exists():
        try:
            with open(TELEGRAM_CONFIG_FILE, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception:
            pass
    return {
        'bot_token': '',
        'chat_id': '',
        'enabled': True
    }

def save_telegram_config(cfg):
    return save_atomic_json(TELEGRAM_CONFIG_FILE, cfg)

DEFAULT_TOPOLOGY = {
    "scada_lan": {
        "zone_name": "เครือข่ายภายใน SCADA (Isolated OT LAN)",
        "subtitle": "วงแลนภายในระบบ SCADA (192.168.1.0/24) | เครือข่าย OT แบบปิด",
        "has_internet": False,
        "subnet": "192.168.1.0/24",
        "netmask": "255.255.255.0",
        "gateway": "ไม่มี (Isolated Air-Gapped)",
        "switch": {
            "name": "LAN Switch",
            "sub1": "เครือข่ายภายใน",
            "sub2": "ไม่ใช่อินเทอร์เน็ต",
            "desc": "OT Switch 8-Port (192.168.1.254)",
            "ip": "192.168.1.254"
        },
        "devices": [
            {
                "id": "PC1",
                "name": "PC1 · SCADA",
                "internet_status": "ไม่มี Internet",
                "has_internet": False,
                "ip": "192.168.1.11",
                "mac": "00:1E:67:D8:11:A1",
                "role": "SCADA โหนด 1 (พอร์ต 4840)",
                "status": "CONFIGURED (Reachability UNKNOWN)",
                "ping": "—"
            },
            {
                "id": "PC2",
                "name": "PC2 · SCADA",
                "internet_status": "ไม่มี Internet",
                "has_internet": False,
                "ip": "192.168.1.12",
                "mac": "00:1E:67:D8:12:B2",
                "role": "SCADA โหนด 2 (พอร์ต 4840)",
                "status": "CONFIGURED (Reachability UNKNOWN)",
                "ping": "—"
            },
            {
                "id": "PC3",
                "name": "PC3 · SCADA",
                "internet_status": "ไม่มี Internet",
                "has_internet": False,
                "ip": "192.168.1.13",
                "mac": "00:1E:67:D8:13:C3",
                "role": "SCADA โหนด 3 (พอร์ต 4840)",
                "status": "CONFIGURED (Reachability UNKNOWN)",
                "ping": "—"
            }
        ]
    },
    "gateway_bridge": {
        "id": "PC4",
        "name": "PC4 · Collector (AQUA COMMAND — เครื่องนี้)",
        "internet_status": "UNKNOWN",
        "has_internet": False,
        "badge": "Dual-Homed Node (เชื่อมต่อ 2 เครือข่ายแบบแยกอิสระ)",
        "nic_scada": {
            "name": "ขาใน SCADA LAN",
            "iface": "enp0s31f6",
            "ip": "192.168.1.14",
            "netmask": "255.255.255.0",
            "target": "LAN Switch ภายใน"
        },
        "nic_wan": {
            "name": "ขานอก Router WAN",
            "iface": "wlp2s0",
            "ip": "192.168.100.177",
            "netmask": "255.255.255.0",
            "gateway": "192.168.100.1",
            "target": "Router Internet (TrueMove H LTE)"
        },
        "role": "รวบรวม Tag จาก LAN ภายใน ส่งแจ้งเตือนผ่าน Internet"
    },
    "internet_wan": {
        "zone_name": "เครือข่ายเราเตอร์ภายนอก (Internet Gateway WAN)",
        "subtitle": "เราเตอร์ 4G LTE TrueMove H (192.168.100.1) | SSID: Nong_Arm | พร้อมส่งข้อมูลออกภายนอก",
        "has_internet": False,
        "router": {
            "name": "Router Internet",
            "sub1": "TrueMove H 4G LTE Router",
            "gateway_ip": "192.168.100.1",
            "ssid": "Nong_Arm",
            "operator": "TrueMove H LTE",
            "netmask": "255.255.255.0",
            "dhcp": "เปิดใช้งาน (DHCP Enabled)",
            "status": "CONFIGURED (Reachability UNKNOWN)",
            "mac": "e8:49:43:21:33:5b"
        },
        "clients": [
            {
                "ip": "192.168.100.177",
                "mac": "ba:7a:37:fe:60:6a",
                "name": "PC4 · Collector (เครื่องประมวลผล AQUA COMMAND นี้)",
                "is_this_pc": True,
                "status": "CONFIGURED (Host)",
                "ping": "—"
            },
            {
                "ip": "192.168.100.135",
                "mac": "5e:86:55:78:8a:77",
                "name": "Client เครื่องลูกข่าย 1 (Unverified Client)",
                "is_this_pc": False,
                "status": "UNKNOWN (Unverified)",
                "ping": "—"
            },
            {
                "ip": "192.168.100.150",
                "mac": "f4:d1:08:56:83:bc",
                "name": "Client เครื่องลูกข่าย 2 (Unverified Client)",
                "is_this_pc": False,
                "status": "UNKNOWN (Unverified)",
                "ping": "—"
            },
            {
                "ip": "192.168.100.178",
                "mac": "50:2e:91:3f:77:30",
                "name": "Client เครื่องลูกข่าย 3 (Unverified Client)",
                "is_this_pc": False,
                "status": "UNKNOWN (Unverified)",
                "ping": "—"
            }
        ]
    }
}

def load_topology():
    if TOPOLOGY_CONFIG_FILE.exists():
        try:
            with open(TOPOLOGY_CONFIG_FILE, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception as e:
            print(f"Error loading topology: {e}", file=sys.stderr)
    return DEFAULT_TOPOLOGY

def save_topology(data):
    save_atomic_json(TOPOLOGY_CONFIG_FILE, data)

# ---------------------------------------------------------
# Cairo Drawing Helpers for Topology Canvas
# ---------------------------------------------------------
def draw_rounded_rect(cr, x, y, w, h, r):
    cr.new_sub_path()
    cr.arc(x + w - r, y + r, r, -math.pi/2, 0)
    cr.arc(x + w - r, y + h - r, r, 0, math.pi/2)
    cr.arc(x + r, y + h - r, r, math.pi/2, math.pi)
    cr.arc(x + r, y + r, r, math.pi, 3*math.pi/2)
    cr.close_path()

def draw_pango_text(cr, text, x, y, font_desc_str="Noto Sans Thai, Sans 10", color=(1.0, 1.0, 1.0)):
    layout = PangoCairo.create_layout(cr)
    desc = Pango.FontDescription.from_string(font_desc_str)
    layout.set_font_description(desc)
    layout.set_text(text)
    cr.set_source_rgb(*color)
    cr.move_to(x, y)
    PangoCairo.show_layout(cr, layout)

DEFAULT_WINCC_EXPORT = Path.home() / 'Downloads' / 'Export all.txt'
repo_export1 = Path(__file__).resolve().parent.parent / 'docs' / 'tags' / 'Export all.txt'
repo_export2 = Path(__file__).resolve().parent.parent.parent / 'docs' / 'tags' / 'Export all.txt'
if not DEFAULT_WINCC_EXPORT.exists():
    if repo_export1.exists():
        DEFAULT_WINCC_EXPORT = repo_export1
    elif repo_export2.exists():
        DEFAULT_WINCC_EXPORT = repo_export2
    elif Path('/home/nong_ing/Downloads/Export all.txt').exists():
        DEFAULT_WINCC_EXPORT = Path('/home/nong_ing/Downloads/Export all.txt')

# ---------------------------------------------------------
# WinCC Tag Scanner (Parses full Siemens WinCC Tag Export)
# ---------------------------------------------------------
def scan_wincc_tags(file_path):
    """Parses standard Siemens WinCC V8.1 Tag Management Export files (33 columns).
    Supports UTF-16 LE and UTF-8 BOM, separates UI fields from raw metadata without losing original columns.
    """
    tags = []
    p = Path(file_path)
    if not p.exists() or not p.is_file():
        return tags

    try:
        raw_bytes = p.read_bytes()
    except OSError as e:
        print(f"Error reading WinCC export {file_path}: {e}", file=sys.stderr)
        return tags

    if not raw_bytes:
        return []

    content = None
    if raw_bytes.startswith(b'\xef\xbb\xbf'):
        try:
            content = raw_bytes[3:].decode('utf-8')
        except UnicodeDecodeError:
            pass
    elif raw_bytes.startswith(b'\xff\xfe'):
        try:
            content = raw_bytes[2:].decode('utf-16-le')
        except UnicodeDecodeError:
            pass
    elif raw_bytes.startswith(b'\xfe\xff'):
        try:
            content = raw_bytes[2:].decode('utf-16-be')
        except UnicodeDecodeError:
            pass

    if content is None:
        for enc in ('utf-8', 'utf-16-le', 'utf-16', 'cp1252'):
            try:
                content = raw_bytes.decode(enc)
                break
            except (UnicodeDecodeError, OSError):
                continue

    if content is None:
        print(f"Error decoding WinCC export {file_path}: unsupported encoding", file=sys.stderr)
        return tags

    if content.startswith('\ufeff'):
        content = content[1:]

    lines = content.splitlines()
    if len(lines) < 3:
        return tags

    tech_headers = [h.strip() for h in lines[1].split('\t')]
    human_headers = [h.strip() for h in lines[2].split('\t')]
    num_cols = max(len(tech_headers), len(human_headers), 33)

    for line in lines[3:]:
        line = line.strip('\r\n')
        if not line:
            continue
        parts = line.split('\t')
        if not parts or not parts[0].strip():
            continue

        raw_metadata = {}
        for col_idx in range(num_cols):
            val = parts[col_idx].strip() if col_idx < len(parts) else ''
            h_name = human_headers[col_idx] if col_idx < len(human_headers) and human_headers[col_idx] else f'Col_{col_idx}'
            raw_metadata[h_name] = val
            if col_idx < len(tech_headers) and tech_headers[col_idx]:
                raw_metadata[tech_headers[col_idx]] = val

        name = parts[0].strip() if len(parts) > 0 else ''
        comment = parts[1].strip() if len(parts) > 1 else ''
        dtype = parts[2].strip() if len(parts) > 2 else ''
        length = parts[3].strip() if len(parts) > 3 else ''
        fmt = parts[4].strip() if len(parts) > 4 else ''
        conn = parts[5].strip() if len(parts) > 5 else ''
        group = parts[6].strip() if len(parts) > 6 else ''
        addr = parts[7].strip() if len(parts) > 7 else ''

        tags.append({
            'name': name,
            'comment': comment,
            'type': dtype,
            'length': length,
            'fmt': fmt,
            'conn': conn,
            'group': group or 'Default',
            'addr': addr or 'Internal',
            'raw_metadata': raw_metadata
        })

    return tags


# ---------------------------------------------------------
# Real Machine Metrics Reader (100% Real, Safe, Non-blocking)
# ---------------------------------------------------------

def check_interface_carrier(iface):
    """Checks physical ethernet / wifi carrier state cross-platform."""
    if not IS_WINDOWS:
        try:
            with open(f'/sys/class/net/{iface}/carrier', 'r') as f:
                return f.read().strip() == '1'
        except Exception:
            pass

    if IS_WINDOWS:
        try:
            kwargs = {}
            if hasattr(subprocess, 'CREATE_NO_WINDOW'):
                kwargs['creationflags'] = subprocess.CREATE_NO_WINDOW
            out = subprocess.check_output(['netsh', 'interface', 'show', 'interface'], **kwargs).decode('utf-8', errors='ignore')
            for line in out.splitlines():
                lower = line.lower()
                if 'connected' in lower and ('ethernet' in lower or 'scada' in lower or 'lan' in lower):
                    return True
        except Exception:
            pass

    return False


def parallel_ping_all(targets, timeout=1.0):
    """Pings all targets concurrently in parallel threads to eliminate blocking lag."""
    results = {}
    with concurrent.futures.ThreadPoolExecutor(max_workers=len(targets) or 4) as executor:
        future_to_ip = {executor.submit(ping_target_real, ip, timeout): ip for ip in targets}
        for future in concurrent.futures.as_completed(future_to_ip):
            ip = future_to_ip[future]
            try:
                results[ip] = future.result()
            except Exception:
                results[ip] = 'nope'
    return results


def ping_target_real(ip, timeout=1.0):
    """Pings target IP cross-platform (Linux & Windows 11). Returns latency string if online, or 'nope' if offline."""
    try:
        kwargs = {
            'stdout': subprocess.PIPE,
            'stderr': subprocess.PIPE,
            'timeout': timeout + 1.2
        }
        if IS_WINDOWS:
            cmd = ['ping', '-n', '1', '-w', str(int(timeout * 1000)), str(ip)]
            if hasattr(subprocess, 'CREATE_NO_WINDOW'):
                kwargs['creationflags'] = subprocess.CREATE_NO_WINDOW
        else:
            cmd = ['ping', '-c', '1', '-W', str(max(1, int(timeout))), str(ip)]

        res = subprocess.run(cmd, **kwargs)
        if res.returncode == 0:
            out = res.stdout.decode('utf-8', errors='ignore')
            for line in out.splitlines():
                lower = line.lower()
                if 'time=' in lower:
                    part = lower.split('time=')[1].split()[0].replace('ms', '')
                    try:
                        return f"{float(part):.1f} ms"
                    except ValueError:
                        return "< 1 ms"
                elif 'time<' in lower:
                    return "< 1 ms"
                elif 'average =' in lower:
                    avg = lower.split('average =')[1].strip().split()[0].replace('ms', '')
                    try:
                        return f"{float(avg):.1f} ms"
                    except ValueError:
                        return "< 1 ms"
            return "< 1 ms"
        return "nope"
    except Exception:
        return "nope"


def read_real_machine_data(network_state=None):
    """Reads actual host system metrics safely cross-platform (Linux & Windows 11)."""
    hostname = socket.gethostname()
    os_name = f"{platform.system()} {platform.release()}"
    if IS_WINDOWS:
        try:
            ver = sys.getwindowsversion()
            if ver.major >= 10 and ver.build >= 22000:
                os_name = f"Windows 11 (Build {ver.build})"
            else:
                os_name = f"Windows {platform.release()} (Build {ver.build})"
        except Exception:
            os_name = f"Windows 11 ({platform.release()})"
    elif Path('/etc/os-release').exists():
        try:
            with open('/etc/os-release') as f:
                for line in f:
                    if line.startswith('PRETTY_NAME='):
                        os_name = line.split('=')[1].strip().strip('"')
                        break
        except Exception:
            pass

    data = {
        'hostname': hostname,
        'os_name': os_name,
        'kernel': platform.release(),
        'arch': platform.machine(),
        'cpu_model': platform.processor() or 'Intel/AMD Processor',
        'cpu_cores': os.cpu_count() or 4,
        'cpu_load': 'Active',
        'ram_total_gb': 16.0,
        'ram_used_gb': 0.0,
        'ram_avail_gb': 0.0,
        'ram_pct': 0.0,
        'disk_total_gb': 0.0,
        'disk_used_gb': 0.0,
        'disk_avail_gb': 0.0,
        'disk_pct': 0.0,
        'ip_lan': '127.0.0.1',
        'uptime_str': 'กำลังคำนวณ...',
    }

    # 1. CPU Load
    try:
        if hasattr(os, 'getloadavg'):
            load1, load5, load15 = os.getloadavg()
            data['cpu_load'] = f"{load1:.2f} (1m)  {load5:.2f} (5m)  {load15:.2f} (15m)"
        else:
            data['cpu_load'] = "Active (Windows Normal)"
    except Exception:
        data['cpu_load'] = "Active"

    # 2. CPU Model
    if IS_WINDOWS:
        try:
            import winreg
            key = winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, r"HARDWARE\DESCRIPTION\System\CentralProcessor\0")
            data['cpu_model'] = winreg.QueryValueEx(key, "ProcessorNameString")[0].strip()
            winreg.CloseKey(key)
        except Exception:
            pass
    elif Path('/proc/cpuinfo').exists():
        try:
            with open('/proc/cpuinfo') as f:
                for line in f:
                    if 'model name' in line:
                        data['cpu_model'] = line.split(':')[1].strip()
                        break
        except Exception:
            pass

    # 3. RAM
    if IS_WINDOWS:
        try:
            import ctypes
            class MEMORYSTATUSEX(ctypes.Structure):
                _fields_ = [
                    ("dwLength", ctypes.c_ulong),
                    ("dwMemoryLoad", ctypes.c_ulong),
                    ("ullTotalPhys", ctypes.c_ulonglong),
                    ("ullAvailPhys", ctypes.c_ulonglong),
                    ("ullTotalPageFile", ctypes.c_ulonglong),
                    ("ullAvailPageFile", ctypes.c_ulonglong),
                    ("ullTotalVirtual", ctypes.c_ulonglong),
                    ("ullAvailVirtual", ctypes.c_ulonglong),
                    ("sullAvailExtendedVirtual", ctypes.c_ulonglong),
                ]
            stat = MEMORYSTATUSEX()
            stat.dwLength = ctypes.sizeof(MEMORYSTATUSEX)
            if ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(stat)):
                total = stat.ullTotalPhys
                avail = stat.ullAvailPhys
                used = total - avail
                data['ram_total_gb'] = total / (1024**3)
                data['ram_used_gb'] = used / (1024**3)
                data['ram_avail_gb'] = avail / (1024**3)
                data['ram_pct'] = (used / total) * 100.0 if total else 0.0
        except Exception:
            pass
    elif Path('/proc/meminfo').exists():
        try:
            mem_total, mem_avail = 0, 0
            with open('/proc/meminfo', 'r') as f:
                for line in f:
                    if line.startswith('MemTotal:'):
                        mem_total = int(line.split()[1]) * 1024
                    elif line.startswith('MemAvailable:'):
                        mem_avail = int(line.split()[1]) * 1024
            if mem_total > 0:
                mem_used = mem_total - mem_avail
                data['ram_total_gb'] = mem_total / (1024**3)
                data['ram_used_gb'] = mem_used / (1024**3)
                data['ram_avail_gb'] = mem_avail / (1024**3)
                data['ram_pct'] = (mem_used / mem_total) * 100.0
        except Exception:
            pass

    # 4. Disk Usage
    try:
        drive = os.path.splitdrive(sys.executable)[0] or (os.path.splitdrive(os.getcwd())[0] if IS_WINDOWS else '/')
        if not drive or drive == '':
            drive = 'C:\\' if IS_WINDOWS else '/'
        elif IS_WINDOWS and not drive.endswith('\\'):
            drive += '\\'
        tot, used, free = shutil.disk_usage(drive)
        data['disk_total_gb'] = tot / (1024**3)
        data['disk_used_gb'] = used / (1024**3)
        data['disk_avail_gb'] = free / (1024**3)
        data['disk_pct'] = (used / tot) * 100.0 if tot else 0.0
    except Exception:
        pass

    # 5. Reuse the background F3 snapshot; GTK metrics refresh never queries D-Bus/netlink.
    try:
        network = network_state or {}
        interfaces = network.get('interfaces', {})
        preferred = interfaces.get(network.get('default_gw_iface'), {}).get('ipv4')
        assigned = preferred or next((row.get('ipv4') for row in interfaces.values() if row.get('ipv4')), None)
        status = local_snapshot_state(network)
        data['ip_lan'] = f"{assigned} (Assigned locally)" if assigned and status == 'OBSERVED_LOCAL' else f'STALE: {assigned}' if assigned and status == 'STALE' else 'NOT OBSERVED'
    except Exception:
        data['ip_lan'] = 'NOT OBSERVED'

    # 6. Uptime
    if IS_WINDOWS:
        try:
            import ctypes
            ms = ctypes.windll.kernel32.GetTickCount64()
            secs = ms / 1000.0
            h = int(secs // 3600)
            m = int((secs % 3600) // 60)
            data['uptime_str'] = f"{h} ชม. {m} นาที"
        except Exception:
            data['uptime_str'] = "ทำงานต่อเนื่อง (Windows)"
    elif Path('/proc/uptime').exists():
        try:
            with open('/proc/uptime', 'r') as f:
                up_secs = float(f.readline().split()[0])
                h = int(up_secs // 3600)
                m = int((up_secs % 3600) // 60)
                data['uptime_str'] = f"{h} ชม. {m} นาที"
        except Exception:
            pass

    return data


# ---------------------------------------------------------
# Default Task Configurations (WinCC V8.1 Task Management)
# ---------------------------------------------------------
DEFAULT_TASKS = []

def load_tasks():
    if TASKS_CONFIG_FILE.exists():
        try:
            with open(TASKS_CONFIG_FILE, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception:
            pass
    return list(DEFAULT_TASKS)

def save_tasks(tasks):
    return save_atomic_json(TASKS_CONFIG_FILE, tasks)


# ---------------------------------------------------------
# [PURGED MOCK DATA: REAL_STATIONS_DATA completely deleted]

CSS_DATA = b"""
@define-color aqua_bg #11161c;
@define-color aqua_surface #1a212a;
@define-color aqua_panel #151b22;
@define-color aqua_raised #222b36;
@define-color aqua_selected #1f2c3a;
@define-color aqua_line #2f3a46;
@define-color aqua_border #66737f;
@define-color aqua_ink #e3e8ee;
@define-color aqua_muted #9aa6b2;
@define-color aqua_accent #6fa8dc;

window {
    background: @aqua_bg;
    color: @aqua_ink;
    font-family: 'IBM Plex Sans Thai', 'Noto Sans Thai', sans-serif;
    font-size: 10pt;
}

label { color: @aqua_ink; }

.wincc-topbar, .wincc-navigation, .alarm-banner {
    background: @aqua_panel;
    padding: 5px 14px;
}
.wincc-topbar, .wincc-navigation { border-bottom: 1px solid @aqua_line; }
.alarm-banner { border-top: 1px solid @aqua_line; }
.wincc-logo {
    color: @aqua_ink;
    font-size: 15px;
    font-weight: 700;
    letter-spacing: 1px;
}
.wincc-title, .alarm-text, .nav-caption, .page-hint { color: @aqua_muted; }
.wincc-title, .alarm-text, .nav-caption { font-size: 12px; }
.nav-caption { padding: 0 3px; }
.wincc-clock {
    color: @aqua_muted;
    font-family: 'IBM Plex Mono', monospace;
    font-size: 12px;
}

.wincc-group {
    background: @aqua_surface;
    border: 1px solid @aqua_line;
    border-radius: 4px;
    padding: 12px;
}
.group-title {
    font-size: 15px;
    font-weight: 600;
    color: @aqua_ink;
    border-bottom: 1px solid @aqua_line;
    padding-bottom: 8px;
}
.page-title {
    color: @aqua_ink;
    font-size: 21px;
    font-weight: 700;
}

/* Modern Equipment Cards */
.scada-card {
    background: linear-gradient(180deg, #182234 0%, #0f172a 100%);
    border: 1px solid #1e293b;
    border-radius: 8px;
    padding: 10px 14px;
    margin: 4px;
    min-width: 220px;
}
.scada-card:hover {
    border-color: #38bdf8;
    background: #1e293b;
}
.card-header {
    font-weight: 700;
    font-size: 11pt;
    color: #f1f5f9;
}

/* Modern Status Indicators & Badges */
.badge-running {
    background-color: rgba(16, 185, 129, 0.2);
    color: #34d399;
    font-weight: 700;
    padding: 3px 10px;
    border: 1px solid #10b981;
    border-radius: 20px;
    font-size: 9pt;
}
.badge-standby {
    background-color: rgba(148, 163, 184, 0.15);
    color: #94a3b8;
    font-weight: 600;
    padding: 3px 10px;
    border: 1px solid #475569;
    border-radius: 20px;
    font-size: 9pt;
}
.badge-sensor {
    background-color: rgba(56, 189, 248, 0.15);
    color: #38bdf8;
    font-weight: 600;
    padding: 3px 10px;
    border: 1px solid #0284c7;
    border-radius: 20px;
    font-size: 9pt;
}
.badge-active, .badge-has-net {
    background-color: rgba(16, 185, 129, 0.2);
    color: #6ee7b7;
    font-weight: 700;
    padding: 3px 10px;
    border: 1px solid #059669;
    border-radius: 20px;
    font-size: 9pt;
}
.badge-stopped, .badge-inactive, .badge-nope, .badge-nope-card, .badge-no-net {
    background-color: rgba(244, 63, 94, 0.18);
    color: #fda4af;
    font-weight: 700;
    padding: 3px 10px;
    border: 1px solid rgba(244, 63, 94, 0.4);
    border-radius: 20px;
    font-size: 9pt;
}
.badge-gateway {
    background-color: rgba(168, 85, 247, 0.18);
    color: #c084fc;
    font-weight: 700;
    padding: 3px 10px;
    border: 1px solid #7c3aed;
    border-radius: 20px;
    font-size: 9pt;
}

/* Shared navigation and page actions. */
.fkey-btn {
    background: @aqua_surface;
    color: @aqua_ink;
    border: 1px solid @aqua_line;
    border-radius: 4px;
    font-weight: 600;
    font-size: 13px;
    min-height: 27px;
    padding: 3px 9px;
}
.fkey-btn:hover { background: @aqua_raised; }
.fkey-btn:checked {
    background: @aqua_selected;
    border-color: @aqua_accent;
    color: @aqua_accent;
}
.fkey-btn:focus-visible { outline: 2px solid @aqua_accent; outline-offset: -2px; }

/* Offline operator manual */
.aqua-manual .manual-header {
    background: @aqua_panel;
    border-bottom: 1px solid @aqua_line;
    padding: 10px 16px;
}
.aqua-manual stacksidebar {
    background: @aqua_panel;
    border-right: 1px solid @aqua_line;
}
.aqua-manual stacksidebar row:selected {
    background: @aqua_selected;
}
.manual-content { padding: 22px 26px; }
.manual-section-title { color: @aqua_ink; font-weight: 700; font-size: 15px; }
.manual-copy { color: @aqua_muted; font-size: 14px; }

/* Modern Action Buttons */
.action-btn {
    background: linear-gradient(135deg, #1e293b 0%, #0f172a 100%);
    color: #f8fafc;
    border: 1px solid #334155;
    border-radius: 8px;
    font-weight: 600;
    padding: 6px 14px;
    font-size: 9.5pt;
}
.action-btn:hover {
    background: #334155;
    border-color: #38bdf8;
}
.action-btn:active {
    background: #0f172a;
}

.btn-autoscan-start {
    background: linear-gradient(135deg, #059669 0%, #10b981 100%);
    color: #ffffff;
    border: 1px solid #047857;
    border-radius: 8px;
    font-weight: 700;
    padding: 6px 16px;
    font-size: 9.5pt;
}
.btn-autoscan-start:hover {
    background: #059669;
}
.btn-autoscan-stop {
    background: linear-gradient(135deg, #dc2626 0%, #ef4444 100%);
    color: #ffffff;
    border: 1px solid #b91c1c;
    border-radius: 8px;
    font-weight: 700;
    padding: 6px 16px;
    font-size: 9.5pt;
}
.btn-autoscan-stop:hover {
    background: #dc2626;
}

/* Catalog and event table. */
.data-table {
    background: @aqua_surface;
    border: 1px solid @aqua_line;
    border-radius: 4px;
}
.table-th, .table-td {
    padding: 7px 10px;
    border-bottom: 1px solid @aqua_line;
    font-size: 13px;
}
.table-th {
    background: @aqua_raised;
    color: @aqua_muted;
    font-weight: 600;
}
.table-td { color: @aqua_ink; }
.table-td.alternate { background: @aqua_panel; }

/* Modern Input Fields & Controls */
entry, textview {
    background-color: #0f172a;
    color: #f8fafc;
    border: 1px solid #334155;
    border-radius: 8px;
    padding: 6px 12px;
}
entry:focus {
    border-color: #38bdf8;
}
checkbutton {
    color: #cbd5e1;
}
progressbar trough {
    background-color: #1e293b;
    border-radius: 4px;
}
progressbar progress {
    background: linear-gradient(90deg, #0284c7 0%, #10b981 100%);
    border-radius: 4px;
}
"""

class AquaWinCCWindow(Gtk.ApplicationWindow):
    def __init__(self, app):
        super().__init__(application=app, title="AQUA COMMAND")
        self.set_default_size(1360, 820)
        self.set_size_request(1024, 700)
        self.connect('close-request', self.on_close_request)

        # Force GTK to prefer dark theme globally so unstyled states never fallback to Adwaita Light
        settings = Gtk.Settings.get_default()
        if settings:
            settings.set_property("gtk-application-prefer-dark-theme", True)

        # Load WinCC Base CSS
        css_provider = Gtk.CssProvider()
        css_provider.load_from_data(CSS_DATA)
        Gtk.StyleContext.add_provider_for_display(
            Gdk.Display.get_default(), css_provider, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION
        )

        # Load F1 Industrial Precision CSS
        f1_css_path = Path(__file__).resolve().parent / 'f1_style.css'
        if f1_css_path.exists():
            try:
                f1_css_provider = Gtk.CssProvider()
                f1_css_provider.load_from_path(str(f1_css_path))
                Gtk.StyleContext.add_provider_for_display(
                    Gdk.Display.get_default(), f1_css_provider, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION + 10
                )
            except Exception as e:
                print(f"[F1_CSS] Warning loading f1_style.css: {e}", file=sys.stderr)

        # Load F2 Task Management CSS
        f2_css_path = Path(__file__).resolve().parent / 'f2_style.css'
        if f2_css_path.exists():
            try:
                f2_css_provider = Gtk.CssProvider()
                f2_css_provider.load_from_path(str(f2_css_path))
                Gtk.StyleContext.add_provider_for_display(
                    Gdk.Display.get_default(), f2_css_provider, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION + 12
                )
            except Exception as e:
                print(f"[F2_CSS] Warning loading f2_style.css: {e}", file=sys.stderr)

        # Load Unified Workspace CSS
        ws_css_path = Path(__file__).resolve().parent / 'workspace_style.css'
        if ws_css_path.exists():
            try:
                ws_css_provider = Gtk.CssProvider()
                ws_css_provider.load_from_path(str(ws_css_path))
                Gtk.StyleContext.add_provider_for_display(
                    Gdk.Display.get_default(), ws_css_provider, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION + 15
                )
            except Exception as e:
                print(f"[WS_CSS] Warning loading workspace_style.css: {e}", file=sys.stderr)

        # State - Fresh Default State (Preload verified catalog if file exists for instant readiness)
        self.config_dir = CONFIG_DIR
        self.scanned_tags = []
        if DEFAULT_WINCC_EXPORT.exists():
            self.scanned_tags = scan_wincc_tags(DEFAULT_WINCC_EXPORT)

        self.tasks = load_tasks()
        self.topology_data = load_topology()
        self.telegram_config = load_telegram_config()
        self.opcua_config = load_opcua_config()
        self.opcua_session_password = ""  # Session-only credential in memory
        # Gate B2: Observable State Store & Manual Single-Shot OPC UA Reader
        project_mapping = Path(__file__).resolve().parent.parent / "config" / "opcua_tag_mapping.json"
        user_mapping = CONFIG_DIR / "opcua_tag_mapping.json"
        mapping_file = user_mapping if user_mapping.exists() else (project_mapping if project_mapping.exists() else Path("config/opcua_tag_mapping.json"))
        self.pki = PkiManager(pki_dir=CONFIG_DIR / "pki")
        self.last_quarantined_server_cert = None
        self.last_quarantined_cert_info = {}
        self.opcua_mapper = NodeIdMapper(mapping_file if mapping_file.exists() else None)
        self.opcua_store = ObservableStateStore()
        self.opcua_reader = ManualOpcUaReader(self.opcua_mapper, self.opcua_store, CONFIG_DIR, pki=self.pki)

        # 5-Second Polling & Task Notification Architecture
        self.durable_storage = DurableStorage(CONFIG_DIR / "aqua_command.db")
        self.task_engine = TaskEngine(self.durable_storage)
        self.task_engine.load_tasks(self.tasks)
        self.notification_worker = NotificationWorker(self.durable_storage)
        self.polling_engine = OpcUaPollingEngine(
            self.opcua_mapper,
            self.opcua_store,
            self.durable_storage,
            self.task_engine,
            self.pki,
            interval_seconds=5.0,
            mode_task_tags_only=True
        )
        self.opcua_discovered_nodes = []  # Strictly separated from local catalog
        self.browse_cancel_flag = threading.Event()  # Cooperative cancellation
        self.task_execution_state = "SUSPENDED_SAFETY_GATE_B1"  # Explicit suspension
        self.alarm_events = [
            (datetime.now().strftime("%d/%m/%Y %H:%M:%S"), "SYSTEM", "INFO", "READY", "ระบบ AQUA COMMAND WinCC V8.1 เริ่มต้นทำงานพร้อมตรวจวัดสถานะ")
        ]
        self.current_task_idx = 0
        self.tag_checkboxes = {}
        self.selected_tags_for_task = set()
        self.internet_online = None  # Unknown until an explicitly authorized check supplies evidence.

        # Real Live Probed Status Cache
        self.live_status = {
            'scada_carrier': False,
            'pings': {
                '192.168.1.11': 'nope',
                '192.168.1.12': 'nope',
                '192.168.1.13': 'nope',
                '192.168.1.254': 'nope',
                '192.168.100.1': 'nope',
                '192.168.100.135': 'nope',
                '192.168.100.150': 'nope',
                '192.168.100.178': 'nope',
            }
        }
        # Auto-Scanner Engine State (Default: Inactive/Standby until user starts it or scans)
        self.auto_scan_active = False
        self.auto_scan_interval = 5      # 5 seconds
        self.auto_scan_duration = 3600   # 1 hour (3600 seconds)
        self.auto_scan_start_time = time.time()
        self.auto_scan_countdown = 5
        self.auto_scan_cycles = 0
        self.scan_in_progress = False
        self.auto_scan_last_time = "เริ่มต้น..."
        self.last_tag_file_mtime = 0

        # Main Root Layout
        root_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        self.set_child(root_box)

        # 1. WinCC Top Bar (Section A - Industrial Precision V1.1)
        topbar = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
        topbar.add_css_class('wincc-topbar')
        root_box.append(topbar)

        logo_label = Gtk.Label(label="AQUA COMMAND")
        logo_label.add_css_class('wincc-logo')
        topbar.append(logo_label)

        title_label = Gtk.Label(label="WinCC V8.1")
        title_label.add_css_class('wincc-title')
        title_label.set_hexpand(True)
        title_label.set_xalign(0.0)
        title_label.set_ellipsize(Pango.EllipsizeMode.END)
        topbar.append(title_label)

        # Section A Status Cluster (Restrained visual weight hierarchy)
        if len(self.scanned_tags) == 0:
            self.pill_scan = Gtk.Label(label="คลัง 0 Tag")
            self.pill_scan.add_css_class('badge-nope')
        else:
            self.pill_scan = Gtk.Label(label=f"คลัง {len(self.scanned_tags)} Tag")
            self.pill_scan.add_css_class('badge-active')
        topbar.append(self.pill_scan)

        self.pill_readonly = Gtk.Label(label="READ ONLY")
        self.pill_readonly.add_css_class('badge-readonly')
        topbar.append(self.pill_readonly)

        self.internet_badge = Gtk.Label(label='เน็ต: ยังไม่ทราบ')
        self.internet_badge.add_css_class('badge-standby')
        topbar.append(self.internet_badge)

        # Legacy status fields used by background and topology handlers.
        self.pill_scada_ip = Gtk.Label(label="Local NIC: NOT VERIFIED")
        self.pill_net = Gtk.Label(label="Internet: ยังไม่ได้ตรวจสอบ")
        self.pill_wan_ip = Gtk.Label(label="")
        self.pill_opcua = Gtk.Label(label="")

        # 2. System Status / Alarm Ribbon Line
        alarm_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        alarm_box.add_css_class('alarm-banner')

        if len(self.scanned_tags) == 0:
            self.alarm_icon = Gtk.Label(label="สถานะ")
            self.alarm_icon.add_css_class('alarm-text')
            alarm_box.append(self.alarm_icon)

            self.alarm_text = Gtk.Label(label="ยังไม่มีข้อมูล Tag · เปิดคลัง Tag แล้วกดรีเฟรชคลัง")
            self.alarm_text.add_css_class('alarm-text')
            self.alarm_text.set_hexpand(True)
        else:
            self.alarm_icon = Gtk.Label(label="คลัง Tag")
            self.alarm_icon.add_css_class('alarm-text')
            alarm_box.append(self.alarm_icon)

            self.alarm_text = Gtk.Label(label=f"โหลดคลัง WinCC แล้ว {len(self.scanned_tags)} Tag · ยังไม่มีผลอ่าน OPC UA")
            self.alarm_text.add_css_class('alarm-text')
            self.alarm_text.set_hexpand(True)
        self.alarm_text.set_xalign(0.0)
        self.alarm_text.set_ellipsize(Pango.EllipsizeMode.END)
        alarm_box.append(self.alarm_text)

        # 3. Stack Pages
        self.stack = Gtk.Stack()
        self.stack.set_hhomogeneous(False)
        self.stack.set_vexpand(True)
        self.stack.set_hexpand(True)
        self.stack.set_transition_type(Gtk.StackTransitionType.NONE)
        root_box.append(self.stack)

        # Build Pages
        self.build_overview_page()
        self.build_task_manager_page() # WinCC Task Manager
        self.build_network_topology_page() # Dual-Router Network Topology View
        self.build_machine_page()
        self.build_tags_page()
        self.build_alarms_page()

        navigation = Gtk.Box(spacing=6)
        navigation.add_css_class('wincc-navigation')
        root_box.insert_child_after(navigation, topbar)
        root_box.append(alarm_box)

        self.nav_btns = {}
        self.settings_button = Gtk.ToggleButton(icon_name='applications-system-symbolic')
        self.settings_button.add_css_class('fkey-btn')
        self.settings_button.set_size_request(42, -1)
        self.settings_button.set_tooltip_text('ตั้งค่าการเชื่อมต่อ')
        self.settings_button.update_property([Gtk.AccessibleProperty.LABEL], ['การตั้งค่า'])

        pages = (
            ('งานประจำ', (
                ('overview', 'ติดตามค่า' if USE_UNIFIED_WORKSPACE else 'ภาพรวมสถานี'),
                ('tasks', 'งานเฝ้าระวัง'),
                ('network', 'ผังการสื่อสาร'),
            )),
            ('เครื่องมือ', (
                ('tags', 'คลัง Tag'),
                ('machine', 'ข้อมูลเครื่อง'),
            )),
        )
        group_button = self.settings_button
        for caption, entries in pages:
            if self.nav_btns:
                navigation.append(Gtk.Separator(orientation=Gtk.Orientation.VERTICAL))
            heading = Gtk.Label(label=caption)
            heading.add_css_class('nav-caption')
            navigation.append(heading)
            for key, text in entries:
                if USE_UNIFIED_WORKSPACE and key == 'tasks':
                    button = Gtk.Button(label=text)
                    button.set_tooltip_text('เปิดงานเฝ้าระวัง')
                    button.connect('clicked', lambda _: self.activate_workspace_mode('task_manager'))
                else:
                    button = Gtk.ToggleButton(label=text)
                    button.set_group(group_button)
                    button.connect('toggled', lambda btn, k=key: self.stack.set_visible_child_name(k) if btn.get_active() else None)
                    if USE_UNIFIED_WORKSPACE and key == 'overview':
                        button.connect('clicked', lambda _: self.activate_workspace_mode('monitoring'))
                    self.nav_btns[key] = button
                button.add_css_class('fkey-btn')
                navigation.append(button)

        navigation.append(Gtk.Box(hexpand=True))
        navigation.append(self.build_help_button())

        self.nav_btns['alarms'] = self.settings_button
        self.settings_button.connect('toggled', lambda btn: self.stack.set_visible_child_name('alarms') if btn.get_active() else None)
        self.stack.connect('notify::visible-child-name', self.on_page_changed)

        exit_btn = Gtk.Button(label='ปิดโปรแกรม')
        exit_btn.add_css_class('fkey-btn')
        exit_btn.connect('clicked', lambda _: self.close())
        alarm_box.append(exit_btn)
        alarm_box.append(self.settings_button)

        key_ctrl = Gtk.EventControllerKey()
        key_ctrl.connect('key-pressed', self.on_global_key_pressed)
        self.add_controller(key_ctrl)

        # Default startup landing page: F1 Overview
        self.stack.set_visible_child_name('overview')
        if 'overview' in self.nav_btns:
            self.nav_btns['overview'].set_active(True)

        # Start the background pollers.
        GLib.timeout_add_seconds(1, self.auto_scan_tick) # Real Auto-Scan Engine!
        self.update_real_data()
        GLib.timeout_add_seconds(2, self.update_real_data)

        # Background Task Runner (Suspended in Gate B1)
        self.running = False
        self.task_thread = None  # Startup Safety: zero background task threads on window init

        # Optional consumer projection; no new industrial client or control ownership.
        self.hybrid_ui = None
        try:
            from observability.ui import DashboardUI
            self.hybrid_ui = DashboardUI(self)
            if self.hybrid_ui.bridge:
                topbar.append(self.hybrid_ui.menu)
                self.render_tags_page_grid()
        except Exception:
            pass  # Grafana integration failure cannot prevent native startup.

    def build_help_button(self):
        self.help_manual = None
        self.help_button = Gtk.Button(label='?')
        self.help_button.add_css_class('fkey-btn')
        self.help_button.set_size_request(38, -1)
        self.help_button.set_tooltip_text('คู่มือการใช้งาน')
        self.help_button.update_property([Gtk.AccessibleProperty.LABEL], ['คู่มือการใช้งาน'])
        self.help_button.connect('clicked', self.show_help_manual)
        return self.help_button

    def show_help_manual(self, _):
        if self.help_manual is None:
            if __package__:
                from .help_manual import HelpManual
            else:
                from help_manual import HelpManual
            self.help_manual = HelpManual(self)
        self.help_manual.present()

    def switch_to_tab(self, tab_key):
        if USE_UNIFIED_WORKSPACE and tab_key in ('overview', 'tasks'):
            self.activate_workspace_mode('task_manager' if tab_key == 'tasks' else 'monitoring')
            return
        self.stack.set_visible_child_name(tab_key)

    def on_page_changed(self, stack, _):
        page = stack.get_visible_child_name()
        if page in self.nav_btns:
            self.nav_btns[page].set_active(True)
        if page == 'tags' and self.tags_page_dirty:
            self.render_tags_page_grid()

    def trigger_rescan(self):
        self.scanned_tags = scan_wincc_tags(DEFAULT_WINCC_EXPORT)
        self.pill_scan.set_text(f"คลัง {len(self.scanned_tags)} Tag")
        self.pill_scan.remove_css_class('badge-nope')
        self.pill_scan.add_css_class('badge-active')
        self.alarm_icon.set_text("[SCANNED]")
        self.alarm_text.set_text(f"รีเฟรชคลัง WinCC แล้ว {len(self.scanned_tags)} Tag")
        self.render_dynamic_overview()
        if hasattr(self, 'render_tags_grid'):
            self.render_tags_grid()
        if hasattr(self, 'render_tags_page_grid'):
            self.render_tags_page_grid()
        # Safety: F7 strictly refreshes local catalog; zero automated network probing
        self.update_real_data()
        if getattr(self, 'hybrid_ui', None) and self.hybrid_ui.bridge:
            self.hybrid_ui.bridge.record_refresh(len(self.scanned_tags))

    def activate_workspace_mode(self, mode):
        self.stack.set_visible_child_name('overview')
        if hasattr(self, 'unified_workspace'):
            if mode == 'task_manager':
                self.unified_workspace.open_task_dialog()
            else:
                self.unified_workspace.set_workspace_mode('monitoring')

    # ---------------------------------------------------------
    # TAB 1: Real WinCC Plant Groups Overview (F1 Industrial Precision / Unified Workspace)
    def build_overview_page(self):
        if USE_UNIFIED_WORKSPACE:
            root = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
            root.set_margin_start(4)
            root.set_margin_end(4)
            root.set_margin_top(4)
            root.set_margin_bottom(4)
            self.unified_workspace = AquaUnifiedWorkspaceView(self, root)
            self.stack.add_named(root, 'overview')
        else:
            scrolled = Gtk.ScrolledWindow()
            scrolled.set_hexpand(True)
            scrolled.set_vexpand(True)
            scrolled.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)

            self.f1_explorer = F1StationExplorerView(self)
            scrolled.set_child(self.f1_explorer.root_widget)
            self.stack.add_named(scrolled, 'overview')
            self.render_dynamic_overview()

    def render_dynamic_overview(self):
        if hasattr(self, 'f1_explorer'):
            self.f1_explorer.update_catalog_data(self.scanned_tags)
        if hasattr(self, 'unified_workspace'):
            self.unified_workspace.sync_catalog_data()
            self.unified_workspace.refresh_group_explorer()
            self.unified_workspace.render_catalog_table()

    # TAB 2: Cloned WinCC V8.1 Task Management & Scanner
    # ---------------------------------------------------------
    def build_task_manager_page(self):
        root = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        root.set_margin_start(10)
        root.set_margin_end(10)
        root.set_margin_top(8)
        root.set_margin_bottom(8)

        # F2 Task Configuration & Monitoring Rule Editor Workstation
        if not USE_UNIFIED_WORKSPACE:
            self.f2_tasks_view = F2TaskManagerView(self, root)
        self.stack.add_named(root, 'tasks')

    def render_tags_grid(self, *args, **kwargs):
        if hasattr(self, 'f2_tasks_view'):
            self.f2_tasks_view.render_discovered_tags()

    def load_task_to_ui(self, idx=0):
        if hasattr(self, 'unified_workspace'):
            self.unified_workspace.switch_to_task(idx)
        elif hasattr(self, 'f2_tasks_view'):
            self.current_task_idx = idx
            self.f2_tasks_view.load_current_task_to_ui()

    def create_new_task(self, _=None):
        if hasattr(self, 'unified_workspace'):
            self.unified_workspace.on_create_new_task()
        elif hasattr(self, 'f2_tasks_view'):
            self.f2_tasks_view.on_create_new_task(None)

    def save_tasks(self):
        return save_tasks(self.tasks)

    def save_all_tasks(self):
        saved = self.save_tasks()
        if hasattr(self, 'alarm_text'):
            self.alarm_text.set_text("บันทึกการตั้งค่า Task ทั้งหมดเรียบร้อยแล้ว" if saved else "บันทึกการตั้งค่า Task ไม่สำเร็จ")
        return saved

    def add_selected_tags_to_current_task(self, _=None):
        if hasattr(self, 'f2_tasks_view'):
            self.f2_tasks_view.on_add_selected_tags(None)

    def remove_tag_from_task(self, tag_name):
        if hasattr(self, 'f2_tasks_view'):
            self.f2_tasks_view.on_remove_tag_from_task(tag_name)

    # ---------------------------------------------------------
    # TAB 3: Dual-Router Network Topology & Multi-IP View (F3 Reconstructed)
    # ---------------------------------------------------------
    def build_network_topology_page(self):
        self.f3_network_view = F3ApiView(self)
        self.topology_canvas = self.f3_network_view.canvas
        self.stack.add_named(self.f3_network_view.root_widget, 'network')

    def render_network_table(self):
        if hasattr(self, 'f3_network_view'):
            self.f3_network_view.render_ip_summary_table()


    def reset_to_factory_defaults(self):
        """Resets all tasks, network topology, and configurations to factory defaults (empty like fresh install)."""
        import copy
        self.topology_data = copy.deepcopy(DEFAULT_TOPOLOGY)
        save_topology(self.topology_data)

        self.scanned_tags = []
        self.tasks = []
        save_tasks([])

        # Reset UI
        self.pill_scan.set_text("สแกนพบ: 0 Tags")
        self.pill_scan.remove_css_class('badge-active')
        self.pill_scan.add_css_class('badge-nope')

        # Switch to F1 (Default Overview Landing Page)
        self.stack.set_visible_child_name('overview')
        if 'overview' in self.nav_btns:
            self.nav_btns['overview'].set_active(True)

        # Stop Auto-scan
        self.auto_scan_active = False
        self.auto_scan_interval = 5
        self.auto_scan_duration = 3600
        self.auto_scan_countdown = 5
        self.auto_scan_cycles = 0

        # Re-render pages
        self.render_dynamic_overview()
        if hasattr(self, 'render_tags_grid'):
            self.render_tags_grid()
        if hasattr(self, 'render_tags_page_grid'):
            self.render_tags_page_grid()
        if hasattr(self, 'render_network_table'):
            self.render_network_table()

        self.alarm_icon.set_text("⚪ สถานะ")
        self.alarm_text.set_text("🔄 รีเซ็ตโปรแกรมกลับสู่ค่าเริ่มต้นว่างเปล่า (เหมือนติดตั้งใหม่) เรียบร้อยแล้ว — เปิดคลัง Tag แล้วกดรีเฟรชคลัง")

    def show_network_config_dialog(self, _):
        dlg = Gtk.Window(title="⚙️ ปรับแต่ง IP และโครงสร้างเราเตอร์ (Multi-Router Config)")
        dlg.set_transient_for(self)
        dlg.set_modal(True)
        dlg.set_default_size(680, 520)

        vbox = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
        vbox.set_margin_start(14)
        vbox.set_margin_end(14)
        vbox.set_margin_top(12)
        vbox.set_margin_bottom(12)
        dlg.set_child(vbox)

        title = Gtk.Label(label="ตั้งค่าหมายเลข IP สำหรับวงแลนภายใน และวงเราเตอร์ภายนอก")
        title.add_css_class('group-title')
        vbox.append(title)

        grid = Gtk.Grid(column_spacing=12, row_spacing=8)
        vbox.append(grid)

        data = self.topology_data
        scada = data.get('scada_lan', {})
        scada_devs = scada.get('devices', [])
        gw = data.get('gateway_bridge', {})
        wan = data.get('internet_wan', {})
        rt = wan.get('router', {})

        # Form fields
        entries = {}
        fields = [
            ("SCADA LAN Subnet:", "scada_subnet", scada.get('subnet', '192.168.1.0/24')),
            ("PC1 IP (สูบน้ำแรงต่ำ 1):", "pc1_ip", scada_devs[0].get('ip') if len(scada_devs) > 0 else '192.168.1.11'),
            ("PC2 IP (สูบน้ำแรงต่ำ 3):", "pc2_ip", scada_devs[1].get('ip') if len(scada_devs) > 1 else '192.168.1.12'),
            ("PC3 IP (สูบน้ำแรงสูง VSD):", "pc3_ip", scada_devs[2].get('ip') if len(scada_devs) > 2 else '192.168.1.13'),
            ("PC4 Gateway (ขาใน SCADA):", "gw_scada_ip", gw.get('nic_scada', {}).get('ip', '192.168.1.14')),
            ("PC4 Gateway (ขานอก WAN):", "gw_wan_ip", gw.get('nic_wan', {}).get('ip', '192.168.100.177')),
            ("Router 1 Gateway IP:", "rt_ip", rt.get('gateway_ip', '192.168.100.1')),
            ("Router 1 WiFi SSID:", "rt_ssid", rt.get('ssid', 'Nong_Arm')),
            ("เราเตอร์ตัวที่ 2 (ถ้ามี):", "rt2_ip", "192.168.200.1 (วงสำรอง)")
        ]

        for row, (lbl_txt, key, val) in enumerate(fields):
            l = Gtk.Label(label=lbl_txt)
            l.set_xalign(0.0)
            l.add_css_class('card-header')
            grid.attach(l, 0, row, 1, 1)

            e = Gtk.Entry(text=val)
            e.set_hexpand(True)
            grid.attach(e, 1, row, 1, 1)
            entries[key] = e

        # Buttons
        btn_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
        btn_box.set_halign(Gtk.Align.END)
        vbox.append(btn_box)

        def save_and_close(_):
            scada['subnet'] = entries['scada_subnet'].get_text()
            if len(scada_devs) > 0:
                scada_devs[0]['ip'] = entries['pc1_ip'].get_text()
            if len(scada_devs) > 1:
                scada_devs[1]['ip'] = entries['pc2_ip'].get_text()
            if len(scada_devs) > 2:
                scada_devs[2]['ip'] = entries['pc3_ip'].get_text()
            gw['nic_scada']['ip'] = entries['gw_scada_ip'].get_text()
            gw['nic_wan']['ip'] = entries['gw_wan_ip'].get_text()
            rt['gateway_ip'] = entries['rt_ip'].get_text()
            rt['ssid'] = entries['rt_ssid'].get_text()

            save_topology(self.topology_data)
            if hasattr(self, 'f3_network_view'):
                self.f3_network_view.topology_data = self.topology_data
                self.f3_network_view.canvas.queue_draw()
                self.f3_network_view.render_ip_summary_table()
            elif hasattr(self, 'topology_canvas'):
                self.topology_canvas.queue_draw()
            self.render_network_table()
            if hasattr(self, 'pill_scada_ip'):
                self.pill_scada_ip.set_text(f"🔒 SCADA: {scada['subnet']} (ไม่มีเน็ต)")
            if hasattr(self, 'pill_wan_ip'):
                self.pill_wan_ip.set_text(f"🌐 WAN: {rt['gateway_ip']} (4G LTE)")
            self.alarm_text.set_text("บันทึกการปรับแต่ง IP และโครงสร้างเราเตอร์เรียบร้อยแล้ว")
            dlg.close()

        save_btn = Gtk.Button(label="💾 บันทึกและปรับปรุงผัง (Save & Apply)")
        save_btn.add_css_class('action-btn')
        save_btn.connect('clicked', save_and_close)
        btn_box.append(save_btn)

        cancel_btn = Gtk.Button(label="ยกเลิก (Cancel)")
        cancel_btn.add_css_class('action-btn')
        cancel_btn.connect('clicked', lambda _: dlg.close())
        btn_box.append(cancel_btn)

        dlg.present()

    # ---------------------------------------------------------
    # Trigger Network Rescan (Non-blocking background thread)
    # ---------------------------------------------------------
    def trigger_network_rescan(self):
        self.alarm_text.set_text("กำลังอ่านสถานะเครือข่ายของเครื่องนี้...")
        t = threading.Thread(target=self.network_rescan_worker, daemon=True)
        t.start()

    def network_rescan_worker(self):
        # 1. Real Carrier Check for SCADA LAN (enp0s31f6) — strictly read-only sysfs
        scada_carrier = check_interface_carrier('enp0s31f6')

        # 2. Zero network pings (Safety: No automated probes on OT LAN)
        pings = {}

        # 3. Internet state (Read current known state; no automated outbound socket)
        has_net = self.internet_online

        # Store in live_status
        self.live_status['scada_carrier'] = scada_carrier
        self.live_status['pings'] = pings

        # Dispatch UI update
        GLib.idle_add(self.apply_network_rescan_results, has_net)

    def update_local_nic_badge(self, carrier):
        network = getattr(getattr(self, 'f3_network_view', None), 'local_state', {})
        status = local_snapshot_state(network)
        name = network.get('active_interface') or network.get('default_gw_iface')
        item = network.get('interfaces', {}).get(name, {})
        observed = item.get('carrier')
        link = ('LINK' if observed is True else 'NO-CARRIER' if observed is False else 'UNKNOWN') if status == 'OBSERVED_LOCAL' else status
        self.pill_scada_ip.set_text(f"Local NIC {name or ''}: {link}")
        self.pill_scada_ip.set_tooltip_text(f"{name or 'UNKNOWN'}: {item.get('ipv4') or 'IPv4 UNKNOWN'} · {status}\nPassive local carrier only; independent from OPC UA, PLC health and tag quality.")
        for style in ('badge-active', 'badge-nope'):
            self.pill_scada_ip.remove_css_class(style)
        self.pill_scada_ip.add_css_class('badge-standby')

    def apply_network_rescan_results(self, has_net):
        self.internet_online = has_net
        scada_carrier = self.live_status.get('scada_carrier', False)
        if hasattr(self, 'pill_scada_ip'):
            self.update_local_nic_badge(scada_carrier)

        if hasattr(self, 'pill_net'):
            if has_net is None:
                self.pill_net.set_text("Internet: ยังไม่ได้ตรวจสอบ")
                self.pill_net.remove_css_class('badge-gateway')
                self.pill_net.remove_css_class('badge-no-net')
                self.pill_net.add_css_class('badge-standby')
                self.alarm_text.set_text("อัปเดตข้อมูลเครือข่ายเครื่องนี้แล้ว • Internet ยังไม่ได้ตรวจสอบ")
            elif has_net:
                self.pill_net.set_text("🟢 Internet Online")
                self.pill_net.remove_css_class('badge-standby')
                self.pill_net.remove_css_class('badge-no-net')
                self.pill_net.add_css_class('badge-gateway')
                self.alarm_text.set_text("สถานะจริง: วงเราเตอร์ 4G ONLINE | วง SCADA (enp0s31f6): nope (ไม่พบการต่อสาย)")
            else:
                self.pill_net.set_text("⚠️ Internet Offline")
                self.pill_net.remove_css_class('badge-standby')
                self.pill_net.remove_css_class('badge-gateway')
                self.pill_net.add_css_class('badge-no-net')
                self.alarm_text.set_text("สถานะจริง: ไม่สามารถออกเน็ตได้ | วง SCADA: nope (ไม่พบการต่อสาย)")

        self.topology_canvas.queue_draw()
        self.render_network_table()
        return False

    # ---------------------------------------------------------
    # Global Function Keys Controller (F1–F9)
    # ---------------------------------------------------------
    def on_global_key_pressed(self, controller, keyval, keycode, state):
        # Program Settings shortcut (Ctrl+,)
        if hasattr(Gdk, 'ModifierType') and (state & Gdk.ModifierType.CONTROL_MASK) and keyval == getattr(Gdk, 'KEY_comma', 44):
            self.switch_to_tab('alarms')
            return True

        key_map = {
            Gdk.KEY_F1: 'overview',
            Gdk.KEY_F2: 'tasks',
            Gdk.KEY_F3: 'network',
            Gdk.KEY_F4: 'machine',
            Gdk.KEY_F5: 'tags',
            Gdk.KEY_F6: 'alarms',
        }
        if keyval in key_map:
            self.switch_to_tab(key_map[keyval])
            return True
        elif keyval == Gdk.KEY_F7:
            self.trigger_rescan()
            return True
        elif keyval == Gdk.KEY_F8:
            self.close()
            return True
        elif keyval == Gdk.KEY_F9:
            self.show_help_manual(None)
            return True
        return False


    # ---------------------------------------------------------
    # TAB 3: Real Host Machine Diagnostics
    # ---------------------------------------------------------
    def build_machine_page(self):
        scrolled = Gtk.ScrolledWindow()
        scrolled.set_hexpand(True)
        scrolled.set_vexpand(True)
        vbox = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
        vbox.set_margin_start(14)
        vbox.set_margin_end(14)
        vbox.set_margin_top(10)
        vbox.set_margin_bottom(10)
        scrolled.set_child(vbox)

        title = Gtk.Label(label='ข้อมูลเครื่องที่รัน AQUA COMMAND', xalign=0)
        title.add_css_class('page-title')
        vbox.append(title)
        hint = Gtk.Label(label='รายละเอียดของเครื่องที่เปิด AQUA COMMAND · ตรวจการเชื่อมต่อ WinCC ได้ในผังการสื่อสาร', xalign=0)
        hint.add_css_class('page-hint')
        vbox.append(hint)

        columns = Gtk.Grid(column_spacing=12, row_spacing=12, column_homogeneous=True)
        vbox.append(columns)
        self.machine_labels = {}
        sections = (
            ('ระบบ', 0, 0, (
                ('ชื่อเครื่อง', 'hostname'), ('ระบบปฏิบัติการ', 'os_name'),
                ('เคอร์เนล', 'kernel'), ('สถาปัตยกรรม', 'arch'),
                ('เวลาเปิดต่อเนื่อง', 'uptime_str'),
            )),
            ('หน่วยประมวลผลและ RAM', 1, 0, (
                ('รุ่น CPU', 'cpu_model'), ('จำนวนคอร์', 'cpu_cores'),
                ('โหลด CPU', 'cpu_load'), ('RAM ทั้งหมด', 'ram_total_gb'),
                ('RAM ที่ใช้', 'ram_used_gb'), ('RAM ว่าง', 'ram_avail_gb'),
            )),
            ('เครือข่ายในเครื่อง', 0, 1, (('IP ประจำเครื่อง', 'ip_lan'),)),
            ('พื้นที่จัดเก็บ', 1, 1, (
                ('ทั้งหมด', 'disk_total_gb'), ('ที่ใช้', 'disk_used_gb'), ('ว่าง', 'disk_avail_gb'),
            )),
        )
        for heading, column, row, fields in sections:
            card = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
            card.add_css_class('wincc-group')
            columns.attach(card, column, row, 1, 1)
            caption = Gtk.Label(label=heading, xalign=0)
            caption.add_css_class('group-title')
            card.append(caption)
            grid = Gtk.Grid(column_spacing=16, row_spacing=8)
            card.append(grid)
            for index, (name, key) in enumerate(fields):
                field = Gtk.Label(label=name, xalign=0)
                field.add_css_class('page-hint')
                grid.attach(field, 0, index, 1, 1)
                value = Gtk.Label(label='กำลังโหลด…', xalign=0, selectable=True, wrap=True, hexpand=True)
                value.set_wrap_mode(Pango.WrapMode.WORD_CHAR)
                grid.attach(value, 1, index, 1, 1)
                self.machine_labels[key] = value

        self.stack.add_named(scrolled, 'machine')

    # ---------------------------------------------------------


    # ---------------------------------------------------------
    # Non-Blocking Asynchronous Scan Engine (Zero Freezing)
    # ---------------------------------------------------------
    def auto_scan_tick(self):
        """Runs every 1 second via GLib. Manages countdown, intervals, and duration without blocking GUI."""
        if not self.auto_scan_active:
            if hasattr(self, 'auto_scan_badge'):
                self.auto_scan_badge.set_text("⏹️ Auto Scan: ปิดอยู่ (กดเพื่อเปิด)")
                self.auto_scan_badge.remove_css_class('badge-active')
                self.auto_scan_badge.add_css_class('badge-standby')
            return True

        now = time.time()
        elapsed = now - self.auto_scan_start_time

        # Check total duration limit (e.g. 1 hour = 3600 seconds)
        if self.auto_scan_duration > 0 and elapsed >= self.auto_scan_duration:
            self.auto_scan_active = False
            if hasattr(self, 'btn_auto_scan'):
                self.btn_auto_scan.set_label("▶️ เริ่ม Auto Scan")
                self.btn_auto_scan.remove_css_class('btn-autoscan-stop')
                self.btn_auto_scan.add_css_class('btn-autoscan-start')
                self.auto_scan_badge.set_text("⏹️ Auto Scan: ครบกำหนดเวลาแล้ว")
                self.auto_scan_remaining_lbl.set_text("⏳ เวลาที่เหลือ: ครบกำหนด (หยุดอัตโนมัติ)")
            self.alarm_text.set_text(f"สแกนอัตโนมัติครบ 1 ชม. เรียบร้อยแล้ว (สแกนสำเร็จทั้งหมด {self.auto_scan_cycles} รอบ)")
            return True

        # Decrement countdown
        self.auto_scan_countdown -= 1
        if self.auto_scan_countdown <= 0:
            # Trigger background scan without blocking main thread!
            self.trigger_single_scan(silent=True)
            self.auto_scan_countdown = self.auto_scan_interval
            self.auto_scan_cycles += 1
            self.auto_scan_last_time = datetime.now().strftime("%H:%M:%S")

        # Update Live Badges (Immediate, zero latency)
        rem_sec = max(0, self.auto_scan_duration - elapsed) if self.auto_scan_duration > 0 else 0
        rem_text = format_duration(rem_sec) if self.auto_scan_duration > 0 else "รันต่อเนื่อง"

        if hasattr(self, 'auto_scan_badge'):
            self.auto_scan_badge.set_text(f"🟢 AUTO SCAN: ทำงาน (ทุกๆ {self.auto_scan_interval}วิ)")
            self.auto_scan_badge.remove_css_class('badge-standby')
            self.auto_scan_badge.add_css_class('badge-active')
            self.auto_scan_countdown_lbl.set_text(f"⏱️ สแกนรอบถัดไป: {self.auto_scan_countdown}s")
            self.auto_scan_remaining_lbl.set_text(f"⏳ เหลือเวลา: {rem_text}")
            self.auto_scan_cycle_lbl.set_text(f"🔄 สแกนแล้ว: {self.auto_scan_cycles} รอบ")
            self.auto_scan_last_time_lbl.set_text(f"🕒 ล่าสุด: {self.auto_scan_last_time}")

        return True

    def trigger_single_scan(self, silent=False):
        """Launches asynchronous background scan. Never blocks the GTK main event loop."""
        if self.scan_in_progress:
            return # A scan is already running in background, do not pile up
        self.scan_in_progress = True
        t = threading.Thread(target=self.async_full_scan_worker, args=(silent,), daemon=True)
        t.start()

    def async_full_scan_worker(self, silent):
        """Runs strictly in background daemon thread (Zero automated network probes)."""
        try:
            # 1. Zero network ping probes (Safety: Strictly passive local discovery)
            pings = {}

            # 2. Check Carrier
            scada_carrier = check_interface_carrier('enp0s31f6')

            # 3. Internet status (Preserves current known state, zero auto probes)
            has_net = self.internet_online

            # 4. Check if Tag file modified
            tag_file_changed = False
            try:
                mtime = os.path.getmtime(DEFAULT_WINCC_EXPORT)
                if mtime != self.last_tag_file_mtime:
                    self.last_tag_file_mtime = mtime
                    tag_file_changed = True
            except Exception:
                pass

            new_tags = scan_wincc_tags(DEFAULT_WINCC_EXPORT) if tag_file_changed else None

            # 5. Read host metrics (passive, safe local metrics)
            metrics = read_real_machine_data()

            # Package and deliver to main thread
            res_data = {
                'pings': pings,
                'scada_carrier': scada_carrier,
                'has_net': has_net,
                'new_tags': new_tags,
                'metrics': metrics,
            }
            GLib.idle_add(self.apply_async_scan_results, res_data, silent)

        except Exception as e:
            print(f"Async scan error: {e}", file=sys.stderr)
            self.scan_in_progress = False

    def apply_async_scan_results(self, res, silent):
        """Runs safely on GTK Main Thread: updates widgets quickly."""
        try:
            self.live_status['scada_carrier'] = res['scada_carrier']
            self.live_status['pings'] = res['pings']
            self.internet_online = res['has_net']

            if res.get('new_tags'):
                self.scanned_tags = res['new_tags']
                self.pill_scan.set_text(f"คลัง {len(self.scanned_tags)} Tag")
                self.pill_scan.remove_css_class('badge-nope')
                self.pill_scan.add_css_class('badge-active')
                if hasattr(self, 'render_dynamic_overview'):
                    self.render_dynamic_overview()
                if hasattr(self, 'render_tags_grid'):
                    self.render_tags_grid()
                if hasattr(self, 'render_tags_page_grid'):
                    self.render_tags_page_grid()

            # Update top pills (Zero emojis, no raw IP in header)
            self.update_local_nic_badge(res['scada_carrier'])

            if res['has_net'] is None:
                self.pill_net.set_text("Internet: ยังไม่ได้ตรวจสอบ")
                self.pill_net.remove_css_class('badge-gateway')
                self.pill_net.remove_css_class('badge-no-net')
                self.pill_net.add_css_class('badge-standby')
                if hasattr(self, 'pill_net_status'):
                    self.pill_net_status.set_text("Internet: ยังไม่ได้ตรวจสอบ")
            elif res['has_net']:
                self.pill_net.set_text("Internet: Online")
                self.pill_net.remove_css_class('badge-standby')
                self.pill_net.remove_css_class('badge-no-net')
                self.pill_net.add_css_class('badge-gateway')
                if hasattr(self, 'pill_net_status'):
                    self.pill_net_status.set_text("Internet: Online")
            else:
                self.pill_net.set_text("Internet: Offline")
                self.pill_net.remove_css_class('badge-standby')
                self.pill_net.remove_css_class('badge-gateway')
                self.pill_net.add_css_class('badge-no-net')
                if hasattr(self, 'pill_net_status'):
                    self.pill_net_status.set_text("Internet: Offline")

            # Redraw Topology Canvas and Table
            if hasattr(self, 'topology_canvas'):
                self.topology_canvas.queue_draw()
            if hasattr(self, 'render_network_table'):
                self.render_network_table()

            # Update Machine Diagnostics
            m = res['metrics']
            if hasattr(self, 'machine_labels') and 'hostname' in self.machine_labels:
                self.machine_labels['cpu_load'].set_text(m['cpu_load'])
                self.machine_labels['ram_used_gb'].set_text(f"{m['ram_used_gb']:.2f} GB ({m['ram_pct']:.1f}%)")
                self.machine_labels['ram_avail_gb'].set_text(f"{m['ram_avail_gb']:.2f} GB")
                self.machine_labels['uptime_str'].set_text(m['uptime_str'])
                self.machine_labels['ip_lan'].set_text(m['ip_lan'])

            if not silent:
                self.alarm_text.set_text(f"สแกนสด 1 ครั้งสำเร็จ: พบ {len(self.scanned_tags)} Tags | ตรวจสอบสถานะฮาร์ดแวร์จริงเรียบร้อย")

        finally:
            self.scan_in_progress = False

        return False # Ensure GLib.idle_add does not repeat

    def toggle_auto_scan(self, _=None):
        """Toggles Auto-Scan ON or OFF."""
        self.auto_scan_active = not self.auto_scan_active
        if self.auto_scan_active:
            self.auto_scan_start_time = time.time()
            self.auto_scan_cycles = 0
            self.auto_scan_countdown = self.auto_scan_interval
            self.btn_auto_scan.set_label("หยุด Auto Scan")
            self.btn_auto_scan.remove_css_class('f2-btn-auto-start')
            self.btn_auto_scan.remove_css_class('btn-autoscan-start')
            self.btn_auto_scan.add_css_class('f2-btn-auto-stop')
            self.trigger_single_scan(silent=True)
            dur_str = "1 ชั่วโมง" if self.auto_scan_duration == 3600 else f"{self.auto_scan_duration}s"
            self.alarm_text.set_text(f"เริ่ม Auto Scan: สแกนทุกๆ {self.auto_scan_interval}วิ (กำหนดระยะเวลารวม {dur_str})")
        else:
            self.btn_auto_scan.set_label("เริ่ม Auto Scan")
            self.btn_auto_scan.remove_css_class('f2-btn-auto-stop')
            self.btn_auto_scan.remove_css_class('btn-autoscan-stop')
            self.btn_auto_scan.add_css_class('f2-btn-auto-start')
            self.alarm_text.set_text(f"สั่งหยุด Auto Scan แล้ว (สแกนสำเร็จไปทั้งหมด {self.auto_scan_cycles} รอบ)")

        if hasattr(self, 'f2_tasks_view'):
            self.f2_tasks_view.load_current_task_to_ui()

    def on_scan_interval_changed(self, drop_down, *args):
        opts = [1, 5, 10, 30, 60]
        idx = drop_down.get_selected()
        if 0 <= idx < len(opts):
            self.auto_scan_interval = opts[idx]
            self.auto_scan_countdown = self.auto_scan_interval
            self.alarm_text.set_text(f"ปรับรอบเวลาสแกนอัตโนมัติเป็น: ทุกๆ {self.auto_scan_interval} วินาที")

    def on_scan_duration_changed(self, drop_down, *args):
        # 0: 1 hr (3600s), 1: continuous (0), 2: 2 hrs (7200s), 3: 8 hrs (28800s)
        dur_map = [3600, 0, 7200, 28800]
        idx = drop_down.get_selected()
        if 0 <= idx < len(dur_map):
            self.auto_scan_duration = dur_map[idx]
            self.auto_scan_start_time = time.time()
            dur_name = "1 ชั่วโมง" if self.auto_scan_duration == 3600 else ("ต่อเนื่อง" if self.auto_scan_duration == 0 else f"{self.auto_scan_duration//3600} ชม.")
            self.alarm_text.set_text(f"ปรับระยะเวลาสแกนอัตโนมัติทั้งหมดเป็น: {dur_name}")


    # TAB 4: Discovered Tag Library Table (All 457 Tags)
    # ---------------------------------------------------------
    def build_tags_page(self):
        scrolled = Gtk.ScrolledWindow()
        scrolled.set_hexpand(True)
        scrolled.set_vexpand(True)
        vbox = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        vbox.set_margin_start(14)
        vbox.set_margin_end(14)
        vbox.set_margin_top(10)
        vbox.set_margin_bottom(10)
        scrolled.set_child(vbox)

        header = Gtk.Box(spacing=10)
        vbox.append(header)
        heading = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4, hexpand=True)
        header.append(heading)
        self.tags_page_title = Gtk.Label(xalign=0)
        self.tags_page_title.add_css_class('page-title')
        heading.append(self.tags_page_title)
        hint = Gtk.Label(label='รายชื่อจากไฟล์ WinCC · เปิดหน้าติดตามค่าเพื่อดูผลอ่านหรือเพิ่ม Tag เข้า Task', xalign=0)
        hint.add_css_class('page-hint')
        heading.append(hint)
        rescan = Gtk.Button(label='รีเฟรชคลัง', valign=Gtk.Align.CENTER)
        rescan.add_css_class('fkey-btn')
        rescan.connect('clicked', lambda _: self.trigger_rescan())
        header.append(rescan)
        workspace = getattr(self, 'unified_workspace', None)
        if workspace and workspace.f1_api:
            for control in (workspace.btn_auto_scan, workspace.badge_scan_status):
                workspace.top_box.remove(control)
                control.set_valign(Gtk.Align.CENTER)
                header.append(control)

        self.tags_page_grid = Gtk.Grid(column_spacing=1, row_spacing=1)
        self.tags_page_grid.add_css_class('data-table')
        vbox.append(self.tags_page_grid)
        self.tags_page_dirty = True
        self.stack.add_named(scrolled, 'tags')

    def render_tags_page_grid(self):
        self.tags_page_dirty = True
        if self.stack.get_visible_child_name() != 'tags':
            return
        self.tags_page_dirty = False
        while self.tags_page_grid.get_first_child():
            self.tags_page_grid.remove(self.tags_page_grid.get_first_child())

        self.tags_page_title.set_text(f"คลัง Tag · {len(self.scanned_tags)} รายการ")

        hybrid = getattr(self, 'hybrid_ui', None)
        show_trends = bool(hybrid and hybrid.bridge)
        headers = ["ชื่อ Tag", "กลุ่มอุปกรณ์", "ชนิดข้อมูล", "ที่อยู่ PLC", "การเชื่อมต่อ"]
        if show_trends:
            headers.append("ประวัติ")
        for col, h in enumerate(headers):
            th = Gtk.Label(label=h)
            th.add_css_class('table-th')
            th.set_xalign(0.0)
            self.tags_page_grid.attach(th, col, 0, 1, 1)

        if not self.scanned_tags:
            empty_lbl = Gtk.Label(label="ยังไม่มี Tag ในคลัง · กดรีเฟรชคลัง เพื่ออ่านไฟล์ WinCC")
            empty_lbl.add_css_class('table-td')
            empty_lbl.set_xalign(0.0)
            self.tags_page_grid.attach(empty_lbl, 0, 1, len(headers), 1)
            return

        for row, t in enumerate(self.scanned_tags, 1):
            for col, val in enumerate([t['name'], t['group'], t['type'], t['addr'], t['conn']]):
                td = Gtk.Label(label=val)
                td.add_css_class('table-td')
                td.set_xalign(0.0)
                td.set_selectable(True)
                td.set_wrap(True)
                td.set_wrap_mode(Pango.WrapMode.WORD_CHAR)
                td.set_hexpand(col in (0, 1, 3))
                if row % 2 == 0:
                    td.add_css_class('alternate')
                self.tags_page_grid.attach(td, col, row, 1, 1)
            if show_trends:
                trend = Gtk.Button(label="Trend")
                trend.set_tooltip_text("เปิดประวัติ Tag ใน Grafana แบบอ่านอย่างเดียว")
                trend.connect('clicked', lambda _, name=t['name']: hybrid.open('tags', tag=name))
                self.tags_page_grid.attach(trend, 5, row, 1, 1)

    # ---------------------------------------------------------
    # TAB 5: WinCC Alarm & Event Logging
    # ---------------------------------------------------------
    def build_alarms_page(self):
        def label(text, css=''):
            widget = Gtk.Label(label=text, xalign=0, wrap=True)
            widget.set_wrap_mode(Pango.WrapMode.WORD_CHAR)
            if css:
                widget.add_css_class(css)
            return widget

        def status(text):
            return label(text, 'badge-standby')

        def action(text, handler, primary=False):
            button = Gtk.Button(label=text)
            button.add_css_class('f6-primary' if primary else 'f6-action')
            button.connect('clicked', handler)
            return button

        def grid_row(grid, row, caption, widget):
            grid.attach(label(caption, 'f6-field-label'), 0, row, 1, 1)
            widget.set_hexpand(True)
            grid.attach(widget, 1, row, 1, 1)

        def add_section(key, title):
            scroll = Gtk.ScrolledWindow()
            scroll.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
            body = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=14)
            body.add_css_class('f6-body')
            scroll.set_child(body)
            self.f6_sections.add_titled(scroll, key, title)
            return body

        def add_columns(body, left_span=1):
            grid = Gtk.Grid(column_spacing=14, column_homogeneous=True)
            body.append(grid)
            left = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=14, valign=Gtk.Align.START)
            right = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=14, valign=Gtk.Align.START)
            grid.attach(left, 0, 0, left_span, 1)
            grid.attach(right, left_span, 0, 1, 1)
            return left, right

        def add_card(body, title, description):
            card = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)
            card.add_css_class('f6-card')
            body.append(card)
            card.append(label(title, 'f6-card-title'))
            if description:
                card.append(label(description, 'f6-help'))
            return card

        page = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        page.add_css_class('f6-settings')

        header = Gtk.Box(spacing=20)
        header.add_css_class('f6-header')
        page.append(header)
        title = label('ตั้งค่าการเชื่อมต่อ', 'f6-page-title')
        title.set_hexpand(True)
        header.append(title)

        self.f6_sections = Gtk.Stack(vexpand=True)
        self.f6_sections.set_hhomogeneous(False)
        self.f6_sections.set_vhomogeneous(False)
        switcher = Gtk.StackSwitcher(stack=self.f6_sections)
        header.append(switcher)
        page.append(self.f6_sections)

        opc = add_section('opcua', 'WinCC OPC UA')
        connection_column, certificate_column = add_columns(opc, left_span=2)
        connection = add_card(connection_column, 'เชื่อมต่อ WinCC',
                              'กรอก URL ของเซิร์ฟเวอร์เพื่ออ่านข้อมูลผ่าน OPC UA แบบอ่านอย่างเดียว')
        certificates = add_card(certificate_column, 'ใบรับรอง OPC UA', '')
        monitoring = add_card(opc, 'อ่านค่าอัตโนมัติ',
                              'ตรวจการเชื่อมต่อก่อนเริ่มอ่านตามรอบ การแจ้งเตือนทำงานตาม Task ที่ตั้งไว้')
        fields = Gtk.Grid(column_spacing=16, row_spacing=8)
        connection.append(fields)
        self.entry_opc_url = Gtk.Entry(placeholder_text='opc.tcp://ชื่อเซิร์ฟเวอร์:พอร์ต')
        self.entry_opc_url.set_text(self.opcua_config.get('endpoint_url', ''))
        grid_row(fields, 0, 'URL เซิร์ฟเวอร์', self.entry_opc_url)

        self.opc_sec_combo = Gtk.DropDown.new_from_strings([
            'None · ไม่เข้ารหัส', 'Basic256Sha256 · ลงนามและเข้ารหัส',
        ])
        self.opc_sec_combo.set_selected(int(self.opcua_config.get('security_policy') == 'Basic256Sha256'))
        grid_row(fields, 1, 'ความปลอดภัย', self.opc_sec_combo)

        self.opc_auth_combo = Gtk.DropDown.new_from_strings([
            'Anonymous · ไม่ใช้บัญชี', 'Username · ใช้บัญชี',
        ])
        self.opc_auth_combo.set_selected(int(self.opcua_config.get('auth_mode') == 'Username'))
        grid_row(fields, 2, 'เข้าสู่ระบบ', self.opc_auth_combo)

        self.f6_opc_credentials = Gtk.Box(spacing=8)
        fields.attach(self.f6_opc_credentials, 1, 3, 1, 1)
        self.entry_opc_user = Gtk.Entry(placeholder_text='ชื่อผู้ใช้', hexpand=True)
        self.entry_opc_user.set_text(self.opcua_config.get('username', ''))
        self.f6_opc_credentials.append(self.entry_opc_user)
        self.entry_opc_pass = Gtk.Entry(placeholder_text='รหัสผ่าน · ใช้เฉพาะรอบนี้', hexpand=True)
        self.entry_opc_pass.set_visibility(False)
        self.entry_opc_pass.set_input_purpose(Gtk.InputPurpose.PASSWORD)
        self.f6_opc_credentials.append(self.entry_opc_pass)
        self.f6_opc_credentials.set_visible(self.opc_auth_combo.get_selected() == 1)
        self.opc_auth_combo.connect(
            'notify::selected', lambda combo, _: self.f6_opc_credentials.set_visible(combo.get_selected() == 1)
        )

        self.lbl_pki_server_trust = status('ยังไม่ได้ตรวจใบรับรองเซิร์ฟเวอร์')
        certificates.append(self.lbl_pki_server_trust)
        self.f6_certificate = Gtk.Expander(label='ดูรายละเอียดใบรับรอง')
        self.f6_certificate.add_css_class('f6-disclosure')
        certificates.append(self.f6_certificate)
        cert_panel = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        cert_panel.add_css_class('f6-certificate')
        self.f6_certificate.set_child(cert_panel)

        client_description = 'ระบบจะสร้างใบรับรองแอปเมื่อจำเป็น'
        if self.pki.client_cert_der.is_file():
            try:
                cert = self.pki.load_cert_from_file(self.pki.client_cert_der)
                client_description = f'ใบรับรองแอป · SHA-256 {self.pki.cert_thumbprint(cert)[:16]}…'
            except Exception:
                pass
        self.lbl_pki_client_cert = label(client_description, 'f6-help')
        cert_panel.append(self.lbl_pki_client_cert)
        self.lbl_pki_server_details = label('', 'f6-help')
        self.lbl_pki_server_details.set_selectable(True)
        cert_panel.append(self.lbl_pki_server_details)
        self.btn_trust_quarantined = action('ยืนยัน Fingerprint และอนุมัติ', self.on_trust_quarantined_certificate)
        self.btn_trust_quarantined.set_sensitive(False)
        self.btn_trust_quarantined.set_halign(Gtk.Align.START)
        cert_panel.append(self.btn_trust_quarantined)

        self.lbl_opc_status = status('ยังไม่ได้ทดสอบการเชื่อมต่อ')
        connection.append(self.lbl_opc_status)
        opc_actions = Gtk.Box(spacing=8, halign=Gtk.Align.END)
        connection.append(opc_actions)
        self.btn_test_opc = action('ทดสอบการเชื่อมต่อ', self.on_test_opcua_connection)
        self.btn_browse_opc = action('ค้นหา Tag', self.on_browse_opcua_tags)
        opc_actions.append(action('บันทึก WinCC', self.on_save_opcua_config, primary=True))
        opc_actions.append(self.btn_test_opc)
        opc_actions.append(self.btn_browse_opc)

        monitoring_controls = Gtk.Box(spacing=12)
        monitoring.append(monitoring_controls)
        self.lbl_mon_telemetry = status('STOPPED (หยุดอยู่)')
        self.lbl_mon_telemetry.set_hexpand(True)
        monitoring_controls.append(self.lbl_mon_telemetry)
        monitoring_actions = Gtk.Box(spacing=8)
        monitoring_controls.append(monitoring_actions)
        self.btn_start_monitoring = action('เริ่มอ่าน', self.on_start_monitoring_clicked)
        self.btn_pause_monitoring = action('พัก', self.on_pause_monitoring_clicked)
        self.btn_stop_monitoring = action('หยุด', self.on_stop_monitoring_clicked)
        self.btn_pause_monitoring.set_sensitive(False)
        self.btn_stop_monitoring.set_sensitive(False)
        monitoring_actions.append(self.btn_start_monitoring)
        monitoring_actions.append(self.btn_pause_monitoring)
        monitoring_actions.append(self.btn_stop_monitoring)

        if __package__:
            from .telemetry_settings import TelemetrySettings
        else:
            from telemetry_settings import TelemetrySettings

        sources = add_section('telemetry', 'แหล่งข้อมูล')
        source_column, reader_column = add_columns(sources, left_span=2)
        source_form = add_card(source_column, 'เลือกแหล่งข้อมูล', 'แหล่งที่เลือกใช้แสดงผลในหน้าติดตามค่า')
        reader_controls = add_card(reader_column, 'การอ่านข้อมูล', 'อ่านครั้งเดียวเพื่อตรวจค่า หรือเริ่มอ่านตามรอบ')
        self.telemetry_settings = TelemetrySettings(self, source_form, reader_controls, label, action, status)

        telegram = add_section('telegram', 'Telegram')
        destination_column, test_column = add_columns(telegram)
        destination = add_card(destination_column, 'ปลายทางแจ้งเตือน', 'ระบุ Bot Token และ Chat ID ที่จะรับข้อความ')
        tg_fields = Gtk.Grid(column_spacing=16, row_spacing=8)
        destination.append(tg_fields)
        self.entry_tg_token = Gtk.Entry(placeholder_text='Token จาก BotFather')
        self.entry_tg_token.set_visibility(False)
        self.entry_tg_token.set_input_purpose(Gtk.InputPurpose.PASSWORD)
        self.entry_tg_token.set_text(self.telegram_config.get('bot_token', ''))
        grid_row(tg_fields, 0, 'Bot Token', self.entry_tg_token)
        self.entry_tg_chat_id = Gtk.Entry(placeholder_text='Chat ID ของผู้ใช้หรือกลุ่ม')
        self.entry_tg_chat_id.set_text(self.telegram_config.get('chat_id', ''))
        grid_row(tg_fields, 1, 'Chat ID', self.entry_tg_chat_id)

        save_tg = action('บันทึกปลายทาง', self.on_save_telegram_config, primary=True)
        save_tg.set_halign(Gtk.Align.END)
        destination.append(save_tg)

        test = add_card(test_column, 'ทดสอบการแจ้งเตือน',
                        'เมื่อกดส่ง ระบบจะบันทึกปลายทางและส่งข้อความจริงไปยัง Chat ID ที่กรอก')
        self.entry_tg_test_msg = Gtk.Entry(placeholder_text='ข้อความที่จะส่ง')
        self.entry_tg_test_msg.set_text('ข้อความทดสอบจาก AQUA COMMAND')
        test.append(self.entry_tg_test_msg)
        self.btn_test_tg = action('ส่งข้อความทดสอบจริง', self.on_test_telegram_send)
        self.btn_test_tg.set_halign(Gtk.Align.END)
        test.append(self.btn_test_tg)
        self.lbl_tg_status = status('ยังไม่ได้ทดสอบส่ง')
        test.append(self.lbl_tg_status)

        history = add_section('history', 'ประวัติเหตุการณ์')
        events = add_card(history, 'ประวัติเหตุการณ์', 'แสดงเหตุการณ์ล่าสุดของโปรแกรม สูงสุด 25 รายการ')
        self.f6_history_empty = label('ยังไม่มีเหตุการณ์', 'f6-help')
        events.append(self.f6_history_empty)
        self.alarm_grid = Gtk.Grid(column_spacing=1, row_spacing=1)
        self.alarm_grid.add_css_class('data-table')
        events.append(self.alarm_grid)
        self.render_alarm_table()

        self.f6_sections.set_visible_child_name('opcua')
        self.stack.add_named(page, 'alarms')

    def render_alarm_table(self):
        while self.alarm_grid.get_first_child():
            self.alarm_grid.remove(self.alarm_grid.get_first_child())

        has_events = bool(self.alarm_events)
        self.f6_history_empty.set_visible(not has_events)
        self.alarm_grid.set_visible(has_events)
        if not has_events:
            return

        headers = ["เวลา", "แหล่งที่มา", "ระดับ", "สถานะ", "รายละเอียด"]
        for col, h in enumerate(headers):
            th = Gtk.Label(label=h)
            th.add_css_class('table-th')
            th.set_xalign(0.0)
            self.alarm_grid.attach(th, col, 0, 1, 1)

        for row, r_data in enumerate(self.alarm_events[:25], 1):
            for col, val in enumerate(r_data):
                td = Gtk.Label(label=str(val))
                td.add_css_class('table-td')
                td.set_xalign(0.0)
                td.set_selectable(True)
                td.set_wrap(True)
                td.set_wrap_mode(Pango.WrapMode.WORD_CHAR)
                if col == 4:
                    td.set_max_width_chars(54)
                    td.set_hexpand(True)
                if col == 2 and val == 'WARN':
                    td.add_css_class('badge-nope')
                elif col == 2 and val == 'INFO':
                    td.add_css_class('badge-sensor')
                elif col == 3 and val in ('DELIVERED', 'ONLINE', 'ACTIVE'):
                    td.add_css_class('badge-running')
                elif col == 3 and val in ('FAILED', 'NO-CARRIER'):
                    td.add_css_class('badge-stopped')
                self.alarm_grid.attach(td, col, row, 1, 1)

    def add_alarm_event(self, time_str, dev, cls, st, msg):
        self.alarm_events.insert(0, (time_str, dev, cls, st, msg))
        if hasattr(self, 'render_alarm_table'):
            self.render_alarm_table()

    def on_save_opcua_config(self, _=None):
        raw_url = self.entry_opc_url.get_text().strip()
        valid, result = validate_opcua_endpoint(raw_url)
        if not valid:
            self.lbl_opc_status.set_text(f"❌ {result}")
            self.lbl_opc_status.remove_css_class('badge-active')
            self.lbl_opc_status.remove_css_class('badge-standby')
            self.lbl_opc_status.add_css_class('badge-nope')
            self.alarm_text.set_text(f"❌ บันทึกล้มเหลว: {result}")
            return

        url = result
        self.opcua_config['endpoint_url'] = url
        sec_idx = self.opc_sec_combo.get_selected()
        self.opcua_config['security_policy'] = 'Basic256Sha256' if sec_idx == 1 else 'None'
        auth_idx = self.opc_auth_combo.get_selected()
        self.opcua_config['auth_mode'] = 'Username' if auth_idx == 1 else 'Anonymous'
        self.opcua_config['username'] = self.entry_opc_user.get_text().strip()

        # Hold Password strictly in session memory (NEVER write to json config!)
        self.opcua_session_password = self.entry_opc_pass.get_text()

        ok = save_opcua_config(self.opcua_config)
        now_str = datetime.now().strftime("%d/%m/%Y %H:%M:%S")
        if ok:
            self.alarm_text.set_text(f"💾 บันทึกการตั้งค่า WinCC OPC UA ({url}) เรียบร้อยแล้ว (สถานะ: กำหนดค่าแล้ว / ยังไม่เชื่อมต่อ)")
            self.lbl_opc_status.set_text("บันทึกค่า WinCC แล้ว")
            self.lbl_opc_status.remove_css_class('badge-nope')
            self.lbl_opc_status.remove_css_class('badge-active')
            self.lbl_opc_status.add_css_class('badge-standby')
            self.add_alarm_event(now_str, "OPC_UA", "INFO", "CONFIGURED", f"บันทึกการตั้งค่า OPC UA: {url} ({self.opcua_config['security_policy']}, {self.opcua_config['auth_mode']})")
        else:
            self.alarm_text.set_text(f"❌ ไม่สามารถบันทึกไฟล์คอนฟิก {OPCUA_CONFIG_FILE} ได้ (Disk/Permission Error)")
            self.lbl_opc_status.set_text("❌ บันทึกล้มเหลว (I/O Error)")
            self.lbl_opc_status.remove_css_class('badge-standby')
            self.lbl_opc_status.remove_css_class('badge-active')
            self.lbl_opc_status.add_css_class('badge-nope')
            self.add_alarm_event(now_str, "OPC_UA", "WARN", "CONFIG_ERR", f"บันทึกไฟล์คอนฟิก {OPCUA_CONFIG_FILE} ล้มเหลว")

    def on_trust_quarantined_certificate(self, _=None):
        if self.last_quarantined_server_cert and Path(self.last_quarantined_server_cert).is_file():
            trusted_p = self.pki.trust_certificate(Path(self.last_quarantined_server_cert))
            thumb = self.last_quarantined_cert_info.get("thumbprint", "")
            self.lbl_pki_server_trust.set_text("🟢 ได้รับความเชื่อถือแล้ว (TRUSTED)")
            self.lbl_pki_server_trust.remove_css_class('badge-nope')
            self.lbl_pki_server_trust.remove_css_class('badge-standby')
            self.lbl_pki_server_trust.add_css_class('badge-active')
            self.btn_trust_quarantined.set_sensitive(False)
            if thumb:
                self.lbl_pki_server_details.set_text(f"Server SHA-256: {thumb} (Verified & Promoted to trusted/certs/)")
            self.alarm_text.set_text(f"🛡️ อนุมัติความเชื่อถือให้ Server Certificate เรียบร้อยแล้ว: {trusted_p.name}")
            now_str = datetime.now().strftime("%d/%m/%Y %H:%M:%S")
            self.add_alarm_event(now_str, "OPC_UA", "INFO", "TRUSTED", f"ผู้ดูแลระบบยืนยัน Fingerprint และอนุมัติ Server Cert: {trusted_p.name} (SHA-256: {thumb[:16]}...)")
        else:
            self.alarm_text.set_text("⚠️ ไม่พบไฟล์ Certificate ที่ถูกกักกันสำหรับอนุมัติ")

    def on_start_monitoring_clicked(self, _=None):
        raw_url = self.entry_opc_url.get_text().strip()
        valid, result = validate_opcua_endpoint(raw_url)
        if not valid:
            self.lbl_mon_telemetry.set_text(f"❌ {result}")
            return

        sec_policy = 'Basic256Sha256' if self.opc_sec_combo.get_selected() == 1 else 'None'
        auth_mode = 'Username' if self.opc_auth_combo.get_selected() == 1 else 'Anonymous'
        username = self.entry_opc_user.get_text().strip()
        password = self.opcua_session_password or self.entry_opc_pass.get_text()

        # Sync latest tasks into task engine
        self.task_engine.load_tasks(self.tasks)

        ok, msg = self.polling_engine.start_monitoring(
            endpoint_url=result,
            sec_policy=sec_policy,
            auth_mode=auth_mode,
            username=username,
            password=password
        )

        if ok:
            self.notification_worker.start()
            self.btn_start_monitoring.set_sensitive(False)
            self.btn_pause_monitoring.set_sensitive(True)
            self.btn_stop_monitoring.set_sensitive(True)
            self.lbl_mon_telemetry.set_text("เปิดการอ่านอัตโนมัติแล้ว")
            self.lbl_mon_telemetry.remove_css_class('badge-standby')
            self.lbl_mon_telemetry.remove_css_class('badge-nope')
            self.lbl_mon_telemetry.add_css_class('badge-active')
            self.alarm_text.set_text("⏱️ เริ่มต้นระบบเฝ้าระวังอัตโนมัติ (5s Polling Engine Started)")
        else:
            self.lbl_mon_telemetry.set_text(f"❌ ไม่สามารถเริ่มได้: {msg}")
            self.lbl_mon_telemetry.remove_css_class('badge-active')
            self.lbl_mon_telemetry.add_css_class('badge-nope')
            self.alarm_text.set_text(f"❌ Preflight Failed: {msg}")

    def on_pause_monitoring_clicked(self, _=None):
        if self.polling_engine.telemetry.state == PollingState.RUNNING:
            self.polling_engine.pause_monitoring()
            self.btn_pause_monitoring.set_label("อ่านต่อ")
            self.lbl_mon_telemetry.set_text("พักการอ่านชั่วคราว")
            self.lbl_mon_telemetry.remove_css_class('badge-active')
            self.lbl_mon_telemetry.add_css_class('badge-sensor')
        elif self.polling_engine.telemetry.state == PollingState.PAUSED:
            self.polling_engine.resume_monitoring()
            self.btn_pause_monitoring.set_label("พัก")
            self.lbl_mon_telemetry.set_text("เปิดการอ่านอัตโนมัติแล้ว")
            self.lbl_mon_telemetry.remove_css_class('badge-sensor')
            self.lbl_mon_telemetry.add_css_class('badge-active')

    def on_stop_monitoring_clicked(self, _=None):
        self.polling_engine.stop_monitoring()
        self.notification_worker.stop()
        self.btn_start_monitoring.set_sensitive(True)
        self.btn_pause_monitoring.set_sensitive(False)
        self.btn_pause_monitoring.set_label("พัก")
        self.btn_stop_monitoring.set_sensitive(False)
        self.lbl_mon_telemetry.set_text("STOPPED (หยุดอยู่)")
        self.lbl_mon_telemetry.remove_css_class('badge-active')
        self.lbl_mon_telemetry.remove_css_class('badge-sensor')
        self.lbl_mon_telemetry.add_css_class('badge-standby')
        self.alarm_text.set_text("⏹️ หยุดระบบเฝ้าระวังเรียบร้อยแล้ว (Session Disconnected)")

    def _update_trust_quarantined_ui(self, can_trust: bool, label_text: str, cert_info: Optional[dict] = None):
        self.btn_trust_quarantined.set_sensitive(can_trust)
        if can_trust:
            self.f6_certificate.set_expanded(True)
        self.lbl_pki_server_trust.set_text(label_text)
        info = cert_info or self.last_quarantined_cert_info or {}
        if info:
            thumb = info.get("thumbprint", "Unknown")
            subj = info.get("subject", "Unknown")
            uris = ", ".join(info.get("san_uris", [])) or "-"
            dns_ip = ", ".join(info.get("san_dns", []) + info.get("san_ips", [])) or "-"
            issuer = info.get("issuer", "Unknown")
            nb = info.get("not_before", "")[:10]
            na = info.get("not_after", "")[:10]
            details = f"Server SHA-256: {thumb}\nSubject: {subj} | Issuer: {issuer}\nURI: {uris} | SAN: {dns_ip} | Valid: {nb} ถึง {na}"
            self.lbl_pki_server_details.set_text(details)
        else:
            self.lbl_pki_server_details.set_text("")

        if can_trust:
            self.lbl_pki_server_trust.remove_css_class('badge-active')
            self.lbl_pki_server_trust.remove_css_class('badge-standby')
            self.lbl_pki_server_trust.add_css_class('badge-nope')
        elif "TRUSTED" in label_text:
            self.lbl_pki_server_trust.remove_css_class('badge-nope')
            self.lbl_pki_server_trust.remove_css_class('badge-standby')
            self.lbl_pki_server_trust.add_css_class('badge-active')

    def on_test_opcua_connection(self, _=None):
        raw_url = self.entry_opc_url.get_text().strip()
        valid, result = validate_opcua_endpoint(raw_url)
        if not valid:
            self.lbl_opc_status.set_text(f"❌ {result}")
            self.lbl_opc_status.remove_css_class('badge-active')
            self.lbl_opc_status.add_css_class('badge-nope')
            self.alarm_text.set_text(f"❌ {result}")
            return

        url = result
        self.opcua_config['endpoint_url'] = url
        sec_policy = 'Basic256Sha256' if self.opc_sec_combo.get_selected() == 1 else 'None'
        auth_mode = 'Username' if self.opc_auth_combo.get_selected() == 1 else 'Anonymous'
        username = self.entry_opc_user.get_text().strip()
        password = self.opcua_session_password or self.entry_opc_pass.get_text()

        # Security check: Prohibit username/password over SecurityPolicy#None
        if auth_mode == 'Username' and sec_policy == 'None':
            self.lbl_opc_status.set_text("❌ ปฏิเสธ: ไม่อนุญาตให้ส่ง Username/Password ในโหมด None")
            self.lbl_opc_status.remove_css_class('badge-active')
            self.lbl_opc_status.remove_css_class('badge-standby')
            self.lbl_opc_status.add_css_class('badge-nope')
            self.alarm_text.set_text("❌ ข้อผิดพลาดความปลอดภัย: ไม่อนุญาตให้ส่ง Username/Password ผ่านช่องทางที่ไม่เข้ารหัส (SecurityPolicy#None)")
            return

        self.lbl_opc_status.set_text("⏳ กำลังเชื่อมต่อไปยัง WinCC OPC UA Server (Connecting)...")
        self.lbl_opc_status.remove_css_class('badge-nope')
        self.lbl_opc_status.remove_css_class('badge-active')
        self.lbl_opc_status.add_css_class('badge-sensor')
        self.btn_test_opc.set_sensitive(False)

        def worker():
            success = False
            status_name = "Error"
            msg = ""
            if not HAS_ASYNCUA:
                success = False
                status_name = "Error"
                msg = "ไม่พบไลบรารี asyncua บนระบบ"
            else:
                try:
                    async def _probe():
                        client = Client(url=url, timeout=4.0)
                        client.application_uri = self.pki.DEFAULT_APP_URI
                        parsed = urlparse(url)
                        expected_host = parsed.hostname or "127.0.0.1"

                        if sec_policy == 'Basic256Sha256':
                            cert_p, key_p = self.pki.ensure_client_certificate()
                            await client.set_security_string(f"Basic256Sha256,SignAndEncrypt,{cert_p},{key_p}")

                            server_cert = getattr(client.security_policy, "peer_certificate", None)
                            if not server_cert:
                                return False, "BadSecurityChecksFailed", "ไม่พบ Server Certificate ที่รองรับ Basic256Sha256 บนเซิร์ฟเวอร์"

                            server_cert_bytes = server_cert if isinstance(server_cert, bytes) else server_cert.public_bytes(serialization.Encoding.DER)
                            val_res = self.pki.validate_server_certificate(
                                cert_bytes=server_cert_bytes,
                                expected_host=expected_host,
                                check_trust_store=True,
                            )
                            cert_info = val_res.get("cert_info", {})
                            if not val_res["valid"]:
                                q_p = val_res.get("quarantine_path")
                                if q_p:
                                    self.last_quarantined_server_cert = Path(q_p)
                                    self.last_quarantined_cert_info = cert_info
                                    thumb_short = cert_info.get("thumbprint", "")[:16]
                                    GLib.idle_add(self._update_trust_quarantined_ui, True, f"⚠️ Quarantined (SHA-256: {thumb_short}...)", cert_info)
                                else:
                                    GLib.idle_add(self._update_trust_quarantined_ui, False, f"❌ {val_res['status_code']}", cert_info)
                                return False, val_res["status_code"], val_res["error"]
                            else:
                                self.last_quarantined_cert_info = cert_info
                                GLib.idle_add(self._update_trust_quarantined_ui, False, "🟢 ได้รับความเชื่อถือแล้ว (TRUSTED)", cert_info)

                        if auth_mode == 'Username':
                            if not username:
                                return False, "Error", "โหมด Username จำเป็นต้องระบุชื่อผู้ใช้งาน"
                            client.set_user(username)
                            client.set_password(password)

                        async with client:
                            server_name = await client.nodes.server.read_browse_name()
                            GLib.idle_add(self._update_trust_quarantined_ui, False, "🟢 TRUSTED (เชื่อมต่อสำเร็จ)")
                            return True, "Disconnected", f"เชื่อมต่อ WinCC OPC UA สำเร็จ! (Server Node: {server_name.Name}) [เซสชันปิดแล้ว]"

                    loop = asyncio.new_event_loop()
                    try:
                        success, status_name, msg = loop.run_until_complete(_probe())
                    finally:
                        loop.close()
                except Exception as ex:
                    success = False
                    status_name = "Error"
                    err_str = str(ex)
                    # Privacy: sanitize secret password from any error/traceback string
                    if password and password in err_str:
                        err_str = err_str.replace(password, "******")
                    if "BadUserAccessDenied" in err_str or "BadIdentityTokenRejected" in err_str:
                        msg = f"การยืนยันตัวตนล้มเหลว (BadUserAccessDenied) สำหรับผู้ใช้ '{username}'"
                    elif "BadCertificateUntrusted" in err_str:
                        msg = "Server Certificate ไม่ได้รับความเชื่อถือ (BadCertificateUntrusted) ถูกกักกันใน rejected/certs/"
                    elif "BadCertificateHostNameInvalid" in err_str:
                        msg = "Hostname/IP ใน Certificate ไม่ตรงกับ Endpoint (BadCertificateHostNameInvalid)"
                    elif "BadCertificateTimeInvalid" in err_str:
                        msg = "Certificate หมดอายุหรือยังไม่ถึงกำหนดใช้งาน (BadCertificateTimeInvalid)"
                    elif "No matching endpoints" in err_str or "BadSecurityPolicyRejected" in err_str:
                        msg = f"เซิร์ฟเวอร์ปฏิเสธ Security Policy '{sec_policy}'"
                    elif isinstance(ex, (ConnectionRefusedError, asyncio.TimeoutError, OSError)):
                        msg = f"ไม่สามารถเชื่อมต่อได้ ({type(ex).__name__})"
                    else:
                        msg = f"ไม่สามารถเชื่อมต่อได้: {err_str[:75]}"

            GLib.idle_add(self.apply_opcua_test_result, success, status_name, msg)

        t = threading.Thread(target=worker, daemon=True)
        t.start()

    def apply_opcua_test_result(self, success, status_name, detail):
        self.btn_test_opc.set_sensitive(True)
        now_str = datetime.now().strftime("%d/%m/%Y %H:%M:%S")
        if success:
            self.lbl_opc_status.set_text("ทดสอบผ่าน · ปิดการเชื่อมต่อแล้ว")
            self.lbl_opc_status.remove_css_class('badge-nope')
            self.lbl_opc_status.remove_css_class('badge-sensor')
            self.lbl_opc_status.add_css_class('badge-active')
            self.alarm_text.set_text(f"🟢 {detail}")
            self.add_alarm_event(now_str, "OPC_UA", "INFO", "ONLINE", f"เชื่อมต่อ WinCC OPC UA Server สำเร็จ: {detail}")
        else:
            self.lbl_opc_status.set_text(f"❌ {status_name}: {detail[:30]}")
            self.lbl_opc_status.remove_css_class('badge-active')
            self.lbl_opc_status.remove_css_class('badge-sensor')
            self.lbl_opc_status.add_css_class('badge-nope')
            self.alarm_text.set_text(f"❌ เชื่อมต่อ WinCC OPC UA ไม่สำเร็จ: {detail}")
            self.add_alarm_event(now_str, "OPC_UA", "WARN", "OFFLINE", f"เชื่อมต่อ WinCC OPC UA ล้มเหลว: {detail}")

    def on_browse_opcua_tags(self, _=None):
        raw_url = self.entry_opc_url.get_text().strip()
        valid, result = validate_opcua_endpoint(raw_url)
        if not valid:
            self.lbl_opc_status.set_text(f"❌ {result}")
            self.lbl_opc_status.remove_css_class('badge-active')
            self.lbl_opc_status.add_css_class('badge-nope')
            self.alarm_text.set_text(f"❌ {result}")
            return

        url = result
        sec_policy = 'Basic256Sha256' if self.opc_sec_combo.get_selected() == 1 else 'None'
        auth_mode = 'Username' if self.opc_auth_combo.get_selected() == 1 else 'Anonymous'
        username = self.entry_opc_user.get_text().strip()
        password = self.opcua_session_password or self.entry_opc_pass.get_text()

        # Security check: Prohibit username/password over SecurityPolicy#None
        if auth_mode == 'Username' and sec_policy == 'None':
            self.lbl_opc_status.set_text("❌ ปฏิเสธ: ไม่อนุญาตให้ส่ง Username/Password ในโหมด None")
            self.lbl_opc_status.remove_css_class('badge-active')
            self.lbl_opc_status.remove_css_class('badge-standby')
            self.lbl_opc_status.add_css_class('badge-nope')
            self.alarm_text.set_text("❌ ข้อผิดพลาดความปลอดภัย: ไม่อนุญาตให้สแกน Tag โดยส่ง Username/Password ผ่านโหมด None")
            return

        self.lbl_opc_status.set_text("⏳ กำลังสแกนหา Tag จาก WinCC ผ่าน OPC UA...")
        self.lbl_opc_status.remove_css_class('badge-nope')
        self.lbl_opc_status.remove_css_class('badge-active')
        self.lbl_opc_status.add_css_class('badge-sensor')
        self.btn_browse_opc.set_sensitive(False)
        self.browse_cancel_flag.clear()

        def worker():
            success = False
            status_name = "Error"
            found_nodes = []
            msg = ""
            if not HAS_ASYNCUA:
                success = False
                status_name = "Error"
                msg = "ไม่พบไลบรารี asyncua บนระบบ"
            else:
                try:
                    async def _browse():
                        client = Client(url=url, timeout=OPCUA_BROWSE_TIMEOUT)
                        client.application_uri = self.pki.DEFAULT_APP_URI
                        parsed = urlparse(url)
                        expected_host = parsed.hostname or "127.0.0.1"

                        if sec_policy == 'Basic256Sha256':
                            cert_p, key_p = self.pki.ensure_client_certificate()
                            await client.set_security_string(f"Basic256Sha256,SignAndEncrypt,{cert_p},{key_p}")

                            server_cert = getattr(client.security_policy, "peer_certificate", None)
                            if not server_cert:
                                return False, "BadSecurityChecksFailed", [], "ไม่พบ Server Certificate ที่รองรับ Basic256Sha256 บนเซิร์ฟเวอร์"

                            server_cert_bytes = server_cert if isinstance(server_cert, bytes) else server_cert.public_bytes(serialization.Encoding.DER)
                            val_res = self.pki.validate_server_certificate(
                                cert_bytes=server_cert_bytes,
                                expected_host=expected_host,
                                check_trust_store=True,
                            )
                            cert_info = val_res.get("cert_info", {})
                            if not val_res["valid"]:
                                q_p = val_res.get("quarantine_path")
                                if q_p:
                                    self.last_quarantined_server_cert = Path(q_p)
                                    self.last_quarantined_cert_info = cert_info
                                    thumb_short = cert_info.get("thumbprint", "")[:16]
                                    GLib.idle_add(self._update_trust_quarantined_ui, True, f"⚠️ Quarantined (SHA-256: {thumb_short}...)", cert_info)
                                else:
                                    GLib.idle_add(self._update_trust_quarantined_ui, False, f"❌ {val_res['status_code']}", cert_info)
                                return False, val_res["status_code"], [], val_res["error"]
                            else:
                                self.last_quarantined_cert_info = cert_info
                                GLib.idle_add(self._update_trust_quarantined_ui, False, "🟢 ได้รับความเชื่อถือแล้ว (TRUSTED)", cert_info)

                        if auth_mode == 'Username':
                            if not username:
                                return False, "Error", [], "โหมด Username จำเป็นต้องระบุชื่อผู้ใช้งาน"
                            client.set_user(username)
                            client.set_password(password)

                        async with client:
                            nodes = []
                            objects = client.nodes.objects

                            async def _traverse(node, depth, parent_name):
                                if depth > MAX_OPCUA_BROWSE_DEPTH or len(nodes) >= MAX_OPCUA_BROWSE_NODES:
                                    return
                                if self.browse_cancel_flag.is_set():
                                    return
                                children = await node.get_children()
                                for c in children:
                                    if self.browse_cancel_flag.is_set() or len(nodes) >= MAX_OPCUA_BROWSE_NODES:
                                        break
                                    bn = await c.read_browse_name()
                                    if bn.Name in ('Server', 'Aliases', 'Locations'):
                                        continue
                                    node_class = await c.read_node_class()
                                    if node_class == ua.NodeClass.Variable:
                                        nodes.append({
                                            'name': bn.Name,
                                            'node_id': str(c.nodeid),
                                            'parent': parent_name
                                        })
                                    elif node_class == ua.NodeClass.Object:
                                        await _traverse(c, depth + 1, bn.Name)

                            await _traverse(objects, depth=1, parent_name="Objects")

                            if self.browse_cancel_flag.is_set():
                                return False, "Cancelled", nodes, "การ Browse ถูกยกเลิกโดยผู้ใช้"

                            capped = len(nodes) >= MAX_OPCUA_BROWSE_NODES
                            if len(nodes) == 0:
                                return True, "Browse Successful", [], "สแกนสำเร็จแต่ไม่พบตัวแปร (0 Nodes)"
                            if capped:
                                return True, "Browse Incomplete", nodes, f"สแกนพบ {len(nodes)} Nodes (PARTIAL/INCOMPLETE: ถึงขีดจำกัดความปลอดภัย {MAX_OPCUA_BROWSE_NODES} Nodes)"
                            return True, "Browse Successful", nodes, f"สแกนพบ {len(nodes)} Nodes ผ่าน OPC UA สำเร็จ"

                    loop = asyncio.new_event_loop()
                    try:
                        success, status_name, found_nodes, msg = loop.run_until_complete(_browse())
                    finally:
                        loop.close()
                except Exception as ex:
                    success = False
                    status_name = "Error"
                    err_str = str(ex)
                    if password and password in err_str:
                        err_str = err_str.replace(password, "******")
                    if "BadUserAccessDenied" in err_str:
                        msg = "การเข้าถึงล้มเหลว: ถูกปฏิเสธสิทธิ์ (BadUserAccessDenied)"
                    elif isinstance(ex, (ConnectionRefusedError, asyncio.TimeoutError, OSError)):
                        msg = f"การเชื่อมต่อหมดเวลาหรือไม่สามารถติดต่อได้ ({type(ex).__name__})"
                    else:
                        msg = f"Browse ล้มเหลว: {err_str[:70]}"

            GLib.idle_add(self.apply_opcua_browse_result, success, status_name, found_nodes, msg)

        t = threading.Thread(target=worker, daemon=True)
        t.start()

    def apply_opcua_browse_result(self, success, status_name, found_nodes, msg):
        self.btn_browse_opc.set_sensitive(True)
        now_str = datetime.now().strftime("%d/%m/%Y %H:%M:%S")
        if success:
            self.opcua_discovered_nodes = found_nodes  # Strictly separate from self.scanned_tags!
            if status_name == "Browse Incomplete":
                self.lbl_opc_status.set_text(f"⚠️ สแกนพบ {len(found_nodes)} Nodes (Incomplete)")
                self.lbl_opc_status.remove_css_class('badge-nope')
                self.lbl_opc_status.remove_css_class('badge-active')
                self.lbl_opc_status.add_css_class('badge-sensor')
                self.alarm_text.set_text(f"⚠️ {msg}")
                self.add_alarm_event(now_str, "OPC_UA", "WARN", "DISCOVERY_PARTIAL", msg)
            else:
                self.lbl_opc_status.set_text(f"🟢 Browse สำเร็จ ({len(found_nodes)} Nodes)")
                self.lbl_opc_status.remove_css_class('badge-nope')
                self.lbl_opc_status.remove_css_class('badge-sensor')
                self.lbl_opc_status.add_css_class('badge-active')
                self.alarm_text.set_text(f"🟢 {msg}")
                self.add_alarm_event(now_str, "OPC_UA", "INFO", "DISCOVERY", f"Browse WinCC OPC UA สำเร็จ ({len(found_nodes)} Nodes)")
        else:
            self.lbl_opc_status.set_text(f"❌ {status_name}: {msg[:30]}")
            self.lbl_opc_status.remove_css_class('badge-active')
            self.lbl_opc_status.remove_css_class('badge-sensor')
            self.lbl_opc_status.add_css_class('badge-nope')
            self.alarm_text.set_text(f"❌ {msg}")
            self.add_alarm_event(now_str, "OPC_UA", "WARN", "DISCOVERY_ERR", f"Browse WinCC OPC UA ล้มเหลว: {msg}")

    def on_save_telegram_config(self, _=None):
        config = {
            **self.telegram_config,
            'bot_token': self.entry_tg_token.get_text().strip(),
            'chat_id': self.entry_tg_chat_id.get_text().strip(),
        }
        if not save_telegram_config(config):
            message = 'บันทึกไม่สำเร็จ · ไม่สามารถเขียนไฟล์ตั้งค่า Telegram'
            self.lbl_tg_status.set_text(message)
            self.lbl_tg_status.set_css_classes(['badge-nope'])
            self.alarm_text.set_text(message)
            return False

        self.telegram_config.update(config)
        self.lbl_tg_status.set_text('บันทึกปลายทางแล้ว')
        self.lbl_tg_status.set_css_classes(['badge-standby'])
        self.alarm_text.set_text('บันทึกปลายทาง Telegram แล้ว')
        return True

    def on_test_telegram_send(self, _=None):
        token = self.entry_tg_token.get_text().strip()
        chat_id = self.entry_tg_chat_id.get_text().strip()
        msg = self.entry_tg_test_msg.get_text().strip()

        if not token or not chat_id:
            self.lbl_tg_status.set_text("❌ กรุณากรอก Token และ Chat ID ก่อนทดสอบ")
            self.lbl_tg_status.remove_css_class('badge-active')
            self.lbl_tg_status.remove_css_class('badge-standby')
            self.lbl_tg_status.add_css_class('badge-nope')
            self.alarm_text.set_text("❌ ไม่สามารถทดสอบส่งได้: ยังไม่ได้ระบุ Telegram Bot Token หรือ Chat ID")
            return

        if not self.on_save_telegram_config():
            return

        self.lbl_tg_status.set_text("⏳ กำลังส่งข้อความทดสอบไปยัง Telegram...")
        self.lbl_tg_status.remove_css_class('badge-nope')
        self.lbl_tg_status.remove_css_class('badge-active')
        self.lbl_tg_status.add_css_class('badge-sensor')
        self.btn_test_tg.set_sensitive(False)

        def worker():
            url = f"https://api.telegram.org/bot{token}/sendMessage"
            payload = json.dumps({
                "chat_id": chat_id,
                "text": msg,
                "parse_mode": "HTML"
            }).encode('utf-8')

            req = urllib.request.Request(
                url,
                data=payload,
                headers={'Content-Type': 'application/json'}
            )
            success = False
            resp_detail = ""
            try:
                with urllib.request.urlopen(req, timeout=8) as response:
                    status = response.getcode()
                    if status == 200:
                        success = True
                        resp_detail = "ส่งข้อความสำเร็จ (HTTP 200 OK)"
                    else:
                        resp_detail = f"HTTP Status {status}"
            except urllib.error.HTTPError as he:
                err_body = he.read().decode('utf-8', errors='ignore')
                resp_detail = f"Telegram Error ({he.code}): {err_body[:90]}"
            except Exception as ex:
                resp_detail = f"Network Error: {str(ex)[:90]}"

            GLib.idle_add(self.apply_telegram_test_result, success, resp_detail, msg)

        t = threading.Thread(target=worker, daemon=True)
        t.start()

    def apply_telegram_test_result(self, success, detail, msg):
        self.btn_test_tg.set_sensitive(True)
        now_str = datetime.now().strftime("%d/%m/%Y %H:%M:%S")
        if success:
            self.lbl_tg_status.set_text("🟢 ส่งข้อความสำเร็จ! (HTTP 200 OK)")
            self.lbl_tg_status.remove_css_class('badge-nope')
            self.lbl_tg_status.remove_css_class('badge-sensor')
            self.lbl_tg_status.add_css_class('badge-active')
            self.alarm_text.set_text("🚀 ทดสอบส่ง Telegram สำเร็จ: ได้รับข้อความทาง Telegram แล้ว")
            self.add_alarm_event(now_str, "TELEGRAM", "INFO", "DELIVERED", f"ทดสอบส่งข้อความแจ้งเตือนผ่าน Telegram Bot สำเร็จ: '{msg[:40]}...")
        else:
            self.lbl_tg_status.set_text(f"❌ {detail[:45]}")
            self.lbl_tg_status.remove_css_class('badge-active')
            self.lbl_tg_status.remove_css_class('badge-sensor')
            self.lbl_tg_status.add_css_class('badge-nope')
            self.alarm_text.set_text(f"❌ ทดสอบส่ง Telegram ไม่สำเร็จ: {detail}")
            self.add_alarm_event(now_str, "TELEGRAM", "WARN", "FAILED", f"ส่ง Telegram ล้มเหลว: {detail}")

    # ---------------------------------------------------------
    # Background Task Runner (Executes ONLY assigned active tasks)
    # ---------------------------------------------------------
    def task_runner_loop(self):
        """Runs periodic scans strictly for active tasks."""
        last_ticks = {}
        while self.running:
            time.sleep(0.5)
            now = time.monotonic()
            for t in self.tasks:
                if not t.get('active'):
                    continue
                tid = t['id']
                cycle = max(1, t.get('cycle_sec', 5))
                if now - last_ticks.get(tid, 0) >= cycle:
                    last_ticks[tid] = now
                    # Execute this specific task!
                    t['scan_count'] = t.get('scan_count', 0) + 1
                    if t.get('action_log'):
                        t['log_count'] = t.get('log_count', 0) + len(t.get('tags', []))
                    if t.get('action_notify'):
                        t['alert_count'] = t.get('alert_count', 0)

    def update_internet_badge(self, snapshot):
        state = local_snapshot_state(snapshot)
        connectivity = snapshot.get('connectivity') if state == 'OBSERVED_LOCAL' else None
        caption = {'FULL': 'ใช้งานได้', 'LIMITED': 'จำกัด', 'PORTAL': 'ต้องเข้าสู่ระบบ',
                   'NONE': 'ไม่เชื่อมต่อ'}.get(connectivity, 'ข้อมูลเก่า' if state == 'STALE' else 'ยังไม่ทราบ')
        gateway = snapshot.get('default_gateway') if state == 'OBSERVED_LOCAL' else None
        label = f'เน็ต: {caption}'
        if gateway:
            label += f' · GW {gateway}'
        self.internet_badge.set_text(label)
        self.internet_badge.set_tooltip_text(
            'สถานะอินเทอร์เน็ตจาก NetworkManager · GW คือเกตเวย์ IPv4 เริ่มต้นของเครื่อง')
        self.internet_badge.set_css_classes(['badge-active' if connectivity == 'FULL' else 'badge-standby'])

    def update_real_data(self):
        """Fetches real host machine metrics and updates UI cleanly."""
        try:
            snapshot = getattr(getattr(self, 'f3_network_view', None), 'local_state', {})
            self.update_internet_badge(snapshot)
            m = read_real_machine_data(snapshot)
            if hasattr(self, 'machine_labels') and 'hostname' in self.machine_labels:
                self.machine_labels['hostname'].set_text(m['hostname'])
                self.machine_labels['os_name'].set_text(m['os_name'])
                self.machine_labels['kernel'].set_text(m['kernel'])
                self.machine_labels['arch'].set_text(m['arch'])
                self.machine_labels['cpu_model'].set_text(m['cpu_model'])
                self.machine_labels['cpu_cores'].set_text(f"{m['cpu_cores']} Threads")
                self.machine_labels['cpu_load'].set_text(m['cpu_load'])
                self.machine_labels['ram_total_gb'].set_text(f"{m['ram_total_gb']:.2f} GB")
                self.machine_labels['ram_used_gb'].set_text(f"{m['ram_used_gb']:.2f} GB ({m['ram_pct']:.1f}%)")
                self.machine_labels['ram_avail_gb'].set_text(f"{m['ram_avail_gb']:.2f} GB")
                self.machine_labels['disk_total_gb'].set_text(f"{m['disk_total_gb']:.2f} GB")
                self.machine_labels['disk_used_gb'].set_text(f"{m['disk_used_gb']:.2f} GB ({m['disk_pct']:.1f}%)")
                self.machine_labels['disk_avail_gb'].set_text(f"{m['disk_avail_gb']:.2f} GB")
                self.machine_labels['ip_lan'].set_text(m['ip_lan'])
                self.machine_labels['uptime_str'].set_text(m['uptime_str'])
                gw = self.topology_data.get('gateway_bridge', {})
                nic_in = gw.get('nic_scada', {})
                carrier = check_interface_carrier('enp0s31f6')
                self.update_local_nic_badge(carrier)
                self.pill_wan_ip.set_text(f"WAN: {m['ip_lan']}")
            if hasattr(self, 'f3_network_view'):
                self.f3_network_view.tick_live()
        except Exception as e:
            print(f"Update error: {e}", file=sys.stderr)
        return True


    def on_close_request(self, *args):
        """Gracefully terminate background workers on window close."""
        self.running = False
        if hasattr(self, 'telemetry_settings'):
            self.telemetry_settings.stop(closing=True)
        if hasattr(self, 'browse_cancel_flag'):
            self.browse_cancel_flag.set()
        if getattr(self, 'hybrid_ui', None):
            self.hybrid_ui.stop()
        if hasattr(self, 'f3_network_view'):
            self.f3_network_view.close()
        return False


class AquaApplication(Gtk.Application):
    def __init__(self, *args, **kwargs):
        super().__init__(application_id="org.aquacommand.Desktop", **kwargs)

    def do_activate(self):
        win = AquaWinCCWindow(self)
        win.present()


def main():
    app = AquaApplication()
    return app.run(sys.argv)


if __name__ == '__main__':
    sys.exit(main())
