"""Native F1/F2 tests using the real catalog and an isolated Task file."""
import json
import os
import time
import sys
import tempfile
import unittest
from contextlib import ExitStack
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import app
from gi.repository import Gdk, Gio, GLib, Gtk
from opcua_store import Quality, TagObservation


def drain_events():
    context = GLib.MainContext.default()
    while context.pending():
        context.iteration(False)


def capture(window, filename):
    directory = os.environ.get('F1_TEST_SCREENSHOTS')
    if not directory:
        return
    window.present()
    paintable = Gtk.WidgetPaintable.new(window)
    deadline = time.monotonic() + 2
    node = None
    while node is None and time.monotonic() < deadline:
        drain_events()
        snapshot = Gtk.Snapshot()
        paintable.snapshot(snapshot, window.get_width(), window.get_height())
        node = snapshot.to_node()
        if node is None:
            window.queue_draw()
            time.sleep(.02)
    if node is None:
        raise RuntimeError(f'Window was not drawn for {filename}')
    texture = window.get_renderer().render_texture(node, None)
    if not texture.save_to_png(str(Path(directory) / filename)):
        raise RuntimeError(f'Failed to save {filename}')


class TestWorkspaceProductionIntegration(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cleanup = ExitStack()
        cls.addClassCleanup(cleanup.close)
        config = Path(cleanup.enter_context(tempfile.TemporaryDirectory()))
        cleanup.enter_context(patch.multiple(
            app, CONFIG_DIR=config, TASKS_CONFIG_FILE=config / 'wincc_tasks.json',
            TOPOLOGY_CONFIG_FILE=config / 'network_topology.json',
            TELEGRAM_CONFIG_FILE=config / 'telegram_config.json',
            OPCUA_CONFIG_FILE=config / 'opcua_config.json',
        ))
        cleanup.enter_context(patch.object(app.AquaWinCCWindow, 'update_real_data', lambda self: False))
        cleanup.enter_context(patch.object(app.F3ApiView, 'refresh_local_state', lambda self: None))
        cleanup.enter_context(patch('workspace.F1ApiView', None))
        cls.application = Gtk.Application(application_id='org.aquacommand.F1Test',
                                          flags=Gio.ApplicationFlags.NON_UNIQUE)
        assert cls.application.register(None)
        cls.win = app.AquaWinCCWindow(cls.application)
        cls.addClassCleanup(cls.win.close)
        if width := os.environ.get('F1_TEST_WIDTH'):
            cls.win.set_default_size(int(width), 900)
        cls.win.present()
        cls.win.tick_clock()
        drain_events()
        cls.ws = cls.win.unified_workspace

    def test_01_real_catalog_and_search(self):
        ws = self.ws
        ws.on_select_group('All')
        self.assertEqual(len(ws.currently_filtered_tags), 457)
        self.assertEqual(len({t['group'] for t in ws.currently_filtered_tags}), 10)
        self.assertIs(self.win.stack.get_visible_child(), ws.root_box)
        self.assertIs(ws.main_hpaned.get_end_child(), ws.center_col)
        self.assertIn('ยังไม่ได้สังเกต', ws.catalog_listbox.get_first_child()._quality_label.get_text())
        capture(self.win, 'f1-overview.png')
        name = ws.currently_filtered_tags[0]['name']
        ws.entry_search.set_text(name)
        ws.on_search_changed(ws.entry_search)
        self.assertIn(name, [t['name'] for t in ws.currently_filtered_tags])
        self.assertLess(len(ws.currently_filtered_tags), 457)
        ws.entry_search.set_text('')
        ws.on_search_changed(ws.entry_search)

    def test_02_f2_opens_task_popup_on_overview(self):
        self.assertTrue(self.win.on_global_key_pressed(None, Gdk.KEY_F2, 0, 0))
        drain_events()
        self.assertEqual(self.win.stack.get_visible_child_name(), 'overview')
        self.assertTrue(self.win.nav_btns['overview'].get_active())
        self.assertTrue(self.ws.task_dialog.get_visible())
        self.assertIn('Task', self.ws.task_dialog.get_title())
        self.ws.task_dialog.close()
        drain_events()

    def test_03_task_fields_and_tags_round_trip(self):
        ws = self.ws
        ws.open_task_dialog()
        count = len(self.win.tasks)
        ws.on_create_new_task()
        self.assertEqual(len(self.win.tasks), count)
        self.assertFalse(ws.chk_task_enabled.get_active())
        self.assertFalse(ws.chk_action_notify.get_active())
        ws.entry_task_name.set_text('ทดสอบบันทึก')
        ws.combo_cycle.set_selected(1)
        ws.chk_action_log.set_active(True)
        ws.chk_action_notify.set_active(True)
        ws.chk_task_enabled.set_active(False)
        ws.on_save_task()
        current = self.win.tasks[ws.selected_task_index]
        self.assertFalse(current['active'])
        self.assertTrue(current['action_log'])
        self.assertTrue(current['action_notify'])
        self.assertEqual(current['name'], 'ทดสอบบันทึก')
        self.assertEqual(json.loads(app.TASKS_CONFIG_FILE.read_text()), self.win.tasks)
        capture(ws.task_dialog, 'f2-task.png')
        ws.task_dialog.close()
        drain_events()

    def ensure_task(self):
        if not self.win.tasks:
            self.ws.open_task_dialog()
            self.ws.on_create_new_task()
            self.assertTrue(self.ws.on_save_task())
            self.ws.task_dialog.close()
            drain_events()

    def test_04_single_add_undo_and_bulk_membership(self):
        self.ensure_task()
        ws = self.ws
        ws.on_select_group('High_VSD')
        names = [tag['name'] for tag in ws.currently_filtered_tags[:10]]
        index = ws.selected_task_index
        self.assertEqual(len(names), 10)
        ws.catalog_listbox.select_row(ws.catalog_rows[names[0]])
        ws.btn_catalog_details.emit('clicked')
        self.assertTrue(ws.inspector_dialog.get_visible())
        ws.inspector_task_selector.set_selected(index)
        ws.btn_add_to_cur_task.emit('clicked')
        self.assertFalse(ws.inspector_dialog.get_visible())
        self.assertIn(names[0], app.load_tasks()[index]['tags'])
        ws._undo_last_add()
        self.assertNotIn(names[0], app.load_tasks()[index]['tags'])
        ws.catalog_checkboxes[names[0]].set_active(True)
        ws._range_requested = True
        ws.catalog_checkboxes[names[-1]].set_active(True)
        self.assertEqual(ws.selected_catalog_tags, set(names))
        ws.on_add_selected_to_task()
        drain_events()
        self.assertTrue(ws.bulk_dialog.get_visible())
        capture(ws.bulk_dialog, 'f1-task-destination.png')
        ws.bulk_submit_button.emit('clicked')
        self.assertEqual(set(app.load_tasks()[index]['tags']), set(names))
        ws._add_tags(index, names)
        self.assertEqual(len(app.load_tasks()[index]['tags']), 10)
        ws.open_task_dialog()
        assigned = next(row for row in ws.assigned_listbox.observe_children() if row._tag_name == names[0])
        ws.assigned_listbox.select_row(assigned)
        ws.btn_remove_assigned.emit('clicked')
        ws.on_save_task()
        self.assertNotIn(names[0], app.load_tasks()[index]['tags'])
        ws.task_dialog.close()
        drain_events()

    def test_05_inspector_opens_without_claiming_live_values(self):
        ws = self.ws
        ws.on_select_group('All')
        row = ws.catalog_listbox.get_first_child()
        self.assertIsNotNone(row)
        ws.catalog_listbox.emit('row-activated', row)
        drain_events()
        self.assertTrue(ws.inspector_dialog.get_visible())
        self.assertIn('ยังไม่ได้สังเกต', ws.insp_grid_values['quality'].get_text())
        capture(ws.inspector_dialog, 'f1-inspector.png')
        name = row._tag_data['name']
        self.win.opcua_store.update_observation(TagObservation(
            name, value=0, quality=Quality.GOOD,
            arrival_time=datetime.now(timezone.utc) - timedelta(seconds=75),
        ))
        ws.render_inspector_tag(row._tag_data)
        self.assertIn('ข้อมูลเก่า', ws.insp_grid_values['quality'].get_text())
        ws.inspector_dialog.close()
        drain_events()

    def test_06_failed_editor_save_keeps_draft_and_original_file(self):
        self.ensure_task()
        ws = self.ws
        ws.open_task_dialog()
        before = app.TASKS_CONFIG_FILE.read_bytes()
        original = self.win.tasks[ws.selected_task_index]['name']
        ws.entry_task_name.set_text('ชื่อที่ยังไม่ได้บันทึก')
        with patch.object(self.win, 'save_tasks', return_value=False):
            self.assertFalse(ws.on_save_task())
        self.assertTrue(ws.has_unsaved_changes)
        self.assertEqual(app.TASKS_CONFIG_FILE.read_bytes(), before)
        self.assertEqual(self.win.tasks[ws.selected_task_index]['name'], original)
        ws.entry_task_name.set_text(original)
        self.assertTrue(ws.on_save_task())
        ws.task_dialog.close()
        drain_events()


    def test_07_catalog_columns_align_with_long_task_name(self):
        ws = self.ws
        ws.on_select_group('All')
        ws.entry_search.set_text('')
        ws.on_search_changed(ws.entry_search)
        first = ws.catalog_listbox.get_first_child()
        second = first.get_next_sibling()
        header = ws.catalog_listbox.get_parent().get_parent().get_prev_sibling()

        def horizontal_bounds(box):
            cells = []
            for cell in box.observe_children():
                success, bounds = cell.compute_bounds(self.win)
                self.assertTrue(success)
                cells.append((round(bounds.get_x()), round(bounds.get_width())))
            return cells

        task_name = 'Task ทดสอบ ' * 30
        with patch.object(self.win, 'tasks', [{'name': task_name, 'tags': [first._tag_data['name']]}]):
            ws.render_catalog_table()
            ws.catalog_listbox.select_row(second)
            deadline = time.monotonic() + .2
            while time.monotonic() < deadline:
                drain_events()
                time.sleep(.01)
            self.assertEqual(first._task_label.get_tooltip_text(), task_name)
            reference = horizontal_bounds(first.get_child())
            self.assertEqual(len(reference), 6)
            self.assertEqual(reference, horizontal_bounds(second.get_child()))
            self.assertEqual(reference, horizontal_bounds(header))
            self.assertTrue(first._task_label.get_layout().is_ellipsized())
            capture(self.win, 'f1-aligned-columns.png')
        ws.render_catalog_table()


    def test_08_selection_and_details_are_separate(self):
        self.ensure_task()
        ws = self.ws
        ws.on_select_group('All')
        ws.on_clear_selection()
        first = ws.catalog_listbox.get_first_child()
        second = first.get_next_sibling()
        selected = first._tag_data['name']
        self.assertFalse(ws.catalog_listbox.get_activate_on_single_click())
        ws.catalog_checkboxes[selected].set_active(True)
        ws.catalog_listbox.select_row(second)
        self.assertFalse(ws.inspector_dialog is not None and ws.inspector_dialog.get_visible())
        self.assertEqual(ws.selected_catalog_tags, {selected})
        self.assertTrue(ws.btn_add_selected.get_sensitive())
        table = ws.catalog_listbox.get_ancestor(Gtk.ScrolledWindow).get_parent()
        self.assertIs(ws.dock_box.get_next_sibling(), table)
        ws.entry_search.set_text('tag_not_in_export_9a278')
        ws.on_search_changed(ws.entry_search)
        self.assertIn('อยู่นอกผลค้นหาหรือกลุ่มนี้ 1', ws.lbl_sel_badge.get_text())
        self.assertFalse(ws.btn_catalog_details.get_sensitive())
        ws.entry_search.set_text('')
        ws.on_search_changed(ws.entry_search)
        capture(self.win, 'f1-selection.png')

        ws.catalog_listbox.select_row(second)
        self.assertTrue(ws.btn_catalog_details.get_sensitive())
        self.assertFalse(any(isinstance(cell, Gtk.Button) for cell in second.get_child().observe_children()))
        ws.btn_catalog_details.emit('clicked')
        drain_events()
        self.assertTrue(ws.inspector_dialog.get_visible())
        self.assertEqual(ws.insp_lbl_name.get_text(), second._tag_data['name'])
        self.assertIsNone(ws.btn_add_to_cur_task.get_ancestor(Gtk.ScrolledWindow))
        self.assertIsNone(ws.btn_close_inspector.get_ancestor(Gtk.ScrolledWindow))
        self.assertFalse(ws.inspector_technical.get_expanded())
        self.assertIsNone(ws.btn_save_task.get_ancestor(Gtk.ScrolledWindow))
        self.assertEqual(ws.selected_catalog_tags, {selected})
        capture(ws.inspector_dialog, 'f1-details.png')
        ws.btn_close_inspector.emit('clicked')
        drain_events()
        self.assertFalse(ws.inspector_dialog.get_visible())
        self.assertEqual(ws.selected_catalog_tags, {selected})

        with patch.object(self.win, 'tasks', []):
            ws.update_selection_badges()
            self.assertEqual(ws.btn_add_selected.get_label(), 'สร้าง Task ก่อน')
            ws.btn_add_selected.emit('clicked')
            self.assertTrue(ws.task_dialog.get_visible())
            self.assertTrue(ws._new_task)
            self.assertEqual(ws.selected_catalog_tags, {selected})
            ws._new_task = False
            ws.load_current_task_to_ui()
            ws.task_dialog.close()
        ws.load_current_task_to_ui()
        ws.on_clear_selection()


    def test_09_task_editor_shows_nine_plain_rows(self):
        ws = self.ws
        names = [tag['name'] for tag in ws.catalog_tags_cache[:9]]
        task = {'id': 'TASK-09', 'name': 'ทดสอบรายการ 9 Tag', 'tags': names}
        with patch.object(self.win, 'tasks', [task]):
            ws.open_task_dialog()
            deadline = time.monotonic() + .3
            while time.monotonic() < deadline:
                drain_events()
                time.sleep(.01)
            list_scroll = ws.assigned_listbox.get_ancestor(Gtk.ScrolledWindow)
            self.assertIsNone(list_scroll.get_parent().get_ancestor(Gtk.ScrolledWindow))
            capture(ws.task_dialog, 'f2-nine-tags.png')
            self.assertGreaterEqual(ws.task_dialog.get_width(), 900)
            rows = [row for row in ws.assigned_listbox.observe_children() if isinstance(row, Gtk.ListBoxRow)]
            self.assertEqual(len(rows), 9)
            for row in rows:
                self.assertFalse(any(isinstance(cell, Gtk.Button) for cell in row.get_child().observe_children()))
            adjustment = list_scroll.get_vadjustment()
            self.assertGreater(adjustment.get_page_size(), 0)
            self.assertGreaterEqual(adjustment.get_page_size(), adjustment.get_upper())
            self.assertFalse(ws.btn_remove_assigned.get_sensitive())
            ws.assigned_listbox.select_row(rows[-1])
            self.assertTrue(ws.btn_remove_assigned.get_sensitive())
            ws.btn_remove_assigned.emit('clicked')
            self.assertEqual(ws._task_draft['tags'], names[:-1])
            self.assertEqual(task['tags'], names)
            self.assertTrue(ws.has_unsaved_changes)
            self.assertFalse(ws.btn_remove_assigned.get_sensitive())

            ws._task_draft['tags'] = [tag['name'] for tag in ws.catalog_tags_cache[:60]]
            ws.render_assigned_tags_table(ws._task_draft)
            deadline = time.monotonic() + .3
            while time.monotonic() < deadline:
                drain_events()
                time.sleep(.01)
            self.assertGreater(adjustment.get_upper(), adjustment.get_page_size())
            self.assertIsNone(ws.btn_save_task.get_ancestor(Gtk.ScrolledWindow))
            ws.load_current_task_to_ui()
            ws.task_dialog.close()
        ws.load_current_task_to_ui()


    def test_10_f6_sections_and_local_telegram_save(self):
        win = self.win
        self.addCleanup(win.switch_to_tab, 'overview')
        self.assertTrue(win.on_global_key_pressed(None, Gdk.KEY_F6, 0, 0))
        self.assertEqual(win.stack.get_visible_child_name(), 'alarms')

        sections = win.f6_sections
        for name in ('opcua', 'telegram', 'history'):
            self.assertIsNotNone(sections.get_child_by_name(name))
        self.assertEqual(sections.get_visible_child_name(), 'opcua')
        self.assertFalse(win.f6_opc_credentials.get_visible())
        self.assertFalse(win.f6_certificate.get_expanded())
        win.entry_opc_url.set_text('')
        capture(win, 'f6-opcua.png')

        win.opc_auth_combo.set_selected(1)
        self.assertTrue(win.f6_opc_credentials.get_visible())
        win.entry_opc_url.set_text('opc.tcp://wincc.example:4840')
        win.opc_sec_combo.set_selected(1)
        win.entry_opc_user.set_text('local-test-user')
        win.entry_opc_pass.set_text('temporary-session-test')
        win.on_save_opcua_config()
        saved_opc = json.loads(app.OPCUA_CONFIG_FILE.read_text())
        self.assertEqual(saved_opc['endpoint_url'], 'opc.tcp://wincc.example:4840')
        self.assertEqual(saved_opc['auth_mode'], 'Username')
        self.assertEqual(saved_opc['security_policy'], 'Basic256Sha256')
        self.assertNotIn('password', saved_opc)
        win.opc_auth_combo.set_selected(0)
        self.assertFalse(win.f6_opc_credentials.get_visible())
        win._update_trust_quarantined_ui(True, 'รอตรวจสอบใบรับรอง', {'thumbprint': 'TEST-FINGERPRINT'})
        self.assertTrue(win.f6_certificate.get_expanded())
        self.assertTrue(win.btn_trust_quarantined.get_sensitive())

        win.set_focus(None)
        drain_events()
        sections.set_visible_child_name('telegram')
        drain_events()
        self.assertEqual(sections.get_visible_child_name(), 'telegram')
        self.assertFalse(win.entry_tg_token.get_visibility())
        capture(win, 'f6-telegram.png')

        win.entry_tg_token.set_text('local-test-token')
        win.entry_tg_chat_id.set_text('12345')
        win.on_save_telegram_config()
        saved = json.loads(app.TELEGRAM_CONFIG_FILE.read_text())
        self.assertEqual(saved['bot_token'], 'local-test-token')
        self.assertEqual(saved['chat_id'], '12345')
        self.assertIn('บันทึก', win.lbl_tg_status.get_text())
        self.assertNotIn('ไม่สำเร็จ', win.lbl_tg_status.get_text())
        original_config = dict(win.telegram_config)
        original_file = app.TELEGRAM_CONFIG_FILE.read_bytes()
        win.entry_tg_chat_id.set_text('67890')
        with patch.object(app, 'save_telegram_config', return_value=False):
            win.on_save_telegram_config()
            with patch.object(app.threading, 'Thread') as thread:
                win.on_test_telegram_send()
                thread.assert_not_called()
        self.assertIn('บันทึกไม่สำเร็จ', win.lbl_tg_status.get_text())
        self.assertEqual(win.telegram_config, original_config)
        self.assertEqual(app.TELEGRAM_CONFIG_FILE.read_bytes(), original_file)

        win.add_alarm_event('08/11/2026 12:00:00', 'TEST', 'INFO', 'CONFIGURED', 'ตัวอย่างประวัติสำหรับทดสอบหน้าจอ')
        win.set_focus(None)
        drain_events()
        sections.set_visible_child_name('history')
        drain_events()
        self.assertEqual(sections.get_visible_child_name(), 'history')
        self.assertTrue(win.alarm_grid.get_mapped())
        history = [label.get_text() for label in win.alarm_grid.observe_children()]
        self.assertIn('ตัวอย่างประวัติสำหรับทดสอบหน้าจอ', history)
        capture(win, 'f6-history.png')


    def test_11_f6_uses_available_width(self):
        win = self.win
        self.addCleanup(win.switch_to_tab, 'overview')
        win.on_global_key_pressed(None, Gdk.KEY_F6, 0, 0)
        win.entry_opc_url.set_text('')
        win.opc_auth_combo.set_selected(1)

        sections = win.f6_sections

        def settled_bounds(widget):
            success, bounds = widget.compute_bounds(sections)
            self.assertTrue(success)
            return bounds

        win.f6_certificate.set_expanded(False)
        win.add_alarm_event('09/11/2026 12:00:00', 'TEST', 'INFO', 'CONFIGURED',
                            'ทดสอบการตัดบรรทัด ' + 'TEST/' * 60)
        for name in ('opcua', 'telegram', 'history'):
            with self.subTest(section=name):
                win.set_focus(None)
                sections.set_visible_child_name(name)
                deadline = time.monotonic() + .3
                while time.monotonic() < deadline:
                    drain_events()
                    time.sleep(.01)

                viewport = sections.get_visible_child().get_child()
                workspace = viewport.get_child()
                self.assertGreaterEqual(settled_bounds(workspace).get_height(), sections.get_height() - 24)
                body = settled_bounds(workspace.get_first_child())
                self.assertGreaterEqual(body.get_width(), sections.get_width() - 48)
                self.assertGreaterEqual(body.get_x(), 0)
                self.assertLessEqual(body.get_x() + body.get_width(), sections.get_width())
                if name == 'opcua':
                    left = settled_bounds(win.entry_opc_url)
                    right = settled_bounds(win.btn_start_monitoring)
                    self.assertGreater(right.get_x(), left.get_x() + left.get_width())
                    self.assertLess(right.get_y(), settled_bounds(win.btn_test_opc).get_y())
                if name == 'telegram':
                    left = settled_bounds(win.entry_tg_chat_id)
                    right = settled_bounds(win.entry_tg_test_msg)
                    self.assertGreater(right.get_x(), left.get_x() + left.get_width())
                if name == 'history':
                    grid = settled_bounds(win.alarm_grid)
                    self.assertLessEqual(grid.get_x() + grid.get_width(), sections.get_width())
                capture(win, f'f6-wide-{name}.png')
                if name == 'opcua':
                    win._update_trust_quarantined_ui(True, 'รอตรวจสอบใบรับรอง',
                                                    {'thumbprint': 'A1B2' * 16})
                    deadline = time.monotonic() + .3
                    while time.monotonic() < deadline:
                        drain_events()
                        time.sleep(.01)
                    cert = settled_bounds(win.lbl_pki_server_details)
                    self.assertLessEqual(cert.get_x() + cert.get_width(), sections.get_width())


if __name__ == '__main__':
    unittest.main()
