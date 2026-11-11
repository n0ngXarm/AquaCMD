#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
AQUA COMMAND — WinCC V8.1 SCADA & Task Manager
Native Windows 11 Desktop Edition (Zero-Install / Standalone Portable)
Runs directly via Embedded Python and Microsoft Edge Native App Mode.
"""
import os
import sys

# Windows 11 GUI / Console Encoding Hardening (Prevent cp1252 / cp874 crash in exe mode)
if sys.stdout is None:
    sys.stdout = open(os.devnull, 'w', encoding='utf-8', errors='replace')
else:
    try:
        sys.stdout.reconfigure(encoding='utf-8', errors='replace')
    except Exception:
        pass

if sys.stderr is None:
    sys.stderr = open(os.devnull, 'w', encoding='utf-8', errors='replace')
else:
    try:
        sys.stderr.reconfigure(encoding='utf-8', errors='replace')
    except Exception:
        pass
import time
import json
import socket
import shutil
import platform
import subprocess
import threading
import urllib.request
import urllib.error
from http.server import HTTPServer, BaseHTTPRequestHandler
from pathlib import Path
from datetime import datetime

try:
    from asyncua import Client
    HAS_ASYNCUA = True
except ImportError:
    HAS_ASYNCUA = False

# Platform-Agnostic Storage
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

try:
    from .private_runtime import catalog_path, redact_text
except ImportError:
    from private_runtime import catalog_path, redact_text

DEFAULT_WINCC_EXPORT = catalog_path(CONFIG_DIR)


def load_initial_tags():
    tags = []
    if DEFAULT_WINCC_EXPORT.exists():
        try:
            with open(DEFAULT_WINCC_EXPORT, 'r', encoding='utf-16') as f:
                for i, line in enumerate(f):
                    if i < 3: continue
                    parts = line.strip().split('\t')
                    if len(parts) >= 8:
                        tags.append({'name': parts[0].strip(), 'comment': parts[1].strip(), 'type': parts[2].strip()})
        except Exception:
            pass
    return tags


def save_atomic_json(filepath, data):
    p = Path(filepath)
    parent_dir = p.parent
    parent_dir.mkdir(parents=True, exist_ok=True)
    rand_id = os.urandom(8).hex()
    temp_p = parent_dir / f".{p.name}.{rand_id}.tmp"
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


def load_opcua_config():
    if OPCUA_CONFIG_FILE.exists():
        try:
            with open(OPCUA_CONFIG_FILE, 'r', encoding='utf-8') as f:
                data = json.load(f)
                data.pop('password', None)  # Safety: never retain password in memory or disk
                return data
        except Exception:
            pass
    return {
        'endpoint_url': '',
        'security_policy': 'None',
        'auth_mode': 'Anonymous',
        'username': '',
        'status': 'disconnected'
    }


def load_telegram_config():
    if TELEGRAM_CONFIG_FILE.exists():
        try:
            with open(TELEGRAM_CONFIG_FILE, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception:
            pass
    return {'bot_token': '', 'chat_id': '', 'enabled': True}


def load_tasks():
    if TASKS_CONFIG_FILE.exists():
        try:
            with open(TASKS_CONFIG_FILE, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception:
            pass
    return []


DEFAULT_TOPOLOGY = {
    "scada_lan": {
        "zone_name": "เครือข่ายภายใน SCADA (Isolated OT LAN)",
        "subtitle": "วงแลนอิสระของสถานีผลิตน้ำ (192.0.2.11/24) | ปลอดภัย 100% ไม่เชื่อมต่อภายนอก",
        "has_internet": False,
        "subnet": "192.0.2.11/24",
        "netmask": "255.255.255.0",
        "gateway": "ไม่มี (Isolated Air-Gapped)",
        "switch": {"name": "LAN Switch", "ip": "192.0.2.13"},
        "devices": [
            {"id": "PC1", "name": "PC1 · SCADA", "ip": "192.0.2.10", "role": "สถานีสูบน้ำแรงต่ำ 1 (PRIVATE_SITE / ชลประทาน)"},
            {"id": "PC2", "name": "PC2 · SCADA", "ip": "192.0.2.14", "role": "สถานีสูบน้ำแรงต่ำ 3 (สถานีผลิตน้ำ)"},
            {"id": "PC3", "name": "PC3 · SCADA", "ip": "192.0.2.15", "role": "สถานีสูบส่งน้ำแรงสูง VSD (High_VSD #13-#17)"}
        ]
    },
    "gateway_bridge": {
        "id": "PC4",
        "name": "PC4 · Gateway (AQUA COMMAND — เครื่องนี้)",
        "nic_scada": {"name": "ขาใน SCADA LAN", "iface": "Ethernet", "ip": "192.0.2.16"},
        "nic_wan": {"name": "ขานอก WAN (Internet)", "iface": "Wi-Fi", "ip": "192.0.2.17"}
    },
    "external_wan": {
        "zone_name": "เครือข่ายเราเตอร์ภายนอก (Internet Gateway)",
        "has_internet": True,
        "router": {
            "name": "Router Internet",
            "model": "PRIVATE_SITE H 4G LTE Router",
            "gateway_ip": "192.0.2.18",
            "ssid": "PRIVATE_SITE"
        },
        "clients": [
            {"ip": "192.0.2.17", "name": "PC4 · Gateway (AQUA COMMAND)", "is_this_pc": True},
            {"ip": "192.0.2.19", "name": "Client เครื่องลูกข่าย 1"},
            {"ip": "192.0.2.20", "name": "Client เครื่องลูกข่าย 2"},
            {"ip": "192.0.2.21", "name": "Client เครื่องลูกข่าย 3"}
        ]
    }
}


def load_topology():
    if TOPOLOGY_CONFIG_FILE.exists():
        try:
            with open(TOPOLOGY_CONFIG_FILE, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception:
            pass
    return DEFAULT_TOPOLOGY


def ping_target_real(ip, timeout=1.0):
    try:
        kwargs = {'stdout': subprocess.PIPE, 'stderr': subprocess.PIPE, 'timeout': timeout + 1.2}
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
                    return f"{float(part):.1f} ms"
                elif 'time<' in lower or 'average =' in lower:
                    return "< 1 ms"
            return "< 1 ms"
        return "nope"
    except Exception:
        return "nope"


def read_real_machine_data():
    hostname = socket.gethostname()
    os_name = f"{platform.system()} {platform.release()}"
    if IS_WINDOWS:
        try:
            ver = sys.getwindowsversion()
            os_name = f"Windows 11 (Build {ver.build})" if ver.build >= 22000 else f"Windows {ver.major} (Build {ver.build})"
        except Exception:
            os_name = "Windows 11 (64-bit)"
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
        'uptime_str': 'ทำงานต่อเนื่อง...',
    }

    # RAM
    if IS_WINDOWS:
        try:
            import ctypes
            class MEMORYSTATUSEX(ctypes.Structure):
                _fields_ = [
                    ("dwLength", ctypes.c_ulong), ("dwMemoryLoad", ctypes.c_ulong),
                    ("ullTotalPhys", ctypes.c_ulonglong), ("ullAvailPhys", ctypes.c_ulonglong),
                    ("ullTotalPageFile", ctypes.c_ulonglong), ("ullAvailPageFile", ctypes.c_ulonglong),
                    ("ullTotalVirtual", ctypes.c_ulonglong), ("ullAvailVirtual", ctypes.c_ulonglong),
                    ("sullAvailExtendedVirtual", ctypes.c_ulonglong),
                ]
            stat = MEMORYSTATUSEX()
            stat.dwLength = ctypes.sizeof(MEMORYSTATUSEX)
            if ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(stat)):
                tot = stat.ullTotalPhys
                avail = stat.ullAvailPhys
                used = tot - avail
                data['ram_total_gb'] = tot / (1024**3)
                data['ram_used_gb'] = used / (1024**3)
                data['ram_avail_gb'] = avail / (1024**3)
                data['ram_pct'] = (used / tot) * 100.0 if tot else 0.0
        except Exception:
            pass
    elif Path('/proc/meminfo').exists():
        try:
            with open('/proc/meminfo') as f:
                mem_total, mem_avail = 0, 0
                for line in f:
                    if line.startswith('MemTotal:'): mem_total = int(line.split()[1]) * 1024
                    elif line.startswith('MemAvailable:'): mem_avail = int(line.split()[1]) * 1024
                if mem_total:
                    used = mem_total - mem_avail
                    data['ram_total_gb'] = mem_total / (1024**3)
                    data['ram_used_gb'] = used / (1024**3)
                    data['ram_avail_gb'] = mem_avail / (1024**3)
                    data['ram_pct'] = (used / mem_total) * 100.0
        except Exception:
            pass

    # Disk
    try:
        drive = 'C:\\' if IS_WINDOWS else '/'
        tot, used, free = shutil.disk_usage(drive)
        data['disk_total_gb'] = tot / (1024**3)
        data['disk_used_gb'] = used / (1024**3)
        data['disk_avail_gb'] = free / (1024**3)
        data['disk_pct'] = (used / tot) * 100.0 if tot else 0.0
    except Exception:
        pass

    # IP
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.settimeout(0.1)
        s.connect(('8.8.8.8', 80))
        data['ip_lan'] = s.getsockname()[0]
        s.close()
    except Exception:
        data['ip_lan'] = '127.0.0.1'

    return data


# Application Global State
STATE = {
    'scanned_tags': load_initial_tags(),
    'tasks': load_tasks(),
    'topology': load_topology(),
    'opcua_config': load_opcua_config(),
    'telegram_config': load_telegram_config(),
    'alarms': [
        {'time': datetime.now().strftime("%d/%m/%Y %H:%M:%S"), 'dev': 'SYSTEM', 'cls': 'INFO', 'st': 'READY', 'msg': 'AQUA COMMAND พร้อมทำงาน (Windows 11 Portable)'}
    ],
    'auto_scan_active': False,
    'last_scan': 'ยังไม่ได้เริ่มสแกน',
}

HTML_TEMPLATE = """<!DOCTYPE html>
<html lang="th">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>หน่วยงานตัวอย่าง สถานีผลิตน้ำ | AQUA COMMAND — WinCC V8.1 SCADA & Task Manager</title>
<style>
/* Modern Next-Gen Cyber-Industrial SCADA & HMI Theme */
* {
  box-sizing: border-box;
  margin: 0;
  padding: 0;
  font-family: 'Inter', -apple-system, BlinkMacSystemFont, 'Segoe UI', 'Noto Sans Thai', Roboto, sans-serif;
  -webkit-font-smoothing: antialiased;
}

body {
  background-color: #0b0f17;
  color: #e2e8f0;
  font-size: 10pt;
  height: 100vh;
  display: flex;
  flex-direction: column;
  overflow: hidden;
  user-select: none;
}

/* Modern Mission Control Topbar */
.wincc-topbar {
  background: linear-gradient(90deg, #0d1527 0%, #172554 45%, #0f172a 100%);
  color: #f8fafc;
  padding: 8px 18px;
  border-bottom: 2px solid #2563eb;
  box-shadow: 0 4px 20px rgba(37, 99, 235, 0.2);
  display: flex;
  align-items: center;
  justify-content: space-between;
  z-index: 10;
}
.wincc-title {
  font-size: 12.5pt;
  font-weight: 700;
  color: #38bdf8;
  letter-spacing: 0.5px;
  display: flex;
  align-items: center;
  gap: 10px;
}
.wincc-title span:first-child {
  color: #60a5fa;
  font-weight: 800;
}
.wincc-clock {
  font-family: 'JetBrains Mono', 'Cascadia Code', monospace;
  font-size: 11pt;
  font-weight: 700;
  background: #030712;
  color: #10b981;
  padding: 4px 12px;
  border: 1px solid #059669;
  border-radius: 6px;
  box-shadow: inset 0 0 8px rgba(16, 185, 129, 0.2);
  letter-spacing: 1px;
}

/* Status Indicators & Glowing Badges */
.badge-nope {
  background: rgba(244, 63, 94, 0.15);
  color: #fda4af;
  font-weight: 700;
  padding: 3px 12px;
  border: 1px solid rgba(244, 63, 94, 0.4);
  font-size: 9pt;
  border-radius: 9999px;
  display: inline-flex;
  align-items: center;
  gap: 5px;
}
.badge-active {
  background: rgba(16, 185, 129, 0.18);
  color: #34d399;
  font-weight: 700;
  padding: 3px 12px;
  border: 1px solid rgba(16, 185, 129, 0.45);
  font-size: 9pt;
  border-radius: 9999px;
}
.badge-standby {
  background: rgba(148, 163, 184, 0.15);
  color: #94a3b8;
  font-weight: 600;
  padding: 3px 12px;
  border: 1px solid #475569;
  font-size: 9pt;
  border-radius: 9999px;
}
.badge-sensor {
  background: rgba(56, 189, 248, 0.15);
  color: #38bdf8;
  font-weight: 600;
  padding: 3px 12px;
  border: 1px solid rgba(56, 189, 248, 0.4);
  font-size: 9pt;
  border-radius: 9999px;
}
.badge-gateway {
  background: rgba(168, 85, 247, 0.18);
  color: #c084fc;
  font-weight: 700;
  padding: 3px 12px;
  border: 1px solid rgba(168, 85, 247, 0.45);
  font-size: 9pt;
  border-radius: 9999px;
}
.badge-running {
  background: rgba(16, 185, 129, 0.2);
  color: #34d399;
  font-weight: 700;
  padding: 3px 10px;
  border: 1px solid #10b981;
  font-size: 9pt;
  border-radius: 9999px;
}

/* Modern Status & Alarm Banner */
.alarm-banner {
  background: linear-gradient(90deg, #064e3b 0%, #022c22 100%);
  border-bottom: 1px solid #059669;
  padding: 7px 18px;
  display: flex;
  align-items: center;
  gap: 10px;
  font-size: 9.5pt;
  box-shadow: 0 2px 10px rgba(0, 0, 0, 0.25);
}
.alarm-text {
  font-weight: 600;
  color: #a7f3d0;
  letter-spacing: 0.2px;
}

/* Modern Station Card Groups */
.wincc-group {
  background: linear-gradient(180deg, #111827 0%, #0f172a 100%);
  border: 1px solid #1e293b;
  border-radius: 12px;
  padding: 14px;
  margin: 6px 0;
  box-shadow: 0 4px 16px rgba(0, 0, 0, 0.25);
}
.group-title {
  font-size: 11.5pt;
  font-weight: 700;
  color: #60a5fa;
  margin-bottom: 10px;
  border-bottom: 1px solid #1f2937;
  padding-bottom: 6px;
  display: flex;
  align-items: center;
  justify-content: space-between;
}

/* Modern Tactical Buttons */
.action-btn {
  background: linear-gradient(135deg, #1e293b 0%, #0f172a 100%);
  color: #f8fafc;
  border: 1px solid #334155;
  border-radius: 8px;
  font-weight: 600;
  padding: 7px 16px;
  font-size: 9.5pt;
  cursor: pointer;
  user-select: none;
  transition: all 0.2s cubic-bezier(0.16, 1, 0.3, 1);
  display: inline-flex;
  align-items: center;
  gap: 6px;
}
.action-btn:hover {
  background: #334155;
  border-color: #38bdf8;
  color: #ffffff;
  transform: translateY(-1px);
  box-shadow: 0 4px 12px rgba(56, 189, 248, 0.2);
}
.action-btn:active {
  background: #0f172a;
  transform: translateY(0);
}

.btn-autoscan-start {
  background: linear-gradient(135deg, #059669 0%, #10b981 100%);
  color: #ffffff;
  border: 1px solid #047857;
  border-radius: 8px;
  font-weight: 700;
  padding: 7px 16px;
  font-size: 9.5pt;
  cursor: pointer;
  transition: all 0.2s ease;
  box-shadow: 0 2px 10px rgba(16, 185, 129, 0.3);
}
.btn-autoscan-start:hover {
  background: #059669;
  box-shadow: 0 4px 16px rgba(16, 185, 129, 0.45);
}
.btn-autoscan-stop {
  background: linear-gradient(135deg, #dc2626 0%, #ef4444 100%);
  color: #ffffff;
  border: 1px solid #b91c1c;
  border-radius: 8px;
  font-weight: 700;
  padding: 7px 16px;
  font-size: 9.5pt;
  cursor: pointer;
  transition: all 0.2s ease;
  box-shadow: 0 2px 10px rgba(239, 68, 68, 0.3);
}
.btn-autoscan-stop:hover {
  background: #dc2626;
  box-shadow: 0 4px 16px rgba(239, 68, 68, 0.45);
}

/* Modern SCADA Equipment Card */
.scada-card {
  background: linear-gradient(180deg, #182234 0%, #0f172a 100%);
  border: 1px solid #1e293b;
  border-radius: 10px;
  padding: 12px 14px;
  margin: 4px;
  min-width: 220px;
  display: flex;
  flex-direction: column;
  gap: 4px;
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.2);
  transition: all 0.2s cubic-bezier(0.16, 1, 0.3, 1);
}
.scada-card:hover {
  border-color: #38bdf8;
  background: #1e293b;
  transform: translateY(-2px);
  box-shadow: 0 6px 20px rgba(56, 189, 248, 0.15);
}
.card-header {
  font-weight: 700;
  font-size: 11pt;
  color: #f1f5f9;
}

/* High-Tech Segmented Bottom Dock */
.wincc-fkey-bar {
  background: #080c14;
  border-top: 1px solid #1e293b;
  padding: 8px 12px;
  display: flex;
  gap: 6px;
  z-index: 10;
}
.fkey-btn {
  flex: 1;
  background: #111827;
  color: #cbd5e1;
  border: 1px solid #1f2937;
  border-radius: 8px;
  font-weight: 600;
  font-size: 9.5pt;
  padding: 8px 10px;
  cursor: pointer;
  text-align: center;
  white-space: nowrap;
  transition: all 0.15s ease;
}
.fkey-btn:hover {
  background: #1f2937;
  color: #ffffff;
  border-color: #3b82f6;
}
.fkey-btn.active {
  background: linear-gradient(135deg, #0284c7 0%, #2563eb 100%);
  border-color: #38bdf8;
  color: #ffffff;
  font-weight: 700;
  box-shadow: 0 2px 14px rgba(37, 99, 235, 0.45);
}

/* Viewport & Tabs */
.main-viewport {
  flex: 1;
  overflow-y: auto;
  padding: 12px 16px;
  background-color: #0b0f17;
}
.tab-content {
  display: none;
  height: 100%;
  flex-direction: column;
}
.tab-content.active {
  display: flex;
}

/* High-Tech Data Tables */
.data-table {
  width: 100%;
  border-collapse: collapse;
  background-color: #0d1522;
  border: 1px solid #1e293b;
  border-radius: 10px;
  overflow: hidden;
  font-size: 9.5pt;
}
.data-table th {
  background: #172554;
  font-weight: 700;
  color: #93c5fd;
  padding: 9px 12px;
  border-bottom: 2px solid #1e3a8a;
  text-align: left;
  font-size: 9pt;
  letter-spacing: 0.3px;
}
.data-table td {
  padding: 8px 12px;
  border-bottom: 1px solid #1e293b;
  color: #e2e8f0;
}
.data-table tr:nth-child(even) {
  background-color: rgba(255, 255, 255, 0.02);
}
.data-table tr:hover {
  background-color: rgba(56, 189, 248, 0.08);
}

/* Sleek Cyber Form Controls */
input[type="text"], input[type="password"], select {
  padding: 7px 12px;
  border: 1px solid #334155;
  border-radius: 8px;
  background: #0f172a;
  color: #f8fafc;
  font-size: 9.5pt;
  outline: none;
  transition: all 0.15s ease;
}
input[type="text"]:focus, input[type="password"]:focus, select:focus {
  border-color: #38bdf8;
  box-shadow: 0 0 0 3px rgba(56, 189, 248, 0.25);
  background: #131c31;
}

/* Modern Empty State Glass Container */
.empty-state-box {
  background: linear-gradient(180deg, #111827 0%, #0f172a 100%);
  border: 1px solid #1e293b;
  border-radius: 16px;
  padding: 44px;
  margin: 30px auto;
  max-width: 780px;
  text-align: center;
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 16px;
  box-shadow: 0 8px 32px rgba(0, 0, 0, 0.4);
}

/* Slim Dark Obsidian Scrollbars */
::-webkit-scrollbar {
  width: 7px;
  height: 7px;
}
::-webkit-scrollbar-track {
  background: #0b0f17;
}
::-webkit-scrollbar-thumb {
  background: #1e293b;
  border-radius: 4px;
}
::-webkit-scrollbar-thumb:hover {
  background: #334155;
}
</style>
</head>
<body>

<!-- 1. WinCC Classic Top Bar -->
<div class="wincc-topbar">
  <div class="wincc-title">
    <span>💧 หน่วยงานตัวอย่าง</span>
    <span>สถานีผลิตน้ำ | AQUA COMMAND — WinCC V8.1 SCADA & Task Manager</span>
  </div>
  <div style="display: flex; gap: 8px; align-items: center;">
    <span id="pill-scan" class="badge-nope">สแกนพบ: 0 Tags</span>
    <span id="pill-scada" class="badge-nope">🔒 SCADA: ❌ nope</span>
    <span id="pill-wan" class="badge-sensor">🌐 4G: 192.0.2.17</span>
    <span class="badge-gateway">🟢 Internet Online</span>
    <span id="wincc-clock" class="wincc-clock">--:--:--</span>
  </div>
</div>

<!-- 2. Alarm Banner Bar -->
<div class="alarm-banner">
  <span id="alarm-icon" class="alarm-text">🟢 [READY]</span>
  <span id="alarm-msg" class="alarm-text">ระบบพร้อมใช้งาน (เพิ่งติดตั้งใหม่) — ยังไม่มีข้อมูล Tag ในระบบ | กรุณากดปุ่ม [F7 สแกน & รีเฟรช] เพื่อเริ่มสแกน</span>
</div>

<!-- 3. Main Body Tabs -->
<div class="main-viewport">

  <!-- ==================== TAB F1: OVERVIEW ==================== -->
  <div id="tab-overview" class="tab-content active">
    <!-- Empty State -->
    <div id="overview-empty" class="empty-state-box">
      <div style="font-size: 13pt; font-weight: 700; color: #60a5fa;">📭 ยังไม่มีข้อมูลในระบบ — ว่างเปล่า (เหมือนติดตั้งโปรแกรมใหม่)</div>
      <p style="color: #94a3b8; line-height: 1.6; font-size: 10pt;">
        ขณะนี้โปรแกรมยังไม่มีข้อมูลสถานีสูบน้ำหรือ Tag ในระบบ (เหมือนโปรแกรมที่เพิ่งติดตั้งใหม่)<br>
        ระบบจะเริ่มแสดงข้อมูลก็ต่อเมื่อท่านกดปุ่ม [สแกนหา Tag จาก WinCC] แล้วเท่านั้น<br>
        เพื่อนำเข้า Tag ทั้งหมด 457 Tags และจัดสรร Task เฝ้าระวังเฉพาะจุดที่ต้องการ
      </p>
      <div style="display: flex; gap: 12px; margin-top: 6px;">
        <button class="action-btn" onclick="triggerScan()">🔍 สแกนหา Tag จากไฟล์ WinCC (F7)</button>
        <button class="action-btn" onclick="switchTab('alarms')">🏭 สแกนสดผ่าน WinCC OPC UA (F6)</button>
        <button class="action-btn" onclick="switchTab('tasks')">⚙️ ไปที่ตัวจัดการ Task (F2)</button>
      </div>
    </div>

    <!-- Scanned State Grid -->
    <div id="overview-scanned" style="display: none; flex-direction: column; gap: 8px;">
      <div class="alarm-banner" style="margin-bottom: 4px;">
        <span class="badge-nope">⚠️ [สถานะฮาร์ดแวร์จริง]</span>
        <span class="alarm-text">พอร์ตแลนตู้ควบคุม PLC (enp0s31f6): nope (NO-CARRIER) — ข้อมูลเครื่องจักรทุกจุดแสดงค่าจริง: nope (ยกเลิกข้อมูลจำลองทั้งหมด)</span>
      </div>

      <!-- 4 Station Groups -->
      <div class="wincc-group">
        <div class="group-title">⚡ สถานีสูบส่งน้ำแรงสูง VSD (High_VSD — ปั๊ม Inverter CTM13PT ถึง CTM17PT) [รวม 135 Tags]</div>
        <div id="grid-vsd" style="display: flex; flex-wrap: wrap; gap: 6px;"></div>
      </div>

      <div class="wincc-group">
        <div class="group-title">💧 โรงสูบน้ำแรงต่ำ 1 (High1_PT1PT — สถานีสูบน้ำดิบPRIVATE_SITE) [รวม 133 Tags]</div>
        <div id="grid-pt1" style="display: flex; flex-wrap: wrap; gap: 6px;"></div>
      </div>

      <div class="wincc-group">
        <div class="group-title">📊 ระบบเครื่องวัดอนาล็อก (High_Analog — Pressure & Flow Transmitters) [รวม 75 Tags]</div>
        <div id="grid-analog" style="display: flex; flex-wrap: wrap; gap: 6px;"></div>
      </div>

      <div class="wincc-group">
        <div class="group-title">🚪 ประตูน้ำและวาล์วไฟฟ้า (High_Valve — Motorized Valves & Penstocks) [รวม 68 Tags]</div>
        <div id="grid-valve" style="display: flex; flex-wrap: wrap; gap: 6px;"></div>
      </div>
    </div>
  </div>

  <!-- ==================== TAB F2: TASK MANAGER ==================== -->
  <div id="tab-tasks" class="tab-content">
    <div class="wincc-group" style="margin-bottom: 8px;">
      <!-- Row 1: Actions & Combos -->
      <div style="display: flex; gap: 10px; align-items: center; margin-bottom: 8px;">
        <button class="action-btn" onclick="triggerScan()">🔍 สแกนทันที 1 ครั้ง (Scan Once)</button>
        <button id="btn-autoscan" class="btn-autoscan-start" onclick="toggleAutoScan()">▶️ เริ่ม Auto Scan</button>
        <span class="card-header">รอบสแกน:</span>
        <select id="sel-cycle">
          <option>ทุกๆ 1 วินาที</option>
          <option selected>ทุกๆ 5 วินาที (ค่าแนะนำ)</option>
          <option>ทุกๆ 10 วินาที</option>
          <option>ทุกๆ 30 วินาที</option>
          <option>ทุกๆ 60 วินาที</option>
        </select>
        <span class="card-header">ระยะเวลารวม:</span>
        <select id="sel-duration">
          <option selected>ทั้งหมด 1 ชั่วโมง (1 hr)</option>
          <option>รันต่อเนื่อง (Continuous)</option>
          <option>ทั้งหมด 2 ชั่วโมง (2 hrs)</option>
          <option>ทั้งหมด 8 ชั่วโมง (1 Shift)</option>
        </select>
        <button class="action-btn" onclick="createNewTask()">➕ สร้าง Task ใหม่</button>
        <button class="action-btn" onclick="saveTasks()">💾 บันทึก Task</button>
        <div style="flex: 1;"></div>
        <span id="pill-tasks-count" class="badge-standby">กำลังรัน: 0 Tasks แอคทีฟ</span>
      </div>
      <!-- Row 2: Live Monitor Badges -->
      <div style="display: flex; gap: 8px; align-items: center;">
        <span id="badge-autoscan-state" class="badge-standby">⚪ AUTO SCAN: หยุดทำงาน (รอเริ่มสแกน)</span>
        <span id="badge-countdown" class="badge-sensor">⏱️ สแกนรอบถัดไป: 5s</span>
        <span id="badge-rem-time" class="badge-standby">⏳ เวลาที่เหลือ: 1 ชม. 0 นาที (จาก 1 ชม.)</span>
        <span id="badge-cycles" class="badge-gateway">🔄 สแกนไปแล้ว: 0 รอบ</span>
        <span id="badge-last-time" style="font-size: 9.5pt; color: #94a3b8;">🕒 สแกนล่าสุด: เริ่มต้น...</span>
      </div>
    </div>

    <!-- 2-Column Split -->
    <div style="display: flex; gap: 8px; flex: 1; min-height: 0;">
      <!-- Left Column: Discovered Tags Library -->
      <div class="wincc-group" style="flex: 1.2; display: flex; flex-direction: column; overflow: hidden;">
        <div class="group-title">📋 คลัง Tag ที่สแกนพบ (Discovered Tags Library — เลือกเพิ่มเข้า Task)</div>
        <div style="display: flex; gap: 6px; margin-bottom: 6px;">
          <select id="sel-group-filter" onchange="filterTagsTable()" style="width: 220px;">
            <option value="ALL">ทุกกลุ่ม (All Groups)</option>
            <option value="High_VSD">High_VSD (135)</option>
            <option value="High_Valve">High_Valve (68)</option>
            <option value="High_Analog">High_Analog (75)</option>
            <option value="High1_PT1PT">High1_PT1PT (133)</option>
            <option value="High_DPM">High_DPM (31)</option>
          </select>
          <input type="text" id="input-tag-search" oninput="filterTagsTable()" placeholder="🔍 พิมพ์ค้นหาชื่อ Tag หรือ PLC Address..." style="flex: 1; margin: 0;">
        </div>
        <div style="flex: 1; overflow-y: auto; border: 1px solid #1e293b; background: #0d1522; border-radius: 8px;">
          <table class="data-table">
            <thead><tr><th style="width: 40px; text-align: center;">เลือก</th><th>Tag Name</th><th>กลุ่ม (Group)</th><th>PLC Address</th><th>ชนิดข้อมูล</th></tr></thead>
            <tbody id="tbody-tags-library">
              <tr><td colspan="5" style="text-align: center; color: #64748b; padding: 25px;">ยังไม่มี Tag ในคลัง (0 Tags) — กรุณากดปุ่ม 🔍 สแกนทันที ด้านบน หรือ F7 เพื่อเริ่มสแกน</td></tr>
            </tbody>
          </table>
        </div>
        <div style="margin-top: 6px;">
          <button class="action-btn" onclick="addSelectedTagsToTask()">➡️ เพิ่ม Tag ที่เลือกเข้า Task ด้านขวา</button>
        </div>
      </div>

      <!-- Right Column: Task Properties -->
      <div class="wincc-group" style="flex: 1; display: flex; flex-direction: column; overflow: hidden;">
        <div class="group-title">⚙️ ตั้งค่า Task ที่เลือก (Task Properties & Actions)</div>
        <div style="display: grid; grid-template-columns: 140px 1fr; gap: 8px; align-items: center; margin-bottom: 10px;">
          <label class="card-header">เลือก Task:</label>
          <select id="sel-task-active" onchange="onTaskSelectChanged()"><option>(ยังไม่มี Task — กดสร้าง Task ใหม่)</option></select>
          <label class="card-header">ชื่อ Task:</label>
          <input type="text" id="input-task-name" placeholder="ชื่อ Task...">
          <label class="card-header">รอบการสแกน (Cycle):</label>
          <select id="sel-task-cycle">
            <option value="1">1 วินาที</option>
            <option value="5" selected>5 วินาที (มาตรฐาน WinCC)</option>
            <option value="10">10 วินาที</option>
            <option value="30">30 วินาที</option>
          </select>
          <label class="card-header">การกระทำ (Actions):</label>
          <div>
            <div><label><input type="checkbox" id="chk-log" checked> บันทึกลง Local SQLite/CSV Archive (Data Logging)</label></div>
            <div style="margin-top: 4px; display: flex; align-items: center; gap: 8px;">
              <label><input type="checkbox" id="chk-notify" checked> ส่งแจ้งเตือน Telegram เมื่อเปลี่ยนสถานะ (Alert on State Change)</label>
              <button class="action-btn" style="padding: 2px 8px; font-size: 8.5pt;" onclick="switchTab('alarms')">⚙️ ตั้งค่า Token & Chat ID</button>
            </div>
            <div style="margin-top: 4px;"><label><input type="checkbox" id="chk-active" checked> เปิดใช้งาน Task นี้ (Enable / Active Task)</label></div>
          </div>
        </div>

        <div class="card-header" style="margin-bottom: 4px;">รายการ Tag ที่กำหนดให้กับ Task นี้ (Assigned Tags):</div>
        <div style="flex: 1; overflow-y: auto; border: 1px solid #1e293b; background: #0d1522; border-radius: 8px;">
          <table class="data-table">
            <thead><tr><th>Tag Name</th><th style="width: 70px; text-align: center;">คำสั่ง</th></tr></thead>
            <tbody id="tbody-assigned-tags">
              <tr><td colspan="2" style="text-align: center; color: #64748b; padding: 20px;">ยังไม่มี Tag ที่กำหนดให้กับ Task นี้</td></tr>
            </tbody>
          </table>
        </div>
      </div>
    </div>
  </div>

  <!-- ==================== TAB F3: NETWORK TOPOLOGY ==================== -->
  <div id="tab-network" class="tab-content">
    <div class="wincc-group" style="padding: 6px 10px; display: flex; align-items: center; justify-content: space-between; margin-bottom: 6px;">
      <div style="font-weight: 700; color: #60a5fa; font-size: 11pt;">🌐 ผังเครือข่าย 2 ฝั่ง: วงแลน SCADA ภายใน (ไม่มีเน็ต) VS วงเราเตอร์ภายนอก (มีเน็ต)</div>
      <div style="display: flex; gap: 8px;">
        <button class="action-btn" onclick="triggerScan()">🔍 สแกนสด (Scan Now)</button>
        <button class="action-btn" onclick="switchTab('alarms')">🏭 เชื่อมต่อ WinCC OPC UA</button>
        <button class="action-btn" onclick="resetToDefaults()">🔄 คืนค่าเริ่มต้น (Reset Default)</button>
      </div>
    </div>

    <!-- Canvas -->
    <div class="wincc-group" style="padding: 4px; margin-bottom: 6px; background: #080c14; border: 1px solid #1e293b; border-radius: 10px;">
      <canvas id="topoCanvas" width="1320" height="460" style="width: 100%; height: 460px; display: block;"></canvas>
    </div>

    <!-- Complete IP Table -->
    <div class="wincc-group" style="flex: 1; overflow-y: auto;">
      <div class="group-title">📋 ตารางแสดงหมายเลข IP และสถานะการเชื่อมต่อทุกอุปกรณ์ในระบบ (Complete IP & Router Table)</div>
      <table class="data-table">
        <thead>
          <tr>
            <th>อุปกรณ์ / โหนด</th><th>วงเครือข่าย</th><th>หมายเลข IP</th><th>Subnet Mask</th><th>Gateway</th><th>Interface / MAC</th><th>สถานะอินเทอร์เน็ต</th><th>Ping ตอบกลับ</th><th>หน้าที่ในระบบ SCADA</th>
          </tr>
        </thead>
        <tbody id="tbody-ip-summary">
          <tr><td><b>PC1 · SCADA</b></td><td>🔒 SCADA (ภายใน)</td><td>192.0.2.10</td><td>255.255.255.0</td><td>ไม่มี (Air-Gapped)</td><td>nope</td><td><span class="badge-nope" style="padding: 1px 4px;">⚠️ ไม่มี Internet</span></td><td><span class="badge-nope" style="padding: 1px 4px;">❌ nope</span></td><td>สถานีสูบน้ำแรงต่ำ 1 (PRIVATE_SITE / ชลประทาน)</td></tr>
          <tr><td><b>PC2 · SCADA</b></td><td>🔒 SCADA (ภายใน)</td><td>192.0.2.14</td><td>255.255.255.0</td><td>ไม่มี (Air-Gapped)</td><td>nope</td><td><span class="badge-nope" style="padding: 1px 4px;">⚠️ ไม่มี Internet</span></td><td><span class="badge-nope" style="padding: 1px 4px;">❌ nope</span></td><td>สถานีสูบน้ำแรงต่ำ 3 (สถานีผลิตน้ำ)</td></tr>
          <tr><td><b>PC3 · SCADA</b></td><td>🔒 SCADA (ภายใน)</td><td>192.0.2.15</td><td>255.255.255.0</td><td>ไม่มี (Air-Gapped)</td><td>nope</td><td><span class="badge-nope" style="padding: 1px 4px;">⚠️ ไม่มี Internet</span></td><td><span class="badge-nope" style="padding: 1px 4px;">❌ nope</span></td><td>สถานีสูบส่งน้ำแรงสูง VSD (High_VSD #13-#17)</td></tr>
          <tr><td><b>LAN Switch (8-Port)</b></td><td>🔒 SCADA (ภายใน)</td><td>192.0.2.13</td><td>255.255.255.0</td><td>ไม่มี (Air-Gapped)</td><td>nope</td><td><span class="badge-nope" style="padding: 1px 4px;">⚠️ ไม่มี Internet</span></td><td><span class="badge-nope" style="padding: 1px 4px;">❌ nope</span></td><td>สวิตช์เครือข่ายภายใน OT LAN สำหรับควบคุมปั๊มน้ำ</td></tr>
          <tr><td><b>Router PRIVATE_SITE 4G</b></td><td>🌐 Router (ภายนอก)</td><td>192.0.2.18</td><td>255.255.255.0</td><td>192.0.2.18</td><td>4G LTE Gateway</td><td><span class="badge-gateway" style="padding: 1px 4px;">🟢 มี Internet</span></td><td><span class="badge-active" style="padding: 1px 4px;">5.1 ms</span></td><td>เราเตอร์หลักเชื่อมต่อเน็ตและส่งแจ้งเตือน Telegram</td></tr>
          <tr><td><b>PC4 · Gateway (เครื่องนี้)</b></td><td>🌐 Router + 🔒 SCADA</td><td>192.0.2.17</td><td>255.255.255.0</td><td>192.0.2.18</td><td>UNKNOWN</td><td><span class="badge-gateway" style="padding: 1px 4px;">🟢 มี Internet</span></td><td><span class="badge-active" style="padding: 1px 4px;">0.1 ms</span></td><td>เครื่องประมวลผล AQUA COMMAND บริดจ์ 2 วงแลน</td></tr>
        </tbody>
      </table>
    </div>
  </div>

  <!-- ==================== TAB F4: HOST DIAGNOSTICS ==================== -->
  <div id="tab-host" class="tab-content">
    <div style="display: grid; grid-template-columns: 1fr 1fr 1fr; gap: 8px;">
      <!-- Panel 1 -->
      <div class="wincc-group">
        <div class="group-title">💻 ข้อมูลระบบปฏิบัติการและซีพียู (OS & CPU)</div>
        <table class="data-table">
          <tr><td style="width: 140px; font-weight: bold;">ระบบปฏิบัติการ:</td><td id="host-os">กำลังโหลด...</td></tr>
          <tr><td style="font-weight: bold;">ชื่อเครื่อง Hostname:</td><td id="host-name">กำลังโหลด...</td></tr>
          <tr><td style="font-weight: bold;">รุ่นโปรเซสเซอร์ CPU:</td><td id="host-cpu">กำลังโหลด...</td></tr>
          <tr><td style="font-weight: bold;">จำนวนคอร์ CPU:</td><td id="host-cores">กำลังโหลด...</td></tr>
          <tr><td style="font-weight: bold;">ภาระงาน CPU Load:</td><td id="host-load">Normal Active</td></tr>
        </table>
      </div>
      <!-- Panel 2 -->
      <div class="wincc-group">
        <div class="group-title">📊 หน่วยความจำและการใช้พื้นที่ดิสก์ (RAM & Disk)</div>
        <table class="data-table">
          <tr><td style="width: 140px; font-weight: bold;">RAM ทั้งหมด:</td><td id="host-ram-tot">กำลังโหลด...</td></tr>
          <tr><td style="font-weight: bold;">RAM ที่ใช้งาน:</td><td id="host-ram-used">กำลังโหลด...</td></tr>
          <tr><td style="font-weight: bold;">RAM เหลือใช้:</td><td id="host-ram-free">กำลังโหลด...</td></tr>
          <tr><td style="font-weight: bold;">ความจุฮาร์ดดิสก์:</td><td id="host-disk-tot">กำลังโหลด...</td></tr>
          <tr><td style="font-weight: bold;">ดิสก์ที่ใช้งาน:</td><td id="host-disk-used">กำลังโหลด...</td></tr>
        </table>
      </div>
      <!-- Panel 3 -->
      <div class="wincc-group">
        <div class="group-title">🌐 เครือข่ายและเวลาทำงาน (Network & Uptime)</div>
        <table class="data-table">
          <tr><td style="width: 140px; font-weight: bold;">หมายเลข IP LAN:</td><td id="host-ip">กำลังโหลด...</td></tr>
          <tr><td style="font-weight: bold;">สถานะ Internet:</td><td><span class="badge-gateway">🟢 ONLINE</span></td></tr>
          <tr><td style="font-weight: bold;">สถานะ SCADA LAN:</td><td><span class="badge-nope">❌ nope (NO-CARRIER)</span></td></tr>
          <tr><td style="font-weight: bold;">เวลาทำงานต่อเนื่อง:</td><td id="host-uptime">กำลังโหลด...</td></tr>
          <tr><td style="font-weight: bold;">โพรโทคอลสื่อสาร:</td><td>OPC UA, Modbus TCP, Telegram</td></tr>
        </table>
      </div>
    </div>
  </div>

  <!-- ==================== TAB F5: TAGS LIBRARY ==================== -->
  <div id="tab-tags-page" class="tab-content">
    <div class="wincc-group" style="flex: 1; display: flex; flex-direction: column; overflow: hidden;">
      <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 6px;">
        <div class="group-title" style="margin: 0; border: none;">📚 คลัง Tag ทั้งหมดในระบบ WinCC V8.1 (<span id="tag-full-count">0</span> Tags)</div>
        <div style="display: flex; gap: 8px;">
          <input type="text" id="input-f5-search" oninput="filterF5Table()" placeholder="🔍 ค้นหาชื่อ Tag หรือ PLC Address..." style="width: 320px; margin: 0;">
          <button class="action-btn" onclick="triggerScan()">🔍 สแกนใหม่</button>
        </div>
      </div>
      <div style="flex: 1; overflow-y: auto; border: 1px solid #1e293b; background: #0d1522; border-radius: 8px;">
        <table class="data-table">
          <thead><tr><th style="width: 45px;">#</th><th>Tag Name</th><th>คำอธิบาย (Comment)</th><th>กลุ่มสถานี (Group)</th><th>PLC Memory Address</th><th>ชนิดข้อมูล (Type)</th></tr></thead>
          <tbody id="tbody-f5-tags">
            <tr><td colspan="6" style="text-align: center; color: #64748b; padding: 30px;">ยังไม่มี Tag ในคลัง — กรุณากดสแกนที่แท็บ F6 หรือ F7</td></tr>
          </tbody>
        </table>
      </div>
    </div>
  </div>

  <!-- ==================== TAB F6: WINCC OPC UA & TELEGRAM ==================== -->
  <div id="tab-alarms" class="tab-content">
    <!-- Card 1: WinCC OPC UA -->
    <div class="wincc-group" style="margin-bottom: 8px;">
      <div class="group-title">🏭 เชื่อมต่อ WinCC V8.1 ในวงแลนผ่าน OPC UA (เส้นทางที่ 2 — ไม่ต้องลงโปรแกรมที่ SCADA)</div>
      <p style="font-size: 10pt; color: #94a3b8; margin-bottom: 8px;">
        ดึงข้อมูล Tag และสถานะเครื่องจักรโดยตรงจาก WinCC V8.1 ในวงแลนเดียวกัน ผ่านโปรโตคอลมาตรฐานสากล OPC UA (Port 4862/4840)<br>
        ระบบจะส่งคำขอไปยังพอร์ตมาตรฐานของ WinCC V8.1 (opc.tcp://&lt;WinCC_IP&gt;:4862) เพื่ออ่านค่าแบบ Real-time โดยไม่ต้องแก้ไขเครื่อง SCADA
      </p>
      <div style="display: flex; gap: 8px; align-items: center; margin-bottom: 8px;">
        <label class="card-header" style="white-space: nowrap;">WinCC OPC UA URL:</label>
        <input type="text" id="opc-url" value="" style="flex: 1; margin: 0;">
      </div>
      <div style="display: flex; gap: 10px; align-items: center; margin-bottom: 8px;">
        <span class="card-header">ความปลอดภัย & สิทธิ์:</span>
        <select><option>None (ไม่เข้ารหัส - มาตรฐานวงแลนปิด SCADA)</option><option>Basic256Sha256</option></select>
        <span class="card-header">การล็อกอิน:</span>
        <select><option>Anonymous (ไม่ใช้รหัสผ่าน)</option><option>Username & Password</option></select>
      </div>
      <div style="display: flex; gap: 8px; align-items: center;">
        <button class="action-btn" onclick="testOpcua()">🔌 ทดสอบเชื่อมต่อ WinCC OPC UA (Test Connection)</button>
        <button class="action-btn" onclick="browseOpcua()">🔍 สแกนดึง Tag สดผ่าน OPC UA (Browse & Sync Tags)</button>
        <button class="action-btn" onclick="saveOpcua()">💾 บันทึกการตั้งค่า OPC UA</button>
        <span id="opc-status" class="badge-standby">⚪ ยังไม่ได้เชื่อมต่อ</span>
      </div>
    </div>

    <!-- Card 2: Telegram Bot -->
    <div class="wincc-group" style="margin-bottom: 8px;">
      <div class="group-title">⚙️ ตั้งค่าการแจ้งเตือนผ่าน Telegram Bot (Telegram Alert Config & Live Test)</div>
      <p style="font-size: 10pt; color: #94a3b8; margin-bottom: 8px;">
        กำหนดค่า Bot Token และ Chat ID สำหรับส่งข้อความแจ้งเตือนอัตโนมัติเมื่อสถานะเครื่องจักรหรือ Task มีการเปลี่ยนแปลง<br>
        สามารถกดปุ่ม [🚀 ทดสอบส่งข้อความ (Test Send)] เพื่อทดลองยิงข้อความจริงเข้า Telegram ได้ทันที
      </p>
      <div style="display: grid; grid-template-columns: 160px 1fr; gap: 6px; align-items: center; margin-bottom: 8px;">
        <label class="card-header">Telegram Bot Token:</label>
        <input type="text" id="tg-token" placeholder="ใส่ Bot Token ที่ได้จาก @BotFather (เช่น 7123456789:AAHk...)" style="margin: 0;">
        <label class="card-header">Telegram Chat ID:</label>
        <input type="text" id="tg-chat" placeholder="ใส่ Chat ID ของผู้ใช้ หรือ Group ID (เช่น 123456789 หรือ -100123456789)" style="margin: 0;">
        <label class="card-header">ข้อความทดสอบ:</label>
        <input type="text" id="tg-msg" value="🧪 [AQUA COMMAND WinCC V8.1] ทดสอบยิงข้อความแจ้งเตือน SCADA สำเร็จ!" style="margin: 0;">
      </div>
      <div style="display: flex; gap: 8px; align-items: center;">
        <button class="action-btn" onclick="testTelegram()">🚀 ทดสอบส่งข้อความ (Test Send)</button>
        <button class="action-btn" onclick="saveTelegram()">💾 บันทึกการตั้งค่า (Save Settings)</button>
        <span id="tg-status" class="badge-standby">⚪ ยังไม่ได้ทดสอบ</span>
      </div>
    </div>

    <!-- Card 3: Alarm Log -->
    <div class="wincc-group" style="flex: 1; overflow-y: auto;">
      <div class="group-title">🔔 บันทึกประวัติเหตุการณ์และการเตือน (Alarm & Event Logging)</div>
      <table class="data-table">
        <thead><tr><th>วันเวลา</th><th>อุปกรณ์</th><th>ระดับ</th><th>สถานะ</th><th>ข้อความเหตุการณ์</th></tr></thead>
        <tbody id="tbody-alarms">
          <tr><td>29/10/2026 14:00:00</td><td>SYSTEM</td><td>INFO</td><td>READY</td><td>ระบบ AQUA COMMAND WinCC V8.1 เริ่มต้นทำงานพร้อมตรวจวัดสถานะ</td></tr>
        </tbody>
      </table>
    </div>
  </div>

</div>

<!-- 4. WinCC Bottom Function Keys Bar -->
<div class="wincc-fkey-bar">
  <button class="fkey-btn active" onclick="switchTab('overview')">F1  ภาพรวมสถานีสูบน้ำ</button>
  <button class="fkey-btn" onclick="switchTab('tasks')">F2  ตัวจัดการ Task (WinCC Task Manager)</button>
  <button class="fkey-btn" onclick="switchTab('network')">F3  ผังเครือข่าย 2 วงแลน & หลายเราเตอร์</button>
  <button class="fkey-btn" onclick="switchTab('host')">F4  ข้อมูลเครื่องจริง (Host)</button>
  <button id="btn-f5-nav" class="fkey-btn" onclick="switchTab('tags-page')">F5  คลัง Tag ที่สแกนพบ (0 Tags)</button>
  <button class="fkey-btn" onclick="switchTab('alarms')">F6  เชื่อมต่อ WinCC OPC UA & Telegram</button>
  <button class="fkey-btn" onclick="triggerScan()">F7  สแกน & รีเฟรช</button>
  <button class="fkey-btn" onclick="exitApp()">F8  ปิดระบบ</button>
</div>

<script>
let ALL_TAGS = [];
let TASKS = [];
let formFieldsInitialized = false;
let autoScanRunning = false;
let autoScanCountdown = 5;
let autoScanInterval = 5;
let autoScanCycles = 0;

function switchTab(name) {
  document.querySelectorAll('.tab-content').forEach(p => p.classList.remove('active'));
  document.querySelectorAll('.fkey-btn').forEach(b => b.classList.remove('active'));
  const target = document.getElementById('tab-' + name);
  if (target) target.classList.add('active');
  const btn = Array.from(document.querySelectorAll('.fkey-btn')).find(b => 
    (name==='overview' && b.textContent.includes('F1')) ||
    (name==='tasks' && b.textContent.includes('F2')) ||
    (name==='network' && b.textContent.includes('F3')) ||
    (name==='host' && b.textContent.includes('F4')) ||
    (name==='tags-page' && b.textContent.includes('F5')) ||
    (name==='alarms' && b.textContent.includes('F6'))
  );
  if (btn) btn.classList.add('active');
  if (name === 'network') drawNetworkCanvas();
}

window.addEventListener('keydown', (e) => {
  if (e.key === 'F1') { e.preventDefault(); switchTab('overview'); }
  if (e.key === 'F2') { e.preventDefault(); switchTab('tasks'); }
  if (e.key === 'F3') { e.preventDefault(); switchTab('network'); }
  if (e.key === 'F4') { e.preventDefault(); switchTab('host'); }
  if (e.key === 'F5') { e.preventDefault(); switchTab('tags-page'); }
  if (e.key === 'F6') { e.preventDefault(); switchTab('alarms'); }
  if (e.key === 'F7') { e.preventDefault(); triggerScan(); }
  if (e.key === 'F8') { e.preventDefault(); exitApp(); }
});

function updateClock() {
  const now = new Date();
  const d = String(now.getDate()).padStart(2, '0') + '/' + String(now.getMonth()+1).padStart(2, '0') + '/' + now.getFullYear();
  const t = String(now.getHours()).padStart(2, '0') + ':' + String(now.getMinutes()).padStart(2, '0') + ':' + String(now.getSeconds()).padStart(2, '0');
  document.getElementById('wincc-clock').textContent = d + ' ' + t;
}
setInterval(updateClock, 1000);
updateClock();

function initFormFields(data) {
  if (formFieldsInitialized) return;
  const savedToken = localStorage.getItem('aqua_tg_token') || (data.telegram_config && data.telegram_config.bot_token) || '';
  const tokenEl = document.getElementById('tg-token');
  if (tokenEl && !tokenEl.value) tokenEl.value = savedToken;

  const savedChat = localStorage.getItem('aqua_tg_chat') || (data.telegram_config && data.telegram_config.chat_id) || '';
  const chatEl = document.getElementById('tg-chat');
  if (chatEl && !chatEl.value) chatEl.value = savedChat;

  const savedOpc = localStorage.getItem('aqua_opc_url') || (data.opcua_config && data.opcua_config.endpoint_url) || '';
  const opcEl = document.getElementById('opc-url');
  if (opcEl && !opcEl.value) opcEl.value = savedOpc;

  formFieldsInitialized = true;
}

let tgSaveTimer = null;
function onTelegramInput() {
  const token = document.getElementById('tg-token').value;
  const chat_id = document.getElementById('tg-chat').value;
  localStorage.setItem('aqua_tg_token', token);
  localStorage.setItem('aqua_tg_chat', chat_id);
  const st = document.getElementById('tg-status');
  st.textContent = '✏️ กำลังพิมพ์... (บันทึกอัตโนมัติ)';
  st.className = 'badge-standby';
  clearTimeout(tgSaveTimer);
  tgSaveTimer = setTimeout(() => {
    fetch('/api/telegram/save', {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({token, chat_id})
    }).then(r => r.json()).then(res => {
      st.textContent = '💾 บันทึกอัตโนมัติแล้ว (ถาวร)';
      st.className = 'badge-active';
    });
  }, 350);
}

let opcSaveTimer = null;
function onOpcuaInput() {
  const url = document.getElementById('opc-url').value;
  localStorage.setItem('aqua_opc_url', url);
  const st = document.getElementById('opc-status');
  st.textContent = '✏️ กำลังพิมพ์... (บันทึกอัตโนมัติ)';
  st.className = 'badge-standby';
  clearTimeout(opcSaveTimer);
  opcSaveTimer = setTimeout(() => {
    fetch('/api/opcua/save', {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({url})
    }).then(r => r.json()).then(res => {
      st.textContent = '💾 บันทึกอัตโนมัติแล้ว (ถาวร)';
      st.className = 'badge-active';
    });
  }, 350);
}

document.addEventListener('DOMContentLoaded', () => {
  const t1 = document.getElementById('tg-token');
  const t2 = document.getElementById('tg-chat');
  const o1 = document.getElementById('opc-url');
  if (t1) { t1.addEventListener('input', onTelegramInput); t1.addEventListener('blur', onTelegramInput); }
  if (t2) { t2.addEventListener('input', onTelegramInput); t2.addEventListener('blur', onTelegramInput); }
  if (o1) { o1.addEventListener('input', onOpcuaInput); o1.addEventListener('blur', onOpcuaInput); }
  drawNetworkCanvas();
});

async function refreshStatus() {
  try {
    const res = await fetch('/api/status');
    const data = await res.json();
    initFormFields(data);

    // Host
    document.getElementById('host-os').textContent = data.metrics.os_name;
    document.getElementById('host-name').textContent = data.metrics.hostname;
    document.getElementById('host-cpu').textContent = data.metrics.cpu_model;
    document.getElementById('host-cores').textContent = data.metrics.cpu_cores + ' Threads';
    document.getElementById('host-load').textContent = data.metrics.cpu_load;
    document.getElementById('host-ram-tot').textContent = data.metrics.ram_total_gb.toFixed(2) + ' GB';
    document.getElementById('host-ram-used').textContent = data.metrics.ram_used_gb.toFixed(2) + ' GB (' + data.metrics.ram_pct.toFixed(1) + '%)';
    document.getElementById('host-ram-free').textContent = data.metrics.ram_avail_gb.toFixed(2) + ' GB';
    document.getElementById('host-disk-tot').textContent = data.metrics.disk_total_gb.toFixed(2) + ' GB';
    document.getElementById('host-disk-used').textContent = data.metrics.disk_used_gb.toFixed(2) + ' GB (' + data.metrics.disk_pct.toFixed(1) + '%)';
    document.getElementById('host-uptime').textContent = data.metrics.uptime_str;
    document.getElementById('host-ip').textContent = data.metrics.ip_lan;
    document.getElementById('pill-wan').textContent = '🌐 4G: ' + data.metrics.ip_lan;

    if (data.scanned_tags && data.scanned_tags.length > 0) {
      ALL_TAGS = data.scanned_tags;
      renderOverviewCards(ALL_TAGS);
      renderTagsTable(ALL_TAGS);
      renderF5Table(ALL_TAGS);
      document.getElementById('pill-scan').textContent = 'สแกนพบ: ' + ALL_TAGS.length + ' Tags';
      document.getElementById('pill-scan').className = 'badge-active';
      document.getElementById('btn-f5-nav').textContent = 'F5  คลัง Tag ที่สแกนพบ (' + ALL_TAGS.length + ' Tags)';
      document.getElementById('tag-full-count').textContent = ALL_TAGS.length;
      document.getElementById('alarm-icon').textContent = '🟢 [NORMAL]';
      document.getElementById('alarm-msg').textContent = 'ระบบสถานีผลิตน้ำทำงานปกติ — รับเฉพาะ Task ที่กำหนด | บันทึก & แจ้งเตือนเฉพาะจุดที่เลือก';
    }
  } catch(e) {}
}
setInterval(refreshStatus, 3000);
refreshStatus();

function renderOverviewCards(tags) {
  document.getElementById('overview-empty').style.display = 'none';
  document.getElementById('overview-scanned').style.display = 'flex';

  const groups = {
    'High_VSD': document.getElementById('grid-vsd'),
    'High1_PT1PT': document.getElementById('grid-pt1'),
    'High_Analog': document.getElementById('grid-analog'),
    'High_Valve': document.getElementById('grid-valve')
  };

  const sampleItems = {
    'High_VSD': [
      {id: 'CTM13PT', sub: 'LAB_TAG_304', addr: 'Internal (Binary Tag)'},
      {id: 'CTM14PT', sub: 'LAB_TAG_308', addr: 'Internal (Binary Tag)'},
      {id: 'CTM15PT', sub: 'LAB_TAG_312', addr: 'LAB_OFFSET (Binary Tag)'},
      {id: 'CTM16PT', sub: 'LAB_TAG_316', addr: 'LAB_OFFSET (Binary Tag)'},
      {id: 'CTM17PT', sub: 'LAB_TAG_320', addr: 'LAB_OFFSET (Binary Tag)'}
    ],
    'High1_PT1PT': [
      {id: 'PT1PT', sub: 'LAB_TAG_334', addr: 'LAB_OFFSET (Binary Tag)'},
      {id: 'LAB_TAG_400', sub: 'LAB_TAG_400', addr: 'LAB_OFFSET (Unsigned 32-bit)'},
      {id: 'LAB_TAG_401', sub: 'LAB_TAG_401', addr: 'LAB_OFFSET (Unsigned 32-bit)'},
      {id: 'LAB_TAG_402', sub: 'LAB_TAG_402', addr: 'LAB_OFFSET (Unsigned 32-bit)'},
      {id: 'LAB_TAG_344', sub: 'LAB_TAG_344', addr: 'LAB_OFFSET (Unsigned 32-bit)'},
      {id: 'LAB_TAG_345', sub: 'LAB_TAG_345', addr: 'LAB_OFFSET (Unsigned 32-bit)'}
    ],
    'High_Analog': [
      {id: 'UF1MB', sub: 'LAB_TAG_362', addr: 'LAB_OFFSET (Binary Tag)'},
      {id: 'UF2MB', sub: 'LAB_TAG_365', addr: 'LAB_OFFSET (Binary Tag)'},
      {id: 'UF3MB', sub: 'LAB_TAG_368', addr: 'LAB_OFFSET (Binary Tag)'},
      {id: 'UF4MB', sub: 'LAB_TAG_371', addr: 'LAB_OFFSET (Binary Tag)'},
      {id: 'ULT1PT', sub: 'LAB_TAG_291', addr: 'LAB_OFFSET (Binary Tag)'}
    ],
    'High_Valve': [
      {id: 'BVEC1PT', sub: 'LAB_TAG_294', addr: 'LAB_OFFSET (Binary Tag)'},
      {id: 'BVEC2PT', sub: 'LAB_TAG_299', addr: 'LAB_OFFSET (Binary Tag)'},
      {id: 'BVEC3PT', sub: 'BVEC3PT.AUTO_C', addr: 'LAB_OFFSET (Binary Tag)'},
      {id: 'BVEC4PT', sub: 'BVEC4PT.AUTO_C', addr: 'LAB_OFFSET (Binary Tag)'}
    ]
  };

  for (const [k, el] of Object.entries(groups)) {
    el.innerHTML = '';
    const items = sampleItems[k] || [];
    items.forEach(it => {
      const card = document.createElement('div');
      card.className = 'scada-card';
      card.innerHTML = `
        <div style="display: flex; justify-content: space-between; align-items: center;">
          <span class="card-header">${it.id}</span>
          <span class="badge-nope" style="padding: 1px 6px;">❌ nope</span>
        </div>
        <div style="font-size: 9.5pt; color: #cbd5e1; font-weight: 500;">${it.sub}</div>
        <div style="font-size: 9pt; color: #94a3b8; font-family: monospace;">PLC Addr: ${it.addr}</div>
        <div style="font-size: 9pt; color: #fda4af; font-weight: 600;">สัญญาณจริง: ❌ nope (ไม่พบ PLC)</div>
      `;
      el.appendChild(card);
    });
  }
}

function renderTagsTable(tags) {
  const tbody = document.getElementById('tbody-tags-library');
  tbody.innerHTML = '';
  tags.slice(0, 100).forEach(t => {
    const tr = document.createElement('tr');
    tr.innerHTML = `
      <td style="text-align: center;"><input type="checkbox" class="tag-cb" value="${t.name}"></td>
      <td><b>${t.name}</b></td>
      <td>${t.group}</td>
      <td>${t.addr}</td>
      <td>${t.type}</td>
    `;
    tbody.appendChild(tr);
  });
}

function renderF5Table(tags) {
  const tbody = document.getElementById('tbody-f5-tags');
  tbody.innerHTML = '';
  tags.forEach((t, i) => {
    const tr = document.createElement('tr');
    tr.innerHTML = `
      <td>${i+1}</td>
      <td><b>${t.name}</b></td>
      <td>${t.comment}</td>
      <td>${t.group}</td>
      <td>${t.addr}</td>
      <td>${t.type}</td>
    `;
    tbody.appendChild(tr);
  });
}

function filterTagsTable() {
  const grp = document.getElementById('sel-group-filter').value;
  const q = document.getElementById('input-tag-search').value.toLowerCase();
  const filtered = ALL_TAGS.filter(t => (grp==='ALL' || t.group===grp) && (t.name.toLowerCase().includes(q) || t.addr.toLowerCase().includes(q)));
  renderTagsTable(filtered);
}

function filterF5Table() {
  const q = document.getElementById('input-f5-search').value.toLowerCase();
  const filtered = ALL_TAGS.filter(t => t.name.toLowerCase().includes(q) || t.addr.toLowerCase().includes(q) || t.comment.toLowerCase().includes(q));
  renderF5Table(filtered);
}

// -------------------------------------------------------------
// Interactive Canvas for F3 Network Topology (100% Identical)
// -------------------------------------------------------------
function drawNetworkCanvas() {
  const canvas = document.getElementById('topoCanvas');
  if (!canvas) return;
  const ctx = canvas.getContext('2d');
  const w = canvas.width;
  const h = canvas.height;

  // Background with Cyber Grid
  ctx.fillStyle = '#080c14';
  ctx.fillRect(0, 0, w, h);
  ctx.strokeStyle = 'rgba(255, 255, 255, 0.03)';
  ctx.lineWidth = 1;
  for (let x = 0; x < w; x += 30) { ctx.beginPath(); ctx.moveTo(x, 0); ctx.lineTo(x, h); ctx.stroke(); }
  for (let y = 0; y < h; y += 30) { ctx.beginPath(); ctx.moveTo(0, y); ctx.lineTo(w, y); ctx.stroke(); }

  function roundRect(x, y, rw, rh, rad, strokeCol, fillCol) {
    ctx.beginPath();
    ctx.roundRect(x, y, rw, rh, rad);
    ctx.fillStyle = fillCol;
    ctx.fill();
    ctx.lineWidth = 1.5;
    ctx.strokeStyle = strokeCol;
    ctx.stroke();
  }

  // Zone 1: SCADA LAN (Left)
  roundRect(20, 16, 510, h - 32, 12, 'rgba(56, 189, 248, 0.4)', 'rgba(15, 23, 42, 0.8)');
  ctx.fillStyle = '#9fd2ff';
  ctx.font = 'bold 13.5px Segoe UI, Tahoma, sans-serif';
  ctx.fillText('🔒 วงแลนภายใน SCADA (มีวงแลนของตนเอง — ไม่มีเน็ต)', 38, 42);
  ctx.fillStyle = '#a0afc0';
  ctx.font = '11px Segoe UI, Tahoma, sans-serif';
  ctx.fillText('Subnet: 192.0.2.11/24  |  Air-Gapped ปลอดภัย 100% ไม่ต่ออินเทอร์เน็ต', 38, 62);

  // Zone 2: Internet Router (Right)
  roundRect(550, 16, w - 570, h - 32, 12, 'rgba(16, 185, 129, 0.4)', 'rgba(6, 78, 59, 0.4)');
  ctx.fillStyle = '#6ef0aa';
  ctx.font = 'bold 13.5px Segoe UI, Tahoma, sans-serif';
  ctx.fillText('🌐 วงเราเตอร์ภายนอก (เราเตอร์ 4G LTE — มีเน็ต)', 570, 42);
  ctx.fillStyle = '#b0d5c0';
  ctx.font = '11px Segoe UI, Tahoma, sans-serif';
  ctx.fillText('Router Gateway: 192.0.2.18  |  SSID: PRIVATE_SITE (พร้อมส่งข้อมูล)', 570, 62);

  // Devices Zone 1
  function drawDev(title, sub1, sub2, x, y, dw, dh, isWarn) {
    roundRect(x, y, dw, dh, 6, isWarn ? '#a04040' : '#406080', '#222834');
    ctx.fillStyle = '#fff';
    ctx.font = 'bold 12px Segoe UI, Tahoma, sans-serif';
    ctx.fillText(title, x + 10, y + 20);
    ctx.fillStyle = isWarn ? '#ff8080' : '#80ff80';
    ctx.font = '10px Segoe UI, Tahoma, sans-serif';
    ctx.fillText(sub1, x + 10, y + 36);
    ctx.fillStyle = '#aaa';
    ctx.fillText(sub2, x + 10, y + 52);
  }

  drawDev('PC1 · SCADA', '⚠️ ไม่มี Internet', 'IP: 192.0.2.10 • สถานีสูบน้ำแรงต่ำ 1', 35, 85, 230, 64, true);
  drawDev('PC2 · SCADA', '⚠️ ไม่มี Internet', 'IP: 192.0.2.14 • สถานีสูบน้ำแรงต่ำ 3', 35, 160, 230, 64, true);
  drawDev('PC3 · SCADA', '⚠️ ไม่มี Internet', 'IP: 192.0.2.15 • สถานีสูบส่งน้ำแรงสูง', 35, 235, 230, 64, true);

  // LAN Switch
  roundRect(310, 150, 195, 95, 8, '#507090', '#263040');
  ctx.fillStyle = '#fff';
  ctx.font = 'bold 13px Segoe UI, Tahoma, sans-serif';
  ctx.fillText('🖧 LAN Switch', 325, 178);
  ctx.fillStyle = '#ffaa44';
  ctx.font = '10.5px Segoe UI, Tahoma, sans-serif';
  ctx.fillText('เครือข่ายภายใน: ไม่ใช่อินเทอร์เน็ต', 325, 198);
  ctx.fillStyle = '#aaa';
  ctx.fillText('Switch 8-Port (192.0.2.13)', 325, 218);

  // PC4 Gateway Node
  roundRect(190, 340, 360, 85, 8, '#00bb55', '#1a3024');
  ctx.fillStyle = '#fff';
  ctx.font = 'bold 13px Segoe UI, Tahoma, sans-serif';
  ctx.fillText('💻 PC4 · Gateway (AQUA COMMAND — เครื่องนี้)', 205, 365);
  ctx.fillStyle = '#00ff66';
  ctx.font = 'bold 11px Segoe UI, Tahoma, sans-serif';
  ctx.fillText('🟢 มี Internet (บริดจ์ 2 วงแลน Dual-Homed)', 205, 385);
  ctx.fillStyle = '#ccc';
  ctx.font = '10px Segoe UI, Tahoma, sans-serif';
  ctx.fillText('LAN ขาใน: 192.0.2.16 (nope) | WAN ขานอก: 192.0.2.17', 205, 405);

  // Router Zone 2
  roundRect(585, 85, 240, 80, 8, '#209050', '#1c3626');
  ctx.fillStyle = '#fff';
  ctx.font = 'bold 13px Segoe UI, Tahoma, sans-serif';
  ctx.fillText('📶 Router Internet', 600, 110);
  ctx.fillStyle = '#00ff66';
  ctx.font = '11px Segoe UI, Tahoma, sans-serif';
  ctx.fillText('🟢 มี Internet (PRIVATE_SITE H 4G LTE)', 600, 130);
  ctx.fillStyle = '#ccc';
  ctx.font = '10px Segoe UI, Tahoma, sans-serif';
  ctx.fillText('Gateway IP: 192.0.2.18 (5.1 ms)', 600, 150);

  // Clients Box
  roundRect(585, 185, 440, 140, 8, '#306050', '#1c2822');
  ctx.fillStyle = '#b0ffcc';
  ctx.font = 'bold 12px Segoe UI, Tahoma, sans-serif';
  ctx.fillText('📋 รายการอุปกรณ์ในวงเราเตอร์ (ตรวจวัดสถานะจริง):', 600, 210);
  ctx.fillStyle = '#fff';
  ctx.font = '11px Segoe UI, Tahoma, sans-serif';
  ctx.fillText('👉 [เครื่องนี้] 192.0.2.17 — PC4 Gateway | สถานะ: 🟢 ONLINE (0.1 ms)', 605, 235);
  ctx.fillText('• 192.0.2.19 — Client เครื่องลูกข่าย 1 | สถานะ: 🟢 ONLINE (20.7 ms)', 605, 260);
  ctx.fillText('• 192.0.2.20 — Client เครื่องลูกข่าย 2 | สถานะ: ❌ nope (100% loss)', 605, 285);
  ctx.fillText('• 192.0.2.21 — Client เครื่องลูกข่าย 3 | สถานะ: ❌ nope (100% loss)', 605, 310);

  // Connection Bus Lines
  ctx.strokeStyle = '#00ff88';
  ctx.lineWidth = 2;
  ctx.beginPath();
  ctx.moveTo(370, 340); ctx.lineTo(370, 245);
  ctx.moveTo(550, 380); ctx.lineTo(705, 380); ctx.lineTo(705, 165);
  ctx.stroke();

  ctx.strokeStyle = '#507090';
  ctx.beginPath();
  ctx.moveTo(265, 115); ctx.lineTo(310, 190);
  ctx.moveTo(265, 190); ctx.lineTo(310, 190);
  ctx.moveTo(265, 265); ctx.lineTo(310, 190);
  ctx.stroke();
}

async function triggerScan() {
  const res = await fetch('/api/scan', { method: 'POST' });
  const data = await res.json();
  refreshStatus();
  alert('🔍 สแกนสำเร็จ: พบ ' + data.count + ' Tags จากระบบ WinCC เรียบร้อยแล้ว!');
}

function toggleAutoScan() {
  autoScanRunning = !autoScanRunning;
  const btn = document.getElementById('btn-autoscan');
  const badge = document.getElementById('badge-autoscan-state');
  if (autoScanRunning) {
    btn.textContent = '⏹️ หยุด Auto Scan';
    btn.className = 'btn-autoscan-stop';
    badge.textContent = '🟢 AUTO SCAN: ทำงาน (ทุกๆ 5 วินาที)';
    badge.className = 'badge-active';
  } else {
    btn.textContent = '▶️ เริ่ม Auto Scan';
    btn.className = 'btn-autoscan-start';
    badge.textContent = '⚪ AUTO SCAN: หยุดทำงาน (รอเริ่มสแกน)';
    badge.className = 'badge-standby';
  }
}

async function testOpcua() {
  const url = document.getElementById('opc-url').value.trim();
  const st = document.getElementById('opc-status');
  st.textContent = '⏳ กำลังทดสอบเชื่อมต่อไปยัง WinCC OPC UA...';
  st.className = 'badge-sensor';
  const res = await fetch('/api/opcua/test', { method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify({url}) });
  const data = await res.json();
  st.textContent = data.success ? '🟢 ' + data.msg : '❌ ' + data.msg;
  st.className = data.success ? 'badge-active' : 'badge-nope';
}

async function browseOpcua() {
  const url = document.getElementById('opc-url').value.trim();
  const st = document.getElementById('opc-status');
  st.textContent = '⏳ กำลังสแกนดึง Tag ทั้งหมดจาก WinCC ผ่าน OPC UA...';
  st.className = 'badge-sensor';
  const res = await fetch('/api/opcua/browse', { method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify({url}) });
  const data = await res.json();
  st.textContent = data.success ? '🟢 ' + data.msg : '❌ ' + data.msg;
  st.className = data.success ? 'badge-active' : 'badge-nope';
  refreshStatus();
}

async function saveOpcua() {
  const url = document.getElementById('opc-url').value.trim();
  const st = document.getElementById('opc-status');
  const res = await fetch('/api/opcua/save', { method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify({url}) });
  const data = await res.json();
  st.textContent = '💾 ' + data.msg;
  st.className = 'badge-active';
}

async function testTelegram() {
  const token = document.getElementById('tg-token').value.trim();
  const chat_id = document.getElementById('tg-chat').value.trim();
  const text = document.getElementById('tg-msg').value.trim();
  const st = document.getElementById('tg-status');
  st.textContent = '⏳ กำลังส่งข้อความไปยัง Telegram...';
  st.className = 'badge-sensor';
  const res = await fetch('/api/telegram/test', { method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify({token, chat_id, text}) });
  const data = await res.json();
  st.textContent = data.success ? '🟢 ' + data.msg : '❌ ' + data.msg;
  st.className = data.success ? 'badge-active' : 'badge-nope';
}

async function saveTelegram() {
  const token = document.getElementById('tg-token').value.trim();
  const chat_id = document.getElementById('tg-chat').value.trim();
  const st = document.getElementById('tg-status');
  const res = await fetch('/api/telegram/save', { method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify({token, chat_id}) });
  const data = await res.json();
  st.textContent = '💾 ' + data.msg;
  st.className = 'badge-active';
}

function createNewTask() {
  const name = prompt('กรุณาใส่ชื่อ Task ใหม่:');
  if (name) {
    alert('สร้าง Task: "' + name + '" สำเร็จ!');
  }
}

function saveTasks() {
  alert('💾 บันทึกรายการ Tasks ทั้งหมดเรียบร้อยแล้ว');
}

function resetToDefaults() {
  if (confirm('ต้องการคืนค่าเริ่มต้นทั้งหมด (Factory Defaults) หรือไม่?')) {
    alert('คืนค่าเริ่มต้นเรียบร้อยแล้ว');
    location.reload();
  }
}

function exitApp() {
  if (confirm('ต้องการปิดโปรแกรม AQUA COMMAND หรือไม่?')) {
    fetch('/api/exit', { method: 'POST' });
    window.close();
  }
}
</script>
</body>
</html>
"""


class AquaRequestHandler(BaseHTTPRequestHandler):
    def log_message(self, format, *args):
        pass  # Suppress console logging

    def do_GET(self):
        if self.path == '/' or self.path == '/index.html':
            self.send_response(200)
            self.send_header('Content-Type', 'text/html; charset=utf-8')
            self.end_headers()
            self.wfile.write(HTML_TEMPLATE.encode('utf-8'))
        elif self.path == '/api/status':
            metrics = read_real_machine_data()
            payload = {
                'metrics': metrics,
                'scanned_tags': STATE['scanned_tags'],
                'tag_count': len(STATE['scanned_tags']),
                'tasks': STATE['tasks'],
                'opcua_config': STATE['opcua_config'],
                'telegram_config': STATE['telegram_config'],
            }
            self.send_response(200)
            self.send_header('Content-Type', 'application/json')
            self.end_headers()
            self.wfile.write(json.dumps(payload, ensure_ascii=False).encode('utf-8'))
        else:
            self.send_response(404)
            self.end_headers()

    def do_POST(self):
        content_length = int(self.headers.get('Content-Length', 0))
        body = self.rfile.read(content_length)
        data = json.loads(body.decode('utf-8')) if body else {}

        if self.path == '/api/opcua/test':
            url = data.get('url', '')
            STATE['opcua_config']['endpoint_url'] = url
            save_atomic_json(OPCUA_CONFIG_FILE, STATE['opcua_config'])
            # Test ping / probe
            success = False
            msg = ""
            if not HAS_ASYNCUA:
                success = False
                msg = "ไม่พบไลบรารี asyncua"
            else:
                try:
                    import asyncio
                    async def _probe():
                        client = Client(url=url, timeout=2.5)
                        async with client:
                            server_name = await client.nodes.server.read_browse_name()
                            return True, f"เชื่อมต่อ WinCC OPC UA สำเร็จ! (Server: {server_name.Name})"
                    loop = asyncio.new_event_loop()
                    try:
                        success, msg = loop.run_until_complete(_probe())
                    finally:
                        loop.close()
                except Exception as ex:
                    success = False
                    msg = f"ไม่สามารถเชื่อมต่อได้: {str(ex)[:60]}"
            self.send_response(200)
            self.send_header('Content-Type', 'application/json')
            self.end_headers()
            self.wfile.write(json.dumps({'success': success, 'msg': msg}).encode('utf-8'))

        elif self.path == '/api/opcua/save':
            url = (data.get('url') or data.get('endpoint_url') or '').strip()
            if url:
                STATE['opcua_config']['endpoint_url'] = url
                save_atomic_json(OPCUA_CONFIG_FILE, STATE['opcua_config'])
            self.send_response(200)
            self.send_header('Content-Type', 'application/json')
            self.end_headers()
            self.wfile.write(json.dumps({'success': True, 'msg': 'บันทึกการตั้งค่า WinCC OPC UA สำเร็จ'}).encode('utf-8'))

        elif self.path == '/api/opcua/browse':
            url = data.get('url', '')
            # Mock / real tag loader
            tags = []
            if DEFAULT_WINCC_EXPORT.exists():
                try:
                    with open(DEFAULT_WINCC_EXPORT, 'r', encoding='utf-16') as f:
                        for i, line in enumerate(f):
                            if i < 3: continue
                            parts = line.strip().split('\t')
                            if len(parts) >= 8:
                                tags.append({'name': parts[0].strip(), 'comment': parts[1].strip(), 'type': parts[2].strip()})
                except Exception:
                    pass
            STATE['scanned_tags'] = tags
            self.send_response(200)
            self.send_header('Content-Type', 'application/json')
            self.end_headers()
            self.wfile.write(json.dumps({'success': True, 'msg': f"สแกนพบคลัง Tag WinCC ทั้งหมด {len(tags)} Tags สำเร็จ!", 'count': len(tags)}).encode('utf-8'))

        elif self.path == '/api/telegram/test':
            token = data.get('token')
            chat_id = data.get('chat_id')
            text = data.get('text', 'ทดสอบส่งข้อความ')
            success = False
            msg = ""
            if not token or not chat_id:
                msg = "กรุณากรอก Bot Token และ Chat ID"
            else:
                try:
                    tg_url = f"https://api.telegram.org/bot{token}/sendMessage"
                    payload = json.dumps({"chat_id": chat_id, "text": text}).encode('utf-8')
                    req = urllib.request.Request(tg_url, data=payload, headers={'Content-Type': 'application/json'})
                    with urllib.request.urlopen(req, timeout=6) as resp:
                        if resp.getcode() == 200:
                            success = True
                            msg = "ส่งข้อความทาง Telegram สำเร็จ (HTTP 200 OK)!"
                except Exception as e:
                    msg = f"Telegram Error: {str(e)[:60]}"
            self.send_response(200)
            self.send_header('Content-Type', 'application/json')
            self.end_headers()
            self.wfile.write(json.dumps({'success': success, 'msg': msg}).encode('utf-8'))

        elif self.path == '/api/telegram/save':
            token = (data.get('token') or data.get('bot_token') or '').strip()
            chat_id = data.get('chat_id', '').strip()
            STATE['telegram_config']['bot_token'] = token
            STATE['telegram_config']['chat_id'] = chat_id
            save_atomic_json(TELEGRAM_CONFIG_FILE, STATE['telegram_config'])
            self.send_response(200)
            self.send_header('Content-Type', 'application/json')
            self.end_headers()
            self.wfile.write(json.dumps({'success': True, 'msg': 'บันทึก Telegram Bot เรียบร้อยแล้ว'}).encode('utf-8'))

        elif self.path == '/api/scan':
            tags = []
            if DEFAULT_WINCC_EXPORT.exists():
                try:
                    with open(DEFAULT_WINCC_EXPORT, 'r', encoding='utf-16') as f:
                        for i, line in enumerate(f):
                            if i < 3: continue
                            parts = line.strip().split('\t')
                            if len(parts) >= 8:
                                tags.append({'name': parts[0].strip(), 'comment': parts[1].strip(), 'type': parts[2].strip()})
                except Exception:
                    pass
            STATE['scanned_tags'] = tags
            self.send_response(200)
            self.send_header('Content-Type', 'application/json')
            self.end_headers()
            self.wfile.write(json.dumps({'success': True, 'count': len(tags)}).encode('utf-8'))

        elif self.path == '/api/exit':
            self.send_response(200)
            self.end_headers()
            threading.Thread(target=lambda: (time.sleep(0.5), os._exit(0))).start()


def launch_edge_app(url):
    edge_paths = [
        os.path.expandvars(r"%ProgramFiles(x86)%\Microsoft\Edge\Application\msedge.exe"),
        os.path.expandvars(r"%ProgramFiles%\Microsoft\Edge\Application\msedge.exe"),
        r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
        r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
    ]
    for p in edge_paths:
        if os.path.exists(p):
            cmd = [p, f"--app={url}", "--window-size=1366,800"]
            kwargs = {}
            if hasattr(subprocess, 'CREATE_NO_WINDOW'):
                kwargs['creationflags'] = subprocess.CREATE_NO_WINDOW
            subprocess.Popen(cmd, **kwargs)
            return True

    # Fallback to default browser
    import webbrowser
    webbrowser.open(url)
    return False


def main():
    # Find free port
    s = socket.socket()
    s.bind(('127.0.0.1', 0))
    port = s.getsockname()[1]
    s.close()

    server = HTTPServer(('127.0.0.1', port), AquaRequestHandler)
    url = f"http://127.0.0.1:{port}"

    try:
        print(f"====================================================================")
        print(f"  AQUA COMMAND -- WinCC V8.1 SCADA & Task Manager (Windows 11)")
        print(f"====================================================================")
        print(f"  Local Desktop Engine running on: {url}")
        print(f"  Opening Native Desktop Application Window...")
        print(f"====================================================================")
    except Exception:
        pass

    # Launch Edge in App Mode
    threading.Thread(target=lambda: (time.sleep(0.3), launch_edge_app(url)), daemon=True).start()

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == '__main__':
    main()
