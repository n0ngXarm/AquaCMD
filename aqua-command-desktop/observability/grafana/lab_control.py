"""Lifecycle actions restricted to the two IDs and label in this Lab's receipt."""
import argparse
import json
from urllib.parse import urlsplit

from lab_config import PRIVATE, enable_owner, prepare, save_state, socket_directory
from lab_start import podman, start_grafana, start_proxy


def main(action):
    state = json.loads((PRIVATE / "state.json").read_text())
    instances = {key: json.loads(podman("inspect", state[key]))[0] for key in ("proxy", "grafana")}
    for value in instances.values():
        assert value["Config"]["Labels"].get("io.aquacommand.lab") == "hybrid-20261105"
    if action == "remount-proxy":
        podman("stop", "--time=5", state["proxy"])
        podman("rm", state["proxy"])
        state["proxy"] = start_proxy()
        save_state(state)
        enable_owner(state["url"])
    elif action == "remount-grafana":
        prepare()
        podman("stop", "--time=5", state["grafana"])
        podman("rm", state["grafana"])
        state["grafana"] = start_grafana(port=urlsplit(state["url"]).port)
        binding = json.loads(podman("inspect", state["grafana"]))[0]["NetworkSettings"]["Ports"]["3000/tcp"]
        assert len(binding) == 1 and binding[0]["HostIp"] == "127.0.0.1"
        state["url"] = "http://127.0.0.1:" + binding[0]["HostPort"]
        save_state(state)
        enable_owner(state["url"])
    elif action in ("restart-grafana", "restart-proxy"):
        podman("restart", "--time=5", state["grafana" if action == "restart-grafana" else "proxy"])
    elif action in ("start", "stop"):
        if action == "start":
            socket_directory()  # Recover the owned private IPC directory after /tmp cleanup.
        for key in (("proxy", "grafana") if action == "start" else ("grafana", "proxy")):
            podman(action, state[key])
        if action == "start":
            binding = json.loads(podman("inspect", state["grafana"]))[0]["NetworkSettings"]["Ports"]["3000/tcp"]
            assert len(binding) == 1 and binding[0]["HostIp"] == "127.0.0.1"
            state["url"] = "http://127.0.0.1:" + binding[0]["HostPort"]
            save_state(state)
            enable_owner(state["url"])
    elif action != "status":
        raise ValueError(action)
    instances = {key: json.loads(podman("inspect", state[key]))[0] for key in instances}
    print(json.dumps({"action": action, "url": state["url"], "grafana_paths":
        [entry for entry in instances["grafana"]["Config"]["Env"] if entry.startswith("GF_PATHS_")], "instances":
        {key: json.loads(podman("inspect", state[key]))[0]["State"]["Status"] for key in instances}}, indent=2))


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("action", choices=("status", "start", "stop", "restart-grafana", "restart-proxy", "remount-proxy", "remount-grafana"))
    main(parser.parse_args().action)
