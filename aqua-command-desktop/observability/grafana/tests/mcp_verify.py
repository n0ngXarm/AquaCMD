"""Real MCP stdio handshake and self-described capability checks, no AI subprocess."""
import json
import os
import select
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from lab_api import request


class Client:
    def __init__(self):
        self.process = subprocess.Popen([sys.executable, str(ROOT / "mcp_launch.py")],
            stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        self.buffer, self.sequence = b"", 0

    def send(self, method, params, *, notification=False):
        self.sequence += 1
        message = {"jsonrpc": "2.0", "method": method, "params": params}
        if not notification:
            message["id"] = self.sequence
        self.process.stdin.write(json.dumps(message).encode() + b"\n")
        self.process.stdin.flush()
        if notification:
            return
        deadline = time.monotonic() + 20
        while time.monotonic() < deadline:
            if b"\n" in self.buffer:
                line, self.buffer = self.buffer.split(b"\n", 1)
                reply = json.loads(line)
                if reply.get("id") == self.sequence:
                    assert not reply.get("error"), reply
                    return reply["result"]
                continue
            ready, _, _ = select.select([self.process.stdout], [], [], max(0, deadline - time.monotonic()))
            if ready:
                chunk = os.read(self.process.stdout.fileno(), 65536)
                if not chunk:
                    raise RuntimeError("MCP process closed stdout")
                self.buffer += chunk
        raise TimeoutError(method)

    def close(self):
        self.process.terminate()
        self.process.wait(timeout=5)


def main():
    client = Client()
    try:
        initialized = client.send("initialize", {"protocolVersion": "2025-06-18", "capabilities": {},
            "clientInfo": {"name": "aqua-lab-capability-verifier", "version": "1"}})
        client.send("notifications/initialized", {}, notification=True)
        tools = client.send("tools/list", {})["tools"]
        result = {"initialize": initialized, "tools": tools, "calls": [],
                  "scope": "ISOLATED_LAB_VIEWER", "current_chat_tools": "NOT_ADVERTISED"}
        if "--calls" in sys.argv[1:]:
            expected = {"list_datasources", "search_dashboards", "get_dashboard_summary", "get_dashboard_panel_queries", "run_panel_query", "user_info"}
            by_name = {tool["name"]: tool for tool in tools}
            assert expected <= by_name.keys()
            assert all(tool.get("annotations", {}).get("readOnlyHint") is True for tool in tools)
            calls = [("list_datasources", {}), ("check_datasources_health", {"uids": ["aqua-runtime"]}),
                ("search_dashboards", {"query": "AQUA"}), ("get_dashboard_summary", {"uid": "aqua-f3"}),
                ("get_dashboard_panel_queries", {"uid": "aqua-f3", "panelId": 2}),
                ("run_panel_query", {"dashboardUid": "aqua-f3", "panelIds": [2], "queryIndex": 0}),
                ("run_panel_query", {"dashboardUid": "aqua-f3", "panelIds": [2], "queryIndex": 1}),
                ("user_info", {})]
            for name, arguments in calls:
                reply = client.send("tools/call", {"name": name, "arguments": arguments})
                assert reply.get("isError") is not True, (name, reply)
                if name == "run_panel_query":
                    decoded = json.loads(reply["content"][0]["text"])
                    panels = decoded["results"]
                    assert panels, decoded
                    for panel in panels.values():
                        assert not panel.get("error") and panel.get("results"), panel
                        for query in panel["results"].values():
                            assert query.get("status") == 200 and not query.get("error"), query
                            assert query.get("frames"), query
                            for frame in query["frames"]:
                                assert len(frame["data"]["values"][0]) > 0, frame
                result["calls"].append({"name": name, "arguments": arguments, "result": reply})
            status, user = request("/api/user", identity="service")
            assert status == 200 and user["isGrafanaAdmin"] is False
            status, dashboard = request("/api/dashboards/uid/aqua-f3", identity="service")
            assert status == 200 and dashboard["meta"]["canEdit"] is False
            status, _ = request("/api/dashboards/db", {"dashboard": dashboard["dashboard"], "overwrite": True}, identity="service")
            assert status == 403, "Service-account dashboard write permitted"
            result["effective_permissions"] = {"isGrafanaAdmin": False, "canEdit": False, "write_status": status}
        evidence = ROOT.parents[3] / "evidence"
        evidence.mkdir(exist_ok=True)
        (evidence / "mcp-capabilities.json").write_text(json.dumps(result, indent=2) + "\n")
        print(json.dumps({"server": initialized.get("serverInfo"), "protocol": initialized.get("protocolVersion"),
                          "tools": [tool["name"] for tool in tools], "calls_completed": len(result["calls"])}, indent=2))
    finally:
        client.close()


if __name__ == "__main__":
    main()
