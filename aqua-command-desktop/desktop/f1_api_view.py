"""F1 Unified Tag Overview & Task Manager WebKit Presentation.
Interfaces between the GTK host and the WebKit-rendered F1 workspace.
Enforces explicit action allowlist, Python payload validation, and atomic task persistence.
"""

from html import escape
import json
import logging
import sys
import threading
from pathlib import Path
from urllib.parse import urlsplit

import gi
gi.require_version('Gtk', '4.0')
gi.require_version('Gdk', '4.0')
gi.require_version('WebKit', '6.0')
from gi.repository import Gdk, Gio, GLib, Gtk, WebKit

ROOT = Path(__file__).resolve().parents[1]
ASSETS = Path(__file__).with_name('f1_api')

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
        if not isinstance(payload.get('task_id'), str):
            return False, "Invalid task_id"
        return True, None

    if action == 'key_event':
        if payload.get('key') not in ('F1', 'F2', 'F3', 'F4', 'F5', 'F6', 'F7', 'F8'):
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

    def __init__(self, owner):
        self.owner = owner
        self.closed = False
        self._undo_stack = []
        self.recent_task_id = 'TASK-01'
        self.live_mode = False

        # WebKit Setup
        session = WebKit.NetworkSession.new_ephemeral()
        session.set_proxy_settings(WebKit.NetworkProxyMode.NO_PROXY, None)

        manager = WebKit.UserContentManager()
        manager.register_script_message_handler('f1Bridge', None)
        manager.connect('script-message-received::f1Bridge', self._on_bridge_message)

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

        self.root_widget = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        self.root_widget.append(self.web)

        # Load assembled HTML
        html_markup = build_html()
        self.web.load_html(html_markup, 'http://127.0.0.1/f1/')

    def _get_serializable_tags(self):
        """Converts owner scanned_tags to clean serializable list with Not Observed status."""
        scanned = getattr(self.owner, 'scanned_tags', []) or []
        obs_store = getattr(self.owner, 'opcua_store', None)

        res = []
        for t in scanned:
            name = t.get('name', '')
            status = 'NO'
            observed_val = None
            quality = 'NOT_OBSERVED'

            # If live session is active in owner's store
            if obs_store and hasattr(obs_store, 'get_latest_observation'):
                obs = obs_store.get_latest_observation(name)
                if obs:
                    status = 'OK' if obs.quality == 'GOOD' else ('STALE' if obs.quality == 'STALE' else 'FAIL')
                    observed_val = obs.value
                    quality = obs.quality

            res.append({
                'name': name,
                'comment': t.get('comment', ''),
                'type': t.get('type', ''),
                'length': t.get('length', ''),
                'fmt': t.get('fmt', ''),
                'conn': t.get('conn', ''),
                'group': t.get('group', 'Default'),
                'addr': t.get('addr', 'Internal'),
                'status': status,
                'observed_value': observed_val,
                'quality': quality,
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

    def push_state_to_webview(self):
        if self.closed or not self.web:
            return
        state_payload = {
            'tags': self._get_serializable_tags(),
            'tasks': self._get_serializable_tasks(),
            'recentTaskId': self.recent_task_id,
            'liveMode': self.live_mode
        }
        json_str = json.dumps(state_payload, ensure_ascii=False)
        self.web.evaluate_javascript(f'window.F1?.onStateUpdated({json_str})', -1, None, None, None, None, None)

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

        action = message.get('action')
        payload = message.get('payload', {})

        if action not in ALLOWLISTED_ACTIONS:
            logger.warning(f"Rejected unallowlisted action: {action}")
            return

        valid, err = validate_payload(action, payload)
        if not valid:
            logger.warning(f"Payload validation failed for {action}: {err}")
            return

        self._dispatch_action(action, payload)

    def _dispatch_action(self, action, payload):
        if action == 'get_state':
            self.push_state_to_webview()

        elif action == 'add_tag_to_task':
            tag_name = payload['tag_name']
            task_id = payload['task_id']
            self.recent_task_id = task_id
            task = next((t for t in self.owner.tasks if t.get('id') == task_id), None)
            if task is not None:
                if 'tags' not in task:
                    task['tags'] = []
                if tag_name not in task['tags']:
                    task['tags'].append(tag_name)
                    self._undo_stack.append({'action': 'add', 'task_id': task_id, 'tags': [tag_name]})
                    self.owner.save_tasks()
            self.push_state_to_webview()

        elif action == 'add_tags_to_task':
            tag_names = payload['tag_names']
            task_id = payload['task_id']
            self.recent_task_id = task_id
            task = next((t for t in self.owner.tasks if t.get('id') == task_id), None)
            if task is not None:
                if 'tags' not in task:
                    task['tags'] = []
                added = []
                for tn in tag_names:
                    if tn not in task['tags']:
                        task['tags'].append(tn)
                        added.append(tn)
                if added:
                    self._undo_stack.append({'action': 'add', 'task_id': task_id, 'tags': added})
                    self.owner.save_tasks()
            self.push_state_to_webview()

        elif action == 'remove_tag_from_task':
            tag_name = payload['tag_name']
            task_id = payload['task_id']
            task = next((t for t in self.owner.tasks if t.get('id') == task_id), None)
            if task is not None and 'tags' in task and tag_name in task['tags']:
                task['tags'].remove(tag_name)
                self._undo_stack.append({'action': 'remove', 'task_id': task_id, 'tags': [tag_name]})
                self.owner.save_tasks()
            self.push_state_to_webview()

        elif action == 'remove_tags_from_task':
            tag_names = payload['tag_names']
            task_id = payload['task_id']
            task = next((t for t in self.owner.tasks if t.get('id') == task_id), None)
            if task is not None and 'tags' in task:
                removed = []
                for tn in tag_names:
                    if tn in task['tags']:
                        task['tags'].remove(tn)
                        removed.append(tn)
                if removed:
                    self._undo_stack.append({'action': 'remove', 'task_id': task_id, 'tags': removed})
                    self.owner.save_tasks()
            self.push_state_to_webview()

        elif action == 'undo_last_action':
            if self._undo_stack:
                item = self._undo_stack.pop()
                task = next((t for t in self.owner.tasks if t.get('id') == item['task_id']), None)
                if task is not None:
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
                    self.owner.save_tasks()
            self.push_state_to_webview()

        elif action == 'save_task':
            updated_info = payload['task']
            task = next((t for t in self.owner.tasks if t.get('id') == updated_info['id']), None)
            if task is not None:
                # Keep draft copy for rollback
                draft_backup = dict(task)
                task['name'] = updated_info['name']
                task['cycle_sec'] = updated_info['cycle_sec']
                task['action_log'] = updated_info['action_log']
                task['action_notify'] = updated_info['action_notify']
                task['active'] = updated_info['active']

                saved = self.owner.save_tasks()
                if not saved:
                    # Rollback in memory
                    task.clear()
                    task.update(draft_backup)
                    logger.error(f"Failed to atomic save task {updated_info['id']}")
            self.push_state_to_webview()

        elif action == 'create_task':
            new_task_data = payload['task']
            new_task = {
                'id': new_task_data['id'],
                'name': new_task_data.get('name', f"Task ใหม่ {new_task_data['id']}"),
                'cycle_sec': new_task_data.get('cycle_sec', 5),
                'action_log': bool(new_task_data.get('action_log', True)),
                'action_notify': bool(new_task_data.get('action_notify', False)),
                'active': bool(new_task_data.get('active', False)),
                'tags': list(new_task_data.get('tags', [])),
                'scan_count': 0,
                'log_count': 0,
                'alert_count': 0
            }
            self.owner.tasks.append(new_task)
            self.recent_task_id = new_task['id']
            self.owner.save_tasks()
            self.push_state_to_webview()

        elif action == 'delete_task':
            task_id = payload['task_id']
            self.owner.tasks = [t for t in self.owner.tasks if t.get('id') != task_id]
            self.owner.save_tasks()
            self.push_state_to_webview()

        elif action == 'navigate_f6':
            if hasattr(self.owner, 'switch_to_tab'):
                self.owner.switch_to_tab('alarms')

        elif action == 'key_event':
            key_name = payload.get('key')
            if hasattr(self.owner, 'on_global_key_pressed') and key_name:
                keyval = getattr(Gdk, f'KEY_{key_name}', None)
                if keyval:
                    self.owner.on_global_key_pressed(None, keyval, 0, 0)

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
        next_num = len(getattr(self.owner, 'tasks', [])) + 1
        new_id = f"TASK-{next_num:02d}"
        new_task = {
            'id': new_id,
            'name': f"Task เฝ้าระวังใหม่ {next_num:02d}",
            'cycle_sec': 5,
            'action_log': True,
            'action_notify': False,
            'active': False,
            'tags': [],
            'scan_count': 0,
            'log_count': 0,
            'alert_count': 0
        }
        self.owner.tasks.append(new_task)
        self.recent_task_id = new_id
        self.owner.save_tasks()
        self.push_state_to_webview()
        self.open_task_dialog(new_id)

    def close(self):
        if self.closed:
            return
        self.closed = True
        if self.web:
            self.web.stop_loading()
            self.web.terminate_web_process()
