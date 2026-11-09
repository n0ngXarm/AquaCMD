"""Read-only resource, namespace, mount and secret-redaction evidence for this Lab."""
import json
import os
import sys
import time
from pathlib import Path

import psutil

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from lab_config import PRIVATE
from lab_owner_manage import running
from lab_start import NETWORK, podman


def main():
    state = json.loads((PRIVATE / "state.json").read_text())
    network = json.loads(podman("network", "inspect", NETWORK))[0]
    assert network["internal"] is True and not network["ipv6_enabled"]
    result = {"network_internal": True, "ipv6_enabled": False, "containers": {}, "owner_samples": []}
    for key in ("grafana", "proxy"):
        info = json.loads(podman("inspect", state[key]))[0]
        assert info["Config"]["Labels"]["io.aquacommand.lab"] == "hybrid-20261105"
        host = info["HostConfig"]
        assert host["ReadonlyRootfs"] and not host["Privileged"]
        process_status = podman("exec", state[key], "cat", "/proc/1/status")
        caps = {row.split(":", 1)[0]: int(row.split()[1], 16) for row in process_status.splitlines()
            if row.startswith(("CapEff:", "CapBnd:"))}
        assert caps == {"CapEff": 0, "CapBnd": 0}, caps
        assert any("no-new-privileges" in option for option in host["SecurityOpt"])
        assert not any("aqua_command.db" in mount["Source"] for mount in info["Mounts"])
        routes = podman("exec", state[key], "cat", "/proc/net/route")
        assert not any(row.split()[1] == "00000000" for row in routes.splitlines()[1:])
        ports = info["NetworkSettings"]["Ports"]
        if key == "grafana":
            assert ports["3000/tcp"][0]["HostIp"] == "127.0.0.1" and len(ports["3000/tcp"]) == 1
        else:
            assert not ports
        result["containers"][key] = {"pid": info["State"]["Pid"], "read_only_root": True, "no_default_route": True,
            "no_runtime_db_mount": True, "privileged": False, "capabilities_dropped": "ALL",
            "capability_bitsets": caps, "security_options": host["SecurityOpt"], "memory_limit_bytes": host["Memory"], "ports": ports}
    owner = psutil.Process(running())
    owner.cpu_percent()
    for _ in range(5):
        time.sleep(1)
        result["owner_samples"].append({"timestamp": time.time(), "cpu_percent": owner.cpu_percent(),
            "rss_bytes": owner.memory_info().rss, "threads": owner.num_threads(), "children": len(owner.children())})
    stats = json.loads(podman("stats", "--no-stream", "--format=json", state["grafana"], state["proxy"]))
    result["container_stats"] = stats
    receipt = json.loads((PRIVATE / "owner-running.json").read_text())
    assert receipt["network_audit"]["blocked_external_attempts"] == 0
    assert receipt["polling_state"] == "STOPPED"
    result["owner_runtime"] = {k: receipt[k] for k in ("polling_state", "threads", "observations", "network_audit")}
    # Check source + evidence bytes against the actual private secrets; do not print values.
    secrets = [(PRIVATE / name).read_bytes().strip() for name in
        ("mcp-token", "projection-token", "id-key", "admin-password", "viewer-password", "grafana-key")]
    roots = [ROOT.parents[1] / "desktop/observability", ROOT / "dashboards", ROOT.parents[3] / "evidence"]
    count = 0
    for directory in roots:
        for path in directory.rglob("*"):
            if path.is_file() and path.suffix in (".py", ".json", ".txt", ".log", ".md", ".mjs"):
                data = path.read_bytes()
                assert not any(secret and secret in data for secret in secrets), "Secret exposure detected in evidence/source"
                count += 1
    result["redaction"] = {"files_checked": count, "actual_secret_matches": 0}
    (ROOT.parents[3] / "evidence/resources-isolation.json").write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
