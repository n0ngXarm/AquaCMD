"""Passive Linux network snapshot. No scans, DNS, remote sockets or configuration writes."""
import ipaddress
import json
import platform
import socket
import subprocess
import time
from datetime import datetime, timezone
from pathlib import Path

from gi.repository import Gio, GLib

if __package__:
    from .f3_evidence import local_snapshot_state
else:
    from f3_evidence import local_snapshot_state


def _unpack(value):
    if isinstance(value, GLib.Variant):
        return _unpack(value.unpack())
    if isinstance(value, dict):
        return {k: _unpack(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_unpack(v) for v in value]
    return value


def _nm_properties():
    """Read a bounded subset of NetworkManager properties; never request a scan."""
    deadline = time.monotonic() + 3.0
    bus = Gio.bus_get_sync(Gio.BusType.SYSTEM, None)

    def call(path, interface, method, parameters=None):
        remaining = int((deadline - time.monotonic()) * 1000)
        if remaining <= 0:
            raise TimeoutError("NetworkManager property deadline")
        return _unpack(bus.call_sync('org.freedesktop.NetworkManager', path, interface, method,
            parameters, None, Gio.DBusCallFlags.NONE, min(remaining, 500), None))

    def props(path, name):
        return call(path, 'org.freedesktop.DBus.Properties', 'GetAll', GLib.Variant('(s)', (name,)))[0]

    manager = 'org.freedesktop.NetworkManager'
    root = '/org/freedesktop/NetworkManager'
    devices = call(root, manager, 'GetDevices')[0]
    records = {}
    for path in devices[:32]:
        item = props(path, 'org.freedesktop.NetworkManager.Device')
        name, kind = item.get('Interface'), item.get('DeviceType')
        if not name or name == 'lo':
            continue
        state = item.get('State')
        record = {'interface_type': {1: 'ETHERNET', 2: 'WIFI', 13: 'BRIDGE', 14: 'GENERIC',
                                   16: 'TUN', 20: 'VETH', 29: 'WIREGUARD', 30: 'WIFI_P2P'}.get(kind, 'OTHER'),
            'device_type_code': kind,
            'connection_state': {10: 'UNMANAGED', 20: 'UNAVAILABLE', 30: 'DISCONNECTED',
                100: 'CONNECTED', 120: 'FAILED'}.get(state, 'CONNECTING' if isinstance(state, int) and 40 <= state < 100 else 'UNKNOWN'),
            'active': state == 100, 'source': 'NETWORKMANAGER_DBUS', 'speed_mbps': None}
        record['field_sources'] = {field: 'NETWORKMANAGER_DBUS' for field in
            ('interface_type', 'connection_state', 'active', 'speed_mbps')}
        if kind in (1, 2):
            extra = props(path, 'org.freedesktop.NetworkManager.Device.' + ('Wired' if kind == 1 else 'Wireless'))
            rate = extra.get('Speed' if kind == 1 else 'Bitrate')
            if isinstance(rate, (int, float)) and rate > 0:
                record['speed_mbps'] = rate if kind == 1 else rate / 1000
            record['speed_kind'] = 'DESIGN_SPEED' if kind == 1 else 'CURRENT_BITRATE'
            if kind == 1 and isinstance(extra.get('Carrier'), bool):
                record['carrier'] = extra['Carrier']
                record['field_sources']['carrier'] = 'NETWORKMANAGER_DBUS'
        ip4 = item.get('Ip4Config')
        if ip4 and ip4 != '/':
            config = props(ip4, 'org.freedesktop.NetworkManager.IP4Config')
            addresses = []
            for address in config.get('AddressData', []):
                try:
                    addresses.append(str(ipaddress.IPv4Interface(f"{address['address']}/{address['prefix']}")))
                except (ValueError, KeyError, TypeError):
                    continue
            record.update(ipv4_addresses=addresses, ipv4=addresses[0] if addresses else None,
                          gateway=config.get('Gateway') or None)
            record['field_sources'].update({field: 'NETWORKMANAGER_DBUS' for field in ('ipv4', 'ipv4_addresses', 'gateway')})
        records[name] = record
    connectivity = 'UNKNOWN'
    try:
        status = props(root, manager)
        if status.get('ConnectivityCheckEnabled') is not False:
            connectivity = {1: 'NONE', 2: 'PORTAL', 3: 'LIMITED', 4: 'FULL'}.get(
                status.get('Connectivity'), 'UNKNOWN')
    except (GLib.Error, OSError, ValueError, TimeoutError):
        pass
    return records, connectivity


def read_router_path(target):
    """Ask the local routing table which IPv4 source and interface it would use."""
    result = {'target': target, 'status': 'UNKNOWN'}
    try:
        address = str(ipaddress.IPv4Address(target))
        route = subprocess.run(['ip', '-j', '-4', 'route', 'get', address], capture_output=True,
                               text=True, timeout=1.0, env={'LC_ALL': 'C', 'PATH': '/usr/sbin:/usr/bin:/sbin:/bin'})
        if route.returncode:
            if 'Network is unreachable' in route.stderr:
                result['status'] = 'NO_ROUTE'
            return result
        routes = json.loads(route.stdout)
        if not routes:
            return result
        entry = routes[0]
        if entry.get('type') in ('blackhole', 'unreachable', 'prohibit', 'throw'):
            result['status'] = 'NO_ROUTE'
        elif entry.get('dev') == 'lo' or entry.get('type') in ('local', 'broadcast'):
            result['status'] = 'LOCAL'
        elif entry.get('dev') and entry.get('prefsrc'):
            result.update(status='ROUTE', device=entry['dev'], source_ip=str(ipaddress.IPv4Address(entry['prefsrc'])),
                          via=str(ipaddress.IPv4Address(entry['gateway'])) if entry.get('gateway') else None)
    except (OSError, ValueError, KeyError, TypeError, AttributeError, subprocess.SubprocessError):
        pass
    return result


def router_path_summary(snapshot):
    state = local_snapshot_state(snapshot)
    paths = snapshot.get('router_paths', {})
    if state != 'OBSERVED_LOCAL':
        paths = {role: {'target': path['target'], 'status': state} for role, path in paths.items()}
    return {'state': state, 'paths': paths}


def read_linux_snapshot(*, router_targets=None):
    observed = time.time()
    state = {'observed_at': observed, 'timestamp': datetime.fromtimestamp(observed, timezone.utc).isoformat(),
        'state': 'UNKNOWN', 'source': 'LINUX_KERNEL', 'interfaces': {}, 'errors': [],
        'default_gateway': None, 'default_gw_iface': None, 'active_interface': None,
        'connectivity': 'UNKNOWN', 'ip_forwarding': None, 'hostname': socket.gethostname(),
        'os_name': f'{platform.system()} {platform.release()}'}
    try:
        state['ip_forwarding'] = Path('/proc/sys/net/ipv4/ip_forward').read_text().strip() == '1'
        for path in Path('/sys/class/net').iterdir():
            if path.name == 'lo':
                continue
            item = {'ipv4': None, 'ipv4_addresses': [], 'source': 'LINUX_KERNEL',
                'interface_type': 'UNKNOWN', 'connection_state': 'UNKNOWN', 'active': None,
                'carrier': None, 'speed_mbps': None, 'field_sources': {}}
            for field, filename in (('carrier', 'carrier'), ('operstate', 'operstate'), ('mac', 'address')):
                try:
                    value = (path / filename).read_text().strip()
                    item[field] = value == '1' if field == 'carrier' else value
                    item['field_sources'][field] = 'LINUX_SYSFS'
                except OSError:
                    pass
            state['interfaces'][path.name] = item
    except OSError:
        state['errors'].append('SYSFS_UNAVAILABLE')
    try:
        result = subprocess.run(['ip', '-j', '-4', 'addr', 'show'], capture_output=True, text=True, timeout=1.5)
        if result.returncode:
            raise OSError('netlink unavailable')
        for link in json.loads(result.stdout):
            if link.get('ifname') not in state['interfaces']:
                continue
            item = state['interfaces'][link['ifname']]
            addresses = [str(ipaddress.IPv4Interface(f"{a['local']}/{a['prefixlen']}"))
                for a in link.get('addr_info', []) if a.get('family') == 'inet']
            item.update(ipv4_addresses=addresses, ipv4=addresses[0] if addresses else None)
            item['field_sources'].update(ipv4='LINUX_NETLINK', ipv4_addresses='LINUX_NETLINK')
    except (OSError, ValueError, KeyError, subprocess.SubprocessError):
        state['errors'].append('IP_ADDRESS_API_UNAVAILABLE')
    try:
        result = subprocess.run(['ip', '-j', '-4', 'route', 'show', 'default'], capture_output=True, text=True, timeout=1.5)
        if result.returncode:
            raise OSError('netlink unavailable')
        routes = [r for r in json.loads(result.stdout) if r.get('dev') in state['interfaces']]
        if routes:
            route = min(routes, key=lambda r: int(r.get('metric', 0)))
            state.update(default_gateway=route.get('gateway'), default_gw_iface=route['dev'], active_interface=route['dev'])
    except (OSError, ValueError, KeyError, subprocess.SubprocessError):
        state['errors'].append('DEFAULT_ROUTE_API_UNAVAILABLE')
    try:
        records, state['connectivity'] = _nm_properties()
        for name, item in records.items():
            current = state['interfaces'].setdefault(name, {})
            sources = current.get('field_sources', {}) | item.get('field_sources', {})
            current.update(item)
            current['field_sources'] = sources
        state['source'] = 'NETWORKMANAGER_DBUS + LINUX_KERNEL'
    except (GLib.Error, OSError, ValueError, TimeoutError):
        state['errors'].append('NETWORKMANAGER_API_UNAVAILABLE')
    if router_targets:
        state['router_paths'] = {role: read_router_path(target) for role, target in router_targets.items()}
    if state['interfaces']:
        state['state'] = 'OBSERVED_LOCAL'
    return state
