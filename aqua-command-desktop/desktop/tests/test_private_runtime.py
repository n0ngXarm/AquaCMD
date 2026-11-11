"""Private catalog selection and existing mapping compatibility; no network."""
import asyncio
import importlib
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from opcua_mapping import NodeIdMapper


class PrivateRuntimeTests(unittest.TestCase):
    def resolver(self):
        try:
            return importlib.import_module('private_runtime')
        except ModuleNotFoundError:
            self.fail('Private catalog selection is unavailable')

    def test_explicit_private_catalog_has_priority_and_missing_does_not_fallback(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            private = root / 'selected.txt'
            with patch.dict(os.environ, {'AQUACMD_CATALOG_PATH': str(private)}), patch.object(Path, 'home', return_value=root):
                self.assertEqual(self.resolver().catalog_path(root / 'profile'), private)
                self.assertFalse(private.exists())

    def test_private_profile_catalog_precedes_legacy_downloads(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            profile = root / 'profile'
            path = profile / 'catalog' / 'Export all.txt'
            path.parent.mkdir(parents=True)
            path.write_text('LAB fixture')
            with patch.dict(os.environ, {}, clear=True), patch.object(Path, 'home', return_value=root):
                self.assertEqual(self.resolver().catalog_path(profile), path)
                path.unlink()
                self.assertEqual(self.resolver().catalog_path(profile), root / 'Downloads' / 'Export all.txt')

    def test_new_install_mapping_is_an_empty_template(self):
        path = Path(__file__).resolve().parents[2] / 'config/opcua_tag_mapping.json'
        self.assertEqual(json.loads(path.read_text())['mappings'], {})

    def test_existing_private_mapping_keeps_exact_tag_node_and_namespace(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / 'mapping.json'
            tag = 'LAB.Existing_Name'
            payload = {'mappings': {tag: {'node_id_identifier': 's=Exact.Node', 'namespace_uri': 'urn:lab:existing', 'verified': True}}}
            path.write_text(json.dumps(payload))
            before = path.read_bytes()
            mapper = NodeIdMapper(path)
            class Client:
                async def get_namespace_index(self, uri):
                    self.uri = uri
                    return 3
            client = Client()
            self.assertTrue(mapper.is_allowed(tag))
            self.assertFalse(mapper.is_allowed(tag.lower()))
            ok, node, error = asyncio.run(mapper.resolve_node_id_string(tag, client))
            self.assertTrue(ok)
            self.assertEqual(node, 'ns=3;s=Exact.Node')
            self.assertEqual(client.uri, 'urn:lab:existing')
            self.assertIsNone(error)
            self.assertEqual(path.read_bytes(), before)
