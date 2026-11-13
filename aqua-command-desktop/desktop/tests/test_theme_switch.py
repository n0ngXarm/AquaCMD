"""Runtime GTK/WebKit theme integration on disposable profiles only."""
import hashlib
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from gi.repository import Gio, Gtk
import app
from ux_native_capture import javascript, settle, wait


class ThemeSwitchTests(unittest.TestCase):
    serial = 0

    def setUp(self):
        directory = tempfile.TemporaryDirectory(prefix='aqua-native-ux-theme-')
        self.addCleanup(directory.cleanup)
        self.directory = Path(directory.name)
        self.patches = [patch.object(app, 'CONFIG_DIR', self.directory),
                        patch.object(app, 'DEFAULT_WINCC_EXPORT', self.directory / 'absent.txt')]
        for item in self.patches:
            item.start()
            self.addCleanup(item.stop)
        type(self).serial += 1
        self.application = Gtk.Application(application_id=f'org.aqua.theme.test{self.serial}', flags=Gio.ApplicationFlags.NON_UNIQUE)
        self.application.register(None)
        self.window = app.AquaWinCCWindow(self.application)
        self.window.present()
        wait(self.window.get_mapped)
        self.addCleanup(self.close_window)

    def close_window(self):
        self.window._close_confirmed = True
        self.window.on_close_request()
        self.window.unified_workspace.f1_api.web.terminate_web_process()
        self.window.destroy()
        self.application.quit()
        settle(.05)

    def test_switch_replaces_css_and_updates_both_views_without_reload_or_activity(self):
        window = self.window
        f1 = window.unified_workspace.f1_api.web
        wait(lambda: javascript(f1, 'Boolean(window.F1)'))
        self.assertEqual(window.theme_mode, 'light')
        self.assertEqual(javascript(f1, 'document.documentElement.dataset.theme'), 'light')
        import json
        from collector.probe_once import EvidenceStore
        config = self.directory / 'probe-targets.json'
        config.write_text(json.dumps({'targets':[{'host':'127.0.0.2','port':4840}], 'ping_timeout_s':.1, 'tcp_timeout_s':.1}))
        store = EvidenceStore(self.directory / 'theme-evidence.db')
        store.connection.close()
        window.f3_network_view.config_path = config
        window.f3_network_view.db_path = store.path
        window.switch_to_tab('network')
        f3 = window.f3_network_view
        wait(lambda: bool(f3.api_url))
        wait(lambda: javascript(f3.web, 'Boolean(window.F3)'))
        original_url = f3.api_url
        javascript(f1, '(window.themeSentinel=17,true)')
        javascript(f3.web, '(window.themeSentinel=23,true)')
        configs = {p: hashlib.sha256(p.read_bytes()).hexdigest() for p in self.directory.rglob('*') if p.is_file()}
        providers = [provider for provider, _ in window._theme_providers]
        tasks = list(window.tasks)
        with patch.object(window.polling_engine, 'stop_monitoring') as stop, patch.object(window.notification_worker, 'stop') as notify_stop:
            for mode in ('dark', 'light', 'dark'):
                self.assertTrue(window.set_theme(mode))
                wait(lambda: javascript(f1, 'document.documentElement.dataset.theme') == mode)
                wait(lambda: javascript(f3.web, 'document.documentElement.dataset.theme') == mode)
                self.assertEqual(Gtk.Settings.get_default().get_property('gtk-application-prefer-dark-theme'), mode == 'dark')
                self.assertEqual(window.theme_button.get_active(), mode == 'dark')
                self.assertTrue(window.theme_buttons[mode].get_active())
            stop.assert_not_called()
            notify_stop.assert_not_called()
        self.assertTrue(all(before is not after for before, (after, _) in zip(providers, window._theme_providers)))
        self.assertEqual(javascript(f1, 'window.themeSentinel'), 17)
        self.assertEqual(javascript(f3.web, 'window.themeSentinel'), 23)
        self.assertEqual(f3.api_url, original_url)
        self.assertEqual(window.tasks, tasks)
        self.assertEqual(window.polling_engine.get_telemetry()['poll_count'], 0)
        self.assertFalse(window.notification_worker.running)
        self.assertIsNone(f3._demo_process)
        self.assertEqual({p: hashlib.sha256(p.read_bytes()).hexdigest() for p in configs}, configs)
        self.assertTrue((self.directory / 'ui_prefs.json').exists())

    def test_document_start_injection_persists_across_reloads_and_first_frame(self):
        window = self.window
        window.set_theme('dark')
        view = window.unified_workspace.f1_api
        for mode in ('dark', 'light'):
            window.set_theme(mode)
            markup = '<html><head><style>body{margin:0}</style></head><body><script>window.frameStamp="'+mode+'";requestAnimationFrame(()=>window.firstFrameTheme=document.documentElement.dataset.theme)</script></body></html>'
            view.web.load_html(markup, 'http://127.0.0.1/f1/')
            wait(lambda: javascript(view.web, 'Boolean(window.firstFrameTheme && window.frameStamp==="'+mode+'")'))
            self.assertEqual(javascript(view.web, 'window.firstFrameTheme'), mode)

    def test_header_and_settings_controls_stay_synchronized(self):
        window = self.window
        window.theme_button.set_active(True)
        self.assertEqual(window.theme_mode, 'dark')
        window.theme_buttons['light'].set_active(True)
        self.assertEqual(window.theme_mode, 'light')
        self.assertFalse(window.theme_button.get_active())
        self.assertTrue(window.theme_buttons['light'].get_active())

    def test_footer_is_not_auto_selected_but_stays_copyable(self):
        label = self.window.alarm_text
        self.window.switch_to_tab('alarms')
        settle(.1)
        self.assertFalse(label.get_focusable())
        self.assertFalse(label.get_selection_bounds()[0])
        self.assertTrue(label.get_selectable())
        label.select_region(0, -1)
        self.assertTrue(label.get_selection_bounds()[0])
        self.assertEqual(label.get_tooltip_text(), label.get_text())

    def test_f2_is_the_only_selected_nav_and_restores_f1_on_close(self):
        window = self.window
        web = window.unified_workspace.f1_api.web
        wait(lambda: javascript(web, 'Boolean(window.F1)'))
        window.switch_to_tab('tasks')
        wait(lambda: javascript(web, 'document.getElementById("modalOverlay").open'))
        self.assertEqual([name for name, button in window.nav_btns.items() if button.get_active()], ['tasks'])
        javascript(web, '(window.F1.setMode("monitoring"),true)')
        wait(lambda: not window.nav_btns['tasks'].get_active())
        self.assertEqual([name for name, button in window.nav_btns.items() if button.get_active()], ['overview'])
        window.switch_to_tab('alarms')
        self.assertEqual([name for name, button in window.nav_btns.items() if button.get_active()], ['alarms'])

    def test_chrome_resizes_after_mapping_and_footer_stays_thin(self):
        window = self.window
        for mode in ('light', 'dark'):
            window.set_theme(mode)
            for width, height in ((1024, 600), (1360, 768), (1920, 1080)):
                window.set_default_size(width, height)
                wait(lambda: (window.get_width(), window.get_height()) == (width, height))
                self.assertLessEqual(window.footer.get_allocated_height(), 32)
                self.assertLessEqual(window.header_box.get_allocated_height(), 56)
                self.assertIs(window.navigation.get_parent(), window.header_box)

    def test_native_component_css_parses_in_both_themes(self):
        from theme_tokens import compile_native_css
        directory = Path(app.__file__).parent
        sources = [app.CSS_DATA] + [(directory / name).read_bytes() for name in
                                   ('style.css', 'f1_style.css', 'f2_style.css', 'workspace_style.css')]
        for mode in ('light', 'dark'):
            for source in sources:
                errors = []
                provider = Gtk.CssProvider()
                provider.connect('parsing-error', lambda _, section, error: errors.append(str(error)))
                provider.load_from_data(compile_native_css(mode, source))
                self.assertEqual(errors, [], (mode, errors))

    def test_compact_catalog_shows_nine_rows_and_quiet_unknown_with_full_type(self):
        from wincc_catalog_fixture import write_catalog
        window = self.window
        window.scanned_tags = app.scan_wincc_tags(write_catalog(self.directory / 'catalog.txt'))
        window.render_dynamic_overview()
        window.set_default_size(1024, 600)
        web = window.unified_workspace.f1_api.web
        wait(lambda: javascript(web, 'document.querySelectorAll(".table-row").length') == 457)
        settle(.2)
        geometry = javascript(web, '''(()=>{const box=document.getElementById('tableViewport').getBoundingClientRect();
          const row=document.querySelector('.table-row'), type=row.querySelector('.cell-type'), status=row.querySelector('.cell-status');
          return {rows:[...document.querySelectorAll('.table-row')].filter(r=>{const b=r.getBoundingClientRect();return b.top>=box.top&&b.bottom<=box.bottom}).length,
            rowHeight:row.getBoundingClientRect().height, typeFits:type.scrollWidth<=type.clientWidth,
            typeTitle:type.title, statusBorder:getComputedStyle(status).borderTopWidth,
            scroll:document.documentElement.scrollWidth, width:innerWidth};})()''')
        self.assertGreaterEqual(geometry['rows'], 9, geometry)
        self.assertTrue(36 <= geometry['rowHeight'] <= 40, geometry)
        self.assertTrue(geometry['typeFits'], geometry)
        self.assertEqual(geometry['typeTitle'], 'Binary Tag')
        self.assertEqual(geometry['statusBorder'], '0px')
        self.assertLessEqual(geometry['scroll'], geometry['width'])

    def test_standard_action_variants_have_the_same_height(self):
        window = self.window
        box = Gtk.Box(spacing=8, valign=Gtk.Align.START)
        controls = []
        for variant in ('primary', 'secondary', 'ghost', 'danger'):
            button = Gtk.Button(label='ทดสอบ', valign=Gtk.Align.START)
            button.add_css_class('button-' + variant)
            box.append(button)
            controls.append(button)
        window.stack.add_named(box, 'component-test')
        window.stack.set_visible_child_name('component-test')
        settle(.1)
        self.assertEqual([button.get_allocated_height() for button in controls], [34] * 4)
        self.assertIs(window.get_titlebar(), window.chrome_handle)


if __name__ == '__main__':
    unittest.main()
