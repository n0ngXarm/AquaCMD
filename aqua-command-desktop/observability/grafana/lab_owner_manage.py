"""Start/stop only this worktree's isolated GTK Lab owner, never the installed app."""
import argparse
import json
import os
import signal
import subprocess
import sys
import time
from pathlib import Path

from lab_config import PRIVATE, ROOT


def running():
    receipt = PRIVATE / "owner-running.json"
    if not receipt.exists():
        return None
    pid = json.loads(receipt.read_text())["pid"]
    process = Path("/proc") / str(pid)
    if not process.exists():
        return None
    try:
        status = process.joinpath("status").read_text()
        if any(line.startswith("State:") and line.split()[1] in ("Z", "X") for line in status.splitlines()):
            return None
        command = process.joinpath("cmdline").read_bytes().split(b"\0")
        cwd = process.joinpath("cwd").resolve(strict=True)
    except (FileNotFoundError, ProcessLookupError):
        return None
    if not any(arg.endswith(b"/lab_owner.py") for arg in command) or cwd != ROOT.parents[1]:
        raise RuntimeError("PID ownership changed; refusing lifecycle action")
    return pid


def main(action):
    pid = running()
    lost_socket = action == "start" and pid and not Path(json.loads((PRIVATE / "owner.json").read_text())["socket_path"]).exists()
    if (action == "stop" or lost_socket) and pid:
        os.kill(pid, signal.SIGTERM)
        for _ in range(50):
            if not running():
                break
            time.sleep(0.1)
        else:
            raise TimeoutError("Lab owner did not stop; no forced termination performed")
        pid = None
    if action == "start" and not pid:
        log = PRIVATE / "owner.log"
        descriptor = os.open(log, os.O_WRONLY | os.O_APPEND | os.O_CREAT, 0o600)
        with os.fdopen(descriptor, "a") as output:
            process = subprocess.Popen([sys.executable, "-B", "-X", "faulthandler", str(ROOT / "lab_owner.py")],
                cwd=ROOT.parents[1], stdin=subprocess.DEVNULL, stdout=output, stderr=output, start_new_session=True)
        for _ in range(50):
            if running() == process.pid:
                break
            if process.poll() is not None:
                raise RuntimeError("Lab owner failed to start; inspect its private log")
            time.sleep(0.1)
        else:
            raise TimeoutError("Lab owner startup not confirmed")
    print(json.dumps({"action": action, "pid": running(), "profile": "ISOLATED_LAB"}))


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("action", choices=("start", "stop", "status"))
    main(parser.parse_args().action)
