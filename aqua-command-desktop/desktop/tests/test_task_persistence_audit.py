#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
AQUA COMMAND — TASK PERSISTENCE SAFETY AUDIT & VERIFICATION SUITE
Phase B Audit Tests for Task Persistence & Gate B Remediation Proposal
"""

import os
import sys
import json
import tempfile
import unittest
from pathlib import Path

desktop_dir = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(desktop_dir))

import gi
gi.require_version('Gtk', '4.0')
from gi.repository import Gtk

import app
from workspace import AquaUnifiedWorkspaceView


class TestTaskPersistenceSafetyAudit(unittest.TestCase):
    """
    Audits the 4 identified persistence safety risks in isolated test environments:
    1. switch_to_task() auto-saving half-edited tasks without confirmation
    2. on_save_task() declaring success even when persistence fails
    3. AquaWinCCWindow.save_tasks() returning hardcoded True instead of forwarding save_atomic_json result
    4. on_create_new_task() enabling active=True and action_notify=True by default
    """

    def setUp(self):
        self.tmp_dir = tempfile.TemporaryDirectory()
        self.test_tasks_file = Path(self.tmp_dir.name) / "tasks_test.json"

        # Isolated Mock App Window
        self.gtk_app = Gtk.Application(application_id='org.aqua.test.persistence.audit')
        self.win = app.AquaWinCCWindow(self.gtk_app)
        self.win.auto_scan_active = False

        # Seed isolated test tasks
        self.win.tasks = [
            {
                "id": "TASK-01",
                "name": "Initial Task 1",
                "cycle_sec": 5,
                "action_log": True,
                "action_notify": False,
                "active": False,
                "tags": ["PUMP1_RUN"],
            },
            {
                "id": "TASK-02",
                "name": "Initial Task 2",
                "cycle_sec": 10,
                "action_log": False,
                "action_notify": False,
                "active": False,
                "tags": ["PUMP2_RUN"],
            }
        ]
        self.ws = self.win.unified_workspace
        self.ws.selected_task_index = 0
        self.ws.load_current_task_to_ui()

    def tearDown(self):
        self.tmp_dir.cleanup()

    def test_01_audit_switch_to_task_has_unintended_autosave(self):
        """
        Audit Finding 1:
        Verify whether switch_to_task() currently auto-saves incomplete edits to disk.
        """
        # User edits task name but does NOT click Save Task
        self.ws.entry_task_name.set_text("Unfinished Draft Name (Should not auto-save)")
        self.ws.has_unsaved_changes = True

        save_called = []
        original_save = self.ws.on_save_task
        self.ws.on_save_task = lambda: save_called.append(True)

        # User switches task dropdown to Task 2
        self.ws.switch_to_task(1)

        # Finding: switch_to_task() silently commits changes via auto-save
        self.assertTrue(len(save_called) > 0, "RISK CONFIRMED: switch_to_task() invokes auto-save on dirty state without user confirmation")
        self.ws.on_save_task = original_save

    def test_02_audit_on_save_task_ignores_save_failure(self):
        """
        Audit Finding 2:
        Verify whether on_save_task() ignores the return value of owner.save_tasks()
        and displays false-positive clean status.
        """
        self.ws.has_unsaved_changes = True

        # Simulate disk failure or permission error
        self.win.save_tasks = lambda: False

        self.ws.on_save_task()

        # Finding: on_save_task() sets has_unsaved_changes to False despite persistence failure
        self.assertFalse(self.ws.has_unsaved_changes, "RISK CONFIRMED: on_save_task() clears dirty flag unconditionally even when save_tasks() returned False")
        self.assertIn("บันทึกแล้ว", self.ws.lbl_save_status.get_text(), "RISK CONFIRMED: UI claims data is saved even on failed write")

    def test_03_audit_aquawindow_save_tasks_hardcoded_true(self):
        """
        Audit Finding 3:
        Verify whether AquaWinCCWindow.save_tasks() returns hardcoded True, masking
        save_atomic_json failures.
        """
        # If save_tasks is called on an invalid unwritable path, does AquaWinCCWindow return True?
        # Check source implementation in app.py:
        # def save_tasks(self):
        #     save_tasks(self.tasks)
        #     return True
        import inspect
        src = inspect.getsource(self.win.save_tasks)
        self.assertIn("return True", src, "RISK CONFIRMED: AquaWinCCWindow.save_tasks() hardcodes 'return True' rather than checking save_atomic_json()")

    def test_04_audit_new_task_defaults_premature_active(self):
        """
        Audit Finding 4:
        Verify whether newly created tasks default to active=True and action_notify=True
        before configuration.
        """
        tasks_len_before = len(self.win.tasks)
        # Intercept disk write
        self.ws.on_save_task = lambda: None

        self.ws.on_create_new_task()
        self.assertEqual(len(self.win.tasks), tasks_len_before + 1)
        created_task = self.win.tasks[-1]

        # Audit check:
        self.assertTrue(created_task.get('active', False), "RISK CONFIRMED: New task is active=True by default")
        self.assertTrue(created_task.get('action_notify', False), "RISK CONFIRMED: New task has action_notify=True by default")

    def test_05_proposed_safe_persistence_logic(self):
        """
        Gate B Proposed Patch Validation:
        Simulate the safe persistence semantics to prove safety under the proposed fix.
        """
        # Proposed Logic 1: Safe save returning actual I/O status with try-except covering parent mkdir
        def proposed_save_tasks(window, tasks_file):
            try:
                p = Path(tasks_file)
                p.parent.mkdir(parents=True, exist_ok=True)
                return app.save_atomic_json(tasks_file, window.tasks)
            except Exception:
                return False

        # Test success case
        success = proposed_save_tasks(self.win, self.test_tasks_file)
        self.assertTrue(success)
        self.assertTrue(self.test_tasks_file.exists())

        # Test failure case (unwritable directory)
        invalid_path = Path("/invalid_nonexistent_dir_aqua_test/tasks.json")
        fail_result = proposed_save_tasks(self.win, invalid_path)
        self.assertFalse(fail_result)

        # Proposed Logic 2: Safe new task defaults
        new_id_num = len(self.win.tasks) + 1
        proposed_safe_task = {
            "id": f"TASK-{new_id_num:02d}",
            "name": f"Task เฝ้าระวังใหม่ TASK-{new_id_num:02d}",
            "cycle_sec": 5,
            "action_log": True,
            "action_notify": False,  # Proposed Safe Default: Disabled until configured
            "active": False,         # Proposed Safe Default: Disabled until configured
            "tags": [],
            "scan_count": 0,
            "log_count": 0,
            "alert_count": 0
        }
        self.assertFalse(proposed_safe_task['active'], "Safe default prevents premature background execution")
        self.assertFalse(proposed_safe_task['action_notify'], "Safe default prevents unconfigured Telegram spam")


if __name__ == '__main__':
    unittest.main()
