"""Unit and contract tests for F1 Unified Tag Overview & Task Manager WebKit View."""
import json
import re
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock

from f1_api_view import F1ApiView, build_html, validate_payload, ALLOWLISTED_ACTIONS

REPO_ROOT = Path(__file__).resolve().parents[3]
ASSETS_DIR = Path(__file__).resolve().parents[1] / 'f1_api'


class TestF1ApiViewContracts(unittest.TestCase):
    def test_01_build_html_offline_contracts(self):
        markup = build_html()
        self.assertNotIn('<script src=', markup, "Cannot have external script tags")
        self.assertNotIn('<link rel="stylesheet"', markup, "Cannot have external stylesheets")
        self.assertIn('Content-Security-Policy', markup, "Must contain strict CSP")
        self.assertIn("default-src 'none'", markup)
        self.assertIn("font-src data:;", markup)
        self.assertIn('IBM Plex Sans Thai', markup, "Must contain embedded Thai fonts")
        self.assertIn('--surface', markup, "Must contain formal theme tokens")
        self.assertIn('prefers-reduced-motion', markup, "Must support prefers-reduced-motion")

    def test_02_zero_hex_colors_in_f1_assets(self):
        hex_rgb_pattern = re.compile(r'#[0-9a-fA-F]{3,8}\b|rgba?\(', re.IGNORECASE)
        for fname in ('view.css', 'view.js', 'index.html'):
            path = ASSETS_DIR / fname
            if not path.exists():
                continue
            text = path.read_text(encoding='utf-8')
            matches = hex_rgb_pattern.findall(text)
            self.assertEqual(len(matches), 0, f"Found illegal raw colors in {fname}: {matches}")

    def test_03_bridge_payload_validation(self):
        # Valid cases
        self.assertTrue(validate_payload('get_state', {})[0])
        self.assertTrue(validate_payload('undo_last_action', {})[0])
        self.assertTrue(validate_payload('navigate_f6', {})[0])

        self.assertTrue(validate_payload('add_tag_to_task', {'tag_name': 'BVEC1PT.AUTO_C', 'task_id': 'TASK-01'})[0])
        self.assertTrue(validate_payload('add_tags_to_task', {'tag_names': ['BVEC1PT.AUTO_C', 'PT01.PV_BAR'], 'task_id': 'TASK-01'})[0])
        self.assertTrue(validate_payload('remove_tag_from_task', {'tag_name': 'BVEC1PT.AUTO_C', 'task_id': 'TASK-01'})[0])
        self.assertTrue(validate_payload('remove_tags_from_task', {'tag_names': ['BVEC1PT.AUTO_C'], 'task_id': 'TASK-01'})[0])

        valid_task = {
            'id': 'TASK-01',
            'name': 'Task 1',
            'cycle_sec': 5,
            'action_log': True,
            'action_notify': False,
            'active': True
        }
        self.assertTrue(validate_payload('save_task', {'task': valid_task})[0])
        self.assertTrue(validate_payload('create_task', {'task': valid_task})[0])
        self.assertTrue(validate_payload('delete_task', {'task_id': 'TASK-01'})[0])
        self.assertTrue(validate_payload('key_event', {'key': 'F2'})[0])

        # Invalid cases
        self.assertFalse(validate_payload('unknown_action', {})[0])
        self.assertFalse(validate_payload('add_tag_to_task', {'tag_name': '', 'task_id': 'TASK-01'})[0])
        self.assertFalse(validate_payload('add_tags_to_task', {'tag_names': 'not-a-list', 'task_id': 'TASK-01'})[0])
        self.assertFalse(validate_payload('save_task', {'task': {'id': 'TASK-01', 'cycle_sec': 999}})[0])
        self.assertFalse(validate_payload('key_event', {'key': 'MALICIOUS_KEY'})[0])
        self.assertFalse(validate_payload('get_state', "not-a-dict")[0])

    def test_04_tags_serializable_not_observed_default(self):
        owner = MagicMock()
        owner.scanned_tags = [
            {'name': 'TAG_1', 'comment': 'C1', 'type': 'Float', 'group': 'High_VSD', 'addr': 'DB1,DBD0', 'raw_metadata': {'Col': 'Val'}},
            {'name': 'TAG_2', 'comment': 'C2', 'type': 'Binary Tag', 'group': 'High_Valve', 'addr': 'DB2,D0.0', 'raw_metadata': {}}
        ]
        owner.tasks = []
        owner.opcua_store = None

        view = F1ApiView.__new__(F1ApiView)
        view.owner = owner

        tags = view._get_serializable_tags()
        self.assertEqual(len(tags), 2)
        for t in tags:
            self.assertEqual(t['status'], 'NO', "Default status must be NOT_OBSERVED (NO)")
            self.assertEqual(t['quality'], 'NOT_OBSERVED')
            self.assertIsNone(t['observed_value'], "Must not invent observed values")
        self.assertEqual(tags[0]['raw_metadata'], {'Col': 'Val'})

    def test_05_add_tag_undo_roundtrip(self):
        owner = MagicMock()
        owner.tasks = [
            {'id': 'TASK-01', 'name': 'Task 1', 'cycle_sec': 5, 'action_log': True, 'action_notify': False, 'active': False, 'tags': []}
        ]
        owner.scanned_tags = []
        owner.save_tasks.return_value = True

        view = F1ApiView.__new__(F1ApiView)
        view.owner = owner
        view.closed = False
        view.web = None
        view._undo_stack = []
        view.recent_task_id = 'TASK-01'
        view.live_mode = False
        view.push_state_to_webview = MagicMock()

        # Add single tag
        view._dispatch_action('add_tag_to_task', {'tag_name': 'BVEC1PT.AUTO_C', 'task_id': 'TASK-01'})
        self.assertIn('BVEC1PT.AUTO_C', owner.tasks[0]['tags'])
        self.assertFalse(owner.tasks[0]['action_notify'], "Must not auto-enable action_notify")
        self.assertFalse(owner.tasks[0]['active'], "Must not auto-enable active")
        self.assertEqual(len(view._undo_stack), 1)

        # Undo addition
        view._dispatch_action('undo_last_action', {})
        self.assertNotIn('BVEC1PT.AUTO_C', owner.tasks[0]['tags'])
        self.assertEqual(len(view._undo_stack), 0)

    def test_06_bulk_add_and_remove_tags(self):
        owner = MagicMock()
        owner.tasks = [
            {'id': 'TASK-01', 'name': 'Task 1', 'cycle_sec': 5, 'action_log': True, 'action_notify': False, 'active': False, 'tags': []}
        ]
        owner.scanned_tags = []
        owner.save_tasks.return_value = True

        view = F1ApiView.__new__(F1ApiView)
        view.owner = owner
        view.closed = False
        view.web = None
        view._undo_stack = []
        view.recent_task_id = 'TASK-01'
        view.live_mode = False
        view.push_state_to_webview = MagicMock()

        # Bulk add
        view._dispatch_action('add_tags_to_task', {'tag_names': ['T1', 'T2', 'T3'], 'task_id': 'TASK-01'})
        self.assertEqual(owner.tasks[0]['tags'], ['T1', 'T2', 'T3'])

        # Remove subset
        view._dispatch_action('remove_tags_from_task', {'tag_names': ['T1', 'T3'], 'task_id': 'TASK-01'})
        self.assertEqual(owner.tasks[0]['tags'], ['T2'])

        # Undo remove
        view._dispatch_action('undo_last_action', {})
        self.assertIn('T1', owner.tasks[0]['tags'])
        self.assertIn('T3', owner.tasks[0]['tags'])

    def test_07_task_save_failure_atomic_rollback(self):
        owner = MagicMock()
        owner.tasks = [
            {'id': 'TASK-01', 'name': 'Original Name', 'cycle_sec': 5, 'action_log': True, 'action_notify': False, 'active': False, 'tags': []}
        ]
        owner.scanned_tags = []
        owner.save_tasks.return_value = False  # Simulate atomic save failure (e.g. disk error)

        view = F1ApiView.__new__(F1ApiView)
        view.owner = owner
        view.closed = False
        view.web = None
        view._undo_stack = []
        view.recent_task_id = 'TASK-01'
        view.live_mode = False
        view.push_state_to_webview = MagicMock()

        view._dispatch_action('save_task', {
            'task': {
                'id': 'TASK-01',
                'name': 'Modified Name That Fails',
                'cycle_sec': 10,
                'action_log': True,
                'action_notify': True,
                'active': True
            }
        })

        # When save fails, task in memory must roll back to original state
        self.assertEqual(owner.tasks[0]['name'], 'Original Name')
        self.assertEqual(owner.tasks[0]['cycle_sec'], 5)
        self.assertFalse(owner.tasks[0]['active'])


if __name__ == '__main__':
    unittest.main()
