"""Inject this Lab's Viewer token into the official MCP process, never argv/TOML."""
import json
import os
import sys

from lab_config import PRIVATE, ROOT

sys.path.insert(0, str(ROOT.parents[1] / "desktop"))
from observability.integration import local_url, private_file


def main():
    state = json.loads(private_file(PRIVATE / "state.json"))
    url = local_url(state["url"])
    environment = os.environ.copy()
    environment.update(GRAFANA_URL=url,
        GRAFANA_SERVICE_ACCOUNT_TOKEN=private_file(PRIVATE / "mcp-token"),
        GRAFANA_USAGE_STATS="disabled", DO_NOT_TRACK="1")
    binary = str(ROOT / "bin/mcp-grafana")
    args = [binary, "--disable-write", "--enabled-tools=search,datasource,dashboard,runpanelquery,user",
            "--usage-stats=disabled", "--log-level=error"]
    os.execve(binary, args, environment)


if __name__ == "__main__":
    main()
