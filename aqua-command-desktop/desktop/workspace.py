#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""GTK Tag overview with contextual Inspector and Task dialogs."""

import re

import gi
gi.require_version('Gtk', '4.0')
from gi.repository import Gtk, Gdk, GLib, Pango

try:
    from .opcua_store import Quality
except ImportError:
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

try:
    from .f1_api_view import F1ApiView
except ImportError:
    try:
        from f1_api_view import F1ApiView
    except ImportError:
        F1ApiView = None

# Clean Data Type Mapping
DATA_TYPE_MAPPING = {
    "Binary Tag": "Bool",
    "Floating-point number 32-bit IEEE 754": "Float",
    "Floating-point number 64-bit IEEE 754": "Double",
    "Unsigned 16-bit value": "Word",
    "Signed 16-bit value": "Int",
    "Unsigned 32-bit value": "DWord",
    "Signed 32-bit value": "DInt",
    "Boolean": "Bool",
    "Float": "Float",
    "Double": "Double",
    "Integer": "Int",
    "Word": "Word",
    "DWord": "DWord",
    "String": "String",
    "Int": "Int",
    "Bool": "Bool"
}

def format_data_type(raw_type):
    return DATA_TYPE_MAPPING.get(raw_type, raw_type or "Real")

# Group Display Metadata (Catalog-Driven & Factual)
GROUP_METADATA = {
    "All": ("ทุกกลุ่มอุปกรณ์ (All Groups)", "รวมสัญญาณจากแคตตาล็อก WinCC"),
    "High_VSD": ("ปั๊มน้ำแรงดันสูง VSD", "ระบบสูบน้ำหลักปรับความเร็วรอบอัตโนมัติ"),
    "High_Valve": ("วาล์วท่อส่งแรงดันสูง", "วาล์วควบคุมการจ่ายน้ำแรงดันสูง"),
    "High1_PT1PT": ("เซนเซอร์วัดแรงดัน PT", "เพรชเชอร์ทรานสมิตเตอร์วัดแรงดันน้ำ"),
    "High_Analog": ("สัญญาณอนาล็อกแรงดันสูง", "เซนเซอร์วัดสัญญาณอนาล็อกทางวิศวกรรม"),
    "High_DPM": ("ดิจิทัลเพาเวอร์มิเตอร์ DPM", "ระบบวัดกำลังไฟฟ้าและพลังงาน"),
    "High1_Sound": ("ระบบตรวจวัดเสียงและความสั่น", "ระบบตรวจสอบความผิดปกติทางกล"),
    "High1_Totalize_Flow": ("มาตรวัดปริมาตรน้ำสะสม", "มิเตอร์วัดปริมาตรน้ำและอัตราการไหล"),
    "Temp_High_Alarm": ("สัญญาณเตือนอุณหภูมิสูง", "ระบบเฝ้าระวังอุณหภูมิปั๊มและมอเตอร์"),
    "Timer_Of_Start_Second_CTM": ("ตัวจับเวลาสตาร์ทปั๊ม", "ระบบกำหนดลำดับเวลาสตาร์ทเครื่องสูบ"),
    "Default": ("ค่าเริ่มต้นระบบ (Default)", "สัญญาณระบบพื้นฐานที่ยังไม่ได้จัดกลุ่ม")
}

# Task Cycle Options
CYCLE_OPTIONS = [
    (1, "1 วินาที (High Priority)"),
    (5, "5 วินาที (มาตรฐาน WinCC V8.1)"),
    (10, "10 วินาที (General Monitoring)"),
    (30, "30 วินาที (Slow Sampling)"),
    (60, "60 วินาที")
]


# One set of widths for both headings and data rows.
CATALOG_COLUMNS = (
    ('เลือก', 36, False),
    ('ชื่อ Tag / ที่อยู่ PLC', 138, True),
    ('กลุ่มอุปกรณ์', 110, False),
    ('ชนิดข้อมูล', 78, False),
    ('สถานะตรวจวัด', 152, False),
    ('Task ที่ผูก', 122, True),
)


ASSIGNED_COLUMNS = (
    ('เลือก', 36, False),
    ('ชื่อ Tag', 136, True),
    ('กลุ่มอุปกรณ์', 110, False),
    ('ชนิดข้อมูล', 84, False),
)


class AquaUnifiedWorkspaceView:
    """Shares one Tag catalog between monitoring and Task management."""

    def __init__(self, owner, root_box):
        self.owner = owner
        self.root_box = root_box

        # State Variables
        self.current_workspace_mode = 'monitoring'  # 'monitoring' (F1) or 'task_manager' (F2)
        self.selected_group_key = "All"
        self.search_query = ""
        self.selected_catalog_tags = set()  # set of tag names selected in library
        self.has_unsaved_changes = False
        self.selected_task_index = getattr(self.owner, 'current_task_idx', 0)
        self._task_draft = None
        self._new_task = False
        self._pending_close = None
        self._undo_add = None
        self._toast_timeout = None
        self._observation_tick = None
        self._range_anchor = None
        self._range_requested = False
        self._syncing_checks = False
        self._rendered_catalog = ()
        self.catalog_rows = {}
        self.inspector_dialog = None
        self.task_dialog = None
        self.bulk_dialog = None

        self.catalog_tags_cache = []
        self.group_counts = {}
        self.currently_filtered_tags = []
        self.selected_inspector_tag = None

        # Widget references
        self.group_list_items = {}
        self.catalog_checkboxes = {}
        self.selected_assigned_tags = set()
        self.assigned_checkboxes = {}
        self.assigned_rows = {}
        self._syncing_assigned_checks = False
        self.task_selector_updating = False

        # Build UI
        self.build_ui()

    # =========================================================================
    # ROOT UI CONSTRUCTION
    # =========================================================================

    def build_ui(self):
        self.root_box.add_css_class('tag-overview')
        self.build_top_header()

        self.main_hpaned = Gtk.Paned(orientation=Gtk.Orientation.HORIZONTAL)
        self.main_hpaned.set_hexpand(True)
        self.main_hpaned.set_vexpand(True)
        self.main_hpaned.set_resize_start_child(False)
        self.main_hpaned.set_shrink_end_child(False)
        self.main_hpaned.set_position(262)
        self.root_box.append(self.main_hpaned)

        self.left_col = self.build_left_group_explorer()
        self.left_col.set_size_request(206, -1)
        self.main_hpaned.set_start_child(self.left_col)
        self.center_col = self.build_center_tag_catalog()
        self.main_hpaned.set_end_child(self.center_col)

        # Keep the existing editor and engineering details, hosted in dialogs.
        self.inspector_view = self.build_inspector_view()
        self.task_config_view = self.build_task_config_view()
        self.sync_catalog_data()
        self.refresh_group_explorer()
        self.render_catalog_table()
        self.load_current_task_to_ui()

        # Modernized F1 WebKit Presentation
        if F1ApiView is not None:
            try:
                self.f1_api = F1ApiView(self.owner)
                self.root_box.append(self.f1_api.root_widget)
                self.main_hpaned.set_visible(False)
                self.top_box.set_visible(False)
            except Exception as e:
                import sys
                print(f"[AquaUnifiedWorkspaceView] F1ApiView fallback: {e}", file=sys.stderr)
                self.f1_api = None
        else:
            self.f1_api = None

        keys = Gtk.EventControllerKey()
        keys.connect('key-pressed', self._on_catalog_key)
        self.root_box.add_controller(keys)
        self.root_box.connect('map', self._on_map)
        self.root_box.connect('un' + 'map', self._on_view_hidden)

    def _on_map(self, *_args):
        if self._observation_tick is None:
            self._observation_tick = GLib.timeout_add_seconds(1, self._refresh_observations)
        self._refresh_observations()

    def _on_view_hidden(self, *_args):
        if self._observation_tick is not None:
            GLib.source_remove(self._observation_tick)
            self._observation_tick = None
        if self._toast_timeout is not None:
            GLib.source_remove(self._toast_timeout)
            self._hide_toast()

    def _refresh_observations(self):
        if getattr(self, 'f1_api', None):
            self.f1_api.refresh_observations()
            return GLib.SOURCE_CONTINUE
        for row in self.catalog_rows.values():
            if row.get_child_visible():
                self._update_observation_cell(row)
        if self.inspector_dialog is not None and self.inspector_dialog.get_visible():
            self._update_inspector_observation()
        return GLib.SOURCE_CONTINUE

    def update_layout_proportions(self, width=1366):
        self.main_hpaned.set_position(max(206, min(300, int(width * .18))))


    def build_top_header(self):
        self.top_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
        self.top_box.add_css_class('workspace-top-ribbon')
        self.root_box.append(self.top_box)

        # Workspace Brand Title
        brand_vbox = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=1)
        self.top_box.append(brand_vbox)

        lbl_brand = Gtk.Label(label="ภาพรวม Tag")
        lbl_brand.add_css_class('workspace-brand-title')
        lbl_brand.set_xalign(0.0)
        brand_vbox.append(lbl_brand)

        lbl_sub = Gtk.Label(label="ค้นหา Tag ดูค่าที่อ่านได้ และจัดการงานเฝ้าระวัง")
        lbl_sub.add_css_class('workspace-subtitle')
        lbl_sub.set_xalign(0.0)
        brand_vbox.append(lbl_sub)

        # Separator
        sep1 = Gtk.Separator(orientation=Gtk.Orientation.VERTICAL)
        sep1.set_margin_start(4)
        sep1.set_margin_end(4)
        self.top_box.append(sep1)

        # Scan Toolbar Controls
        self.btn_scan_once = Gtk.Button(label="รีเฟรชคลัง Tag")
        self.btn_scan_once.add_css_class('f2-btn-scan-once')
        self.btn_scan_once.connect('clicked', lambda _: self.owner.trigger_rescan())
        self.top_box.append(self.btn_scan_once)

        is_running = getattr(self.owner, 'auto_scan_active', False)
        self.btn_auto_scan = Gtk.Button(label="หยุดรีเฟรชอัตโนมัติ" if is_running else "รีเฟรชอัตโนมัติ")
        self.btn_auto_scan.add_css_class('f2-btn-auto-stop' if is_running else 'f2-btn-auto-start')
        self.btn_auto_scan.connect('clicked', self.on_toggle_auto_scan)
        self.top_box.append(self.btn_auto_scan)
        self.owner.btn_auto_scan = self.btn_auto_scan

        lbl_int = Gtk.Label(label="รอบ: 5s")
        lbl_int.add_css_class('f2-scan-label')
        self.top_box.append(lbl_int)

        self.badge_scan_status = Gtk.Label(label="ปิดอยู่")
        self.badge_scan_status.add_css_class('f2-scan-status-idle')
        self.top_box.append(self.badge_scan_status)

        spacer = Gtk.Box()
        spacer.set_hexpand(True)
        self.top_box.append(spacer)

        self.btn_top_f2 = Gtk.Button(label='งานเฝ้าระวัง')
        self.btn_top_f2.add_css_class('workspace-mode-btn-active')
        self.btn_top_f2.connect('clicked', lambda _: self.open_task_dialog())
        self.top_box.append(self.btn_top_f2)

    # =========================================================================
    # 2. COLUMN 1: SHARED EQUIPMENT GROUP EXPLORER (LEFT ~20%)
    # =========================================================================

    def build_left_group_explorer(self):
        left_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        left_box.add_css_class('workspace-col-panel')

        # Header
        hdr = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        hdr.add_css_class('f1-panel-header')
        left_box.append(hdr)

        lbl_title = Gtk.Label(label="กลุ่มอุปกรณ์")
        lbl_title.add_css_class('f1-panel-title')
        lbl_title.set_hexpand(True)
        lbl_title.set_xalign(0.0)
        hdr.append(lbl_title)

        self.lbl_group_count_badge = Gtk.Label(label="")
        self.lbl_group_count_badge.add_css_class('f1-badge-accent')
        hdr.append(self.lbl_group_count_badge)

        # Scrolled List
        self.group_scroll = Gtk.ScrolledWindow()
        self.group_scroll.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        self.group_scroll.set_hexpand(True)
        self.group_scroll.set_vexpand(True)
        self.group_scroll.add_css_class('f1-group-scroll')
        left_box.append(self.group_scroll)

        self.group_listbox = Gtk.ListBox()
        self.group_listbox.set_selection_mode(Gtk.SelectionMode.SINGLE)
        self.group_listbox.add_css_class('f1-group-list')
        self.group_listbox.connect('row-selected', self.on_group_row_selected)
        self.group_scroll.set_child(self.group_listbox)

        return left_box

    def refresh_group_explorer(self):
        """Populates Equipment Groups list from dynamic catalog tags"""
        while self.group_listbox.get_first_child():
            self.group_listbox.remove(self.group_listbox.get_first_child())

        groups_in_cat = sorted(list(set(t['group'] for t in self.catalog_tags_cache)))
        self.lbl_group_count_badge.set_text(f"{len(groups_in_cat)} กลุ่ม")

        display_groups = ["All"] + [g for g in groups_in_cat if g != 'Default']
        if 'Default' in groups_in_cat:
            display_groups.append('Default')

        self.group_row_widgets = {}
        target_row = None

        for g_key in display_groups:
            meta = GROUP_METADATA.get(g_key, (g_key, "กลุ่มอุปกรณ์ SCADA"))
            count = self.group_counts.get(g_key, 0)

            row = Gtk.ListBoxRow()
            row._group_key = g_key
            row_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
            row_box.set_margin_start(6)
            row_box.set_margin_end(6)
            row_box.set_margin_top(4)
            row_box.set_margin_bottom(4)
            row.set_child(row_box)

            vbox = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=1)
            vbox.set_hexpand(True)
            row_box.append(vbox)

            title = 'ทุกกลุ่มอุปกรณ์' if g_key == 'All' else meta[0]
            lbl_gname = Gtk.Label(label=title, wrap=True, lines=2)
            lbl_gname.set_wrap_mode(Pango.WrapMode.WORD_CHAR)
            lbl_gname.set_xalign(0.0)
            lbl_gname.add_css_class('f2-group-name')
            lbl_gname.set_ellipsize(Pango.EllipsizeMode.END)
            vbox.append(lbl_gname)

            lbl_gdesc = Gtk.Label(label=meta[1])
            lbl_gdesc.set_xalign(0.0)
            lbl_gdesc.add_css_class('f2-group-desc')
            lbl_gdesc.set_ellipsize(Pango.EllipsizeMode.END)
            vbox.append(lbl_gdesc)

            row.set_tooltip_text(f"{meta[0]} · {meta[1]}")
            cnt_pill = Gtk.Label(label=str(count), width_chars=3, valign=Gtk.Align.CENTER)
            cnt_pill.add_css_class('f2-group-count')
            row_box.append(cnt_pill)

            self.group_listbox.append(row)
            self.group_row_widgets[g_key] = row
            if g_key == self.selected_group_key:
                target_row = row

        if target_row:
            self.group_listbox.select_row(target_row)

    def on_group_row_selected(self, listbox, row):
        if row and hasattr(row, '_group_key'):
            self.on_select_group(row._group_key)

    def on_select_group(self, group_key):
        self.selected_group_key = group_key
        meta = GROUP_METADATA.get(group_key, (group_key, "ระบบ SCADA"))
        self.lbl_catalog_title.set_text(f"คลัง Tag: {meta[0]}")
        self.lbl_catalog_sub.set_text(meta[1])

        # Filter banner for single-tag group Default
        if group_key == 'Default':
            self.filter_banner_box.set_visible(True)
            self.lbl_filter_banner.set_text("📌 กำลังแสดงเฉพาะกลุ่ม: Default (1 รายการ · WinCC Unassigned Tag)")
        else:
            self.filter_banner_box.set_visible(False)

        self._apply_catalog_filter()

    # =========================================================================
    # 3. COLUMN 2: SHARED SEARCHABLE TAG CATALOG (CENTER ~48%)
    # =========================================================================

    def build_center_tag_catalog(self):
        center_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        center_box.add_css_class('workspace-col-panel')

        # Top Group Summary Header
        summary_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        summary_box.add_css_class('f2-table-header-box')
        center_box.append(summary_box)

        title_vbox = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=1)
        title_vbox.set_hexpand(True)
        summary_box.append(title_vbox)

        self.lbl_catalog_title = Gtk.Label(label="คลัง Tag: ปั๊มน้ำแรงดันสูง VSD")
        self.lbl_catalog_title.add_css_class('f2-catalog-title')
        self.lbl_catalog_title.set_xalign(0.0)
        title_vbox.append(self.lbl_catalog_title)

        self.lbl_catalog_sub = Gtk.Label(label="ระบบสูบน้ำหลักปรับความเร็วรอบอัตโนมัติ")
        self.lbl_catalog_sub.add_css_class('f2-catalog-subtitle')
        self.lbl_catalog_sub.set_xalign(0.0)
        title_vbox.append(self.lbl_catalog_sub)

        # Search Bar
        search_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        center_box.append(search_box)

        self.entry_search = Gtk.SearchEntry()
        self.entry_search.set_hexpand(True)
        self.entry_search.add_css_class('workspace-search')
        self.entry_search.set_placeholder_text("ค้นหาชื่อ Tag กลุ่ม หรือที่อยู่ PLC  ·  /")
        self.entry_search.connect('search-changed', self.on_search_changed)
        search_box.append(self.entry_search)

        # Active Filter Banner
        self.filter_banner_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        self.filter_banner_box.add_css_class('workspace-filter-banner')
        self.filter_banner_box.set_visible(False)
        center_box.append(self.filter_banner_box)

        self.lbl_filter_banner = Gtk.Label(label="")
        self.lbl_filter_banner.set_xalign(0.0)
        self.lbl_filter_banner.set_hexpand(True)
        self.lbl_filter_banner.add_css_class('f2-filter-label')
        self.filter_banner_box.append(self.lbl_filter_banner)

        btn_clear_f = Gtk.Button(label="แสดงทุกกลุ่ม (All)")
        btn_clear_f.add_css_class('f2-btn-clear-filter')
        btn_clear_f.connect('clicked', lambda _: self.on_select_group("All"))
        self.filter_banner_box.append(btn_clear_f)

        table = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        table.set_vexpand(True)
        center_box.append(table)

        headings = [self._catalog_label(caption, 'f2-col-header') for caption, _, _ in CATALOG_COLUMNS]
        col_hdr = self._catalog_columns(headings)
        col_hdr.add_css_class('f2-table-header-row')
        table.append(col_hdr)

        tbl_scroll = Gtk.ScrolledWindow()
        tbl_scroll.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        tbl_scroll.set_vexpand(True)
        tbl_scroll.add_css_class('workspace-table-scroll')
        table.append(tbl_scroll)

        self.catalog_listbox = Gtk.ListBox()
        self.catalog_listbox.set_selection_mode(Gtk.SelectionMode.SINGLE)
        self.catalog_listbox.add_css_class('f2-table-list')
        self.catalog_listbox.set_activate_on_single_click(False)
        self.catalog_listbox.set_filter_func(self._row_matches)
        self.catalog_listbox.connect('row-activated', self._on_row_activated)
        clicks = Gtk.GestureClick(button=Gdk.BUTTON_PRIMARY, propagation_phase=Gtk.PropagationPhase.CAPTURE)
        clicks.connect('pressed', self._on_catalog_row_pressed)
        clicks.connect('released', self._on_catalog_row_released)
        clicks.connect('stopped', self._clear_catalog_press)
        self.catalog_listbox.add_controller(clicks)
        keys = Gtk.EventControllerKey(propagation_phase=Gtk.PropagationPhase.CAPTURE)
        keys.connect('key-pressed', self._on_catalog_selection_key)
        self.catalog_listbox.add_controller(keys)
        tbl_scroll.set_child(self.catalog_listbox)

        self.dock_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        self.dock_box.add_css_class('workspace-dock-bar')
        center_box.insert_child_after(self.dock_box, self.filter_banner_box)

        self.lbl_sel_badge = Gtk.Label(xalign=0, hexpand=True, ellipsize=Pango.EllipsizeMode.END)
        self.lbl_sel_badge.add_css_class('tag-flow-hint')
        self.dock_box.append(self.lbl_sel_badge)

        self.btn_catalog_details = Gtk.Button(label='ดูรายละเอียด', sensitive=False)
        self.btn_catalog_details.set_tooltip_text('เลือกแถวแล้วกดปุ่ม หรือดับเบิลคลิกที่แถว')
        self.btn_catalog_details.connect('clicked', self._open_selected_catalog_row)
        self.dock_box.append(self.btn_catalog_details)
        self.catalog_listbox.connect('row-selected', self._update_catalog_details)

        self.btn_clear_sel = Gtk.Button(label='ล้างการเลือก')
        self.btn_clear_sel.add_css_class('f2-btn-clear-selection')
        self.btn_clear_sel.connect('clicked', lambda _: self.on_clear_selection())
        self.dock_box.append(self.btn_clear_sel)

        self.btn_add_selected = Gtk.Button(label='เพิ่มเข้า Task')
        self.btn_add_selected.add_css_class('tag-flow-primary')
        self.btn_add_selected.connect('clicked', lambda _: self.on_add_selected_to_task())
        self.dock_box.append(self.btn_add_selected)

        self.toast = Gtk.Revealer()
        self.toast.set_transition_type(Gtk.RevealerTransitionType.SLIDE_UP)
        self.toast.set_transition_duration(160 if Gtk.Settings.get_default().get_property('gtk-enable-animations') else 0)
        center_box.append(self.toast)
        toast_body = Gtk.Box(spacing=12)
        toast_body.add_css_class('tag-overview-toast')
        self.toast.set_child(toast_body)
        self.toast_label = Gtk.Label(xalign=0, hexpand=True, wrap=True)
        toast_body.append(self.toast_label)
        self.undo_button = Gtk.Button(label='ย้อนกลับ')
        self.undo_button.connect('clicked', self._undo_last_add)
        toast_body.append(self.undo_button)
        return center_box

    def _row_matches(self, row, *_):
        group = row._tag_data.get('group', 'Default')
        return (self.selected_group_key == 'All' or group == self.selected_group_key) and self.search_query in row._search_text

    def on_search_changed(self, entry):
        self.search_query = entry.get_text().strip().lower()
        self._apply_catalog_filter()

    def _apply_catalog_filter(self):
        self._range_anchor = None
        self.catalog_listbox.invalidate_filter()
        self.currently_filtered_tags = [
            row._tag_data for row in self.catalog_rows.values() if self._row_matches(row)
        ]
        for row in self.catalog_rows.values():
            if not self._row_matches(row):
                continue
            self._update_observation_cell(row)
            name = row._tag_data.get('name', '')
            match = re.search(re.escape(self.search_query), name, re.IGNORECASE) if self.search_query else None
            if match:
                start, end = match.span()
                row._name_label.set_markup(
                    GLib.markup_escape_text(name[:start]) +
                    '<span foreground="#96c9ff" weight="bold">' +
                    GLib.markup_escape_text(name[start:end]) + '</span>' +
                    GLib.markup_escape_text(name[end:])
                )
            else:
                row._name_label.set_text(name)
        self.update_selection_badges()

    def _present_observation(self, name):
        store = getattr(self.owner, 'opcua_store', None)
        obs = store.get_observation(name) if store else None
        if obs is None or obs.quality == Quality.NOT_OBSERVED:
            return '？ ยังไม่ได้สังเกต', 'badge-standby', '—', '—', None
        data = obs.to_presentation(stale_threshold_sec=60)
        if obs.quality in (Quality.BAD, Quality.DISCONNECTED):
            status = '✕ คุณภาพเสีย' if obs.quality == Quality.BAD else '✕ ไม่ตอบ'
            badge = 'badge-nope'
        elif obs.quality == Quality.STALE or obs.is_stale(60):
            status, badge = '◔ ข้อมูลเก่า', 'badge-sensor'
        elif obs.quality == Quality.GOOD:
            status, badge = '✓ ปกติ', 'badge-active'
        else:
            status, badge = '⚠ คุณภาพไม่แน่นอน', 'badge-sensor'
        return status, badge, data['display_val'], data['timestamp_str'], obs

    @staticmethod
    def _catalog_label(text, css=None):
        label = Gtk.Label(label=text, xalign=0, ellipsize=Pango.EllipsizeMode.END)
        # Keep long content from changing the natural width of a single row.
        label.set_max_width_chars(1)
        if css:
            label.add_css_class(css)
        return label

    @staticmethod
    def _catalog_columns(cells, columns=CATALOG_COLUMNS):
        box = Gtk.Box(spacing=8)
        for cell, (_, width, expand) in zip(cells, columns):
            cell.set_size_request(width, -1)
            cell.set_hexpand(expand)
            box.append(cell)
        return box

    def _make_catalog_row(self, tag):
        name = tag.get('name', '')
        row = Gtk.ListBoxRow()
        row.set_cursor_from_name('pointer')
        row._tag_data = tag
        row._search_text = ' '.join(str(tag.get(key, '')) for key in ('name', 'group', 'type', 'addr', 'conn')).lower()
        checkbox = Gtk.CheckButton(valign=Gtk.Align.CENTER)
        checkbox.set_size_request(-1, 36)
        checkbox.set_tooltip_text(f'เลือก {name} · Shift เพื่อเลือกช่วง')
        gesture = Gtk.GestureClick.new()
        gesture.set_propagation_phase(Gtk.PropagationPhase.CAPTURE)
        gesture.connect('pressed', self._on_checkbox_pressed)
        checkbox.add_controller(gesture)
        checkbox.connect('toggled', self.make_chk_callback(name))
        self.catalog_checkboxes[name] = checkbox
        identity = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2, valign=Gtk.Align.CENTER)
        row._name_label = self._catalog_label(name, 'f2-tag-name-label')
        identity.append(row._name_label)
        address = tag.get('addr') or '—'
        identity.append(self._catalog_label(address, 'tag-cell-secondary'))
        identity.set_tooltip_text(f'{name} · {address}')

        group = tag.get('group', 'Default')
        group_label = self._catalog_label(group, 'f2-tag-group-label')
        group_label.set_tooltip_text(group)
        data_type = format_data_type(tag.get('type'))
        type_label = self._catalog_label(data_type, 'tag-cell-secondary')
        type_label.set_tooltip_text(data_type)

        observation = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2, valign=Gtk.Align.CENTER)
        row._quality_label = self._catalog_label('')
        row._value_label = self._catalog_label('', 'tag-cell-secondary')
        observation.append(row._quality_label)
        observation.append(row._value_label)

        row._task_label = self._catalog_label('—', 'tag-cell-secondary')
        box = self._catalog_columns((
            checkbox, identity, group_label, type_label, observation, row._task_label,
        ))
        box.set_margin_start(6)
        box.set_margin_end(6)
        box.set_size_request(-1, 48)
        row.set_child(box)
        return row

    def render_catalog_table(self):
        """Build rows once per catalog change and refresh observation/Task cells."""
        if self._rendered_catalog != tuple(self.catalog_tags_cache):
            while self.catalog_listbox.get_first_child():
                self.catalog_listbox.remove(self.catalog_listbox.get_first_child())
            self.catalog_rows.clear()
            self.catalog_checkboxes.clear()
            self._rendered_catalog = tuple(self.catalog_tags_cache)
            for tag in self.catalog_tags_cache:
                row = self._make_catalog_row(tag)
                self.catalog_rows[tag.get('name', '')] = row
                self.catalog_listbox.append(row)
            self.selected_catalog_tags.intersection_update(self.catalog_rows)
            self._apply_catalog_filter()

        tasks = getattr(self.owner, 'tasks', [])
        assigned = {}
        for task in tasks:
            for name in task.get('tags', []):
                assigned.setdefault(name, []).append(task.get('name') or task.get('id', 'Task'))
        for name, row in self.catalog_rows.items():
            self._update_observation_cell(row)
            task_names = ', '.join(assigned.get(name, []))
            row._task_label.set_text(task_names or '—')
            row._task_label.set_tooltip_text(task_names or None)
        self.update_selection_badges()

    def _update_observation_cell(self, row):
        status, badge, value, stamp, _ = self._present_observation(row._tag_data.get('name', ''))
        if row._quality_label.get_text() != status:
            row._quality_label.set_text(status)
            row._quality_label.set_css_classes([badge, 'tag-state'])
        label = value if stamp == '—' else f'{value} · {stamp}'
        if row._value_label.get_text() != label:
            row._value_label.set_text(label)
            row._value_label.set_tooltip_text(label if label != '—' else None)

    def _on_checkbox_pressed(self, gesture, *_):
        self._range_requested = bool(gesture.get_current_event_state() & Gdk.ModifierType.SHIFT_MASK)

    def _catalog_row_at(self, x, y):
        picked = self.catalog_listbox.pick(x, y, Gtk.PickFlags.DEFAULT)
        if picked is None:
            return None
        row = picked if isinstance(picked, Gtk.ListBoxRow) else picked.get_ancestor(Gtk.ListBoxRow)
        if row is not None and row.get_parent() == self.catalog_listbox:
            tag_data = getattr(row, '_tag_data', None)
            if tag_data and tag_data.get('name') in self.catalog_checkboxes:
                checkbox = self.catalog_checkboxes[tag_data['name']]
                if picked != checkbox and not picked.is_ancestor(checkbox):
                    return row
        return None

    def _on_catalog_row_pressed(self, gesture, n_press, x, y):
        gesture._catalog_press_row = self._catalog_row_at(x, y) if n_press == 1 else None
        gesture._catalog_press_state = gesture.get_current_event_state()

    def _clear_catalog_press(self, gesture):
        gesture._catalog_press_row = None

    def _on_catalog_row_released(self, gesture, n_press, x, y):
        row = getattr(gesture, '_catalog_press_row', None)
        self._clear_catalog_press(gesture)
        if n_press == 1 and row is not None and row == self._catalog_row_at(x, y):
            self._toggle_catalog_row(row, gesture._catalog_press_state)

    def _on_catalog_selection_key(self, controller, key, _code, state):
        if key != Gdk.KEY_space or state & (Gdk.ModifierType.CONTROL_MASK | Gdk.ModifierType.ALT_MASK):
            return False
        focus = self.catalog_listbox.get_root().get_focus()
        if isinstance(focus, Gtk.ListBoxRow) and focus.get_parent() == self.catalog_listbox:
            self._toggle_catalog_row(focus, state)
            return True
        self._range_requested = False
        return False

    def _toggle_catalog_row(self, row, state):
        checkbox = self.catalog_checkboxes[row._tag_data['name']]
        self._range_requested = bool(state & Gdk.ModifierType.SHIFT_MASK)
        checkbox.set_active(not checkbox.get_active())

    def make_chk_callback(self, tag_name):
        def cb(button):
            if self._syncing_checks:
                return
            names = [tag.get('name') for tag in self.currently_filtered_tags]
            selected = [tag_name]
            if self._range_requested and self._range_anchor in names and tag_name in names:
                a, b = sorted((names.index(self._range_anchor), names.index(tag_name)))
                selected = names[a:b + 1]
            self._range_requested = False
            self._range_anchor = tag_name
            if button.get_active():
                self.selected_catalog_tags.update(selected)
            else:
                self.selected_catalog_tags.difference_update(selected)
            self.update_selection_badges()
        return cb

    def update_selection_badges(self):
        self._syncing_checks = True
        try:
            for name, checkbox in self.catalog_checkboxes.items():
                active = name in self.selected_catalog_tags
                checkbox.set_active(active)
                row = self.catalog_rows[name]
                if active:
                    row.add_css_class('tag-row-checked')
                else:
                    row.remove_css_class('tag-row-checked')
        finally:
            self._syncing_checks = False
        count = len(self.selected_catalog_tags)
        shown = sum(tag['name'] in self.selected_catalog_tags for tag in self.currently_filtered_tags)
        hidden = count - shown
        if count:
            message = f'เลือกแล้ว {count} Tag'
            if hidden:
                message += f' · อยู่นอกผลค้นหาหรือกลุ่มนี้ {hidden}'
        else:
            message = 'คลิกแถวเพื่อเลือก Tag · Shift + คลิกเพื่อเลือกช่วง'
        self.lbl_sel_badge.set_text(message)
        tasks = getattr(self.owner, 'tasks', [])
        button_text = 'เพิ่มเข้า Task'
        if count:
            button_text = f'เพิ่ม {count} Tag เข้า Task' if tasks else 'สร้าง Task ก่อน'
        self.btn_add_selected.set_label(button_text)
        self.btn_add_selected.set_sensitive(bool(count))
        self.btn_clear_sel.set_visible(bool(count))
        self._update_catalog_details(self.catalog_listbox, self.catalog_listbox.get_selected_row())

    def on_clear_selection(self):
        self.selected_catalog_tags.clear()
        self._range_anchor = None
        self.update_selection_badges()

    def _update_catalog_details(self, _listbox, row):
        self.btn_catalog_details.set_sensitive(row is not None and self._row_matches(row))

    def _open_selected_catalog_row(self, _button):
        row = self.catalog_listbox.get_selected_row()
        if row is not None and self._row_matches(row):
            self._on_row_activated(self.catalog_listbox, row)

    def _on_row_activated(self, listbox, row):
        self.selected_inspector_tag = row._tag_data
        self.open_tag_dialog()

    def _on_catalog_key(self, controller, key, _code, state):
        focus = self.owner.get_focus() if isinstance(self.owner, Gtk.Window) else None
        if key == Gdk.KEY_slash and not (state & (Gdk.ModifierType.CONTROL_MASK | Gdk.ModifierType.ALT_MASK)):
            if not isinstance(focus, Gtk.Editable):
                self.entry_search.grab_focus()
                return True
        if key == Gdk.KEY_Down and isinstance(focus, Gtk.Editable) and self.currently_filtered_tags:
            row = self.catalog_rows[self.currently_filtered_tags[0]['name']]
            self.catalog_listbox.select_row(row)
            row.grab_focus()
            return True
        return False

    def _make_popup(self, title, content, width, height, close_handler=None):
        popup = Gtk.Window(title=title, modal=True, default_width=width, default_height=height)
        if isinstance(self.owner, Gtk.Window):
            popup.set_transient_for(self.owner)
            popup.set_destroy_with_parent(True)
        popup.add_css_class('tag-overview-popup')
        popup.set_child(content)
        popup.set_hide_on_close(True)
        if close_handler is not None:
            popup.connect('close-request', close_handler)

        keys = Gtk.EventControllerKey()
        def on_key(controller, key, _code, state):
            if key == Gdk.KEY_Escape:
                popup.close()
                return True
            return False
        keys.connect('key-pressed', on_key)
        popup.add_controller(keys)
        return popup

    def open_tag_dialog(self):
        if self.selected_inspector_tag is None:
            return
        if self.inspector_dialog is None:
            self.inspector_dialog = self._make_popup('รายละเอียด Tag', self.inspector_view, 620, 400)
            self.inspector_dialog.connect('notify::visible', self._restore_tag_focus)
        self._populate_task_picker(self.inspector_task_selector)
        self.inspector_action_error.set_visible(False)
        self.inspector_technical.set_expanded(False)
        self.render_inspector_tag(self.selected_inspector_tag)
        self.inspector_dialog.present()
        self.btn_close_inspector.grab_focus()

    def _restore_tag_focus(self, popup, _):
        if not popup.get_visible() and self.selected_inspector_tag:
            row = self.catalog_rows.get(self.selected_inspector_tag.get('name'))
            if row is not None:
                row.grab_focus()

    def open_task_dialog(self):
        if getattr(self, 'f1_api', None) and not getattr(self.f1_api, 'closed', False):
            self.current_workspace_mode = 'task_manager'
            self.f1_api.open_task_dialog()
            return

        if self.task_dialog is None:
            width, height = 1000, 650
            if isinstance(self.owner, Gtk.Window):
                width = max(900, min(1180, int(self.owner.get_width() * .86)))
                height = max(540, min(800, int(self.owner.get_height() * .86)))
            self.task_dialog = self._make_popup(
                'งานเฝ้าระวัง', self.task_config_view, width, height, self._on_close_task_dialog
            )
        if not self.task_dialog.get_visible():
            self.load_current_task_to_ui()
        self.current_workspace_mode = 'task_manager'
        self.task_dialog.present()
        self.task_selector_combo.grab_focus()

    def set_workspace_mode(self, mode_name):
        if getattr(self, 'f1_api', None) and not getattr(self.f1_api, 'closed', False):
            self.current_workspace_mode = mode_name
            self.f1_api.set_workspace_mode(mode_name)
            if mode_name == 'task_manager':
                self.f1_api.open_task_dialog()
            return

        if mode_name == 'task_manager':
            self.open_task_dialog()
        else:
            self.current_workspace_mode = 'monitoring'


    # -------------------------------------------------------------------------
    # SUB-VIEW: F1 INSPECTOR (HIGH CONTRAST & STRUCTURED)
    # -------------------------------------------------------------------------

    def build_inspector_view(self):
        panel = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        scrolled = Gtk.ScrolledWindow(vexpand=True)
        scrolled.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        panel.append(scrolled)

        body = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)
        scrolled.set_child(body)
        self.insp_lbl_name = Gtk.Label(xalign=0, selectable=True, wrap=True)
        self.insp_lbl_name.set_wrap_mode(Pango.WrapMode.WORD_CHAR)
        self.insp_lbl_name.add_css_class('tag-dialog-name')
        body.append(self.insp_lbl_name)

        self.insp_lbl_comment = Gtk.Label(xalign=0, wrap=True)
        self.insp_lbl_comment.add_css_class('tag-flow-hint')
        body.append(self.insp_lbl_comment)

        summary = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        summary.add_css_class('workspace-inspector-grid')
        body.append(summary)
        self.insp_grid_values = {}
        summary.append(self._build_inspector_fields((
            ('live_val', 'ค่าล่าสุด'),
            ('quality', 'สถานะการอ่าน'),
            ('last_obs', 'เวลาอ่านล่าสุด'),
            ('source', 'แหล่งข้อมูล'),
        )))
        self.insp_grid_values['live_val'].add_css_class('tag-dialog-reading')

        self.inspector_technical = Gtk.Expander(label='ข้อมูลทางเทคนิค')
        self.inspector_technical.add_css_class('tag-technical-disclosure')
        body.append(self.inspector_technical)
        self.inspector_technical.set_child(self._build_inspector_fields((
            ('group', 'กลุ่มอุปกรณ์'),
            ('type', 'ชนิดข้อมูล'),
            ('conn', 'การเชื่อมต่อ'),
            ('addr', 'ที่อยู่ PLC'),
        )))

        footer = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        footer.add_css_class('tag-dialog-footer')
        panel.append(footer)

        self.inspector_action_error = Gtk.Label(xalign=0, wrap=True, visible=False)
        self.inspector_action_error.add_css_class('badge-nope')
        footer.append(self.inspector_action_error)

        task_row = Gtk.Box(spacing=8)
        footer.append(task_row)
        self.inspector_task_prompt = Gtk.Label(label='Task ปลายทาง', xalign=0, hexpand=True)
        task_row.append(self.inspector_task_prompt)
        self.inspector_task_selector = Gtk.DropDown(hexpand=True)
        self.inspector_task_selector.connect('notify::selected', self._on_inspector_task_selected)
        task_row.append(self.inspector_task_selector)
        self.btn_add_to_cur_task = Gtk.Button(label='เพิ่ม Tag นี้')
        self.btn_add_to_cur_task.add_css_class('tag-flow-primary')
        self.btn_add_to_cur_task.connect('clicked', lambda _: self.on_add_single_tag_to_task())
        task_row.append(self.btn_add_to_cur_task)

        actions = Gtk.Box(spacing=8)
        footer.append(actions)
        self.btn_read_live = Gtk.Button(label='อ่านค่า 1 ครั้ง')
        self.btn_read_live.connect('clicked', lambda _: self.on_read_selected_tag_once())
        actions.append(self.btn_read_live)
        self.btn_open_f6 = Gtk.Button(label='ตั้งค่า OPC UA')
        self.btn_open_f6.connect('clicked', self._open_f6_from_inspector)
        actions.append(self.btn_open_f6)
        actions.append(Gtk.Box(hexpand=True))

        self.btn_close_inspector = Gtk.Button(label='ปิด')
        self.btn_close_inspector.connect('clicked', lambda _: self.inspector_dialog.close())
        actions.append(self.btn_close_inspector)
        return panel

    def _build_inspector_fields(self, fields):
        grid = Gtk.Grid(column_spacing=16, row_spacing=7)
        for row, (key, caption) in enumerate(fields):
            label = Gtk.Label(label=caption, xalign=0)
            label.add_css_class('workspace-inspector-key')
            grid.attach(label, 0, row, 1, 1)
            value = Gtk.Label(label='—', xalign=0, selectable=True, wrap=True, hexpand=True)
            value.set_wrap_mode(Pango.WrapMode.WORD_CHAR)
            value.add_css_class('workspace-inspector-val')
            grid.attach(value, 1, row, 1, 1)
            self.insp_grid_values[key] = value
        return grid

    def render_inspector_tag(self, tag):
        if not tag:
            return
        self._update_inspector_add()

        self.insp_lbl_name.set_text(tag.get('name', 'UNKNOWN'))
        comment = tag.get('comment', '').strip()
        self.insp_lbl_comment.set_text(comment)
        self.insp_lbl_comment.set_visible(bool(comment))

        grp_name = tag.get('group', 'Default')
        group_title = GROUP_METADATA.get(grp_name, (grp_name, ''))[0]
        self.insp_grid_values['group'].set_text(f'{group_title} · {grp_name}' if grp_name != group_title else grp_name)
        self.insp_grid_values['type'].set_text(f"{format_data_type(tag.get('type', 'Real'))} ({tag.get('type', 'Real')})")
        self.insp_grid_values['conn'].set_text(tag.get('conn') or '—')
        self.insp_grid_values['addr'].set_text(tag.get('addr') or '—')

        tag_name = tag.get('name', '')
        mapper = getattr(self.owner, 'opcua_mapper', None)
        reader = getattr(self.owner, 'opcua_reader', None)
        can_read = bool(reader and mapper and mapper.is_allowed(tag_name))
        self.btn_read_live.set_sensitive(can_read)
        self.btn_read_live.set_label('อ่านค่า 1 ครั้ง' if can_read else 'ยังอ่านค่าไม่ได้')
        self.btn_read_live.set_tooltip_text(None if can_read else 'Tag นี้ยังไม่ได้ตั้งค่าให้อ่านผ่าน OPC UA')
        self._update_inspector_observation()

    def _update_inspector_observation(self):
        tag = self.selected_inspector_tag
        if not tag:
            return
        status, badge, value, stamp, obs = self._present_observation(tag.get('name', ''))
        self.insp_grid_values['source'].set_text('OPC UA · ค่าที่โปรแกรมบันทึก' if obs else 'WinCC Export · ข้อมูล Tag')
        quality = self.insp_grid_values['quality']
        quality.set_text(status)
        quality.set_css_classes(['workspace-inspector-val', 'tag-dialog-quality', badge])
        self.insp_grid_values['live_val'].set_text(value)
        self.insp_grid_values['last_obs'].set_text(stamp)

    def _open_f6_from_inspector(self, _button):
        self.inspector_dialog.close()
        self.owner.switch_to_tab('alarms')

    def _on_inspector_task_selected(self, *_args):
        self._update_inspector_add()

    def _update_inspector_add(self):
        if not hasattr(self, 'btn_add_to_cur_task'):
            return
        tasks = getattr(self.owner, 'tasks', [])
        idx = self.inspector_task_selector.get_selected()
        name = (self.selected_inspector_tag or {}).get('name')
        already_assigned = 0 <= idx < len(tasks) and name in tasks[idx].get('tags', [])
        self.inspector_task_prompt.set_hexpand(not tasks)
        self.inspector_task_selector.set_visible(bool(tasks))
        self.inspector_task_prompt.set_text('Task ปลายทาง' if tasks else 'สร้าง Task ก่อนเพิ่ม Tag')
        self.btn_add_to_cur_task.set_label(
            'สร้าง Task' if not tasks else 'อยู่ใน Task นี้แล้ว' if already_assigned else 'เพิ่ม Tag นี้'
        )
        self.btn_add_to_cur_task.set_sensitive(bool(name) and not already_assigned)


    def on_read_selected_tag_once(self):
        """Gate B2: Executes operator-initiated manual single-shot read for selected tag."""
        if not self.selected_inspector_tag:
            return
        tag_name = self.selected_inspector_tag.get('name')
        if not tag_name:
            return

        reader = getattr(self.owner, 'opcua_reader', None)
        cfg = getattr(self.owner, 'opcua_config', {})
        url = cfg.get('endpoint_url', 'opc.tcp://127.0.0.1:48460/freeopcua/b2_live_pipeline/')
        sec_policy = cfg.get('security_policy', 'None')
        auth_mode = cfg.get('auth_mode', 'Anonymous')
        username = cfg.get('username', '')
        password = getattr(self.owner, 'opcua_session_password', '')

        if not reader:
            return

        self.btn_read_live.set_sensitive(False)
        self.btn_read_live.set_label('กำลังอ่านค่า…')

        def on_done(obs):
            self.btn_read_live.set_sensitive(True)
            self.btn_read_live.set_label('อ่านค่า 1 ครั้ง')
            if self.selected_inspector_tag and self.selected_inspector_tag.get('name') == tag_name:
                self.render_inspector_tag(self.selected_inspector_tag)
            self.render_catalog_table()

        reader.read_tag_once_async(
            tag_name=tag_name,
            endpoint_url=url,
            sec_policy=sec_policy,
            auth_mode=auth_mode,
            username=username,
            password=password,
            callback=on_done
        )

    def on_add_single_tag_to_task(self):
        if not getattr(self.owner, 'tasks', []):
            self.inspector_dialog.close()
            self.open_task_dialog()
            self.on_create_new_task()
            return
        if self.selected_inspector_tag and self._add_tags(
                self.inspector_task_selector.get_selected(), [self.selected_inspector_tag['name']]):
            self.inspector_dialog.close()

    def _current_task_index(self):
        tasks = getattr(self.owner, 'tasks', [])
        if not tasks:
            return Gtk.INVALID_LIST_POSITION
        return max(0, min(self.selected_task_index, len(tasks) - 1))

    def _populate_task_picker(self, picker):
        tasks = getattr(self.owner, 'tasks', [])
        picker.set_model(Gtk.StringList.new([f"{task.get('id', '')} · {task.get('name', '')}" for task in tasks]))
        picker.set_selected(self._current_task_index())

    def _add_tags(self, idx, names):
        tasks = getattr(self.owner, 'tasks', [])
        if not 0 <= idx < len(tasks):
            return False
        task = tasks[idx]
        added = list(dict.fromkeys(name for name in names if name not in task.get('tags', [])))
        if not added:
            self._show_add_error('Tag ที่เลือกอยู่ใน Task นี้แล้ว')
            return False
        had_tags = 'tags' in task
        previous = task.get('tags', [])
        task['tags'] = [*previous, *added]
        if not self.owner.save_tasks():
            if had_tags:
                task['tags'] = previous
            else:
                task.pop('tags')
            self._show_add_error('บันทึก Task ไม่สำเร็จ')
            return False
        self.selected_task_index = idx
        self.owner.current_task_idx = idx
        self._undo_add = (task, tuple(added))
        self.render_catalog_table()
        if getattr(self, 'f1_api', None):
            self.f1_api.push_state_to_webview()
        self._show_toast(f"เพิ่ม {len(added)} Tag เข้า {task.get('name', 'Task')}", undo=True)
        return True

    def _show_add_error(self, message):
        if self.inspector_dialog is not None and self.inspector_dialog.get_visible():
            label = self.inspector_action_error
        elif self.bulk_dialog is not None and self.bulk_dialog.get_visible():
            label = self.bulk_action_error
        else:
            self._show_toast(message)
            return
        label.set_text(message)
        label.set_visible(True)

    def _show_toast(self, text, *, undo=False):
        if self._toast_timeout is not None:
            GLib.source_remove(self._toast_timeout)
        self.toast_label.set_text(text)
        self.undo_button.set_visible(undo)
        self.toast.set_reveal_child(True)
        self._toast_timeout = GLib.timeout_add_seconds(8, self._hide_toast)

    def _hide_toast(self):
        self._toast_timeout = None
        self._undo_add = None
        self.toast.set_reveal_child(False)
        return GLib.SOURCE_REMOVE

    def _undo_last_add(self, *_args):
        if self._undo_add is None:
            return
        task, added = self._undo_add
        if not any(current is task for current in getattr(self.owner, 'tasks', [])):
            self._undo_add = None
            self._show_toast('Task นี้ไม่อยู่ในรายการแล้ว')
            return
        previous = task.get('tags', [])
        task['tags'] = [name for name in previous if name not in added]
        if not self.owner.save_tasks():
            task['tags'] = previous
            self._show_toast('ย้อนกลับไม่สำเร็จ ลองอีกครั้งได้', undo=True)
            return
        self._undo_add = None
        self.render_catalog_table()
        if getattr(self, 'f1_api', None):
            self.f1_api.push_state_to_webview()
        self._show_toast(f'ย้อนกลับการเพิ่ม {len(added)} Tag แล้ว')


    def build_task_config_view(self):
        panel = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        body = Gtk.Box(spacing=12, vexpand=True)
        body.add_css_class('tag-task-body')
        panel.append(body)

        settings = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8, valign=Gtk.Align.START)
        body.append(settings)

        # SECTION 1: ข้อมูลและการระบุตัวตนของ Task
        sec1 = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        sec1.add_css_class('f2-section-card')
        settings.append(sec1)

        s1_title = Gtk.Label(label="ตั้งค่า Task")
        s1_title.add_css_class('f2-section-title')
        s1_title.set_xalign(0.0)
        sec1.append(s1_title)

        # Task Selector + Create New
        sel_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        sec1.append(sel_row)

        lbl_s = Gtk.Label(label="เลือก Task:")
        lbl_s.add_css_class('f2-form-label')
        sel_row.append(lbl_s)

        self.task_selector_combo = Gtk.DropDown()
        self.task_selector_combo.set_size_request(220, -1)
        self.task_selector_combo.connect('notify::selected', self.on_task_selector_changed)
        sel_row.append(self.task_selector_combo)

        btn_new = Gtk.Button(label="สร้าง Task")
        btn_new.set_size_request(-1, 40)
        btn_new.add_css_class('f2-btn-new-task')
        btn_new.connect('clicked', lambda _: self.on_create_new_task())
        sel_row.append(btn_new)

        # Grid Details
        grid1 = Gtk.Grid(column_spacing=8, row_spacing=6)
        sec1.append(grid1)

        # Task ID
        lbl_id = Gtk.Label(label="Task ID:")
        lbl_id.add_css_class('f2-form-label')
        lbl_id.set_xalign(0.0)
        grid1.attach(lbl_id, 0, 0, 1, 1)

        self.lbl_task_id_val = Gtk.Label(label="TASK-01")
        self.lbl_task_id_val.add_css_class('f2-task-id-pill')
        self.lbl_task_id_val.set_xalign(0.0)
        grid1.attach(self.lbl_task_id_val, 1, 0, 1, 1)

        # Task Name
        lbl_name = Gtk.Label(label="ชื่อ Task:")
        lbl_name.add_css_class('f2-form-label')
        lbl_name.set_xalign(0.0)
        grid1.attach(lbl_name, 0, 1, 1, 1)

        self.entry_task_name = Gtk.Entry()
        self.entry_task_name.set_size_request(280, -1)
        self.entry_task_name.connect('changed', self.on_task_field_changed)
        grid1.attach(self.entry_task_name, 1, 1, 1, 1)

        # Task Cycle
        lbl_cy = Gtk.Label(label="รอบตรวจสอบ:")
        lbl_cy.add_css_class('f2-form-label')
        lbl_cy.set_xalign(0.0)
        grid1.attach(lbl_cy, 0, 2, 1, 1)

        cycle_list = Gtk.StringList.new([c[1] for c in CYCLE_OPTIONS])
        self.combo_cycle = Gtk.DropDown.new(cycle_list, None)
        self.combo_cycle.set_selected(1)  # 5s
        self.combo_cycle.set_size_request(240, -1)
        self.combo_cycle.connect('notify::selected', self.on_task_field_changed)
        grid1.attach(self.combo_cycle, 1, 2, 1, 1)

        # Status badge
        lbl_st = Gtk.Label(label="สถานะ Task:")
        lbl_st.add_css_class('f2-form-label')
        lbl_st.set_xalign(0.0)
        grid1.attach(lbl_st, 0, 3, 1, 1)

        self.lbl_task_state_badge = Gtk.Label(label="พร้อมทำงาน")
        self.lbl_task_state_badge.add_css_class('f2-task-status-ready')
        self.lbl_task_state_badge.set_xalign(0.0)
        grid1.attach(self.lbl_task_state_badge, 1, 3, 1, 1)

        # SECTION 2: การทำงานเมื่อตรวจพบสัญญาณ (Task Actions)
        sec2 = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        sec2.add_css_class('f2-section-card')
        settings.append(sec2)

        s2_title = Gtk.Label(label="เมื่อ Task ทำงาน")
        s2_title.add_css_class('f2-section-title')
        s2_title.set_xalign(0.0)
        sec2.append(s2_title)

        self.chk_action_log = Gtk.CheckButton(label="บันทึกประวัติในเครื่อง", height_request=36)
        self.chk_action_log.set_active(True)
        self.chk_action_log.connect('toggled', self.on_task_field_changed)
        sec2.append(self.chk_action_log)

        tg_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        sec2.append(tg_row)

        self.chk_action_notify = Gtk.CheckButton(label="แจ้งเตือนผ่าน Telegram", height_request=36, hexpand=True)
        self.chk_action_notify.set_active(True)
        self.chk_action_notify.connect('toggled', self.on_task_field_changed)
        tg_row.append(self.chk_action_notify)

        btn_f6_hint = Gtk.Button(label="เปิดการตั้งค่า →")
        btn_f6_hint.set_cursor_from_name('pointer')
        btn_f6_hint.add_css_class('f2-action-hint-btn')
        btn_f6_hint.set_tooltip_text('เปิดการตั้งค่าเพื่อกรอก Bot Token และ Chat ID ในแท็บ Telegram')
        btn_f6_hint.connect('clicked', self._on_navigate_to_f6)
        tg_row.append(btn_f6_hint)

        self.chk_task_enabled = Gtk.CheckButton(label="เปิดใช้งาน Task นี้", height_request=36)
        self.chk_task_enabled.set_active(True)
        self.chk_task_enabled.connect('toggled', self.on_task_field_changed)
        sec2.append(self.chk_task_enabled)
        for option in (self.chk_action_log, self.chk_action_notify, self.chk_task_enabled):
            option.set_cursor_from_name('pointer')
            option.add_css_class('tag-task-option')

        assigned = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8, hexpand=True)
        assigned.add_css_class('f2-section-card')
        body.append(assigned)

        toolbar = Gtk.Box(spacing=8)
        assigned.append(toolbar)
        self.lbl_assigned_title = Gtk.Label(label='Tag ใน Task (0 รายการ)', xalign=0, hexpand=True)
        self.lbl_assigned_title.add_css_class('f2-section-title')
        toolbar.append(self.lbl_assigned_title)
        self.btn_clear_all_assigned = Gtk.Button(label='ล้าง Tag ทั้งหมด', sensitive=False)
        self.btn_clear_all_assigned.add_css_class('f2-btn-clear-selection')
        self.btn_clear_all_assigned.connect('clicked', self._clear_all_assigned)
        toolbar.append(self.btn_clear_all_assigned)
        self.btn_remove_assigned = Gtk.Button(label='เอา Tag ที่เลือกออก', sensitive=False)
        self.btn_remove_assigned.set_tooltip_text('การเอาออกจะมีผลเมื่อกดบันทึก Task')
        self.btn_remove_assigned.connect('clicked', self._remove_selected_assigned)
        toolbar.append(self.btn_remove_assigned)

        table = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, vexpand=True)
        assigned.append(table)
        self.chk_assigned_select_all = Gtk.CheckButton(valign=Gtk.Align.CENTER)
        self.chk_assigned_select_all.set_tooltip_text('เลือกทั้งหมด / ยกเลิกการเลือก')
        self.chk_assigned_select_all.connect('toggled', self._on_assigned_select_all_toggled)
        headings = [
            self.chk_assigned_select_all,
            self._catalog_label('ชื่อ Tag', 'f2-col-header'),
            self._catalog_label('กลุ่มอุปกรณ์', 'f2-col-header'),
            self._catalog_label('ชนิดข้อมูล', 'f2-col-header'),
        ]
        header = self._catalog_columns(headings, ASSIGNED_COLUMNS)
        header.add_css_class('tag-assigned-header')
        table.append(header)

        as_scroll = Gtk.ScrolledWindow(vexpand=True)
        as_scroll.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        as_scroll.add_css_class('f2-assigned-scroll')
        table.append(as_scroll)

        self.assigned_listbox = Gtk.ListBox(selection_mode=Gtk.SelectionMode.SINGLE)
        self.assigned_listbox.set_activate_on_single_click(False)
        self.assigned_listbox.add_css_class('f2-assigned-list')
        self.assigned_listbox.connect(
            'row-selected', lambda _list, _row: self._update_assigned_selection_ui()
        )
        assigned_clicks = Gtk.GestureClick(button=Gdk.BUTTON_PRIMARY, propagation_phase=Gtk.PropagationPhase.CAPTURE)
        assigned_clicks.connect('pressed', self._on_assigned_row_pressed)
        assigned_clicks.connect('released', self._on_assigned_row_released)
        assigned_clicks.connect('stopped', self._clear_assigned_press)
        self.assigned_listbox.add_controller(assigned_clicks)
        assigned_keys = Gtk.EventControllerKey(propagation_phase=Gtk.PropagationPhase.CAPTURE)
        assigned_keys.connect('key-pressed', self._on_assigned_key_pressed)
        self.assigned_listbox.add_controller(assigned_keys)
        placeholder = Gtk.Label(label='ยังไม่มี Tag ใน Task นี้', xalign=0)
        placeholder.add_css_class('tag-assigned-placeholder')
        self.assigned_listbox.set_placeholder(placeholder)
        as_scroll.set_child(self.assigned_listbox)

        # STICKY BOTTOM SAVE TASK BAR
        save_bar = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        save_bar.add_css_class('tag-dialog-footer')
        panel.append(save_bar)

        self.lbl_save_status = Gtk.Label(label="พร้อมใช้งาน · ข้อมูลได้รับการบันทึกแล้ว")
        self.lbl_save_status.add_css_class('f2-save-status-clean')
        self.lbl_save_status.set_hexpand(True)
        self.lbl_save_status.set_wrap(True)
        self.lbl_save_status.set_xalign(0.0)
        save_bar.append(self.lbl_save_status)

        back = Gtk.Button(label='กลับไปหน้า Tag')
        back.connect('clicked', lambda _: self.task_dialog.close())
        save_bar.append(back)

        self.btn_save_task = Gtk.Button(label="บันทึก Task")
        self.btn_save_task.set_size_request(-1, 42)
        self.btn_save_task.add_css_class('tag-flow-primary')
        self.btn_save_task.connect('clicked', lambda _: self.on_save_task())
        save_bar.append(self.btn_save_task)

        return panel

    # -------------------------------------------------------------------------
    # TASK OPERATIONS & PERSISTENCE
    # -------------------------------------------------------------------------

    def load_current_task_to_ui(self):
        tasks = getattr(self.owner, 'tasks', [])
        if not self._new_task:
            if tasks:
                self.selected_task_index = self._current_task_index()
                task = tasks[self.selected_task_index]
                self._task_draft = {**task, 'tags': list(task.get('tags', []))}
            else:
                self._task_draft = None
        self._render_task_form()

    def _render_task_form(self):
        self.task_selector_updating = True
        try:
            tasks = getattr(self.owner, 'tasks', [])
            labels = [f"{task.get('id', '')} · {task.get('name', '')}" for task in tasks]
            if self._new_task:
                labels.append('Task ใหม่ · ยังไม่ได้บันทึก')
            self.task_selector_combo.set_model(Gtk.StringList.new(labels))
            self.task_selector_combo.set_selected(
                self.selected_task_index if self._task_draft else Gtk.INVALID_LIST_POSITION
            )
            draft = self._task_draft or {}
            self.lbl_task_id_val.set_text(draft.get('id', '—'))
            self.entry_task_name.set_text(draft.get('name', ''))
            cycle_idx = next(
                (idx for idx, (seconds, _) in enumerate(CYCLE_OPTIONS)
                 if seconds == draft.get('cycle_sec')), 1
            )
            # Keep nonstandard intervals already stored in Task JSON.
            cycles = list(CYCLE_OPTIONS)
            cycle = draft.get('cycle_sec')
            if isinstance(cycle, int) and cycle > 0 and all(seconds != cycle for seconds, _ in cycles):
                cycle_idx = len(cycles)
                cycles.append((cycle, f'{cycle} วินาที'))
            self._editor_cycles = cycles
            self.combo_cycle.set_model(Gtk.StringList.new([label for _, label in cycles]))
            self.combo_cycle.set_selected(cycle_idx)
            self.chk_action_log.set_active(draft.get('action_log', False))
            self.chk_action_notify.set_active(draft.get('action_notify', False))
            self.chk_task_enabled.set_active(draft.get('active', False))
            for widget in (self.entry_task_name, self.combo_cycle, self.chk_action_log,
                           self.chk_action_notify, self.chk_task_enabled, self.btn_save_task):
                widget.set_sensitive(self._task_draft is not None)
            self.render_assigned_tags_table(draft)
            self.has_unsaved_changes = self._new_task
            self.update_dirty_status()
        finally:
            self.task_selector_updating = False


    def render_assigned_tags_table(self, task):
        while row := self.assigned_listbox.get_row_at_index(0):
            self.assigned_listbox.remove(row)

        self.selected_assigned_tags.clear()
        self.assigned_checkboxes.clear()
        self.assigned_rows.clear()

        assigned = task.get('tags', [])
        self.lbl_assigned_title.set_text(f"Tag ใน Task ({len(assigned)} รายการ)")

        if hasattr(self, 'chk_assigned_select_all'):
            self.chk_assigned_select_all.set_active(False)
            self.chk_assigned_select_all.set_sensitive(len(assigned) > 0)

        if hasattr(self, 'btn_clear_all_assigned'):
            self.btn_clear_all_assigned.set_sensitive(len(assigned) > 0)

        if hasattr(self, 'btn_remove_assigned'):
            self.btn_remove_assigned.set_label('เอา Tag ที่เลือกออก')
            self.btn_remove_assigned.set_sensitive(False)

        if len(assigned) > 0:
            self.lbl_task_state_badge.set_text(f"พร้อมทำงาน · มี {len(assigned)} Tags")
            self.lbl_task_state_badge.remove_css_class('f2-scan-status-idle')
            self.lbl_task_state_badge.add_css_class('f2-task-status-ready')
        else:
            self.lbl_task_state_badge.set_text("ยังไม่มี Tag ผูกกับ Task")
            self.lbl_task_state_badge.remove_css_class('f2-task-status-ready')
            self.lbl_task_state_badge.add_css_class('f2-scan-status-idle')

        for name in assigned:
            catalog_row = self.catalog_rows.get(name)
            tag = catalog_row._tag_data if catalog_row is not None else {}
            data_type = tag.get('type')
            row = Gtk.ListBoxRow()
            row._tag_name = name
            row.set_tooltip_text(name)
            row.set_cursor_from_name('pointer')

            checkbox = Gtk.CheckButton(valign=Gtk.Align.CENTER)
            checkbox.set_size_request(-1, 32)
            checkbox.set_tooltip_text(f'เลือก {name}')

            def make_assigned_cb(tag_name):
                def cb(btn):
                    if getattr(self, '_syncing_assigned_checks', False):
                        return
                    if btn.get_active():
                        self.selected_assigned_tags.add(tag_name)
                    else:
                        self.selected_assigned_tags.discard(tag_name)
                    self._update_assigned_selection_ui()
                return cb

            checkbox.connect('toggled', make_assigned_cb(name))
            self.assigned_checkboxes[name] = checkbox
            self.assigned_rows[name] = row

            row.set_child(self._catalog_columns((
                checkbox,
                self._catalog_label(name, 'f2-tag-name-label'),
                self._catalog_label(tag.get('group') or '—', 'tag-cell-secondary'),
                self._catalog_label(format_data_type(data_type) if data_type else '—', 'tag-cell-secondary'),
            ), ASSIGNED_COLUMNS))
            self.assigned_listbox.append(row)

    def _update_assigned_selection_ui(self):
        self._syncing_assigned_checks = True
        try:
            for name, chk in self.assigned_checkboxes.items():
                active = name in self.selected_assigned_tags
                if chk.get_active() != active:
                    chk.set_active(active)
                row = self.assigned_rows.get(name)
                if row is not None:
                    if active:
                        row.add_css_class('tag-row-checked')
                    else:
                        row.remove_css_class('tag-row-checked')
        finally:
            self._syncing_assigned_checks = False

        count = len(self.selected_assigned_tags)
        if count > 0:
            self.btn_remove_assigned.set_label(f"เอา Tag ที่เลือกออก ({count})")
            self.btn_remove_assigned.set_sensitive(True)
        else:
            row = self.assigned_listbox.get_selected_row()
            if row is not None:
                self.btn_remove_assigned.set_label('เอา Tag ที่เลือกออก')
                self.btn_remove_assigned.set_sensitive(True)
            else:
                self.btn_remove_assigned.set_label('เอา Tag ที่เลือกออก')
                self.btn_remove_assigned.set_sensitive(False)

        if hasattr(self, 'chk_assigned_select_all'):
            total = len(self._task_draft.get('tags', [])) if self._task_draft else 0
            if total > 0 and count == total:
                self.chk_assigned_select_all.set_active(True)
            elif count == 0:
                self.chk_assigned_select_all.set_active(False)

        if hasattr(self, 'btn_clear_all_assigned'):
            total = len(self._task_draft.get('tags', [])) if self._task_draft else 0
            self.btn_clear_all_assigned.set_sensitive(total > 0)

    def _on_assigned_select_all_toggled(self, checkbutton):
        if getattr(self, '_syncing_assigned_checks', False):
            return
        active = checkbutton.get_active()
        if active:
            if self._task_draft:
                self.selected_assigned_tags = set(self._task_draft.get('tags', []))
        else:
            self.selected_assigned_tags.clear()
        self._update_assigned_selection_ui()

    def _assigned_row_at(self, x, y):
        picked = self.assigned_listbox.pick(x, y, Gtk.PickFlags.DEFAULT)
        if picked is None:
            return None
        row = picked if isinstance(picked, Gtk.ListBoxRow) else picked.get_ancestor(Gtk.ListBoxRow)
        if row is not None and row.get_parent() == self.assigned_listbox:
            tag_name = getattr(row, '_tag_name', None)
            if tag_name and tag_name in self.assigned_checkboxes:
                checkbox = self.assigned_checkboxes[tag_name]
                if picked != checkbox and not picked.is_ancestor(checkbox):
                    return row
        return None

    def _on_assigned_row_pressed(self, gesture, n_press, x, y):
        gesture._assigned_press_row = self._assigned_row_at(x, y) if n_press == 1 else None

    def _clear_assigned_press(self, gesture):
        gesture._assigned_press_row = None

    def _on_assigned_row_released(self, gesture, n_press, x, y):
        row = getattr(gesture, '_assigned_press_row', None)
        self._clear_assigned_press(gesture)
        if n_press == 1 and row is not None and row == self._assigned_row_at(x, y):
            self._toggle_assigned_row(row)

    def _on_assigned_key_pressed(self, controller, key, _code, state):
        if key != Gdk.KEY_space or state & (Gdk.ModifierType.CONTROL_MASK | Gdk.ModifierType.ALT_MASK):
            return False
        focus = self.assigned_listbox.get_root().get_focus()
        if isinstance(focus, Gtk.ListBoxRow) and focus.get_parent() == self.assigned_listbox:
            self._toggle_assigned_row(focus)
            return True
        return False

    def _toggle_assigned_row(self, row):
        name = getattr(row, '_tag_name', None)
        if name and name in self.assigned_checkboxes:
            checkbox = self.assigned_checkboxes[name]
            checkbox.set_active(not checkbox.get_active())

    def _on_navigate_to_f6(self, _button):
        def navigate():
            if self.task_dialog is not None and self.task_dialog.get_visible():
                self.task_dialog.set_visible(False)
            if hasattr(self.owner, 'switch_to_tab'):
                self.owner.switch_to_tab('alarms')
            elif getattr(self.owner, 'nav_btns', {}).get('alarms'):
                self.owner.nav_btns['alarms'].set_active(True)
            elif hasattr(self.owner, 'stack'):
                self.owner.stack.set_visible_child_name('alarms')
        self._guard_task_changes(navigate)

    def _remove_selected_assigned(self, _button):
        if self._task_draft is None:
            return
        to_remove = set(self.selected_assigned_tags)
        if not to_remove:
            row = self.assigned_listbox.get_selected_row()
            if row and getattr(row, '_tag_name', None):
                to_remove.add(row._tag_name)
        if not to_remove:
            return
        self._task_draft['tags'] = [t for t in self._task_draft.get('tags', []) if t not in to_remove]
        self.selected_assigned_tags.clear()
        self.has_unsaved_changes = True
        self.render_assigned_tags_table(self._task_draft)
        self.update_dirty_status()

    def _clear_all_assigned(self, _button):
        if self._task_draft is None:
            return
        self._task_draft['tags'] = []
        self.selected_assigned_tags.clear()
        self.has_unsaved_changes = True
        self.render_assigned_tags_table(self._task_draft)
        self.update_dirty_status()

    def on_add_selected_to_task(self):
        if not self.selected_catalog_tags:
            return
        if not getattr(self.owner, 'tasks', []):
            self.open_task_dialog()
            self.on_create_new_task()
            return
        if self.bulk_dialog is None:
            panel = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)
            panel.set_margin_start(18)
            panel.set_margin_end(18)
            panel.set_margin_top(18)
            panel.set_margin_bottom(18)
            self.bulk_label = Gtk.Label(xalign=0, wrap=True)
            panel.append(self.bulk_label)
            self.bulk_task_selector = Gtk.DropDown()
            self.bulk_task_selector.set_size_request(-1, 40)
            panel.append(self.bulk_task_selector)
            self.bulk_action_error = Gtk.Label(xalign=0, wrap=True)
            self.bulk_action_error.add_css_class('badge-nope')
            panel.append(self.bulk_action_error)
            actions = Gtk.Box(spacing=8, halign=Gtk.Align.END)
            panel.append(actions)
            cancel = Gtk.Button(label='ยกเลิก')
            cancel.connect('clicked', lambda _: self.bulk_dialog.close())
            actions.append(cancel)
            self.bulk_submit_button = Gtk.Button(label='ยืนยันเพิ่ม Tag')
            self.bulk_submit_button.set_size_request(-1, 40)
            self.bulk_submit_button.add_css_class('tag-flow-primary')
            self.bulk_submit_button.connect('clicked', self._submit_bulk_add)
            actions.append(self.bulk_submit_button)
            self.bulk_dialog = self._make_popup('เพิ่ม Tag เข้า Task', panel, 480, 175)
        self.bulk_label.set_text(f'เลือก Task ปลายทางสำหรับ {len(self.selected_catalog_tags)} Tag ที่ติ๊กไว้')
        self._populate_task_picker(self.bulk_task_selector)
        self.bulk_action_error.set_visible(False)
        self.bulk_dialog.present()
        self.bulk_task_selector.grab_focus()

    def _submit_bulk_add(self, _button):
        names = [name for name in self.catalog_rows if name in self.selected_catalog_tags]
        if self._add_tags(self.bulk_task_selector.get_selected(), names):
            self.on_clear_selection()
            self.bulk_dialog.close()

    def on_task_field_changed(self, *_args):
        if not self.task_selector_updating and self._task_draft is not None:
            self.has_unsaved_changes = True
            self.update_dirty_status()

    def update_dirty_status(self):
        if self.has_unsaved_changes:
            self.lbl_save_status.set_text('มีการแก้ไขที่ยังไม่ได้บันทึก')
            self.lbl_save_status.set_css_classes(['f2-save-status-dirty'])
        else:
            self.lbl_save_status.set_text('บันทึกแล้ว' if self._task_draft else 'สร้าง Task เพื่อเริ่มใช้งาน')
            self.lbl_save_status.set_css_classes(['f2-save-status-clean'])

    def on_task_selector_changed(self, drop_down, _param_spec):
        if not self.task_selector_updating:
            self.switch_to_task(drop_down.get_selected())

    def switch_to_task(self, idx):
        tasks = getattr(self.owner, 'tasks', [])
        if not 0 <= idx < len(tasks) or idx == self.selected_task_index:
            return
        if self.has_unsaved_changes:
            self.task_selector_updating = True
            self.task_selector_combo.set_selected(self.selected_task_index)
            self.task_selector_updating = False
        self._guard_task_changes(lambda: self._select_saved_task(idx))

    def _select_saved_task(self, idx):
        self._new_task = False
        self.selected_task_index = idx
        self.owner.current_task_idx = idx
        self.load_current_task_to_ui()
        self.render_catalog_table()

    def _guard_task_changes(self, proceed):
        if not self.has_unsaved_changes:
            proceed()
            return
        if self._pending_close is not None:
            return
        dialog = Gtk.MessageDialog(
            transient_for=self.task_dialog,
            modal=True,
            message_type=Gtk.MessageType.QUESTION,
            buttons=Gtk.ButtonsType.NONE,
            text='ยังมีการแก้ Task ที่ไม่ได้บันทึก',
        )
        dialog.add_button('กลับไปแก้', Gtk.ResponseType.CANCEL)
        dialog.add_button('ละทิ้งการแก้ไข', Gtk.ResponseType.REJECT)
        dialog.add_button('บันทึก', Gtk.ResponseType.ACCEPT)
        dialog.set_default_response(Gtk.ResponseType.CANCEL)
        self._pending_close = dialog

        def response(widget, choice):
            self._pending_close = None
            widget.destroy()
            if choice == Gtk.ResponseType.REJECT:
                self._new_task = False
                self.load_current_task_to_ui()
                proceed()
            elif choice == Gtk.ResponseType.ACCEPT and self.on_save_task():
                proceed()

        dialog.connect('response', response)
        dialog.present()

    def _on_close_task_dialog(self, _window):
        def close():
            self.task_dialog.set_visible(False)
            self.current_workspace_mode = 'monitoring'
            self.btn_top_f2.grab_focus()
        self._guard_task_changes(close)
        return True

    def on_save_task(self):
        if self._task_draft is None:
            return False
        tasks = getattr(self.owner, 'tasks', [])
        idx = self.selected_task_index
        if not self._new_task and not 0 <= idx < len(tasks):
            return False

        cycle_idx = self.combo_cycle.get_selected()
        cycle = self._editor_cycles[cycle_idx][0] if 0 <= cycle_idx < len(self._editor_cycles) else 5
        updates = dict(
            name=self.entry_task_name.get_text().strip() or self._task_draft['id'],
            cycle_sec=cycle,
            action_log=self.chk_action_log.get_active(),
            action_notify=self.chk_action_notify.get_active(),
            active=self.chk_task_enabled.get_active(),
            tags=list(self._task_draft.get('tags', [])),
        )
        if self._new_task:
            task = {**self._task_draft, **updates}
            tasks.append(task)
            idx = len(tasks) - 1
        else:
            previous = tasks[idx]
            task = {**previous, **updates}
            tasks[idx] = task
        if not self.owner.save_tasks():
            if self._new_task:
                tasks.pop()
            else:
                tasks[idx] = previous
            self.has_unsaved_changes = True
            self.update_dirty_status()
            self.lbl_save_status.set_text('บันทึกไม่สำเร็จ · การแก้ไขยังอยู่ในหน้าต่างนี้')
            return False

        self._select_saved_task(idx)
        return True

    def on_create_new_task(self):
        self._guard_task_changes(self._create_task_draft)

    def _create_task_draft(self):
        tasks = getattr(self.owner, 'tasks', [])
        existing_ids = {task.get('id') for task in tasks}
        number = 1
        while f'TASK-{number:02d}' in existing_ids:
            number += 1
        identifier = f'TASK-{number:02d}'
        self._new_task = True
        self.selected_task_index = len(tasks)
        self._task_draft = {
            'id': identifier, 'name': f'Task ใหม่ {identifier}', 'cycle_sec': 5,
            'action_log': True, 'action_notify': False, 'active': False, 'tags': [],
            'scan_count': 0, 'log_count': 0, 'alert_count': 0,
        }
        self._render_task_form()
        self.entry_task_name.grab_focus()
        self.entry_task_name.select_region(0, -1)


    def on_toggle_auto_scan(self, button):
        if hasattr(self.owner, 'auto_scan_active'):
            self.owner.auto_scan_active = not self.owner.auto_scan_active
            is_running = self.owner.auto_scan_active
            self.btn_auto_scan.set_label("หยุดรีเฟรชอัตโนมัติ" if is_running else "รีเฟรชอัตโนมัติ")
            if is_running:
                self.btn_auto_scan.remove_css_class('f2-btn-auto-start')
                self.btn_auto_scan.add_css_class('f2-btn-auto-stop')
                self.badge_scan_status.set_text("กำลังรีเฟรชตามรอบ")
                self.badge_scan_status.remove_css_class('f2-scan-status-idle')
                self.badge_scan_status.add_css_class('f2-scan-status-running')
            else:
                self.btn_auto_scan.remove_css_class('f2-btn-auto-stop')
                self.btn_auto_scan.add_css_class('f2-btn-auto-start')
                self.badge_scan_status.set_text("ปิดอยู่")
                self.badge_scan_status.remove_css_class('f2-scan-status-running')
                self.badge_scan_status.add_css_class('f2-scan-status-idle')

    def sync_catalog_data(self):
        """Synchronizes 457 tags from owner.scanned_tags"""
        self.catalog_tags_cache = getattr(self.owner, 'scanned_tags', [])
        self.group_counts = {"All": len(self.catalog_tags_cache)}
        for t in self.catalog_tags_cache:
            g = t.get('group', 'Default')
            self.group_counts[g] = self.group_counts.get(g, 0) + 1
        if getattr(self, 'f1_api', None):
            self.f1_api.sync_catalog_data()
