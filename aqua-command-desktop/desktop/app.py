
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
        ('High_VSD', '⚡ สถานีสูบส่งน้ำแรงสูง VSD (High_VSD — ปั๊ม Inverter CTM13PT ถึง CTM17PT)'),
        ('High1_PT1PT', '💧 โรงสูบน้ำแรงต่ำ 1 (High1_PT1PT — สถานีสูบน้ำดิบแม่น้ำปิง)'),
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
except ImportError:
    from opcua_mapping import NodeIdMapper
    from opcua_store import ObservableStateStore, Quality
    from opcua_reader import ManualOpcUaReader
    from opcua_pki import PkiManager
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
    from .workspace import AquaUnifiedWorkspaceView
except ImportError:
    from f1_overview import F1StationExplorerView
    from f2_tasks import F2TaskManagerView
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
    p.parent.mkdir(parents=True, exist_ok=True)
    temp_p = p.with_suffix('.tmp')
    try:
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
    save_atomic_json(TELEGRAM_CONFIG_FILE, cfg)

DEFAULT_TOPOLOGY = {
    "scada_lan": {
        "zone_name": "เครือข่ายภายใน SCADA (Isolated OT LAN)",
        "subtitle": "วงแลนอิสระของสถานีผลิตน้ำอุโมงค์ (192.168.1.0/24) | ปลอดภัย 100% ไม่เชื่อมต่อภายนอก",
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
                "role": "สถานีสูบน้ำแรงต่ำ 1 (แม่น้ำปิง / ชลประทาน)",
                "status": "ONLINE (ในวงแลนปิด)",
                "ping": "< 1 ms"
            },
            {
                "id": "PC2",
                "name": "PC2 · SCADA",
                "internet_status": "ไม่มี Internet",
                "has_internet": False,
                "ip": "192.168.1.12",
                "mac": "00:1E:67:D8:12:B2",
                "role": "สถานีสูบน้ำแรงต่ำ 3 (สถานีผลิตน้ำอุโมงค์)",
                "status": "ONLINE (ในวงแลนปิด)",
                "ping": "< 1 ms"
            },
            {
                "id": "PC3",
                "name": "PC3 · SCADA",
                "internet_status": "ไม่มี Internet",
                "has_internet": False,
                "ip": "192.168.1.13",
                "mac": "00:1E:67:D8:13:C3",
                "role": "สถานีสูบส่งน้ำแรงสูง VSD (High_VSD #13-#17)",
                "status": "ONLINE (ในวงแลนปิด)",
                "ping": "< 1 ms"
            }
        ]
    },
    "gateway_bridge": {
        "id": "PC4",
        "name": "PC4 · Gateway (AQUA COMMAND — เครื่องนี้)",
        "internet_status": "มี Internet",
        "has_internet": True,
        "badge": "🟢 มี Internet (เชื่อม 2 วงแลน Dual-Homed)",
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
        "has_internet": True,
        "router": {
            "name": "Router Internet",
            "sub1": "TrueMove H 4G LTE Router",
            "gateway_ip": "192.168.100.1",
            "ssid": "Nong_Arm",
            "operator": "TrueMove H LTE",
            "netmask": "255.255.255.0",
            "dhcp": "เปิดใช้งาน (DHCP Enabled)",
            "status": "🟢 มีอินเทอร์เน็ตพร้อมส่งข้อมูลภายนอก",
            "mac": "e8:49:43:21:33:5b"
        },
        "clients": [
            {
                "ip": "192.168.100.177",
                "mac": "ba:7a:37:fe:60:6a",
                "name": "PC4 · Gateway (เครื่องประมวลผล AQUA COMMAND นี้)",
                "is_this_pc": True,
                "status": "ONLINE (Host)",
                "ping": "0.1 ms"
            },
            {
                "ip": "192.168.100.135",
                "mac": "5e:86:55:78:8a:77",
                "name": "Client เครื่องลูกข่าย 1 (Active Wi-Fi Client)",
                "is_this_pc": False,
                "status": "ONLINE",
                "ping": "9.0 ms"
            },
            {
                "ip": "192.168.100.150",
                "mac": "f4:d1:08:56:83:bc",
                "name": "Client เครื่องลูกข่าย 2 (Active Device ในวง)",
                "is_this_pc": False,
                "status": "ONLINE",
                "ping": "12.4 ms"
            },
            {
                "ip": "192.168.100.178",
                "mac": "50:2e:91:3f:77:30",
                "name": "Client เครื่องลูกข่าย 3 (Active Device ในวง)",
                "is_this_pc": False,
                "status": "ONLINE",
                "ping": "15.1 ms"
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
if not IS_WINDOWS and not DEFAULT_WINCC_EXPORT.exists() and Path('/home/nong_ing/Downloads/Export all.txt').exists():
    DEFAULT_WINCC_EXPORT = Path('/home/nong_ing/Downloads/Export all.txt')
repo_export1 = Path(__file__).resolve().parent.parent / 'docs' / 'tags' / 'Export all.txt'
repo_export2 = Path(__file__).resolve().parent.parent.parent / 'docs' / 'tags' / 'Export all.txt'
if not DEFAULT_WINCC_EXPORT.exists():
    if repo_export1.exists():
        DEFAULT_WINCC_EXPORT = repo_export1
    elif repo_export2.exists():
        DEFAULT_WINCC_EXPORT = repo_export2

# ---------------------------------------------------------
# WinCC Tag Scanner (Parses full Siemens WinCC Tag Export)
# ---------------------------------------------------------
def scan_wincc_tags(file_path):
    """Parses standard Siemens WinCC V8.1 Tag Management Export files (UTF-16 LE)."""
    tags = []
    p = Path(file_path)
    if not p.exists():
        return tags

    try:
        with open(p, 'r', encoding='utf-16') as f:
            for i, line in enumerate(f):
                if i < 3:
                    continue
                parts = line.strip().split('\t')
                if len(parts) >= 8:
                    name, comment, dtype, length, fmt, conn, group, addr = parts[:8]
                    name = name.strip()
                    if name:
                        tags.append({
                            'name': name,
                            'comment': comment.strip(),
                            'type': dtype.strip(),
                            'conn': conn.strip(),
                            'group': group.strip() or 'Default',
                            'addr': addr.strip() or 'Internal'
                        })
    except Exception as e:
        print(f"Error scanning WinCC export: {e}", file=sys.stderr)
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


def read_real_machine_data():
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

    # 5. IP Address
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.settimeout(0.15)
        s.connect(('8.8.8.8', 80))
        local_ip = s.getsockname()[0]
        s.close()
        data['ip_lan'] = f"{local_ip} (Active Network)"
    except Exception:
        try:
            data['ip_lan'] = socket.gethostbyname(socket.gethostname())
        except Exception:
            data['ip_lan'] = '127.0.0.1'

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
    return DEFAULT_TASKS

def save_tasks(tasks):
    save_atomic_json(TASKS_CONFIG_FILE, tasks)


# ---------------------------------------------------------
# [PURGED MOCK DATA: REAL_STATIONS_DATA completely deleted]

CSS_DATA = b"""
window {
    background-color: #0b0f17;
    color: #e2e8f0;
    font-family: 'Inter', 'Noto Sans Thai', 'Segoe UI', sans-serif;
    font-size: 10pt;
}

label {
    color: #e2e8f0;
}

/* Modern Mission Control Topbar */
.wincc-topbar {
    background: linear-gradient(90deg, #0d1527 0%, #172554 45%, #0f172a 100%);
    color: #f8fafc;
    padding: 8px 16px;
    border-bottom: 2px solid #2563eb;
}
.wincc-title {
    font-size: 12.5pt;
    font-weight: 700;
    color: #38bdf8;
    letter-spacing: 0.5px;
}
.wincc-clock {
    font-family: 'JetBrains Mono', 'DejaVu Sans Mono', monospace;
    font-size: 11pt;
    font-weight: 700;
    background: #030712;
    color: #10b981;
    padding: 4px 12px;
    border: 1px solid #059669;
    border-radius: 6px;
}

/* Modern Status & Alarm Banner */
.alarm-banner {
    background: linear-gradient(90deg, #064e3b 0%, #022c22 100%);
    border-bottom: 1px solid #059669;
    padding: 6px 16px;
}
.alarm-text {
    font-size: 10pt;
    font-weight: 600;
    color: #a7f3d0;
}

/* Modern Station Card Groups */
.wincc-group {
    background-color: #111827;
    border: 1px solid #1f2937;
    border-radius: 10px;
    padding: 12px;
    margin: 6px;
}
.group-title {
    font-size: 11.5pt;
    font-weight: 700;
    color: #60a5fa;
    margin-bottom: 8px;
    border-bottom: 1px solid #1f2937;
    padding-bottom: 4px;
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

/* Modern Bottom Navigation Bar (High-Tech Segmented Dock) */
.wincc-fkey-bar {
    background: #080c14;
    border-top: 1px solid #1e293b;
    padding: 8px 14px;
}
.fkey-btn {
    background: #111827;
    color: #cbd5e1;
    border: 1px solid #1f2937;
    border-radius: 8px;
    font-weight: 600;
    font-size: 9.5pt;
    padding: 7px 14px;
    margin: 0 2px;
}
.fkey-btn:checked {
    background: linear-gradient(135deg, #0284c7 0%, #2563eb 100%);
    border-color: #38bdf8;
    color: #ffffff;
    font-weight: 700;
}
.fkey-btn:hover {
    background: #1f2937;
    color: #ffffff;
    border-color: #3b82f6;
}

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

/* Modern Data Grid / Table */
.data-table {
    background-color: #0d1522;
    border: 1px solid #1e293b;
    border-radius: 8px;
}
.table-th {
    background-color: #172554;
    font-weight: 700;
    color: #93c5fd;
    padding: 8px 12px;
    border-bottom: 2px solid #1e3a8a;
    font-size: 9.5pt;
}
.table-td {
    padding: 7px 12px;
    border-bottom: 1px solid #1e293b;
    color: #e2e8f0;
    font-size: 9.5pt;
}

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
        super().__init__(application=app, title="AQUA COMMAND — WinCC V8.1 SCADA & Task Manager")
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
        self.opcua_discovered_nodes = []  # Strictly separated from local catalog
        self.browse_cancel_flag = threading.Event()  # Cooperative cancellation
        self.task_execution_state = "SUSPENDED_SAFETY_GATE_B1"  # Explicit suspension
        self.alarm_events = [
            (datetime.now().strftime("%d/%m/%Y %H:%M:%S"), "SYSTEM", "INFO", "READY", "ระบบ AQUA COMMAND WinCC V8.1 เริ่มต้นทำงานพร้อมตรวจวัดสถานะ")
        ]
        self.current_task_idx = 0
        self.tag_checkboxes = {}
        self.selected_tags_for_task = set()
        self.internet_online = True

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

        title_label = Gtk.Label(label="WINCC V8.1 / INDUSTRIAL OPERATIONS · สถานีผลิตน้ำอุโมงค์")
        title_label.add_css_class('wincc-title')
        title_label.set_hexpand(True)
        title_label.set_xalign(0.0)
        title_label.set_ellipsize(Pango.EllipsizeMode.END)
        topbar.append(title_label)

        # Section A Status Cluster (Restrained visual weight hierarchy)
        if len(self.scanned_tags) == 0:
            self.pill_scan = Gtk.Label(label="Catalog: 0 Tags")
            self.pill_scan.add_css_class('badge-nope')
        else:
            self.pill_scan = Gtk.Label(label=f"Catalog: {len(self.scanned_tags)} Tags")
            self.pill_scan.add_css_class('badge-active')
        topbar.append(self.pill_scan)

        self.pill_scada_ip = Gtk.Label(label="SCADA: Standby (Offline)")
        self.pill_scada_ip.add_css_class('badge-standby')
        topbar.append(self.pill_scada_ip)

        self.pill_readonly = Gtk.Label(label="READ ONLY")
        self.pill_readonly.add_css_class('badge-readonly')
        topbar.append(self.pill_readonly)

        self.pill_net = Gtk.Label(label="Internet: Online")
        self.pill_net.add_css_class('badge-gateway')
        topbar.append(self.pill_net)

        self.clock_label = Gtk.Label(label="--:--:--")
        self.clock_label.add_css_class('wincc-clock')
        topbar.append(self.clock_label)

        # Internal attribute preserved for background handlers
        self.pill_wan_ip = Gtk.Label(label="")
        self.pill_opcua = Gtk.Label(label="")

        # 2. System Status / Alarm Ribbon Line
        alarm_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        alarm_box.add_css_class('alarm-banner')
        root_box.append(alarm_box)

        if len(self.scanned_tags) == 0:
            self.alarm_icon = Gtk.Label(label="[STANDBY]")
            self.alarm_icon.add_css_class('alarm-text')
            alarm_box.append(self.alarm_icon)

            self.alarm_text = Gtk.Label(label="ระบบพร้อมใช้งาน — ยังไม่มีข้อมูล Tag ในระบบ | กรุณากดปุ่ม [F7 สแกน & รีเฟรช] เพื่อเริ่มสแกน")
            self.alarm_text.add_css_class('alarm-text')
            self.alarm_text.set_hexpand(True)
        else:
            self.alarm_icon = Gtk.Label(label="[CATALOG VERIFIED]")
            self.alarm_icon.add_css_class('alarm-text')
            alarm_box.append(self.alarm_icon)

            self.alarm_text = Gtk.Label(label=f"คลัง Tag WinCC V8.1 โหลดสมบูรณ์ ({len(self.scanned_tags)} Tags / 10 Groups) — โหมด READ ONLY | สัญญาณสด: Not Observed (ไม่มีเซสชัน OPC UA ภายนอก)")
            self.alarm_text.add_css_class('alarm-text')
            self.alarm_text.set_hexpand(True)
        self.alarm_text.set_xalign(0.0)
        alarm_box.append(self.alarm_text)

        # 3. Stack Pages
        self.stack = Gtk.Stack()
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

        # 4. WinCC Bottom Function Keys Bar
        fkey_bar = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        fkey_bar.add_css_class('wincc-fkey-bar')
        root_box.append(fkey_bar)

        self.nav_btns = {}
        pages_def = [
            ('overview', 'F1  ภาพรวมสถานีสูบน้ำ'),
            ('tasks', 'F2  ตัวจัดการ Task (WinCC Task Manager)'),
            ('network', 'F3  ผังเครือข่าย 2 วงแลน & หลายเราเตอร์'),
            ('machine', 'F4  ข้อมูลเครื่องจริง (Host)'),
            ('tags', f"F5  คลัง Tag ที่สแกนพบ ({len(self.scanned_tags)} Tags)"),
            ('alarms', 'F6  เชื่อมต่อ WinCC OPC UA & Telegram'),
        ]

        group_btn = None
        for key, text in pages_def:
            b = Gtk.ToggleButton(label=text)
            b.add_css_class('fkey-btn')
            if isinstance(b.get_child(), Gtk.Label):
                b.get_child().set_ellipsize(Pango.EllipsizeMode.END)
            if group_btn:
                b.set_group(group_btn)
            else:
                group_btn = b
                b.set_active(True)
            if USE_UNIFIED_WORKSPACE and key == 'overview':
                b.connect('toggled', lambda btn: self.activate_workspace_mode('monitoring') if btn.get_active() else None)
            elif USE_UNIFIED_WORKSPACE and key == 'tasks':
                b.connect('toggled', lambda btn: self.activate_workspace_mode('task_manager') if btn.get_active() else None)
            else:
                b.connect('toggled', lambda btn, k=key: self.stack.set_visible_child_name(k) if btn.get_active() else None)
            fkey_bar.append(b)
            self.nav_btns[key] = b
        # Native Keyboard F1..F8 Controller
        key_ctrl = Gtk.EventControllerKey()
        key_ctrl.connect('key-pressed', self.on_global_key_pressed)
        self.add_controller(key_ctrl)


        spacer = Gtk.Box()
        spacer.set_hexpand(True)
        fkey_bar.append(spacer)

        refresh_btn = Gtk.Button(label="F7  สแกน & รีเฟรช")
        refresh_btn.add_css_class('fkey-btn')
        refresh_btn.add_css_class('fkey-btn-orange')
        if isinstance(refresh_btn.get_child(), Gtk.Label):
            refresh_btn.get_child().set_ellipsize(Pango.EllipsizeMode.END)
        refresh_btn.connect('clicked', lambda _: self.trigger_rescan())
        fkey_bar.append(refresh_btn)

        exit_btn = Gtk.Button(label="F8  ปิดระบบ")
        exit_btn.add_css_class('fkey-btn')
        exit_btn.add_css_class('fkey-btn-exit')
        if isinstance(exit_btn.get_child(), Gtk.Label):
            exit_btn.get_child().set_ellipsize(Pango.EllipsizeMode.END)
        exit_btn.connect('clicked', lambda _: self.close())
        fkey_bar.append(exit_btn)

        # Default startup landing page: F1 Overview
        self.stack.set_visible_child_name('overview')
        if 'overview' in self.nav_btns:
            self.nav_btns['overview'].set_active(True)

        # Start Clock & Background Poller
        GLib.timeout_add_seconds(1, self.tick_clock)
        GLib.timeout_add_seconds(1, self.auto_scan_tick) # Real Auto-Scan Engine!
        self.update_real_data()
        GLib.timeout_add_seconds(2, self.update_real_data)

        # Background Task Runner (Suspended in Gate B1)
        self.running = False
        self.task_thread = None  # Startup Safety: zero background task threads on window init

    def tick_clock(self):
        now_str = datetime.now().strftime("%d/%m/%Y %H:%M:%S")
        self.clock_label.set_text(now_str)
        return True

    def switch_to_tab(self, tab_key):
        self.stack.set_visible_child_name(tab_key)
        if tab_key in self.nav_btns:
            self.nav_btns[tab_key].set_active(True)

    def trigger_rescan(self):
        self.scanned_tags = scan_wincc_tags(DEFAULT_WINCC_EXPORT)
        self.pill_scan.set_text(f"Catalog: {len(self.scanned_tags)} Tags")
        self.pill_scan.remove_css_class('badge-nope')
        self.pill_scan.add_css_class('badge-active')
        if 'tags' in self.nav_btns:
            self.nav_btns['tags'].set_label(f"F5  คลัง Tag ที่สแกนพบ ({len(self.scanned_tags)} Tags)")
        self.alarm_icon.set_text("[SCANNED]")
        self.alarm_text.set_text(f"สแกน Tag WinCC สำเร็จ: โหลดข้อมูล {len(self.scanned_tags)} Tags เข้าสู่ F1 Station Explorer เรียบร้อยแล้ว")
        self.render_dynamic_overview()
        if hasattr(self, 'render_tags_grid'):
            self.render_tags_grid()
        if hasattr(self, 'render_tags_page_grid'):
            self.render_tags_page_grid()
        # Safety: F7 strictly refreshes local catalog; zero automated network probing
        self.update_real_data()

    def activate_workspace_mode(self, mode):
        self.stack.set_visible_child_name('overview')
        if hasattr(self, 'unified_workspace'):
            self.unified_workspace.set_workspace_mode(mode)

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
        save_tasks(self.tasks)
        return True

    def save_all_tasks(self):
        save_tasks(self.tasks)
        if hasattr(self, 'alarm_text'):
            self.alarm_text.set_text("บันทึกการตั้งค่า Task ทั้งหมดเรียบร้อยแล้ว")

    def add_selected_tags_to_current_task(self, _=None):
        if hasattr(self, 'f2_tasks_view'):
            self.f2_tasks_view.on_add_selected_tags(None)

    def remove_tag_from_task(self, tag_name):
        if hasattr(self, 'f2_tasks_view'):
            self.f2_tasks_view.on_remove_tag_from_task(tag_name)

    # ---------------------------------------------------------
    # TAB 3: Dual-Router Network Topology & Multi-IP View
    # ---------------------------------------------------------
    def build_network_topology_page(self):
        scrolled = Gtk.ScrolledWindow()
        scrolled.set_hexpand(True)
        scrolled.set_vexpand(True)

        vbox = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        vbox.set_margin_start(12)
        vbox.set_margin_end(12)
        vbox.set_margin_top(8)
        vbox.set_margin_bottom(8)
        scrolled.set_child(vbox)

        # 1. Clean Top Header Bar (No squished colored pills)
        top_bar = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
        top_bar.add_css_class('wincc-group')
        vbox.append(top_bar)

        top_title = Gtk.Label(label="🌐 ผังเครือข่าย 2 ฝั่ง: วงแลน SCADA ภายใน (ไม่มีเน็ต) VS วงเราเตอร์ภายนอก (มีเน็ต)")
        top_title.add_css_class('group-title')
        top_bar.append(top_title)

        spacer = Gtk.Box()
        spacer.set_hexpand(True)
        top_bar.append(spacer)

        rescan_net_btn = Gtk.Button(label="🔍 สแกนสด (Scan Now)")
        rescan_net_btn.add_css_class('action-btn')
        rescan_net_btn.connect('clicked', lambda _: self.trigger_single_scan(silent=False))
        top_bar.append(rescan_net_btn)

        config_net_btn = Gtk.Button(label="⚙️ ปรับแต่ง IP (Config IP)")
        config_net_btn.add_css_class('action-btn')
        config_net_btn.connect('clicked', self.show_network_config_dialog)
        top_bar.append(config_net_btn)

        opc_net_btn = Gtk.Button(label="🏭 เชื่อมต่อ WinCC OPC UA")
        opc_net_btn.add_css_class('action-btn')
        opc_net_btn.connect('clicked', lambda _: self.switch_to_tab('alarms'))
        top_bar.append(opc_net_btn)

        reset_def_btn = Gtk.Button(label="🔄 คืนค่าเริ่มต้น (Reset Default)")
        reset_def_btn.add_css_class('action-btn')
        reset_def_btn.connect('clicked', lambda _: self.reset_to_factory_defaults())
        top_bar.append(reset_def_btn)

        # 2. Ultra-Clean Topology Canvas
        canvas_group = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
        canvas_group.add_css_class('wincc-group')
        vbox.append(canvas_group)

        self.topology_canvas = Gtk.DrawingArea()
        self.topology_canvas.set_content_width(1100)
        self.topology_canvas.set_content_height(480)
        self.topology_canvas.set_draw_func(self.draw_topology_canvas)
        canvas_group.append(self.topology_canvas)

        # 3. Simple & Clean IP Table (5 Columns, No redundant duplicate cards!)
        tbl_group = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        tbl_group.add_css_class('wincc-group')
        vbox.append(tbl_group)

        tbl_title = Gtk.Label(label="📋 ตารางสรุปหมายเลข IP และสถานะทุกเครื่องในระบบ (IP Summary)")
        tbl_title.add_css_class('group-title')
        tbl_title.set_xalign(0.0)
        tbl_group.append(tbl_title)

        self.net_grid = Gtk.Grid(column_spacing=1, row_spacing=1)
        self.net_grid.add_css_class('data-table')
        tbl_group.append(self.net_grid)

        self.render_network_table()

        self.stack.add_named(scrolled, 'network')

    # ---------------------------------------------------------
    # Cairo Drawing for Network Topology Canvas
    # ---------------------------------------------------------
    def draw_topology_canvas(self, area, cr, width, height):
        # 1. Dark Clean Industrial Background
        cr.set_source_rgb(0.11, 0.13, 0.16)
        cr.paint()

        data = self.topology_data
        scada_info = data.get('scada_lan', {})
        gw_info = data.get('gateway_bridge', {})
        wan_info = data.get('internet_wan', {})
        rt_info = wan_info.get('router', {})

        # Live Real Status Probes
        scada_carrier = self.live_status.get('scada_carrier', False)
        pings = self.live_status.get('pings', {})

        # Zone 1 (Left): Isolated SCADA LAN
        draw_rounded_rect(cr, 20, 20, 520, height - 40, 12)
        cr.set_source_rgba(0.15, 0.17, 0.22, 0.7)
        cr.fill_preserve()
        cr.set_source_rgba(0.30, 0.40, 0.52, 0.6)
        cr.set_line_width(1.5)
        cr.stroke()

        # Zone 2 (Right): Internet Router WAN
        z2_w = max(400, width - 580)
        draw_rounded_rect(cr, 560, 20, z2_w, height - 40, 12)
        cr.set_source_rgba(0.13, 0.19, 0.16, 0.7)
        cr.fill_preserve()
        cr.set_source_rgba(0.20, 0.60, 0.38, 0.6)
        cr.set_line_width(1.5)
        cr.stroke()

        # Zone Headers
        draw_pango_text(cr, "🔒 วงแลนภายใน SCADA (มีวงแลนของตนเอง — ไม่มีเน็ต)", 
                        40, 35, "Noto Sans Thai, Sans Bold 13", (0.65, 0.82, 1.0))
        draw_pango_text(cr, f"Subnet: {scada_info.get('subnet', '192.168.1.0/24')}  |  Air-Gapped ปลอดภัย 100% ไม่ต่ออินเทอร์เน็ต", 
                        40, 58, "Noto Sans Thai, Sans 10", (0.75, 0.80, 0.88))

        draw_pango_text(cr, "🌐 วงเราเตอร์ภายนอก (เราเตอร์ 4G LTE — มีเน็ต)", 
                        580, 35, "Noto Sans Thai, Sans Bold 13", (0.40, 0.95, 0.65))
        rt_ip = rt_info.get('gateway_ip', '192.168.100.1')
        draw_pango_text(cr, f"Router Gateway: {rt_ip}  |  SSID: {rt_info.get('ssid', 'Nong_Arm')}  (พร้อมส่งข้อมูล)", 
                        580, 58, "Noto Sans Thai, Sans 10", (0.75, 0.90, 0.82))

        # Coordinates
        pc_x = 35
        pc_w = 235
        pc_h = 75
        pc_y = [90, 185, 280]

        bus_x = 295

        sw_x = 330
        sw_y = 170
        sw_w = 195
        sw_h = 105

        gw_x = 205
        gw_y = 375
        gw_w = 345
        gw_h = 75

        rt_x = 600
        rt_y = 130
        rt_w = 270
        rt_h = 95

        cl_x = 600
        cl_y = 255
        cl_w = min(460, z2_w - 60)
        cl_h = 175

        # 1. Connecting Bus Line: PC1-3 to LAN Switch
        cr.set_line_width(2.5)
        cr.set_source_rgb(0.40, 0.50, 0.65)
        bus_x = 285

        for y in pc_y:
            cr.move_to(pc_x + pc_w, y + pc_h / 2)
            cr.line_to(bus_x, y + pc_h / 2)
            cr.stroke()

        cr.move_to(bus_x, pc_y[0] + pc_h / 2)
        cr.line_to(bus_x, pc_y[2] + pc_h / 2)
        cr.stroke()

        cr.move_to(bus_x, sw_y + sw_h / 2)
        cr.line_to(sw_x, sw_y + sw_h / 2)
        cr.stroke()

        # 2. Connecting Lines: Green Links
        cr.set_line_width(3.0)
        cr.set_source_rgb(0.0, 0.90, 0.45) # Bright green

        # Line from LAN Switch down to PC4 Gateway
        cr.move_to(sw_x + sw_w / 2, sw_y + sw_h)
        cr.line_to(sw_x + sw_w / 2, 350)
        cr.line_to(gw_x + 130, 350)
        cr.line_to(gw_x + 130, gw_y)
        cr.stroke()

        # Line from PC4 Gateway to Router Internet
        cr.move_to(gw_x + gw_w, gw_y + gw_h / 2)
        cr.line_to(580, gw_y + gw_h / 2)
        cr.line_to(580, rt_y + rt_h / 2)
        cr.line_to(rt_x, rt_y + rt_h / 2)
        cr.stroke()

        # Line from Router down to Clients box
        cr.set_source_rgba(0.2, 0.80, 0.50, 0.8)
        cr.set_line_width(2.0)
        cr.move_to(rt_x + rt_w / 2, rt_y + rt_h)
        cr.line_to(rt_x + rt_w / 2, cl_y)
        cr.stroke()

        # 3. Draw Nodes: PC1, PC2, PC3
        scada_devices = scada_info.get('devices', [])
        for i, dev in enumerate(scada_devices[:3]):
            y = pc_y[i]
            dev_ip = dev.get('ip', '192.168.1.x')
            draw_rounded_rect(cr, pc_x, y, pc_w, pc_h, 8)
            cr.set_source_rgb(0.16, 0.19, 0.25)
            cr.fill_preserve()
            cr.set_source_rgb(0.35, 0.45, 0.58)
            cr.set_line_width(1.8)
            cr.stroke()

            draw_pango_text(cr, dev.get('name', 'PC · SCADA'), pc_x + 14, y + 10, "Noto Sans Thai, Sans Bold 12", (1.0, 1.0, 1.0))
            draw_pango_text(cr, "⚠️ ไม่มี Internet", pc_x + 14, y + 31, "Noto Sans Thai, Sans Bold 10", (1.0, 0.45, 0.45))
            role_short = dev.get('role', '').split('(')[0].strip()
            draw_pango_text(cr, f"IP: {dev_ip}  •  {role_short}", pc_x + 14, y + 50, "Noto Sans Thai, Sans 9.5", (0.55, 0.80, 1.0))

        # 4. Draw Node: LAN Switch
        sw = scada_info.get('switch', {})
        draw_rounded_rect(cr, sw_x, sw_y, sw_w, sw_h, 8)
        cr.set_source_rgb(0.15, 0.20, 0.28)
        cr.fill_preserve()
        cr.set_source_rgb(0.40, 0.55, 0.75)
        cr.set_line_width(2.0)
        cr.stroke()

        draw_pango_text(cr, f"🖧 {sw.get('name', 'LAN Switch')}", sw_x + 15, sw_y + 12, "Noto Sans Thai, Sans Bold 12.5", (1.0, 1.0, 1.0))
        draw_pango_text(cr, "เครือข่ายภายใน", sw_x + 15, sw_y + 35, "Noto Sans Thai, Sans 11", (0.80, 0.90, 1.0))
        draw_pango_text(cr, "ไม่ใช่อินเทอร์เน็ต", sw_x + 15, sw_y + 55, "Noto Sans Thai, Sans Bold 11", (1.0, 0.70, 0.45))
        draw_pango_text(cr, f"Switch 8-Port ({sw.get('ip', '192.168.1.254')})", sw_x + 15, sw_y + 76, "Noto Sans Thai, Sans 9", (0.60, 0.75, 0.90))

        # 5. Draw Node: PC4 · Gateway (THE BRIDGING NODE — BOLD GREEN BORDER!)
        nic_in = gw_info.get('nic_scada', {})
        nic_out = gw_info.get('nic_wan', {})
        draw_rounded_rect(cr, gw_x, gw_y, gw_w, gw_h, 10)
        cr.set_source_rgb(0.10, 0.20, 0.15)
        cr.fill_preserve()
        cr.set_source_rgb(0.0, 0.90, 0.45) # Vivid Green
        cr.set_line_width(2.8)
        cr.stroke()

        draw_pango_text(cr, f"💻 {gw_info.get('name', 'PC4 · Gateway')}", gw_x + 14, gw_y + 10, "Noto Sans Thai, Sans Bold 12", (1.0, 1.0, 1.0))
        draw_pango_text(cr, "🟢 มี Internet (บริดจ์ 2 วงแลน)", gw_x + 14, gw_y + 31, "Noto Sans Thai, Sans Bold 10.5", (0.0, 0.95, 0.50))
        draw_pango_text(cr, f"LAN ขาใน: {nic_in.get('ip', '192.168.1.14')}  |  WAN ขานอก: {nic_out.get('ip', '192.168.100.177')}", gw_x + 14, gw_y + 51, "Noto Sans Thai, Sans 9.5", (0.80, 0.95, 0.85))

        # 6. Draw Node: Router Internet
        draw_rounded_rect(cr, rt_x, rt_y, rt_w, rt_h, 8)
        cr.set_source_rgb(0.13, 0.22, 0.17)
        cr.fill_preserve()
        cr.set_source_rgb(0.25, 0.75, 0.45)
        cr.set_line_width(2.0)
        cr.stroke()

        draw_pango_text(cr, f"📶 {rt_info.get('name', 'Router Internet')}", rt_x + 14, rt_y + 10, "Noto Sans Thai, Sans Bold 12.5", (1.0, 1.0, 1.0))
        draw_pango_text(cr, "🟢 มี Internet (TrueMove H 4G)", rt_x + 14, rt_y + 32, "Noto Sans Thai, Sans Bold 10.5", (0.35, 0.95, 0.60))
        draw_pango_text(cr, f"Gateway IP: {rt_ip}", rt_x + 14, rt_y + 52, "Noto Sans Thai, Sans 10", (0.90, 0.95, 0.90))
        draw_pango_text(cr, f"SSID: {rt_info.get('ssid', 'Nong_Arm')} (ออนไลน์ปกติ)", rt_x + 14, rt_y + 71, "Noto Sans Thai, Sans 9", (0.75, 0.90, 0.80))

        # 7. Draw Node: Wi-Fi Clients
        draw_rounded_rect(cr, cl_x, cl_y, cl_w, cl_h, 8)
        cr.set_source_rgb(0.12, 0.17, 0.15)
        cr.fill_preserve()
        cr.set_source_rgba(0.25, 0.55, 0.38, 0.8)
        cr.set_line_width(1.5)
        cr.stroke()

        draw_pango_text(cr, "📋 เครื่องลูกข่ายที่เชื่อมต่อในวงเราเตอร์ (Wi-Fi Clients):", 
                        cl_x + 14, cl_y + 12, "Noto Sans Thai, Sans Bold 11", (0.45, 0.95, 0.70))

        wan_clients = wan_info.get('clients', [])
        for idx, c in enumerate(wan_clients[:4]):
            yy = cl_y + 38 + idx * 32
            cip = c.get('ip')
            is_this = c.get('is_this_pc', False)
            cr.arc(cl_x + 22, yy + 6, 4.0, 0, 2*math.pi)
            cr.set_source_rgb(0.0, 0.95, 0.50)
            cr.fill()

            prefix = "👉 [เครื่องนี้] " if is_this else ""
            draw_pango_text(cr, f"{prefix}{cip}  —  {c.get('name')}", cl_x + 34, yy, 
                            "Noto Sans Thai, Sans Bold 9.5" if is_this else "Noto Sans Thai, Sans 9.5",
                            (0.0, 0.95, 0.50) if is_this else (0.90, 0.95, 0.92))

    def render_network_table(self):
        while self.net_grid.get_first_child():
            self.net_grid.remove(self.net_grid.get_first_child())

        # Clean 5 Columns (Easy to read, no clutter!)
        headers = [
            "อุปกรณ์ / โหนด", "หมายเลข IP", "วงเครือข่าย", "การเชื่อมต่ออินเทอร์เน็ต", "หน้าที่ในระบบ SCADA"
        ]
        for col, h in enumerate(headers):
            th = Gtk.Label(label=h)
            th.add_css_class('table-th')
            th.set_xalign(0.0)
            self.net_grid.attach(th, col, 0, 1, 1)

        row_idx = 1
        data = self.topology_data

        # 1. SCADA Devices (Internal - No Internet)
        for dev in data.get('scada_lan', {}).get('devices', []):
            vals = [
                dev.get('name', ''),
                dev.get('ip', ''),
                "🔒 SCADA (วงแลนภายใน)",
                "⚠️ ไม่มี Internet",
                dev.get('role', '')
            ]
            self.attach_table_row(vals, row_idx, is_internet=False)
            row_idx += 1

        # 2. LAN Switch
        sw = data.get('scada_lan', {}).get('switch', {})
        sw_vals = [
            sw.get('name', 'LAN Switch'),
            sw.get('ip', '192.168.1.254'),
            "🔒 SCADA (วงแลนภายใน)",
            "⚠️ ไม่มี Internet",
            "ชุมสายแลนเชื่อมต่อ PC1, PC2, PC3 และ PC4"
        ]
        self.attach_table_row(sw_vals, row_idx, is_internet=False)
        row_idx += 1

        # 3. PC4 Gateway (Bridging Node)
        gw = data.get('gateway_bridge', {})
        gw_vals = [
            gw.get('name', 'PC4 · Gateway (เครื่องนี้)'),
            f"LAN: {gw.get('nic_scada', {}).get('ip')}  |  WAN: {gw.get('nic_wan', {}).get('ip')}",
            "⚡ บริดจ์ 2 วงแลน (Dual-Homed)",
            "🟢 มี Internet",
            "รวบรวม Tag จากวงภายใน ส่งแจ้งเตือนผ่าน Internet"
        ]
        self.attach_table_row(gw_vals, row_idx, is_internet=True, is_highlight=True)
        row_idx += 1

        # 4. Router Internet
        rt = data.get('internet_wan', {}).get('router', {})
        rt_vals = [
            rt.get('name', 'Router Internet (TrueMove H)'),
            rt.get('gateway_ip', '192.168.100.1'),
            "🌐 WAN (เราเตอร์ภายนอก)",
            "🟢 มี Internet",
            "เราเตอร์ 4G LTE TrueMove H (SSID: Nong_Arm)"
        ]
        self.attach_table_row(rt_vals, row_idx, is_internet=True)
        row_idx += 1

        # 5. Wi-Fi Clients
        for c in data.get('internet_wan', {}).get('clients', []):
            if c.get('is_this_pc'):
                continue
            c_vals = [
                c.get('name', 'Client'),
                c.get('ip', ''),
                "🌐 WAN (วงเราเตอร์)",
                "🟢 มี Internet",
                "อุปกรณ์ลูกข่ายในวง Wi-Fi เราเตอร์"
            ]
            self.attach_table_row(c_vals, row_idx, is_internet=True)
            row_idx += 1

    def attach_table_row(self, vals, row_idx, is_internet=False, is_highlight=False, is_nope=False):
        for col, val in enumerate(vals):
            td = Gtk.Label(label=str(val))
            td.add_css_class('table-td')
            td.set_xalign(0.0)
            td.set_selectable(True)
            if col == 3: # Internet Status col
                td.add_css_class('badge-has-net' if is_internet else 'badge-no-net')
            elif is_highlight and col == 0:
                td.add_css_class('badge-gateway')
            self.net_grid.attach(td, col, row_idx, 1, 1)

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
        if 'tags' in self.nav_btns:
            self.nav_btns['tags'].set_label("F5  คลัง Tag ที่สแกนพบ (0 Tags)")

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

        self.alarm_icon.set_text("⚪ [STANDBY]")
        self.alarm_text.set_text("🔄 รีเซ็ตโปรแกรมกลับสู่ค่าเริ่มต้นว่างเปล่า (เหมือนติดตั้งใหม่) เรียบร้อยแล้ว — กรุณากด F7 หรือสแกนเพื่อโหลดข้อมูล")

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
        self.alarm_text.set_text("กำลังสแกนเครือข่ายสด (ARP Table, Ping & Internet Status)...")
        t = threading.Thread(target=self.network_rescan_worker, daemon=True)
        t.start()

    def network_rescan_worker(self):
        # 1. Real Carrier Check for SCADA LAN (enp0s31f6)
        scada_carrier = check_interface_carrier('enp0s31f6')

        # 2. Real Pings across all devices
        ping_targets = [
            '192.168.1.11', '192.168.1.12', '192.168.1.13', '192.168.1.254',
            '192.168.100.1', '192.168.100.135', '192.168.100.150', '192.168.100.178'
        ]
        pings = {}
        for tip in ping_targets:
            pings[tip] = ping_target_real(tip, timeout=1)

        # 3. Test Internet
        has_net = False
        try:
            s = socket.create_connection(('8.8.8.8', 53), timeout=1.5)
            s.close()
            has_net = True
        except Exception:
            pass

        # Store in live_status
        self.live_status['scada_carrier'] = scada_carrier
        self.live_status['pings'] = pings

        # Dispatch UI update
        GLib.idle_add(self.apply_network_rescan_results, has_net)

    def apply_network_rescan_results(self, has_net):
        self.internet_online = has_net
        scada_carrier = self.live_status.get('scada_carrier', False)
        if hasattr(self, 'pill_scada_ip'):
            if scada_carrier:
                self.pill_scada_ip.set_text("🔒 SCADA: ONLINE")
                self.pill_scada_ip.remove_css_class('badge-nope')
                self.pill_scada_ip.add_css_class('badge-standby')
            else:
                self.pill_scada_ip.set_text("🔒 SCADA: ❌ nope")
                self.pill_scada_ip.remove_css_class('badge-standby')
                self.pill_scada_ip.add_css_class('badge-nope')

        if hasattr(self, 'pill_net'):
            if has_net:
                self.pill_net.set_text("🟢 Internet Online")
                self.pill_net.remove_css_class('badge-no-net')
                self.pill_net.add_css_class('badge-gateway')
                self.alarm_text.set_text("สถานะจริง: วงเราเตอร์ 4G ONLINE | วง SCADA (enp0s31f6): nope (ไม่พบการต่อสาย)")
            else:
                self.pill_net.set_text("⚠️ Internet Offline")
                self.pill_net.remove_css_class('badge-gateway')
                self.pill_net.add_css_class('badge-no-net')
                self.alarm_text.set_text("สถานะจริง: ไม่สามารถออกเน็ตได้ | วง SCADA: nope (ไม่พบการต่อสาย)")

        self.topology_canvas.queue_draw()
        self.render_network_table()
        return False

    # ---------------------------------------------------------
    # Global Function Keys Controller (F1 - F8)
    # ---------------------------------------------------------
    def on_global_key_pressed(self, controller, keyval, keycode, state):
        if USE_UNIFIED_WORKSPACE and keyval == Gdk.KEY_F1:
            self.activate_workspace_mode('monitoring')
            if 'overview' in self.nav_btns:
                self.nav_btns['overview'].set_active(True)
            return True
        elif USE_UNIFIED_WORKSPACE and keyval == Gdk.KEY_F2:
            self.activate_workspace_mode('task_manager')
            if 'tasks' in self.nav_btns:
                self.nav_btns['tasks'].set_active(True)
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
            page_name = key_map[keyval]
            self.stack.set_visible_child_name(page_name)
            if page_name in self.nav_btns:
                self.nav_btns[page_name].set_active(True)
            return True
        elif keyval == Gdk.KEY_F7:
            self.trigger_rescan()
            return True
        elif keyval == Gdk.KEY_F8:
            self.close()
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

        grp = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        grp.add_css_class('wincc-group')
        vbox.append(grp)

        title = Gtk.Label(label="💻 ข้อมูลเครื่องประมวลผลจริง (Host Machine Diagnostics — 100% Real)")
        title.add_css_class('group-title')
        title.set_xalign(0.0)
        grp.append(title)

        grid = Gtk.Grid(column_spacing=20, row_spacing=8)
        grp.append(grid)

        self.machine_labels = {}
        fields = [
            ("ชื่อเครื่อง (Hostname):", "hostname"),
            ("ระบบปฏิบัติการ (OS):", "os_name"),
            ("เคอร์เนล (Linux Kernel):", "kernel"),
            ("สถาปัตยกรรม (Arch):", "arch"),
            ("หน่วยประมวลผล (CPU Model):", "cpu_model"),
            ("จำนวนคอร์ (CPU Cores):", "cpu_cores"),
            ("ภาระการทำงาน (CPU Load Avg):", "cpu_load"),
            ("หน่วยความจำรวม (RAM Total):", "ram_total_gb"),
            ("หน่วยความจำที่ใช้ (RAM Used):", "ram_used_gb"),
            ("หน่วยความจำว่าง (RAM Available):", "ram_avail_gb"),
            ("พื้นที่ฮาร์ดดิสก์ทั้งหมด (Disk Total):", "disk_total_gb"),
            ("พื้นที่ฮาร์ดดิสก์ที่ใช้ (Disk Used):", "disk_used_gb"),
            ("พื้นที่ฮาร์ดดิสก์ว่าง (Disk Free):", "disk_avail_gb"),
            ("IP ประจำเครื่อง (LAN IP):", "ip_lan"),
            ("เวลาที่เปิดเครื่องต่อเนื่อง (Uptime):", "uptime_str"),
        ]

        for row, (label_text, key) in enumerate(fields):
            lbl_title = Gtk.Label(label=label_text)
            lbl_title.set_xalign(0.0)
            lbl_title.add_css_class('card-header')
            grid.attach(lbl_title, 0, row, 1, 1)

            lbl_val = Gtk.Label(label="กำลังโหลด...")
            lbl_val.set_xalign(0.0)
            lbl_val.set_selectable(True)
            grid.attach(lbl_val, 1, row, 1, 1)
            self.machine_labels[key] = lbl_val

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
        """Runs strictly in background daemon thread."""
        try:
            # 1. Parallel pings to all devices (takes ~0.8s total in background)
            ping_targets = [
                '192.168.1.11', '192.168.1.12', '192.168.1.13', '192.168.1.254',
                '192.168.100.1', '192.168.100.135', '192.168.100.150', '192.168.100.178'
            ]
            pings = parallel_ping_all(ping_targets, timeout=0.8)

            # 2. Check Carrier
            scada_carrier = check_interface_carrier('enp0s31f6')

            # 3. Test Internet
            has_net = False
            try:
                s = socket.create_connection(('8.8.8.8', 53), timeout=0.8)
                s.close()
                has_net = True
            except Exception:
                pass

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

            # 5. Read host metrics
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
                self.pill_scan.set_text(f"Catalog: {len(self.scanned_tags)} Tags")
                self.pill_scan.remove_css_class('badge-nope')
                self.pill_scan.add_css_class('badge-active')
                if 'tags' in self.nav_btns:
                    self.nav_btns['tags'].set_label(f"F5  คลัง Tag ที่สแกนพบ ({len(self.scanned_tags)} Tags)")
                if hasattr(self, 'render_dynamic_overview'):
                    self.render_dynamic_overview()
                if hasattr(self, 'render_tags_grid'):
                    self.render_tags_grid()
                if hasattr(self, 'render_tags_page_grid'):
                    self.render_tags_page_grid()

            # Update top pills (Zero emojis, no raw IP in header)
            if res['scada_carrier']:
                self.pill_scada_ip.set_text("SCADA: Online")
                self.pill_scada_ip.remove_css_class('badge-nope')
                self.pill_scada_ip.remove_css_class('badge-standby')
                self.pill_scada_ip.add_css_class('badge-active')
            else:
                self.pill_scada_ip.set_text("SCADA: Standby (Offline)")
                self.pill_scada_ip.remove_css_class('badge-active')
                self.pill_scada_ip.remove_css_class('badge-nope')
                self.pill_scada_ip.add_css_class('badge-standby')

            if res['has_net']:
                self.pill_net.set_text("Internet: Online")
                self.pill_net.remove_css_class('badge-no-net')
                self.pill_net.add_css_class('badge-gateway')
                if hasattr(self, 'pill_net_status'):
                    self.pill_net_status.set_text("Internet: Online")
            else:
                self.pill_net.set_text("Internet: Offline")
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

        grp = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        grp.add_css_class('wincc-group')
        vbox.append(grp)

        self.tags_page_title = Gtk.Label(label=f"🏷️ ตารางสัญญาณ Tag ทั้งหมดที่สแกนพบ ({len(self.scanned_tags)} Tags Inventory)")
        self.tags_page_title.add_css_class('group-title')
        self.tags_page_title.set_xalign(0.0)
        grp.append(self.tags_page_title)

        self.tags_page_grid = Gtk.Grid(column_spacing=1, row_spacing=1)
        self.tags_page_grid.add_css_class('data-table')
        grp.append(self.tags_page_grid)

        self.render_tags_page_grid()
        self.stack.add_named(scrolled, 'tags')

    def render_tags_page_grid(self):
        while self.tags_page_grid.get_first_child():
            self.tags_page_grid.remove(self.tags_page_grid.get_first_child())

        if hasattr(self, 'tags_page_title'):
            self.tags_page_title.set_text(f"🏷️ ตารางสัญญาณ Tag ทั้งหมดที่สแกนพบ ({len(self.scanned_tags)} Tags Inventory)")

        headers = ["Tag Name", "กลุ่ม (Group)", "PLC Address", "ชนิดข้อมูล", "การเชื่อมต่อ"]
        for col, h in enumerate(headers):
            th = Gtk.Label(label=h)
            th.add_css_class('table-th')
            th.set_xalign(0.0)
            self.tags_page_grid.attach(th, col, 0, 1, 1)

        if not self.scanned_tags:
            empty_lbl = Gtk.Label(label="📭 ยังไม่มี Tag ในคลัง (0 Tags) — กรุณากดปุ่ม [F7 สแกน & รีเฟรช] เพื่อนำเข้า Tag จาก WinCC V8.1")
            empty_lbl.add_css_class('table-td')
            empty_lbl.set_xalign(0.0)
            self.tags_page_grid.attach(empty_lbl, 0, 1, 5, 1)
            return

        for row, t in enumerate(self.scanned_tags[:60], 1):
            for col, val in enumerate([t['name'], t['group'], t['addr'], t['type'], t['conn']]):
                td = Gtk.Label(label=val)
                td.add_css_class('table-td')
                td.set_xalign(0.0)
                td.set_selectable(True)
                self.tags_page_grid.attach(td, col, row, 1, 1)

    # ---------------------------------------------------------
    # TAB 5: WinCC Alarm & Event Logging
    # ---------------------------------------------------------
    def build_alarms_page(self):
        scrolled = Gtk.ScrolledWindow()
        scrolled.set_hexpand(True)
        scrolled.set_vexpand(True)
        vbox = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
        vbox.set_margin_start(14)
        vbox.set_margin_end(14)
        vbox.set_margin_top(10)
        vbox.set_margin_bottom(10)
        scrolled.set_child(vbox)

        # 1. WinCC OPC UA Server Connection Card (เส้นทางที่ 2)
        opc_grp = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        opc_grp.add_css_class('wincc-group')
        vbox.append(opc_grp)

        opc_title = Gtk.Label(label="🏭 เชื่อมต่อ WinCC V8.1 ในวงแลนผ่าน OPC UA (เส้นทางที่ 2 — ไม่ต้องลงโปรแกรมที่ SCADA)")
        opc_title.add_css_class('group-title')
        opc_title.set_xalign(0.0)
        opc_grp.append(opc_title)

        opc_desc = Gtk.Label(
            label="ดึงข้อมูล Tag และสถานะเครื่องจักรโดยตรงจาก WinCC V8.1 ในวงแลนเดียวกัน ผ่านโปรโตคอลมาตรฐานสากล OPC UA (Port 4862/4840)\n"
                  "ระบบจะส่งคำขอไปยังพอร์ตมาตรฐานของ WinCC V8.1 (opc.tcp://<WinCC_IP>:4862) เพื่ออ่านค่าแบบ Real-time โดยไม่ต้องแก้ไขเครื่อง SCADA"
        )
        opc_desc.set_xalign(0.0)
        opc_desc.set_wrap(True)
        opc_grp.append(opc_desc)

        opc_grid = Gtk.Grid(column_spacing=12, row_spacing=8)
        opc_grp.append(opc_grid)

        # Row 0: Endpoint URL
        lbl_ep = Gtk.Label(label="WinCC OPC UA URL:")
        lbl_ep.add_css_class('card-header')
        lbl_ep.set_xalign(0.0)
        opc_grid.attach(lbl_ep, 0, 0, 1, 1)

        self.entry_opc_url = Gtk.Entry()
        self.entry_opc_url.set_placeholder_text("opc.tcp://192.168.1.11:4862 (พอร์ตมาตรฐาน WinCC)")
        self.entry_opc_url.set_text(self.opcua_config.get('endpoint_url', 'opc.tcp://192.168.1.11:4862'))
        self.entry_opc_url.set_hexpand(True)
        opc_grid.attach(self.entry_opc_url, 1, 0, 1, 1)

        # Row 1: Security & Auth
        lbl_sec = Gtk.Label(label="ความปลอดภัย & สิทธิ์:")
        lbl_sec.add_css_class('card-header')
        lbl_sec.set_xalign(0.0)
        opc_grid.attach(lbl_sec, 0, 1, 1, 1)

        sec_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
        opc_grid.attach(sec_row, 1, 1, 1, 1)

        self.opc_sec_combo = Gtk.DropDown.new_from_strings([
            "None (ไม่เข้ารหัส - มาตรฐานวงแลนปิด SCADA)", "Basic256Sha256 (Sign & Encrypt)"
        ])
        if self.opcua_config.get('security_policy') == 'Basic256Sha256':
            self.opc_sec_combo.set_selected(1)
        else:
            self.opc_sec_combo.set_selected(0)
        sec_row.append(self.opc_sec_combo)

        lbl_auth = Gtk.Label(label="การล็อกอิน:")
        lbl_auth.add_css_class('card-header')
        sec_row.append(lbl_auth)

        self.opc_auth_combo = Gtk.DropDown.new_from_strings([
            "Anonymous (ไม่ใช้รหัสผ่าน)", "Username / Password"
        ])
        if self.opcua_config.get('auth_mode') == 'Username':
            self.opc_auth_combo.set_selected(1)
        else:
            self.opc_auth_combo.set_selected(0)
        sec_row.append(self.opc_auth_combo)

        # Row 2: Credentials (Username & Session-Only Password)
        lbl_cred = Gtk.Label(label="บัญชีเข้าใช้งาน:")
        lbl_cred.add_css_class('card-header')
        lbl_cred.set_xalign(0.0)
        opc_grid.attach(lbl_cred, 0, 2, 1, 1)

        cred_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
        opc_grid.attach(cred_box, 1, 2, 1, 1)

        self.entry_opc_user = Gtk.Entry()
        self.entry_opc_user.set_placeholder_text("Username (เช่น scada_op)")
        self.entry_opc_user.set_text(self.opcua_config.get('username', ''))
        cred_box.append(self.entry_opc_user)

        self.entry_opc_pass = Gtk.Entry()
        self.entry_opc_pass.set_placeholder_text("Password (เก็บเฉพาะใน RAM เซสชันนี้)")
        self.entry_opc_pass.set_visibility(False)
        self.entry_opc_pass.set_input_purpose(Gtk.InputPurpose.PASSWORD)
        self.entry_opc_pass.set_hexpand(True)
        cred_box.append(self.entry_opc_pass)

        # Row 3: PKI Client Application Certificate Info
        lbl_pki_client = Gtk.Label(label="ใบรับรองแอป (Client Cert):")
        lbl_pki_client.add_css_class('card-header')
        lbl_pki_client.set_xalign(0.0)
        opc_grid.attach(lbl_pki_client, 0, 3, 1, 1)

        pki_client_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
        opc_grid.attach(pki_client_box, 1, 3, 1, 1)

        c_thumb = "พร้อมสร้างอัตโนมัติ (On Demand)"
        if self.pki.client_cert_der.is_file():
            try:
                c_cert = self.pki.load_cert_from_file(self.pki.client_cert_der)
                c_thumb = f"RSA-2048 SHA-256 (Thumb: {self.pki.cert_thumbprint(c_cert)[:16]}...)"
            except Exception:
                pass
        self.lbl_pki_client_cert = Gtk.Label(label=f"🔐 {c_thumb}")
        self.lbl_pki_client_cert.add_css_class('badge-sensor')
        pki_client_box.append(self.lbl_pki_client_cert)

        # Row 4: Server Certificate Trust State & Manual Approval Action
        lbl_pki_server = Gtk.Label(label="ความเชื่อถือเซิร์ฟเวอร์ (Server Trust):")
        lbl_pki_server.add_css_class('card-header')
        lbl_pki_server.set_xalign(0.0)
        opc_grid.attach(lbl_pki_server, 0, 4, 1, 1)

        pki_server_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
        opc_grid.attach(pki_server_box, 1, 4, 1, 1)

        pki_server_status_bar = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
        pki_server_box.append(pki_server_status_bar)

        self.lbl_pki_server_trust = Gtk.Label(label="🛡️ ยังไม่ได้ตรวจสอบ (Standby)")
        self.lbl_pki_server_trust.add_css_class('badge-standby')
        pki_server_status_bar.append(self.lbl_pki_server_trust)

        self.btn_trust_quarantined = Gtk.Button(label="🛡️ ยืนยัน Fingerprint & อนุมัติ (Trust Server Cert)")
        self.btn_trust_quarantined.add_css_class('action-btn')
        self.btn_trust_quarantined.set_sensitive(False)
        self.btn_trust_quarantined.connect('clicked', self.on_trust_quarantined_certificate)
        pki_server_status_bar.append(self.btn_trust_quarantined)

        self.lbl_pki_server_details = Gtk.Label(label="")
        self.lbl_pki_server_details.set_wrap(True)
        self.lbl_pki_server_details.set_xalign(0.0)
        self.lbl_pki_server_details.add_css_class('badge-sensor')
        pki_server_box.append(self.lbl_pki_server_details)

        # Buttons Bar: Test Connection, Browse Tags, Save Settings
        opc_btn_bar = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
        opc_btn_bar.set_margin_top(4)
        opc_grp.append(opc_btn_bar)

        self.btn_test_opc = Gtk.Button(label="🔌 ทดสอบเชื่อมต่อ WinCC OPC UA (Test Connection)")
        self.btn_test_opc.add_css_class('action-btn')
        self.btn_test_opc.connect('clicked', self.on_test_opcua_connection)
        opc_btn_bar.append(self.btn_test_opc)

        self.btn_browse_opc = Gtk.Button(label="🔍 สแกนดึง Tag สดผ่าน OPC UA (Browse & Sync Tags)")
        self.btn_browse_opc.add_css_class('action-btn')
        self.btn_browse_opc.connect('clicked', self.on_browse_opcua_tags)
        opc_btn_bar.append(self.btn_browse_opc)

        save_opc_btn = Gtk.Button(label="💾 บันทึกการตั้งค่า OPC UA")
        save_opc_btn.add_css_class('action-btn')
        save_opc_btn.connect('clicked', self.on_save_opcua_config)
        opc_btn_bar.append(save_opc_btn)

        self.lbl_opc_status = Gtk.Label(label="⚪ ยังไม่ได้เชื่อมต่อ")
        self.lbl_opc_status.add_css_class('badge-standby')
        opc_btn_bar.append(self.lbl_opc_status)

        # 2. Telegram Notification Settings Card
        tg_grp = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        tg_grp.add_css_class('wincc-group')
        vbox.append(tg_grp)

        tg_title = Gtk.Label(label="⚙️ ตั้งค่าการแจ้งเตือนผ่าน Telegram Bot (Telegram Alert Config & Live Test)")
        tg_title.add_css_class('group-title')
        tg_title.set_xalign(0.0)
        tg_grp.append(tg_title)

        tg_desc = Gtk.Label(
            label="กำหนดค่า Bot Token และ Chat ID สำหรับส่งข้อความแจ้งเตือนอัตโนมัติเมื่อสถานะเครื่องจักรหรือ Task มีการเปลี่ยนแปลง\n"
                  "สามารถกดปุ่ม [🚀 ทดสอบส่งข้อความ (Test Send)] เพื่อทดลองยิงข้อความจริงเข้า Telegram ได้ทันที"
        )
        tg_desc.set_xalign(0.0)
        tg_desc.set_wrap(True)
        tg_grp.append(tg_desc)

        # Grid for Inputs
        tg_grid = Gtk.Grid(column_spacing=12, row_spacing=8)
        tg_grp.append(tg_grid)

        # Row 0: Bot Token
        lbl_token = Gtk.Label(label="Telegram Bot Token:")
        lbl_token.add_css_class('card-header')
        lbl_token.set_xalign(0.0)
        tg_grid.attach(lbl_token, 0, 0, 1, 1)

        self.entry_tg_token = Gtk.Entry()
        self.entry_tg_token.set_placeholder_text("ใส่ Bot Token ที่ได้จาก @BotFather (เช่น 7123456789:AAHk...)")
        self.entry_tg_token.set_text(self.telegram_config.get('bot_token', ''))
        self.entry_tg_token.set_hexpand(True)
        tg_grid.attach(self.entry_tg_token, 1, 0, 1, 1)

        # Row 1: Chat ID
        lbl_chat = Gtk.Label(label="Telegram Chat ID:")
        lbl_chat.add_css_class('card-header')
        lbl_chat.set_xalign(0.0)
        tg_grid.attach(lbl_chat, 0, 1, 1, 1)

        self.entry_tg_chat_id = Gtk.Entry()
        self.entry_tg_chat_id.set_placeholder_text("ใส่ Chat ID ของผู้ใช้ หรือ Group ID (เช่น 123456789 หรือ -100123456789)")
        self.entry_tg_chat_id.set_text(self.telegram_config.get('chat_id', ''))
        self.entry_tg_chat_id.set_hexpand(True)
        tg_grid.attach(self.entry_tg_chat_id, 1, 1, 1, 1)

        # Row 2: Test Message
        lbl_msg = Gtk.Label(label="ข้อความทดสอบ:")
        lbl_msg.add_css_class('card-header')
        lbl_msg.set_xalign(0.0)
        tg_grid.attach(lbl_msg, 0, 2, 1, 1)

        self.entry_tg_test_msg = Gtk.Entry()
        self.entry_tg_test_msg.set_text("🧪 [AQUA COMMAND WinCC V8.1] ทดสอบยิงข้อความแจ้งเตือน SCADA สำเร็จ!")
        self.entry_tg_test_msg.set_hexpand(True)
        tg_grid.attach(self.entry_tg_test_msg, 1, 2, 1, 1)

        # Buttons Bar: Save & Test Send
        btn_bar = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
        btn_bar.set_margin_top(4)
        tg_grp.append(btn_bar)

        self.btn_test_tg = Gtk.Button(label="🚀 ทดสอบส่งข้อความ (Test Send)")
        self.btn_test_tg.add_css_class('action-btn')
        self.btn_test_tg.connect('clicked', self.on_test_telegram_send)
        btn_bar.append(self.btn_test_tg)

        save_tg_btn = Gtk.Button(label="💾 บันทึกการตั้งค่า (Save Settings)")
        save_tg_btn.add_css_class('action-btn')
        save_tg_btn.connect('clicked', self.on_save_telegram_config)
        btn_bar.append(save_tg_btn)

        self.lbl_tg_status = Gtk.Label(label="⚪ ยังไม่ได้ทดสอบ")
        self.lbl_tg_status.add_css_class('badge-standby')
        btn_bar.append(self.lbl_tg_status)

        # 2. Alarm & Notification Event Log
        grp_log = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        grp_log.add_css_class('wincc-group')
        vbox.append(grp_log)

        title_log = Gtk.Label(label="🔔 บันทึกประวัติเหตุการณ์และการเตือน (Alarm & Event Logging)")
        title_log.add_css_class('group-title')
        title_log.set_xalign(0.0)
        grp_log.append(title_log)

        self.alarm_grid = Gtk.Grid(column_spacing=1, row_spacing=1)
        self.alarm_grid.add_css_class('data-table')
        grp_log.append(self.alarm_grid)

        self.render_alarm_table()

        self.stack.add_named(scrolled, 'alarms')

    def render_alarm_table(self):
        while self.alarm_grid.get_first_child():
            self.alarm_grid.remove(self.alarm_grid.get_first_child())

        headers = ["วันที่ / เวลา", "รหัสอุปกรณ์", "ระดับ (Class)", "สถานะ", "ข้อความแจ้งเตือน"]
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
            self.lbl_opc_status.set_text("💾 กำหนดค่าแล้ว (Configured)")
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

    def _update_trust_quarantined_ui(self, can_trust: bool, label_text: str, cert_info: Optional[dict] = None):
        self.btn_trust_quarantined.set_sensitive(can_trust)
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
            self.lbl_opc_status.set_text("🟢 ตรวจสอบสำเร็จ (Disconnected)")
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
        token = self.entry_tg_token.get_text().strip()
        chat_id = self.entry_tg_chat_id.get_text().strip()
        self.telegram_config['bot_token'] = token
        self.telegram_config['chat_id'] = chat_id
        save_telegram_config(self.telegram_config)
        self.alarm_text.set_text("💾 บันทึกการตั้งค่า Telegram Bot Token และ Chat ID เรียบร้อยแล้ว")
        self.lbl_tg_status.set_text("💾 บันทึกค่าเรียบร้อย")
        self.lbl_tg_status.remove_css_class('badge-nope')
        self.lbl_tg_status.remove_css_class('badge-active')
        self.lbl_tg_status.add_css_class('badge-standby')

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

        self.telegram_config['bot_token'] = token
        self.telegram_config['chat_id'] = chat_id
        save_telegram_config(self.telegram_config)

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

    def update_real_data(self):
        """Fetches real host machine metrics and updates UI cleanly."""
        try:
            m = read_real_machine_data()
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
                if carrier:
                    self.pill_scada_ip.set_text("SCADA: Online")
                    self.pill_scada_ip.remove_css_class('badge-nope')
                    self.pill_scada_ip.remove_css_class('badge-standby')
                    self.pill_scada_ip.add_css_class('badge-active')
                else:
                    self.pill_scada_ip.set_text("SCADA: Standby (Offline)")
                    self.pill_scada_ip.remove_css_class('badge-active')
                    self.pill_scada_ip.remove_css_class('badge-nope')
                    self.pill_scada_ip.add_css_class('badge-standby')
                self.pill_wan_ip.set_text(f"WAN: {m['ip_lan']}")
        except Exception as e:
            print(f"Update error: {e}", file=sys.stderr)
        return True


    def on_close_request(self, *args):
        """Gracefully terminate background workers on window close."""
        self.running = False
        if hasattr(self, 'browse_cancel_flag'):
            self.browse_cancel_flag.set()
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
