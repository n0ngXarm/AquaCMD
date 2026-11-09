import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import lab_owner_manage as lifecycle


class LifecycleTests(unittest.TestCase):
    def run_case(self, state, command, *, disappeared=False):
        with tempfile.TemporaryDirectory() as tmp:
            private = Path(tmp)
            (private / "owner-running.json").write_text(json.dumps({"pid": 123}))
            proc = MagicMock()
            pid = proc.__truediv__.return_value
            pid.exists.return_value = True
            files = {name: MagicMock() for name in ("status", "cmdline", "cwd")}
            files["status"].read_text.return_value = "Name:\ttest\nState:\t" + state + "\n"
            files["cmdline"].read_bytes.return_value = command
            if disappeared:
                files["cmdline"].read_bytes.side_effect = FileNotFoundError()
            files["cwd"].resolve.return_value = lifecycle.ROOT.parents[1]
            pid.joinpath.side_effect = lambda name: files[name]
            with patch.object(lifecycle, "PRIVATE", private), patch.object(lifecycle, "Path", return_value=proc):
                return lifecycle.running()

    def test_dead_owned_process_is_stopped(self):
        self.assertIsNone(self.run_case("Z (zombie)", b""))

    def test_process_exit_during_inspection_is_stopped(self):
        self.assertIsNone(self.run_case("S (sleeping)", b"", disappeared=True))

    def test_reused_live_pid_is_never_accepted(self):
        with self.assertRaises(RuntimeError):
            self.run_case("S (sleeping)", b"unrelated\0")

    def test_matching_live_owner_is_accepted(self):
        self.assertEqual(self.run_case("S (sleeping)", b"python3\0/example/lab_owner.py\0"), 123)


if __name__ == "__main__":
    unittest.main()
