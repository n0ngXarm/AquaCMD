"""Presentation regressions on the real GTK4 window; no operational action is started."""
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from gi.repository import Gdk, Gio, Gtk
import app
from ux_native_capture import wait, settle, javascript


class DesktopPolishTests(unittest.TestCase):
    application_index = 0
    def setUp(self):
        self.profile = tempfile.TemporaryDirectory(prefix='aqua-native-ux-unit-')
        self.addCleanup(self.profile.cleanup)
        self.directory = Path(self.profile.name)
        self.patches = [patch.object(app, 'CONFIG_DIR', self.directory),
                        patch.object(app, 'DEFAULT_WINCC_EXPORT', self.directory/'missing.txt')]
        for item in self.patches:
            item.start()
            self.addCleanup(item.stop)
        type(self).application_index += 1
        self.application = Gtk.Application(application_id=f'org.aqua.ux.unit{self.application_index}', flags=Gio.ApplicationFlags.NON_UNIQUE)
        self.application.register(None)
        self.window = app.AquaWinCCWindow(self.application)
        self.window.present()
        wait(self.window.get_mapped)
        self.addCleanup(self.close_window)

    def close_window(self):
        window = self.window
        if getattr(window, '_close_dialog', None):
            window._close_dialog.response(Gtk.ResponseType.CANCEL)
        # Cleanup after a test, not a user-initiated close action.
        window._close_confirmed = True
        window.on_close_request()
        window.unified_workspace.f1_api.web.terminate_web_process()
        window.destroy()
        self.application.quit()
        settle(.05)

    def test_f8_always_asks_even_when_idle_and_cancel_keeps_monitoring_resources(self):
        window = self.window
        self.assertEqual(window.polling_engine.get_telemetry()['state'], 'STOPPED')
        self.assertTrue(window.on_global_key_pressed(None, Gdk.KEY_F8, 0, 0))
        dialog = getattr(window, '_close_dialog', None)
        self.assertIsNotNone(dialog)
        wait(dialog.get_mapped)
        self.assertTrue(dialog.get_modal())
        self.assertEqual(dialog.get_default_widget(), dialog.get_widget_for_response(Gtk.ResponseType.CANCEL))
        self.assertFalse(window.f3_network_view.closed)
        window.on_global_key_pressed(None, Gdk.KEY_F8, 0, 0)
        self.assertIs(window._close_dialog, dialog)
        dialog.response(Gtk.ResponseType.CANCEL)
        self.assertIsNone(window._close_dialog)
        self.assertTrue(window.get_visible())
        self.assertFalse(window.f3_network_view.closed)

    def test_normal_close_runs_original_cleanup_only_after_explicit_acceptance(self):
        window = self.window
        with patch.object(window.f3_network_view, 'close', wraps=window.f3_network_view.close) as close:
            window.close()
            dialog = getattr(window, '_close_dialog', None)
            self.assertIsNotNone(dialog)
            close.assert_not_called()
            dialog.response(Gtk.ResponseType.ACCEPT)
            close.assert_called_once_with()
        self.assertFalse(window.get_visible())
        self.assertTrue(window.f3_network_view.closed)

    def test_navigation_shortcuts_and_task_dialog_selected_state(self):
        window = self.window
        for page, key in [('overview','F1'),('tasks','F2'),('network','F3'),('machine','F4'),('tags','F5'),('alarms','F6')]:
            self.assertIn(key, window.nav_btns[page].get_tooltip_text())
        self.assertIn('Ctrl+,', window.settings_button.get_tooltip_text())
        self.assertIn('F8', window.exit_button.get_tooltip_text())
        self.assertIn('F9', window.help_button.get_tooltip_text())
        web = window.unified_workspace.f1_api.web
        wait(lambda: javascript(web, 'Boolean(window.F1)'))
        window.on_global_key_pressed(None, Gdk.KEY_F2, 0, 0)
        wait(lambda: window.nav_btns['tasks'].get_active())
        wait(lambda: javascript(web, "document.getElementById('modalOverlay').open"))
        javascript(web, "(window.F1.setMode('monitoring'), true)")
        wait(lambda: not window.nav_btns['tasks'].get_active())
        self.assertEqual(window.unified_workspace.current_workspace_mode, 'monitoring')
        self.assertEqual(window.polling_engine.get_telemetry()['poll_count'], 0)

    def test_status_ribbon_keeps_full_selectable_text_and_reports_refresh_state(self):
        window = self.window
        message = 'ตรวจความพร้อมไม่ผ่าน: CERT_ERROR · ' + 'เหตุผลจากระบบ ' * 30
        window.alarm_text.set_text(message)
        self.assertEqual(window.alarm_text.get_tooltip_text(), message)
        self.assertTrue(window.alarm_text.get_selectable())
        window.auto_scan_active = False
        window.auto_scan_interval = 30
        window.update_catalog_refresh_status()
        self.assertIn('ปิด', window.catalog_refresh_status.get_text())
        self.assertIn('30', window.catalog_refresh_status.get_text())
        self.assertEqual(window.polling_engine.get_telemetry()['poll_count'], 0)

    def test_f3_demo_is_disabled_with_a_reason_when_telegram_is_not_configured(self):
        window = self.window
        window.on_global_key_pressed(None, Gdk.KEY_F3, 0, 0)
        view = window.f3_network_view
        wait(lambda: view.web is not None)
        wait(lambda: javascript(view.web, "Boolean(document.getElementById('f3-demo'))"))
        self.assertTrue(javascript(view.web, "document.getElementById('f3-demo').disabled"))
        self.assertIn('F6', javascript(view.web, "document.getElementById('f3-demo').title"))
        self.assertIsNone(view._demo_process)

    def test_f3_real_delivery_confirmation_masks_destination_and_cancel_starts_nothing(self):
        import json
        view = self.window.f3_network_view
        config = {'enabled':True, 'bot_token':'123:synthetic-ui-only', 'chat_id':'synthetic-chat-123456'}
        view._telegram_demo_config.write_text(json.dumps(config))
        self.window.on_global_key_pressed(None, Gdk.KEY_F3, 0, 0)
        wait(lambda: view.web is not None)
        wait(lambda: javascript(view.web, "Boolean(document.getElementById('f3-demo'))"))
        with patch.object(view, '_open_demo') as start:
            javascript(view.web, "(document.getElementById('f3-demo').click(), true)")
            wait(lambda: getattr(view, '_demo_confirmation', None) is not None)
            dialog = view._demo_confirmation
            text = dialog.get_property('secondary-text')
            self.assertIn('SIMULATED', text)
            self.assertIn('***3456', text)
            self.assertNotIn(config['chat_id'], text)
            self.assertNotIn(config['bot_token'], text)
            self.assertEqual(dialog.get_default_widget(), dialog.get_widget_for_response(Gtk.ResponseType.CANCEL))
            dialog.response(Gtk.ResponseType.CANCEL)
            start.assert_not_called()
            javascript(view.web, "(document.getElementById('f3-demo').click(), true)")
            wait(lambda: view._demo_confirmation is not None)
            view._demo_confirmation.response(Gtk.ResponseType.ACCEPT)
            start.assert_called_once_with()
            javascript(view.web, "(document.getElementById('f3-demo').click(), true)")
            wait(lambda: view._demo_confirmation is not None)
            config['chat_id'] = 'synthetic-changed-765432'
            view._telegram_demo_config.write_text(json.dumps(config))
            view._demo_confirmation.response(Gtk.ResponseType.ACCEPT)
            start.assert_called_once_with()
        self.assertIsNone(view._demo_process)

    def test_empty_catalog_has_one_real_next_action_and_stale_readings_keep_age(self):
        web = self.window.unified_workspace.f1_api.web
        wait(lambda: javascript(web, 'Boolean(window.F1)'))
        self.assertIn('ยังไม่มีคลัง Tag', javascript(web, "document.getElementById('tableBody').textContent"))
        self.assertEqual(javascript(web, "document.querySelectorAll('#tableBody .btn-primary').length"), 1)
        javascript(web, "(document.getElementById('btnResetFilters').click(), true)")
        wait(lambda: self.window.stack.get_visible_child_name() == 'tags')
        self.window.on_global_key_pressed(None, Gdk.KEY_F1, 0, 0)
        javascript(web, """(window.F1.onStateUpdated({tags:[{name:'LAB.STALE',group:'LAB',type:'Float',status:'STALE',observed_value:12.5,observation_at:'2026-01-01T00:00:00Z',age_text:'2 นาทีที่แล้ว',tasks:[]}],tasks:[]}), true)""")
        text = javascript(web, "document.querySelector('.cell-status').textContent")
        self.assertIn('12.5', text)
        self.assertIn('ข้อมูลล่าสุดเมื่อ', text)
        self.assertIn('2 นาทีที่แล้ว', text)
        self.assertEqual(self.window.polling_engine.get_telemetry()['poll_count'], 0)

    def test_accessibility_keyboard_path_and_accessible_labels(self):
        # 1. Accessible labels on GTK buttons
        self.assertIsNotNone(self.window.exit_button)
        self.assertIn('F8', self.window.exit_button.get_tooltip_text())
        self.assertIn('F9', self.window.help_button.get_tooltip_text())
        self.assertIn('F6', self.window.settings_button.get_tooltip_text())

        # 2. F1 web view keyboard path and accessible labels
        web = self.window.unified_workspace.f1_api.web
        wait(lambda: javascript(web, 'Boolean(window.F1)'))
        javascript(web, """(window.F1.onStateUpdated({
            tags:[
                {name:'LAB.ACC1',group:'LAB',type:'Float',status:'OK',observed_value:42.0,observation_at:'2026-01-01T00:00:00Z',age_text:'1 วินาทีที่แล้ว',tasks:[]},
                {name:'LAB.ACC2',group:'LAB',type:'Float',status:'FAIL',observed_value:null,observation_at:'2026-01-01T00:00:00Z',age_text:'1 วินาทีที่แล้ว',tasks:[]}
            ],
            tasks:[{id:'TASK-01',name:'Task หลัก',cycle_sec:5,active:true,action_log:true,action_notify:false,tags:['LAB.ACC1']}]
        }), true)""")

        # Verify row tabindex and role
        self.assertEqual(javascript(web, "document.querySelector('.table-row').getAttribute('role')"), 'row')
        self.assertEqual(javascript(web, "document.querySelector('.table-row').getAttribute('tabindex')"), '0')

        # Verify action buttons have accessible labels (aria-label)
        self.assertTrue(javascript(web, "Boolean(document.querySelector('.btn-quick-task').getAttribute('aria-label'))"))
        self.assertTrue(javascript(web, "Boolean(document.querySelector('.btn-inspect').getAttribute('aria-label'))"))

        # Verify Esc closes modal and returns focus
        javascript(web, "(document.querySelector('.btn-inspect').click(), true)")
        wait(lambda: javascript(web, "document.getElementById('modalOverlay').open"))
        javascript(web, """(document.dispatchEvent(new KeyboardEvent('keydown', {key: 'Escape', bubbles: true})), true)""")
        wait(lambda: not javascript(web, "document.getElementById('modalOverlay').open"))

        # 3. F3 network view node accessible labels and close button
        self.window.on_global_key_pressed(None, Gdk.KEY_F3, 0, 0)
        view = self.window.f3_network_view
        wait(lambda: view.web is not None)
        wait(lambda: javascript(view.web, "Boolean(document.getElementById('f3-demo'))"))
        self.assertEqual(javascript(view.web, "document.querySelector('[data-close]').getAttribute('aria-label')"), 'ปิดหน้าต่าง')
        self.assertTrue(javascript(view.web, """(
            snapshot = {nodes: [{id: 'station_1', label: 'Station 1', kind: 'scada', last: null}], stale_ms: 60000},
            render(),
            Boolean(document.querySelector('.node').getAttribute('aria-label'))
        )"""))

        # 4. Verify prefers-reduced-motion exists in CSS files
        f1_css = (Path(__file__).resolve().parents[1] / 'f1_api/view.css').read_text()
        f3_css = (Path(__file__).resolve().parents[1] / 'f3_api/view.css').read_text()
        self.assertIn('@media (prefers-reduced-motion: reduce)', f1_css)
        self.assertIn('@media (prefers-reduced-motion: reduce)', f3_css)
        self.assertEqual(self.window.polling_engine.get_telemetry()['poll_count'], 0)



class PresentationStyleTests(unittest.TestCase):
    def test_css_has_no_secondary_text_below_ten_points(self):
        import re
        root = Path(__file__).resolve().parents[1]
        files = [root/name for name in ('style.css','f1_style.css','f2_style.css','workspace_style.css')]
        files += [root/area/name for area in ('f1_api','f3_api') for name in ('view.css',)]
        violations=[]
        for file in files:
            for match in re.finditer(r'font-size:\s*([0-9.]+)(pt|px)', file.read_text()):
                points=float(match[1]) * (0.75 if match[2]=='px' else 1)
                if points < 10: violations.append((file.name,match[0]))
        self.assertEqual(violations, [])

    def test_contrast_samples_meet_normal_text_target(self):
        from ux_contrast import contrast, measurements
        self.assertEqual(contrast('#ffffff','#000000'), 21)
        self.assertTrue(all(row['passes_4_5'] for row in measurements()))


if __name__ == '__main__':
    unittest.main()
