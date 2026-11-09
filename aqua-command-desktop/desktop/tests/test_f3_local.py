"""NetworkManager property decoding with an in-memory bus, no network access."""
import unittest
from unittest.mock import Mock, patch

import f3_local


class LocalAdapterTests(unittest.TestCase):
    def bus(self, bitrate=72000, other_type=1):
        records = {
            ('/device/1', 'org.freedesktop.NetworkManager.Device'): {
                'Interface': 'lab-wifi', 'DeviceType': 2, 'State': 100, 'Ip4Config': '/ip4/1'},
            ('/device/1', 'org.freedesktop.NetworkManager.Device.Wireless'): {'Bitrate': bitrate},
            ('/ip4/1', 'org.freedesktop.NetworkManager.IP4Config'): {
                'AddressData': [{'address': '127.0.0.7', 'prefix': 8}, {'address': '127.0.0.8', 'prefix': 8}],
                'Gateway': '127.0.0.1'},
            ('/device/2', 'org.freedesktop.NetworkManager.Device'): {
                'Interface': 'lab-ethernet', 'DeviceType': other_type, 'State': 30, 'Ip4Config': '/'},
            ('/device/2', 'org.freedesktop.NetworkManager.Device.Wired'): {'Speed': 0, 'Carrier': False}}
        bus = Mock()
        def call(service, path, interface, method, parameters, reply, flags, timeout, cancellable):
            self.assertLessEqual(timeout, 500)
            self.assertGreater(timeout, 0)
            self.assertIn(method, ('GetDevices', 'GetAll'))
            return [['/device/1', '/device/2']] if method == 'GetDevices' else [records[path, parameters.unpack()[0]]]
        bus.call_sync.side_effect = call
        return bus

    def test_current_wifi_rate_addresses_and_inactive_ethernet_are_distinct(self):
        with patch.object(f3_local.Gio, 'bus_get_sync', return_value=self.bus()):
            result = f3_local._nm_properties()
        wifi, ethernet = result['lab-wifi'], result['lab-ethernet']
        self.assertEqual(wifi['speed_mbps'], 72)
        self.assertEqual(wifi['speed_kind'], 'CURRENT_BITRATE')
        self.assertEqual(wifi['ipv4_addresses'], ['127.0.0.7/8', '127.0.0.8/8'])
        self.assertTrue(wifi['active'])
        self.assertEqual(ethernet['connection_state'], 'DISCONNECTED')
        self.assertFalse(ethernet['carrier'])
        self.assertIsNone(ethernet['speed_mbps'])
        self.assertNotIn('network_zone', wifi)

    def test_zero_wifi_rate_is_unknown(self):
        with patch.object(f3_local.Gio, 'bus_get_sync', return_value=self.bus(0)):
            self.assertIsNone(f3_local._nm_properties()['lab-wifi']['speed_mbps'])

    def test_bridge_generic_and_p2p_type_codes_are_not_interchanged(self):
        for code, label in ((13, 'BRIDGE'), (14, 'GENERIC'), (30, 'WIFI_P2P')):
            with self.subTest(code=code), patch.object(f3_local.Gio, 'bus_get_sync', return_value=self.bus(other_type=code)):
                self.assertEqual(f3_local._nm_properties()['lab-ethernet']['interface_type'], label)

    def test_unavailable_nm_remains_a_visible_partial_snapshot(self):
        with patch.object(f3_local, '_nm_properties', side_effect=OSError('unavailable')), \
                patch.object(f3_local.subprocess, 'run', side_effect=OSError('unavailable')):
            result = f3_local.read_linux_snapshot()
        self.assertIn('NETWORKMANAGER_API_UNAVAILABLE', result['errors'])
        self.assertIn('IP_ADDRESS_API_UNAVAILABLE', result['errors'])
        self.assertIsNone(result['active_interface'])
        self.assertIsInstance(result['observed_at'], float)

    def test_lowest_metric_default_route_is_primary_without_role_inference(self):
        with patch.object(f3_local, '_nm_properties', return_value={}), \
                patch.object(f3_local.subprocess, 'run') as run:
            # Use current local interface names, but synthetic route and address data only.
            name = next(p.name for p in f3_local.Path('/sys/class/net').iterdir() if p.name != 'lo')
            run.side_effect = [Mock(returncode=0, stdout='[]'), Mock(returncode=0, stdout=f'['
                f'{{"dev":"{name}","gateway":"127.0.0.2","metric":600}},'
                f'{{"dev":"{name}","gateway":"127.0.0.1","metric":10}}]')]
            result = f3_local.read_linux_snapshot()
        self.assertEqual(result['default_gateway'], '127.0.0.1')
        self.assertEqual(result['active_interface'], name)
        self.assertNotIn('SCADA_OT', str(result))


if __name__ == '__main__':
    unittest.main()
