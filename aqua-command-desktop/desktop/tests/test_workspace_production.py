#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
AQUA COMMAND — UNIFIED MONITORING & TASK WORKSPACE V1
Automated Production Integration Test Suite
"""

import os
import sys
import unittest
from pathlib import Path

desktop_dir = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(desktop_dir))

import gi
gi.require_version('Gtk', '4.0')
from gi.repository import Gtk, GLib

import app
from workspace import AquaUnifiedWorkspaceView

class TestWorkspaceProductionIntegration(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        # Create test GTK application
        cls.gtk_app = Gtk.Application(application_id='org.aqua.test.workspace.prod')
        cls.win = app.AquaWinCCWindow(cls.gtk_app)
        cls.win.auto_scan_active = False

    def test_01_feature_flag_active(self):
        """Verify that USE_UNIFIED_WORKSPACE is enabled and unified_workspace is mounted"""
        self.assertTrue(app.USE_UNIFIED_WORKSPACE, "Feature flag USE_UNIFIED_WORKSPACE must be True")
        self.assertTrue(hasattr(self.win, 'unified_workspace'), "Window must have unified_workspace instance")
        self.assertIsInstance(self.win.unified_workspace, AquaUnifiedWorkspaceView)

    def test_02_catalog_tags_loaded(self):
        """Verify that 457 tags are loaded from Export all.txt into unified workspace"""
        ws = self.win.unified_workspace
        self.assertEqual(len(ws.catalog_tags_cache), 457, "Should have 457 tags in catalog cache")
        self.assertIn("High_VSD", ws.group_counts)
        self.assertEqual(ws.group_counts["All"], 457)
        self.assertEqual(ws.group_counts["High_VSD"], 135)
        self.assertEqual(ws.group_counts["High_Valve"], 68)

    def test_03_f1_and_f2_mode_transitions(self):
        """Verify F1 monitoring mode and F2 task mode switching without side effects"""
        ws = self.win.unified_workspace

        # Switch to F1
        self.win.activate_workspace_mode('monitoring')
        self.assertEqual(ws.current_workspace_mode, 'monitoring')
        self.assertEqual(ws.context_stack.get_visible_child_name(), 'monitoring')
        self.assertFalse(ws.btn_add_selected.get_visible())
        self.assertTrue(ws.lbl_dock_guide.get_visible())

        # Switch to F2
        self.win.activate_workspace_mode('task_manager')
        self.assertEqual(ws.current_workspace_mode, 'task_manager')
        self.assertEqual(ws.context_stack.get_visible_child_name(), 'task_manager')
        self.assertTrue(ws.btn_add_selected.get_visible())
        self.assertFalse(ws.lbl_dock_guide.get_visible())

    def test_04_multi_group_tag_selection_and_addition(self):
        """Verify multi-group tag selection and addition into task"""
        ws = self.win.unified_workspace
        ws.selected_catalog_tags.clear()

        # Clear current task tags to test fresh addition
        cur_task = self.win.tasks[ws.selected_task_index]
        cur_task['tags'] = []
        ws.has_unsaved_changes = False

        # Select 2 tags from High_VSD
        ws.on_select_group("High_VSD")
        vsd_tags = [t['name'] for t in ws.currently_filtered_tags[:2]]
        for t in vsd_tags:
            ws.selected_catalog_tags.add(t)

        # Select 2 tags from High_Valve
        ws.on_select_group("High_Valve")
        valve_tags = [t['name'] for t in ws.currently_filtered_tags[:2]]
        for t in valve_tags:
            ws.selected_catalog_tags.add(t)

        self.assertEqual(len(ws.selected_catalog_tags), 4)

        # Add to current task
        ws.on_add_selected_to_task()

        self.assertTrue(ws.has_unsaved_changes)
        self.assertEqual(len(cur_task['tags']), 4)
        # Selection should be cleared after addition
        self.assertEqual(len(ws.selected_catalog_tags), 0)

        # Save task and verify clean status
        ws.on_save_task()
        self.assertFalse(ws.has_unsaved_changes)

    def test_05_task_crud_and_dirty_safeguard(self):
        """Verify creating new task and dirty state auto-save safeguard"""
        ws = self.win.unified_workspace
        initial_tasks_len = len(self.win.tasks)

        # Create new task
        ws.on_create_new_task()
        self.assertEqual(len(self.win.tasks), initial_tasks_len + 1)
        self.assertEqual(ws.selected_task_index, len(self.win.tasks) - 1)

        # Modify task name
        ws.entry_task_name.set_text("Unit Test Dynamic Task Name")
        self.assertTrue(ws.has_unsaved_changes)

        # Switching task auto-saves unsaved changes
        ws.switch_to_task(0)
        self.assertEqual(ws.selected_task_index, 0)
        self.assertEqual(self.win.tasks[-1]['name'], "Unit Test Dynamic Task Name")

    def test_06_filter_banner_on_default_group(self):
        """Verify filter banner appears on single-tag group Default"""
        ws = self.win.unified_workspace
        ws.on_select_group("Default")
        self.assertTrue(ws.filter_banner_box.get_visible())
        self.assertEqual(len(ws.currently_filtered_tags), 1)

        # Clear filter
        ws.on_select_group("All")
        self.assertFalse(ws.filter_banner_box.get_visible())
        self.assertEqual(len(ws.currently_filtered_tags), 457)

    def test_07_persistence_schema_invariants(self):
        """Verify Gate B schema invariants in wincc_tasks.json"""
        for t in self.win.tasks:
            self.assertIn('id', t)
            self.assertIn('name', t)
            self.assertIn('cycle_sec', t)
            self.assertIn('action_log', t)
            self.assertIn('action_notify', t)
            self.assertIn('active', t)
            self.assertIn('tags', t)

if __name__ == '__main__':
    unittest.main()
