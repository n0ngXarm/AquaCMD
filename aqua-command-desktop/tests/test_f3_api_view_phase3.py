"""Phase 3 frontend packaging/metadata contracts; no field connections."""
import importlib
import json
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


class FrontendContracts(unittest.TestCase):
    def module(self):
        return importlib.import_module('desktop.f3_api_view')

    def test_inline_page_has_only_local_assets_and_escapes_config_metadata(self):
        module = self.module()
        markup = module.build_html({'192.0.2.11': {'label': '</script><script>bad()</script>', 'zone': 'SCADA_OT'}})
        self.assertNotIn('</script><script>bad()', markup)
        self.assertNotIn('<script src=', markup)
        self.assertNotIn('<link rel="stylesheet"', markup)
        self.assertIn('prefers-reduced-motion', markup)
        self.assertIn('/api/f3/evidence', markup)
        self.assertIn('/api/stream', markup)
        self.assertIn('ไม่ได้รับข้อมูลจาก backend', markup)

    def test_metadata_cannot_inject_measurements_or_multiple_addresses(self):
        module = self.module()
        with tempfile.TemporaryDirectory(dir=ROOT/'tests') as temporary:
            path = Path(temporary)/'network.json'
            path.write_text(json.dumps({'devices': [
                {'configured_ip': '192.0.2.11', 'alias': 'Unit A', 'network_zone': 'SCADA_OT',
                 'type': 'wincc', 'observed_ip': '192.0.2.99', 'state': 'READ_OK', 'value': 42.5},
                {'configured_ip': '192.0.2.12 / 198.51.100.10', 'type': 'local_host'},
                {'configured_ip': 'example.invalid', 'network_zone': 'EXTERNAL_WAN'}]}))
            metadata = module.load_metadata(path)
        self.assertEqual(metadata, {'192.0.2.11': {'label': 'Unit A', 'zone': 'SCADA_OT', 'kind': 'wincc'}})

    def test_application_uses_new_api_view_and_closes_it_with_the_window(self):
        source = (ROOT/'desktop/app.py').read_text()
        self.assertTrue('self.f3_network_view = F3ApiView(self)' in source, 'F3 must use the API view')
        self.assertTrue('self.f3_network_view.close()' in source, 'Owner close must stop the API view')

    def test_only_http_loopback_base_is_allowed_in_the_webview(self):
        module = self.module()
        for value in ('https://example.invalid/', 'http://192.0.2.11:4840/', 'file:///etc/passwd',
                      'http://127.0.0.1.evil.invalid:1234/', 'http://user@127.0.0.1:1234/'):
            with self.subTest(value=value):
                self.assertFalse(module.is_api_uri(value, 'http://127.0.0.1:1234'))
        self.assertTrue(module.is_api_uri('http://127.0.0.1:1234/f3/', 'http://127.0.0.1:1234'))


if __name__ == '__main__':
    unittest.main()
