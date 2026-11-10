"""Unit and contract tests for F1 Unified Tag Overview & Task Manager WebKit View."""
from datetime import datetime, timezone, timedelta
import json
from pathlib import Path
import re
import unittest
from unittest.mock import MagicMock, patch

from f1_api_view import F1ApiView, build_html, validate_payload, ALLOWLISTED_ACTIONS
from opcua_store import ObservableStateStore, Quality, TagObservation

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
            self.assertEqual(t['age_text'], 'ยังไม่ได้สังเกต')
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
        view.revision = 0
        view.push_state_to_webview = MagicMock()
        view._send_bridge_response = MagicMock()

        # Add single tag
        view._dispatch_action('add_tag_to_task', {'tag_name': 'BVEC1PT.AUTO_C', 'task_id': 'TASK-01'}, 'req_001')
        self.assertIn('BVEC1PT.AUTO_C', owner.tasks[0]['tags'])
        self.assertFalse(owner.tasks[0]['action_notify'], "Must not auto-enable action_notify")
        self.assertFalse(owner.tasks[0]['active'], "Must not auto-enable active")
        self.assertEqual(len(view._undo_stack), 1)
        self.assertEqual(view.revision, 1)

        # Undo addition
        view._dispatch_action('undo_last_action', {}, 'req_002')
        self.assertNotIn('BVEC1PT.AUTO_C', owner.tasks[0]['tags'])
        self.assertEqual(len(view._undo_stack), 0)
        self.assertEqual(view.revision, 2)

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
        view.revision = 0
        view.push_state_to_webview = MagicMock()
        view._send_bridge_response = MagicMock()

        # Bulk add
        view._dispatch_action('add_tags_to_task', {'tag_names': ['T1', 'T2', 'T3'], 'task_id': 'TASK-01'}, 'req_001')
        self.assertEqual(owner.tasks[0]['tags'], ['T1', 'T2', 'T3'])

        # Remove subset
        view._dispatch_action('remove_tags_from_task', {'tag_names': ['T1', 'T3'], 'task_id': 'TASK-01'}, 'req_002')
        self.assertEqual(owner.tasks[0]['tags'], ['T2'])

        # Undo remove
        view._dispatch_action('undo_last_action', {}, 'req_003')
        self.assertIn('T1', owner.tasks[0]['tags'])
        self.assertIn('T3', owner.tasks[0]['tags'])

    def test_07_task_save_failure_atomic_rollback(self):
        owner = MagicMock()
        owner.tasks = [
            {'id': 'TASK-01', 'name': 'Original Name', 'cycle_sec': 5, 'action_log': True, 'action_notify': False, 'active': False, 'tags': []}
        ]
        owner.scanned_tags = []
        owner.save_tasks.return_value = False  # Simulate atomic save failure (e.g. disk full)

        view = F1ApiView.__new__(F1ApiView)
        view.owner = owner
        view.closed = False
        view.web = None
        view._undo_stack = []
        view.recent_task_id = 'TASK-01'
        view.live_mode = False
        view.revision = 0
        view.push_state_to_webview = MagicMock()
        view._send_bridge_response = MagicMock()

        view._dispatch_action('save_task', {
            'task': {
                'id': 'TASK-01',
                'name': 'Modified Name That Fails',
                'cycle_sec': 10,
                'action_log': True,
                'action_notify': True,
                'active': True
            }
        }, 'req_save_fail')

        # When save fails, task in memory must roll back to original state
        self.assertEqual(owner.tasks[0]['name'], 'Original Name')
        self.assertEqual(owner.tasks[0]['cycle_sec'], 5)
        self.assertFalse(owner.tasks[0]['active'])
        self.assertEqual(view.revision, 0, "Revision must not increment on failure")
        self.assertEqual(len(view._undo_stack), 0, "Undo stack must not be updated on failure")

        # Bridge response must indicate failure
        view._send_bridge_response.assert_called_with(
            'req_save_fail',
            ok=False,
            error="บันทึกไม่สำเร็จ (save_task) · ระบบคืนค่าเดิมเรียบร้อยแล้ว",
            revision=0
        )

    def test_08_duplicate_add_rejection(self):
        owner = MagicMock()
        owner.tasks = [
            {'id': 'TASK-01', 'name': 'Task 1', 'cycle_sec': 5, 'action_log': True, 'action_notify': False, 'active': False, 'tags': ['EXISTING_TAG']}
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
        view.revision = 0
        view.push_state_to_webview = MagicMock()
        view._send_bridge_response = MagicMock()

        # Try to add duplicate tag
        view._dispatch_action('add_tag_to_task', {'tag_name': 'EXISTING_TAG', 'task_id': 'TASK-01'}, 'req_dup')
        # Mutation rejected because tag already exists
        self.assertEqual(len(owner.tasks[0]['tags']), 1)
        self.assertEqual(view.revision, 0)
        view._send_bridge_response.assert_called_with('req_dup', ok=False, error="Mutation rejected or not found", revision=0)

    def test_09_observable_state_store_integration_and_dynamic_age(self):
        owner = MagicMock()
        owner.scanned_tags = [
            {'name': 'TAG_GOOD', 'comment': 'C1', 'type': 'Float', 'group': 'High_VSD', 'addr': 'DB1,DBD0'},
            {'name': 'TAG_STALE', 'comment': 'C2', 'type': 'Float', 'group': 'High_VSD', 'addr': 'DB1,DBD4'},
            {'name': 'TAG_BAD', 'comment': 'C3', 'type': 'Float', 'group': 'High_VSD', 'addr': 'DB1,DBD8'},
            {'name': 'TAG_NOT_OBSERVED', 'comment': 'C4', 'type': 'Float', 'group': 'High_VSD', 'addr': 'DB1,DBD12'},
        ]
        owner.tasks = []

        now = datetime.now(timezone.utc)
        obs_good = MagicMock()
        obs_good.quality = 'GOOD'
        obs_good.value = 1450.5
        obs_good.source_time = now - timedelta(seconds=12)
        obs_good.is_stale.return_value = False

        obs_stale = MagicMock()
        obs_stale.quality = 'GOOD'
        obs_stale.value = 1200.0
        obs_stale.source_time = now - timedelta(seconds=180)
        obs_stale.is_stale.return_value = True

        obs_bad = MagicMock()
        obs_bad.quality = 'BAD'
        obs_bad.value = None
        obs_bad.source_time = now - timedelta(seconds=5)
        obs_bad.is_stale.return_value = False

        obs_store = MagicMock()
        obs_store.get_observation.side_effect = lambda name: {
            'TAG_GOOD': obs_good,
            'TAG_STALE': obs_stale,
            'TAG_BAD': obs_bad,
        }.get(name, None)
        owner.opcua_store = obs_store

        view = F1ApiView.__new__(F1ApiView)
        view.owner = owner

        tags = view._get_serializable_tags()
        self.assertEqual(len(tags), 4)

        tag_map = {t['name']: t for t in tags}
        # Good tag: status OK, age dynamic
        self.assertEqual(tag_map['TAG_GOOD']['status'], 'OK')
        self.assertEqual(tag_map['TAG_GOOD']['quality'], 'GOOD')
        self.assertEqual(tag_map['TAG_GOOD']['observed_value'], 1450.5)
        self.assertIn('วินาทีที่แล้ว', tag_map['TAG_GOOD']['age_text'])

        # Stale tag: status STALE
        self.assertEqual(tag_map['TAG_STALE']['status'], 'STALE')
        self.assertEqual(tag_map['TAG_STALE']['quality'], 'STALE')
        self.assertIn('นาทีที่แล้ว', tag_map['TAG_STALE']['age_text'])

        # Bad tag: status FAIL
        self.assertEqual(tag_map['TAG_BAD']['status'], 'FAIL')
        self.assertEqual(tag_map['TAG_BAD']['quality'], 'BAD')
        self.assertEqual(tag_map['TAG_BAD']['age_text'], 'สัญญาณขัดข้อง')

        # Not observed tag: status NO
        self.assertEqual(tag_map['TAG_NOT_OBSERVED']['status'], 'NO')
        self.assertEqual(tag_map['TAG_NOT_OBSERVED']['quality'], 'NOT_OBSERVED')
        self.assertEqual(tag_map['TAG_NOT_OBSERVED']['age_text'], 'ยังไม่ได้สังเกต')

    def test_untrusted_receipts_do_not_look_current(self):
        owner = MagicMock()
        endpoint = 'opc.tcp://127.0.0.1:4850'
        owner.opcua_config = {'endpoint_url': endpoint}
        owner.scanned_tags = [{'name': name} for name in ('Uncertain', 'Future', 'PriorBinding')]
        owner.tasks = []
        owner.opcua_store = ObservableStateStore()
        now = datetime.now(timezone.utc)
        for name, quality, ts, binding in (
            ('Uncertain', Quality.UNCERTAIN, now, endpoint),
            ('Future', Quality.GOOD, now + timedelta(seconds=90), endpoint),
            ('PriorBinding', Quality.GOOD, now, endpoint + '/other'),
        ):
            owner.opcua_store.update_observation(TagObservation(
                name, value=17, quality=quality, arrival_time=ts, endpoint_url=binding))
        view = F1ApiView.__new__(F1ApiView)
        view.owner = owner
        tags = {tag['name']: tag for tag in view._get_serializable_tags()}
        self.assertEqual((tags['Uncertain']['status'], tags['Uncertain']['quality']), ('FAIL', 'UNCERTAIN'))
        self.assertEqual(tags['Future']['status'], 'STALE')
        self.assertEqual(tags['PriorBinding']['status'], 'NO')
        self.assertTrue(all(tag['observed_value'] is None for tag in tags.values()))

    def test_observation_tick_sends_only_changed_receipts(self):
        view = F1ApiView.__new__(F1ApiView)
        view.owner = MagicMock(scanned_tags=[{'name': 'Tag1'}, {'name': 'Tag2'}], opcua_config={})
        view.owner.opcua_store = ObservableStateStore()
        view.web = MagicMock()
        view.web.get_mapped.return_value = True
        view._sent_observations = {}
        view.refresh_observations()
        view.web.evaluate_javascript.reset_mock()

        now = datetime.now(timezone.utc)
        view.owner.opcua_store.update_observation(TagObservation(
            'Tag1', value=0, quality=Quality.GOOD, arrival_time=now))
        original_fields = view._observation_fields
        with patch.object(view, '_observation_fields', side_effect=lambda name, _now: original_fields(name, now)):
            view.refresh_observations()
            view.web.evaluate_javascript.assert_called_once()
            script = view.web.evaluate_javascript.call_args.args[0]
            self.assertTrue(script.startswith('window.F1?.onObservationsUpdated('))
            payload = json.loads(script.removeprefix('window.F1?.onObservationsUpdated(').removesuffix(')'))
            self.assertEqual([(item['name'], item['observed_value']) for item in payload], [('Tag1', 0)])
            view.web.evaluate_javascript.reset_mock()
            view.refresh_observations()
        view.web.evaluate_javascript.assert_not_called()

    def test_10_multiple_task_association(self):
        owner = MagicMock()
        owner.scanned_tags = [
            {'name': 'VALVE_01', 'comment': 'Main Valve', 'type': 'Binary Tag', 'group': 'High_Valve', 'addr': 'DB1,D0.0'}
        ]
        # Same tag belongs to both TASK-01 and TASK-02
        owner.tasks = [
            {'id': 'TASK-01', 'name': 'Scan Task 1', 'tags': ['VALVE_01']},
            {'id': 'TASK-02', 'name': 'Alarm Task 2', 'tags': ['VALVE_01', 'OTHER_TAG']}
        ]
        owner.opcua_store = None

        view = F1ApiView.__new__(F1ApiView)
        view.owner = owner

        tags = view._get_serializable_tags()
        self.assertEqual(len(tags), 1)
        self.assertEqual(tags[0]['tasks'], ['TASK-01', 'TASK-02'], "Must report all bound task IDs")

    def test_11_next_task_id_no_collision(self):
        owner = MagicMock()
        owner.tasks = [
            {'id': 'TASK-01'},
            {'id': 'TASK-02'},
            {'id': 'TASK-04'},  # TASK-03 is free
        ]

        view = F1ApiView.__new__(F1ApiView)
        view.owner = owner

        # Next id should be TASK-03 (filling lowest available slot)
        self.assertEqual(view._next_task_id(), 'TASK-03')

    def test_12_f2_single_dialog_delegation(self):
        from workspace import AquaUnifiedWorkspaceView
        owner = MagicMock()
        root = MagicMock()

        ws = AquaUnifiedWorkspaceView.__new__(AquaUnifiedWorkspaceView)
        ws.owner = owner
        ws.task_dialog = None
        ws.f1_api = MagicMock()
        ws.f1_api.closed = False

        # When f1_api is present, open_task_dialog must delegate to f1_api and NOT instantiate GTK dialog
        ws.open_task_dialog()
        ws.f1_api.open_task_dialog.assert_called_once()
        self.assertIsNone(ws.task_dialog, "GTK task_dialog must NOT be instantiated when f1_api is active")

    def test_13_settings_shortcuts_and_group_styling(self):
        index_html = (ASSETS_DIR / 'index.html').read_text(encoding='utf-8')
        view_css = (ASSETS_DIR / 'view.css').read_text(encoding='utf-8')
        view_js = (ASSETS_DIR / 'view.js').read_text(encoding='utf-8')

        self.assertNotIn('btnOpenSettings', index_html)
        self.assertIn('.group-btn', view_css)
        self.assertIn('.group-item', view_css)
        self.assertIn("e.key === 'F6'", view_js)
        self.assertIn("e.ctrlKey && (e.key === ',' || e.code === 'Comma')", view_js)
        self.assertIn('navigate_f6', view_js)

    def test_14_navigate_f6_dispatches_to_alarms(self):
        owner = MagicMock()
        view = F1ApiView.__new__(F1ApiView)
        view.owner = owner
        view.revision = 1
        view.closed = False
        view._send_bridge_response = MagicMock()

        view._dispatch_action('navigate_f6', {}, 'req-f6')
        owner.switch_to_tab.assert_called_once_with('alarms')
        view._send_bridge_response.assert_called_once_with('req-f6', ok=True, revision=1)

    def test_15_task_dialog_assigned_row_selection_and_sync(self):
        view_css = (ASSETS_DIR / 'view.css').read_text(encoding='utf-8')
        view_js = (ASSETS_DIR / 'view.js').read_text(encoding='utf-8')

        # CSS rules for assigned tag row selection and custom check
        self.assertIn('.assigned-tags-table', view_css)
        self.assertIn('.assigned-tag-row', view_css)
        self.assertIn('.assigned-tag-row.is-selected', view_css)
        self.assertIn('.table-check', view_css)

        # JS functions for row clicking, sync, and range selection
        self.assertIn('syncAssignedSelectionUI', view_js)
        self.assertIn('toggleAssignedRow', view_js)
        self.assertIn('assigned-tag-row', view_js)


if __name__ == '__main__':
    unittest.main()
