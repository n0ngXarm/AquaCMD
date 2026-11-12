"""F1 Unified Tag Overview & Task Manager WebKit Presentation.
Interfaces between the GTK host and the WebKit-rendered F1 workspace.
Enforces explicit action allowlist, Python payload validation, transactional task persistence,
and genuine observation state from ObservableStateStore.
"""

from copy import deepcopy
from datetime import datetime, timezone
from html import escape
import json
import math
import logging
from pathlib import Path
import re
import sqlite3
import sys
from urllib.parse import urlsplit

import gi
gi.require_version('Gtk', '4.0')
gi.require_version('Gdk', '4.0')
gi.require_version('WebKit', '6.0')
from gi.repository import Gdk, Gio, GLib, Gtk, WebKit

try:
    from .opcua_store import Quality
except (ImportError, ValueError):
    try:
        from opcua_store import Quality
    except ImportError:
        class Quality:
            GOOD = "GOOD"
            BAD = "BAD"
            UNCERTAIN = "UNCERTAIN"
            STALE = "STALE"
            NOT_OBSERVED = "NOT_OBSERVED"
            DISCONNECTED = "DISCONNECTED"

ROOT = Path(__file__).resolve().parents[1]
ASSETS = Path(__file__).with_name('f1_api')
UNOBSERVED = dict(status='NO', observed_value=None, quality='NOT_OBSERVED',
                  age_text='ยังไม่ได้สังเกต', observation_source='', observation_at='')
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
from collector import telemetry

logger = logging.getLogger('AquaF1ApiView')

ALLOWLISTED_ACTIONS = {
    'get_state',
    'add_tag_to_task',
    'add_tags_to_task',
    'remove_tag_from_task',
    'remove_tags_from_task',
    'save_task',
    'create_task',
    'delete_task',
    'undo_last_action',
    'navigate_f6',
    'key_event',
}


def validate_payload(action, payload):
    """Strictly validates bridge payloads against schema allowlist."""
    if not isinstance(payload, dict):
        return False, "Payload must be a dictionary"

    if action in ('get_state', 'undo_last_action', 'navigate_f6'):
        return True, None

    if action == 'add_tag_to_task':
        tag_name = payload.get('tag_name')
        task_id = payload.get('task_id')
        if not isinstance(tag_name, str) or not tag_name.strip():
            return False, "Invalid tag_name"
        if not isinstance(task_id, str) or not task_id.strip():
            return False, "Invalid task_id"
        return True, None

    if action == 'add_tags_to_task':
        tag_names = payload.get('tag_names')
        task_id = payload.get('task_id')
        if not isinstance(tag_names, list) or not all(isinstance(x, str) and x.strip() for x in tag_names):
            return False, "Invalid tag_names list"
        if not isinstance(task_id, str) or not task_id.strip():
            return False, "Invalid task_id"
        return True, None

    if action == 'remove_tag_from_task':
        tag_name = payload.get('tag_name')
        task_id = payload.get('task_id')
        if not isinstance(tag_name, str) or not isinstance(task_id, str):
            return False, "Invalid tag_name or task_id"
        return True, None

    if action == 'remove_tags_from_task':
        tag_names = payload.get('tag_names')
        task_id = payload.get('task_id')
        if not isinstance(tag_names, list) or not all(isinstance(x, str) for x in tag_names):
            return False, "Invalid tag_names"
        if not isinstance(task_id, str):
            return False, "Invalid task_id"
        return True, None

    if action == 'save_task':
        task = payload.get('task')
        if not isinstance(task, dict):
            return False, "Invalid task object"
        if not isinstance(task.get('id'), str) or not task.get('id'):
            return False, "Invalid task id"
        if not isinstance(task.get('name'), str):
            return False, "Invalid task name"
        if task.get('cycle_sec') not in (1, 5, 10, 30, 60):
            return False, "Invalid cycle_sec"
        if not isinstance(task.get('action_log'), bool) or not isinstance(task.get('action_notify'), bool) or not isinstance(task.get('active'), bool):
            return False, "Invalid boolean flags"
        return True, None

    if action == 'create_task':
        task = payload.get('task')
        if not isinstance(task, dict):
            return False, "Invalid task object"
        if not isinstance(task.get('id'), str) or not task.get('id'):
            return False, "Invalid task id"
        if not isinstance(task.get('name'), str):
            return False, "Invalid task name"
        if task.get('cycle_sec') not in (1, 5, 10, 30, 60):
            return False, "Invalid cycle_sec"
        return True, None

    if action == 'delete_task':
        if not isinstance(payload.get('task_id'), str) or not payload.get('task_id'):
            return False, "Invalid task_id"
        return True, None

    if action == 'key_event':
        if payload.get('key') not in ('F1', 'F2', 'F3', 'F4', 'F5', 'F6', 'F7', 'F8', 'F9'):
            return False, "Invalid function key"
        return True, None

    return False, "Action not allowed"


def build_html():
    """Assembles offline air-gapped HTML page with embedded fonts and theme."""
    page = (ASSETS / 'index.html').read_text(encoding='utf-8')
    fonts = (ASSETS / 'fonts_embedded.css').read_text(encoding='utf-8') if (ASSETS / 'fonts_embedded.css').exists() else ''
    theme = (ASSETS / 'formal-theme.css').read_text(encoding='utf-8') if (ASSETS / 'formal-theme.css').exists() else ''
    view_css = (ASSETS / 'view.css').read_text(encoding='utf-8') if (ASSETS / 'view.css').exists() else ''

    css_combined = fonts + '\n' + theme + '\n' + view_css
    page = page.replace('/*F1_CSS*/', css_combined)

    js_code = (ASSETS / 'view.js').read_text(encoding='utf-8') if (ASSETS / 'view.js').exists() else ''
    page = page.replace('/*F1_JS*/', js_code)
    return page


class F1ApiView:
    """GTK WebKit Controller for F1 Unified Tag Overview & Task Manager."""

    revision = 0
    recent_task_id = 'TASK-01'
    live_mode = False
    closed = False

    def __init__(self, owner):
        self.owner = owner
        self.closed = False
        self._undo_stack = []
        self.recent_task_id = 'TASK-01'
        self.live_mode = False
        self.revision = 0
        self._sent_observations = {}

        # WebKit Setup
        session = WebKit.NetworkSession.new_ephemeral()
        session.set_proxy_settings(WebKit.NetworkProxyMode.NO_PROXY, None)

        manager = WebKit.UserContentManager()
        manager.register_script_message_handler('f1Bridge', None)
        manager.connect('script-message-received::f1Bridge', self._on_bridge_message)
        manager.register_script_message_handler('f1Presentation', None)
        manager.connect('script-message-received::f1Presentation', self._on_presentation_message)

        self.web = WebKit.WebView(network_session=session, user_content_manager=manager)
        self.web.set_hexpand(True)
        self.web.set_vexpand(True)

        settings = self.web.get_settings()
        for name in ('enable-webgl', 'enable-html5-database', 'enable-html5-local-storage',
                     'enable-media-stream', 'enable-developer-extras', 'enable-dns-prefetching'):
            try:
                setattr(settings, 'props.' + name.replace('-', '_'), False)
            except (AttributeError, TypeError):
                pass
        settings.props.default_font_size = 14
        settings.props.default_font_family = 'IBM Plex Sans Thai'
        settings.props.monospace_font_family = 'IBM Plex Mono'

        # Security sandbox: strictly block arbitrary network navigation
        self.web.connect('decide-policy', self._on_decide_policy)

        self.root_widget = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        self.root_widget.append(self.web)

        # Load assembled HTML
        html_markup = build_html()
        self.web.load_html(html_markup, 'http://127.0.0.1/f1/')

    def _on_presentation_message(self, _manager, value):
        """Synchronize the native F2 highlight with its existing WebKit dialog."""
        if self.closed:
            return
        try:
            message = json.loads(value.to_string())
        except (ValueError, TypeError, AttributeError):
            return
        if not isinstance(message, dict) or set(message) != {'taskDialogOpen'} or type(message['taskDialogOpen']) is not bool:
            return
        update = getattr(self.owner, 'set_task_dialog_active', None)
        if callable(update):
            update(message['taskDialogOpen'])

    def _on_decide_policy(self, webview, decision, decision_type):
        if decision_type == WebKit.PolicyDecisionType.NAVIGATION_ACTION:
            action = decision.get_navigation_action()
            uri = action.get_request().get_uri()
            parts = urlsplit(uri)
            if parts.scheme in ('http', 'https') and parts.netloc in ('127.0.0.1', 'localhost'):
                decision.use()
                return True
            decision.ignore()
            return True
        return False

    def _next_task_id(self):
        """Finds next truly unused TASK-XX identifier."""
        tasks = getattr(self.owner, 'tasks', []) or []
        existing_ids = {str(t.get('id', '')) for t in tasks}
        num = 1
        while f"TASK-{num:02d}" in existing_ids:
            num += 1
        return f"TASK-{num:02d}"

    def _telemetry_snapshot(self):
        directory = getattr(self.owner, 'config_dir', None)
        if not isinstance(directory, (str, Path)):
            return None
        directory = Path(directory)
        try:
            source = telemetry.load_config(directory / telemetry.CONFIG_NAME)
        except FileNotFoundError:
            return None
        except (OSError, ValueError, TypeError, RecursionError):
            return 'แหล่งสำรอง · ตั้งค่าไม่ถูกต้อง', None
        method = 'OPC DA' if source['transport'] == 'opcda' else source['transport'].upper()
        label = f'{method} · {source["source_id"]}'
        if source['lab']:
            label += ' · SIMULATED'
        try:
            snapshot = telemetry.read_snapshot(directory / telemetry.DB_NAME, source)
            if snapshot:
                snapshot = telemetry.decode_snapshot(
                    json.dumps({key: snapshot[key] for key in ('observed_at', 'values')},
                               ensure_ascii=False, separators=(',', ':')).encode(),
                    source['tags'], datetime.now(timezone.utc), per_tag_time=source['transport'] == 'opcda')
        except (OSError, ValueError, TypeError, KeyError, sqlite3.Error, RecursionError):
            snapshot = None
        return label, snapshot

    def _alternative_fields(self, name, now, alternative):
        label, snapshot = alternative
        unknown = dict(UNOBSERVED, observation_source=label)
        reading = snapshot['values'].get(name) if snapshot else None
        if reading is None:
            return unknown
        stamp = reading.get('observed_at', snapshot['observed_at'])
        return self._format_observation(unknown, reading['quality'], reading['value'],
                                        datetime.fromisoformat(stamp) if stamp else None, now)

    def _observation_fields(self, name, now):
        unknown = dict(UNOBSERVED)
        store = getattr(self.owner, 'opcua_store', None)
        observation = store.get_observation(name) if store else None
        if observation is None:
            return unknown
        config = getattr(self.owner, 'opcua_config', None)
        binding = getattr(observation, 'endpoint_url', None)
        if (isinstance(config, dict) and 'endpoint_url' in config and
                isinstance(binding, str) and binding and binding != config['endpoint_url']):
            return unknown
        unknown['observation_source'] = 'OPC UA' if observation.quality != Quality.NOT_OBSERVED else ''
        ref = observation.source_time or observation.arrival_time
        return self._format_observation(unknown, observation.quality, observation.value, ref, now)

    @staticmethod
    def _format_observation(unknown, quality, value, ref, now):
        result = dict(unknown)
        if isinstance(ref, datetime):
            if ref.tzinfo is None:
                ref = ref.replace(tzinfo=timezone.utc)
            result['observation_at'] = ref.isoformat()
        if quality in (Quality.BAD, Quality.DISCONNECTED, Quality.UNCERTAIN):
            return dict(result, status='FAIL', observed_value=None, quality=quality,
                        age_text='คุณภาพไม่แน่นอน' if quality == Quality.UNCERTAIN else 'สัญญาณขัดข้อง')
        if quality not in (Quality.GOOD, Quality.STALE) or not isinstance(ref, datetime):
            return unknown
        seconds = (now - ref).total_seconds()
        if seconds < 0:
            return dict(result, status='STALE', observed_value=None, quality='STALE',
                        age_text='เวลาหลักฐานอยู่ในอนาคต')
        if not isinstance(value, (str, int, float)) or (isinstance(value, float) and not math.isfinite(value)):
            value = None
        if seconds < 60:
            age_text = f'{int(seconds)} วินาทีที่แล้ว'
        elif seconds < 3600:
            age_text = f'{int(seconds // 60)} นาทีที่แล้ว'
        else:
            age_text = f'{int(seconds // 3600)} ชม. ที่แล้ว'
        stale = seconds > 60 or quality == Quality.STALE
        return dict(result, status='STALE' if stale else 'OK', observed_value=value,
                    quality='STALE' if stale else 'GOOD', age_text=age_text)

    def _get_serializable_tags(self):
        """Converts owner scanned_tags to clean serializable list with authentic observations.
        Uses public ObservableStateStore API. Quality, freshness, and age are strictly evaluated.
        """
        scanned = getattr(self.owner, 'scanned_tags', []) or []
        tasks = getattr(self.owner, 'tasks', []) or []
        now_utc = datetime.now(timezone.utc)
        alternative = self._telemetry_snapshot()

        res = []
        for t in scanned:
            name = t.get('name', '')
            tag_tasks = [t['id'] for t in tasks if name in t.get('tags', [])]
            fields = (self._observation_fields(name, now_utc) if alternative is None
                      else self._alternative_fields(name, now_utc, alternative))

            res.append({
                'name': name,
                'comment': t.get('comment', ''),
                'type': t.get('type', ''),
                'length': t.get('length', ''),
                'fmt': t.get('fmt', ''),
                'conn': t.get('conn', ''),
                'group': t.get('group', 'Default'),
                'addr': t.get('addr', 'Internal'),
                **fields,
                'tasks': tag_tasks,
                'raw_metadata': t.get('raw_metadata', {})
            })
        return res

    def _get_serializable_tasks(self):
        tasks = getattr(self.owner, 'tasks', []) or []
        res = []
        for t in tasks:
            res.append({
                'id': t.get('id', ''),
                'name': t.get('name', ''),
                'cycle_sec': t.get('cycle_sec', 5),
                'action_log': bool(t.get('action_log', False)),
                'action_notify': bool(t.get('action_notify', False)),
                'active': bool(t.get('active', False)),
                'tags': list(t.get('tags', [])),
                'scan_count': t.get('scan_count', 0),
                'log_count': t.get('log_count', 0),
                'alert_count': t.get('alert_count', 0)
            })
        return res

    def _get_serializable_state(self):
        return {
            'tags': self._get_serializable_tags(),
            'tasks': self._get_serializable_tasks(),
            'recentTaskId': self.recent_task_id,
            'liveMode': self.live_mode,
            'revision': self.revision
        }

    def push_state_to_webview(self):
        if self.closed or not getattr(self, 'web', None):
            return
        state_payload = self._get_serializable_state()
        json_str = json.dumps(state_payload, ensure_ascii=False)
        self.web.evaluate_javascript(f'window.F1?.onStateUpdated({json_str})', -1, None, None, None, None, None)

    def refresh_observations(self):
        """Refresh receipt fields without rebuilding the catalog or a Task draft."""
        if self.closed or not self.web.get_mapped():
            return
        now = datetime.now(timezone.utc)
        alternative = self._telemetry_snapshot()
        current = {}
        updates = []
        for tag in getattr(self.owner, 'scanned_tags', ()) or ():
            name = tag.get('name', '')
            fields = (self._observation_fields(name, now) if alternative is None
                      else self._alternative_fields(name, now, alternative))
            current[name] = fields
            previous = self._sent_observations.get(name)
            if fields != previous and (previous is not None or fields['status'] != 'NO' or alternative is not None):
                updates.append({'name': name, **fields})
        self._sent_observations = current
        if updates:
            payload = json.dumps(updates, ensure_ascii=False)
            self.web.evaluate_javascript(f'window.F1?.onObservationsUpdated({payload})', -1, None, None, None, None, None)

    def _send_bridge_response(self, request_id, ok, error=None, revision=0, state=None):
        """Explicit bridge response contract for transactional operations."""
        if self.closed or not getattr(self, 'web', None):
            return
        resp = {
            'request_id': request_id,
            'ok': bool(ok),
            'error': str(error) if error else None,
            'revision': revision,
            'state': state
        }
        json_str = json.dumps(resp, ensure_ascii=False)
        self.web.evaluate_javascript(f'window.F1?.onBridgeResponse({json_str})', -1, None, None, None, None, None)

    def _apply_mutation(self, action_name, mutation_fn, request_id=None, undo_action=None):
        """Transactional mutation helper.
        Backs up owner.tasks, applies mutation, saves atomically, and rolls back on any failure.
        Updates undo stack and sends success response ONLY after disk persistence succeeds.
        """
        orig_tasks = getattr(self.owner, 'tasks', [])
        backup_tasks = deepcopy(orig_tasks)

        try:
            mutation_result = mutation_fn()
            if mutation_result is False:
                self.owner.tasks = backup_tasks
                self._send_bridge_response(request_id, ok=False, error="Mutation rejected or not found", revision=self.revision)
                return False

            saved = self.owner.save_tasks() if hasattr(self.owner, 'save_tasks') else False
            if not saved:
                # Rollback on disk / persistence failure
                self.owner.tasks = backup_tasks
                logger.error(f"Transactional save failed for {action_name}; state rolled back.")
                self._send_bridge_response(
                    request_id,
                    ok=False,
                    error=f"บันทึกไม่สำเร็จ ({action_name}) · ระบบคืนค่าเดิมเรียบร้อยแล้ว",
                    revision=self.revision
                )
                return False

            # Success path
            self.revision += 1
            if undo_action is not None:
                self._undo_stack.append(undo_action)

            current_state = self._get_serializable_state()
            self._send_bridge_response(request_id, ok=True, revision=self.revision, state=current_state)
            self.push_state_to_webview()
            return True

        except Exception as e:
            self.owner.tasks = backup_tasks
            logger.exception(f"Unexpected error in {action_name}: {e}")
            self._send_bridge_response(request_id, ok=False, error=str(e), revision=self.revision)
            return False

    def _on_bridge_message(self, manager, value):
        if self.closed:
            return
        try:
            if hasattr(value, 'to_json'):
                raw_str = value.to_json(0)
            elif hasattr(value, 'to_string'):
                raw_str = value.to_string()
            else:
                raw_str = str(value)

            message = json.loads(raw_str)
            if isinstance(message, str):
                message = json.loads(message)
        except Exception as e:
            logger.warning(f"Error parsing bridge message: {e}")
            return

        if not isinstance(message, dict):
            logger.warning("Bridge message must be a JSON object")
            return

        action = message.get('action')
        payload = message.get('payload', {})
        request_id = message.get('request_id') or payload.get('request_id')

        if action not in ALLOWLISTED_ACTIONS:
            logger.warning(f"Rejected unallowlisted action: {action}")
            self._send_bridge_response(request_id, ok=False, error=f"Action not allowlisted: {action}", revision=self.revision)
            return

        valid, err = validate_payload(action, payload)
        if not valid:
            logger.warning(f"Payload validation failed for {action}: {err}")
            self._send_bridge_response(request_id, ok=False, error=err, revision=self.revision)
            return

        self._dispatch_action(action, payload, request_id)

    def _dispatch_action(self, action, payload, request_id=None):
        if action == 'get_state':
            self._send_bridge_response(request_id, ok=True, revision=self.revision, state=self._get_serializable_state())
            self.push_state_to_webview()

        elif action == 'add_tag_to_task':
            tag_name = payload['tag_name']
            task_id = payload['task_id']
            self.recent_task_id = task_id

            def mut():
                task = next((t for t in self.owner.tasks if t.get('id') == task_id), None)
                if task is None:
                    return False
                if 'tags' not in task:
                    task['tags'] = []
                if tag_name not in task['tags']:
                    task['tags'].append(tag_name)
                    return True
                return False  # Duplicate action: tag already in task

            undo = {'action': 'add', 'task_id': task_id, 'tags': [tag_name]}
            self._apply_mutation('add_tag_to_task', mut, request_id, undo)

        elif action == 'add_tags_to_task':
            tag_names = payload['tag_names']
            task_id = payload['task_id']
            self.recent_task_id = task_id
            added = []

            def mut():
                task = next((t for t in self.owner.tasks if t.get('id') == task_id), None)
                if task is None:
                    return False
                if 'tags' not in task:
                    task['tags'] = []
                for tn in tag_names:
                    if tn not in task['tags']:
                        task['tags'].append(tn)
                        added.append(tn)
                return bool(added)

            undo = {'action': 'add', 'task_id': task_id, 'tags': added}
            self._apply_mutation('add_tags_to_task', mut, request_id, undo)

        elif action == 'remove_tag_from_task':
            tag_name = payload['tag_name']
            task_id = payload['task_id']

            def mut():
                task = next((t for t in self.owner.tasks if t.get('id') == task_id), None)
                if task is not None and 'tags' in task and tag_name in task['tags']:
                    task['tags'].remove(tag_name)
                    return True
                return False

            undo = {'action': 'remove', 'task_id': task_id, 'tags': [tag_name]}
            self._apply_mutation('remove_tag_from_task', mut, request_id, undo)

        elif action == 'remove_tags_from_task':
            tag_names = payload['tag_names']
            task_id = payload['task_id']
            removed = []

            def mut():
                task = next((t for t in self.owner.tasks if t.get('id') == task_id), None)
                if task is not None and 'tags' in task:
                    for tn in tag_names:
                        if tn in task['tags']:
                            task['tags'].remove(tn)
                            removed.append(tn)
                    return bool(removed)
                return False

            undo = {'action': 'remove', 'task_id': task_id, 'tags': removed}
            self._apply_mutation('remove_tags_from_task', mut, request_id, undo)

        elif action == 'undo_last_action':
            if not self._undo_stack:
                self._send_bridge_response(request_id, ok=False, error="ไม่มีการกระทำที่สามารถยกเลิกได้", revision=self.revision)
                return

            last_item = self._undo_stack[-1]

            def mut():
                item = self._undo_stack.pop()
                task = next((t for t in self.owner.tasks if t.get('id') == item['task_id']), None)
                if task is None:
                    return False
                if item['action'] == 'add':
                    for tn in item['tags']:
                        if tn in task.get('tags', []):
                            task['tags'].remove(tn)
                elif item['action'] == 'remove':
                    if 'tags' not in task:
                        task['tags'] = []
                    for tn in item['tags']:
                        if tn not in task['tags']:
                            task['tags'].append(tn)
                return True

            self._apply_mutation('undo_last_action', mut, request_id, None)

        elif action == 'save_task':
            updated_info = payload['task']

            def mut():
                task = next((t for t in self.owner.tasks if t.get('id') == updated_info['id']), None)
                if task is None:
                    return False
                task['name'] = updated_info['name']
                task['cycle_sec'] = updated_info['cycle_sec']
                task['action_log'] = bool(updated_info['action_log'])
                task['action_notify'] = bool(updated_info['action_notify'])
                task['active'] = bool(updated_info['active'])
                if 'tags' in updated_info and isinstance(updated_info['tags'], list):
                    task['tags'] = list(updated_info['tags'])
                return True

            self._apply_mutation('save_task', mut, request_id, None)

        elif action == 'create_task':
            new_task_data = payload['task']
            new_id = new_task_data.get('id')
            existing_ids = {t.get('id') for t in self.owner.tasks}
            if not new_id or new_id in existing_ids:
                new_id = self._next_task_id()

            new_task = {
                'id': new_id,
                'name': new_task_data.get('name') or f"Task ใหม่ {new_id}",
                'cycle_sec': new_task_data.get('cycle_sec', 5),
                'action_log': bool(new_task_data.get('action_log', True)),
                'action_notify': bool(new_task_data.get('action_notify', False)),
                'active': bool(new_task_data.get('active', False)),
                'tags': list(new_task_data.get('tags', [])),
                'scan_count': 0,
                'log_count': 0,
                'alert_count': 0
            }

            def mut():
                self.owner.tasks.append(new_task)
                self.recent_task_id = new_id
                return True

            self._apply_mutation('create_task', mut, request_id, None)

        elif action == 'delete_task':
            task_id = payload['task_id']

            def mut():
                orig_len = len(self.owner.tasks)
                self.owner.tasks = [t for t in self.owner.tasks if t.get('id') != task_id]
                return len(self.owner.tasks) < orig_len

            self._apply_mutation('delete_task', mut, request_id, None)

        elif action == 'navigate_f6':
            if hasattr(self.owner, 'switch_to_tab'):
                self.owner.switch_to_tab('alarms')
            elif getattr(self.owner, 'nav_btns', {}).get('alarms'):
                self.owner.nav_btns['alarms'].set_active(True)
            self._send_bridge_response(request_id, ok=True, revision=self.revision)

        elif action == 'key_event':
            key_name = payload.get('key')
            if hasattr(self.owner, 'on_global_key_pressed') and key_name:
                keyval = getattr(Gdk, f'KEY_{key_name}', None)
                if keyval:
                    self.owner.on_global_key_pressed(None, keyval, 0, 0)
            self._send_bridge_response(request_id, ok=True, revision=self.revision)

    # Public Methods Expected by app.py
    def open_task_dialog(self, task_id=None):
        t_id = task_id or self.recent_task_id
        safe_id = json.dumps(t_id, ensure_ascii=False)
        self.web.evaluate_javascript(f'window.F1?.openTaskDialog({safe_id})', -1, None, None, None, None, None)

    def set_workspace_mode(self, mode):
        safe_mode = json.dumps(mode, ensure_ascii=False)
        self.web.evaluate_javascript(f'window.F1?.setMode({safe_mode})', -1, None, None, None, None, None)

    def sync_catalog_data(self):
        self.push_state_to_webview()

    def refresh_group_explorer(self):
        self.push_state_to_webview()

    def render_catalog_table(self):
        self.push_state_to_webview()

    def switch_to_task(self, idx):
        if 0 <= idx < len(getattr(self.owner, 'tasks', [])):
            task = self.owner.tasks[idx]
            self.recent_task_id = task.get('id', 'TASK-01')
            self.open_task_dialog(self.recent_task_id)

    def on_create_new_task(self):
        new_id = self._next_task_id()
        new_task = {
            'id': new_id,
            'name': f"Task เฝ้าระวังใหม่ {new_id}",
            'cycle_sec': 5,
            'action_log': True,
            'action_notify': False,
            'active': False,
            'tags': [],
            'scan_count': 0,
            'log_count': 0,
            'alert_count': 0
        }
        def mut():
            self.owner.tasks.append(new_task)
            self.recent_task_id = new_id
            return True

        self._apply_mutation('create_task', mut, None, None)
        self.open_task_dialog(new_id)

    def close(self):
        if self.closed:
            return
        self.closed = True
        if getattr(self, 'web', None):
            try:
                self.web.stop_loading()
                self.web.terminate_web_process()
            except Exception:
                pass
