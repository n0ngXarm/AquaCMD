"""Start only this new internal rootless Lab. No host service/firewall changes."""
import json
import os
import subprocess

from lab_config import PRIVATE, ROOT, enable_owner, prepare, save_state, socket_directory

LABEL = "io.aquacommand.lab=hybrid-20261105"
NETWORK = "aqua-hybrid-20261105"
GRAFANA = "docker.io/grafana/grafana@sha256:488984b716c0862639f91a698adbe2862677a5a07bad42da5f03f3030883b205"
PYTHON = "docker.io/library/python@sha256:1acc95d63ef1c8cc902e9a10a8ae080e1377325771d2819beb48156e1b3b9673"


def podman(*args):
    result = subprocess.run(["podman", *args], capture_output=True, text=True, timeout=90)
    if result.returncode:
        raise RuntimeError("Podman failed: " + result.stderr.strip()[:2000])
    return result.stdout.strip()


def common_args():
    return ["--detach", "--pull=never", "--network", NETWORK, "--label", LABEL,
        "--userns=keep-id", "--user", f"{os.getuid()}:{os.getgid()}", "--cap-drop=ALL",
        "--security-opt=no-new-privileges", "--read-only", "--pids-limit=128",
        "--restart=on-failure:3", "--tmpfs=/tmp:rw,noexec,nosuid,size=64m"]


def start_proxy():
    return podman("run", *common_args(), "--name", "aqua-hybrid-projection", "--network-alias=aqua-projection",
        "--security-opt=label=disable",
        "--memory=128m", "--cpus=0.5", "--env=AQUA_PROXY_CONTAINER=1", "--env=PYTHONDONTWRITEBYTECODE=1",
        "--env=PYTHONPATH=/app", "--volume", f"{ROOT.parents[1] / 'desktop/observability'}:/app/observability:ro,z",
        "--volume", f"{socket_directory()}:/run/aqua:ro,z",
        "--volume", f"{PRIVATE / 'projection-token'}:/run/secrets/projection-token:ro,z",
        PYTHON, "python3", "-m", "observability.proxy", "--token-file", "/run/secrets/projection-token",
        "--socket-path", "/run/aqua/api.sock")


def start_grafana(port=""):
    return podman("run", *common_args(), "--name", "aqua-hybrid-grafana", "--memory=768m", "--cpus=2",
        "--env=GF_PATHS_PLUGINS=/opt/grafana-plugins",
        f"--publish=127.0.0.1:{port}:3000", "--volume", f"{PRIVATE / 'data'}:/var/lib/grafana:rw,z",
        "--volume", f"{ROOT / 'grafana.ini'}:/etc/grafana/grafana.ini:ro,z",
        "--volume", f"{PRIVATE / 'provisioning'}:/etc/grafana/provisioning:ro,z",
        "--volume", f"{ROOT / 'dashboards'}:/etc/grafana/dashboards:ro,z",
        "--volume", f"{ROOT / 'plugins'}:/opt/grafana-plugins:ro,z",
        "--volume", f"{PRIVATE / 'admin-password'}:/run/secrets/admin-password:ro,z",
        "--volume", f"{PRIVATE / 'grafana-key'}:/run/secrets/grafana-key:ro,z", GRAFANA)


def main():
    prepare()
    # No replacement/deletion of resources: pre-existing names cause an explicit failure.
    podman("network", "create", "--internal", "--label", LABEL, NETWORK)
    proxy = start_proxy()
    grafana = start_grafana()
    bindings = json.loads(podman("inspect", "aqua-hybrid-grafana"))[0]["NetworkSettings"]["Ports"]["3000/tcp"]
    if len(bindings) != 1 or bindings[0]["HostIp"] != "127.0.0.1":
        raise RuntimeError("Unexpected UI binding")
    url = "http://127.0.0.1:" + bindings[0]["HostPort"]
    state = {"url": url, "network": NETWORK, "proxy": proxy, "grafana": grafana,
        "grafana_image": GRAFANA, "python_image": PYTHON}
    save_state(state)
    enable_owner(url)
    print(json.dumps(state, indent=2))


if __name__ == "__main__":
    main()
