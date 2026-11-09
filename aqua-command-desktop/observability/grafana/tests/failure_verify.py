"""Real isolated Lab consumer/source failures, recovery, and core loopback regression."""
import hashlib
import http.client
import json
import sqlite3
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from lab_api import request
from lab_config import PRIVATE, socket_directory
from lab_owner_manage import main as owner_action, running
from lab_start import podman
from lab_diagnose import Unix


def projection(path="health", method="GET", authenticated=True):
    client = Unix("localhost")
    try:
        headers = {"Authorization": "Bearer " + (PRIVATE / "projection-token").read_text().strip()} if authenticated else {}
        client.request(method, "/v1/runtime/" + path, headers=headers)
        response = client.getresponse()
        return response.status, json.loads(response.read())
    finally:
        client.close()


def query_graph():
    status, dashboard = request("/api/dashboards/uid/aqua-f3", identity="viewer")
    assert status == 200
    queries = next(p for p in dashboard["dashboard"]["panels"] if p["id"] == 2)["targets"]
    return request("/api/ds/query", {"from": "now-1h", "to": "now", "queries": queries}, identity="viewer")


def wait_health():
    for _ in range(40):
        try:
            if request("/api/health", identity="anonymous")[0] == 200:
                return
        except (OSError, http.client.HTTPException):
            pass
        time.sleep(0.25)
    raise TimeoutError("Lab Grafana did not recover")


def main():
    state = json.loads((PRIVATE / "state.json").read_text())
    for key in ("grafana", "proxy"):
        info = json.loads(podman("inspect", state[key]))[0]
        assert info["Config"]["Labels"]["io.aquacommand.lab"] == "hybrid-20261105"
    owner_pid = running()
    assert owner_pid
    result = {"scope": "ISOLATED_LAB", "checks": []}
    for method, path, auth, expected in (("GET", "health", False, 401), ("POST", "health", True, 405),
            ("GET", "unknown", True, 404), ("GET", "history?window=all", True, 400),
            ("GET", "health?token=blocked", True, 400), ("GET", "health", True, 200)):
        status, _ = projection(path, method, auth)
        assert status == expected, (method, path, status)
        result["checks"].append({"method": method, "path": path, "status": status})
    db_path = PRIVATE / "profile/.config/aqua-command/aqua_command.db"
    before_hash = hashlib.sha256(db_path.read_bytes()).hexdigest()
    for _ in range(20):
        assert projection("history?window=7d")[0] == 200
    assert hashlib.sha256(db_path.read_bytes()).hexdigest() == before_hash
    result["sqlite_read_load"] = {"requests": 20, "db_sha256_unchanged": True}
    owner_stopped = grafana_stopped = False
    try:
        owner_action("stop")
        owner_stopped = True
        status, data = query_graph()
        assert status >= 400 and all(row.get("error") and not any(
            len(column) for frame in row.get("frames", []) for column in frame["data"]["values"])
            for row in data["results"].values()), ("Source failure returned measurements", status)
        result["source_down"] = {"status": status, "query_errors": len(data["results"]), "measurement_rows": 0}
        owner_action("start")
        owner_stopped = False
        status, data = query_graph()
        assert status == 200 and all(not row.get("error") and row.get("frames") for row in data["results"].values())
        result["source_recovery"] = "PASS"
        podman("stop", "--time=5", state["grafana"])
        grafana_stopped = True
        try:
            request("/api/health", identity="anonymous")
        except (OSError, http.client.HTTPException):
            pass
        else:
            raise AssertionError("Grafana still reachable after stop")
        first = projection()[1]["captured_at"]
        time.sleep(6)
        assert running() and projection()[1]["captured_at"] != first
        result["consumer_down"] = {"gtk_owner_alive": True, "producer_capture_advances": True}
        runner = ROOT.parents[5] / "artifacts/aqua-f3-dialog/run_isolated.py"
        command = [sys.executable, "-B", "-X", "faulthandler", str(runner), "--project", str(ROOT.parents[1]),
            "--pattern", "test_opcua_5s_polling_and_task_engine.py", "--pattern", "test_network_resilience_and_recovery.py"]
        log = ROOT.parents[3] / "evidence/core-consumer-down.log"
        print("Grafana stopped; running supplied core polling/storage/task/outbox loopback tests", flush=True)
        with log.open("w") as output:
            core = subprocess.run(command, stdout=output, stderr=subprocess.STDOUT, timeout=240)
        result["core_consumer_down"] = {"exit_code": core.returncode, "log": log.name}
        podman("start", state["grafana"])
        grafana_stopped = False
        wait_health()
        status, data = query_graph()
        assert status == 200 and all(row.get("frames") and not row.get("error") for row in data["results"].values())
        result["consumer_recovery"] = "PASS"
        assert core.returncode == 0, "Supplied core regression failed; inspect core-consumer-down.log"
    finally:
        if owner_stopped:
            owner_action("start")
        if grafana_stopped:
            podman("start", state["grafana"])
        (ROOT.parents[3] / "evidence/failure-recovery.json").write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
