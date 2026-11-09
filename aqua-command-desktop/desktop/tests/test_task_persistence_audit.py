"""Regression checks for the Task file save contract, without opening GTK."""
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import app


class TestTaskPersistenceSafetyAudit(unittest.TestCase):
    def test_task_round_trip_keeps_schema_and_unknown_fields(self):
        tasks = [{
            'id': 'TASK-01', 'name': 'Task ตัวอย่าง', 'cycle_sec': 10,
            'action_log': True, 'action_notify': False, 'active': False,
            'tags': ['TestTag'], 'custom_extension': {'keep': True},
        }]
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'wincc_tasks.json'
            with patch.object(app, 'TASKS_CONFIG_FILE', path):
                self.assertTrue(app.AquaWinCCWindow.save_tasks(SimpleNamespace(tasks=tasks)))
                self.assertEqual(app.load_tasks(), tasks)

    def test_write_failure_reaches_workspace_caller(self):
        with tempfile.TemporaryDirectory() as directory:
            parent = Path(directory) / 'not-a-directory'
            parent.write_text('sentinel')
            with patch.object(app, 'TASKS_CONFIG_FILE', parent / 'wincc_tasks.json'):
                self.assertFalse(app.AquaWinCCWindow.save_tasks(SimpleNamespace(tasks=[])))
                self.assertEqual(parent.read_text(), 'sentinel')


if __name__ == '__main__':
    unittest.main()
