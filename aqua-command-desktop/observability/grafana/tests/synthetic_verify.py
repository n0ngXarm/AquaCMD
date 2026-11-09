"""Explicit synthetic Infinity acceptance; never touches the runtime datasource/owner."""
import copy
import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT.parents[1] / "desktop")]
from build_f3 import build
from dashboard_common import fields, panel, text
from lab_api import request
from observability.adapter import COLORS, graph
from observability.contract import Contract
from opcua_store import TagObservation

UID = "aqua-synthetic-acceptance"
DS = {"type": "yesoreyeram-infinity-datasource", "uid": UID}
STATES = ("CONFIGURED", "UNKNOWN", "STALE", "REACHABLE", "TCP_CONNECTED", "OPC_UA_CONNECTED", "READ_VERIFIED", "ERROR")


def inline(query, data, root=""):
    query = copy.deepcopy(query)
    query.update(datasource=DS, source="inline", data=json.dumps(data), url="", root_selector=root)
    return query


def prepare():
    # Reserved documentation address; it is only a value passed to the pure contract.
    endpoint = "opc.tcp://192.0.2.10:4840"
    now = time.time()
    contract = Contract(b"SYNTHETIC_ACCEPTANCE_ONLY_KEY_0000")
    rows = []
    cases = [("GOOD_ZERO", 0, "GOOD", now), ("GOOD_FALSE", False, "GOOD", now),
             ("BAD", False, "BAD", now), ("UNKNOWN", 0, "NOT_OBSERVED", now),
             ("STALE", 9, "GOOD", now - 30)]
    for label, value, quality, observed in cases:
        obs = TagObservation(label, value=value, quality=quality,
            arrival_time=datetime.fromtimestamp(observed, timezone.utc), endpoint_url=endpoint)
        row = contract.tag(obs, {endpoint: "synthetic-device"}, now)
        rows.append(dict(row, case=label, numeric=row["value"] if type(row["value"]) in (int, float) else None))
    devices = [{"device_id": "synthetic-" + state, "alias": state, "kind": "OPC_UA_SOURCE",
        "connection_status": state, "data_quality": "GOOD" if state == "READ_VERIFIED" else "NOT_OBSERVED",
        "session_state": "UNKNOWN", "tcp_status": "UNKNOWN", "certificate_status": "UNKNOWN",
        "provenance": "SYNTHETIC_ACCEPTANCE", "observed_at": None, "target_ref": None}
        for state in STATES]
    topology = graph(devices, [], {}, now)
    dashboard = build()
    dashboard.update(uid=UID, title="SYNTHETIC · Acceptance only · never runtime", id=None,
        tags=["SYNTHETIC", "acceptance-only"], description="Explicit isolated synthetic fixtures; no live fallback", links=[], refresh="")
    topology_panel = next(p for p in dashboard["panels"] if p["type"] == "nodeGraph")
    topology_panel.update(datasource=DS, gridPos={"x": 0, "y": 10, "w": 24, "h": 16}, title="SYNTHETIC · State colors")
    topology_panel["targets"] = [inline(q, topology, root=q["root_selector"]) for q in topology_panel["targets"]]
    table = panel(10, "SYNTHETIC · NULL / zero / false", "table", 3, 7)
    table["datasource"] = DS
    from dashboard_common import query
    table["targets"] = [inline(query("unused", fields("case", "quality", "value") + [("numeric", "", "number")]), rows)]
    dashboard["panels"] = [text(1, "# SYNTHETIC ACCEPTANCE ONLY\nThese values are artificial fixtures. RUNTIME datasource and owner are untouched."), table, topology_panel]
    status, _ = request("/api/datasources/uid/" + UID)
    if status == 404:
        status, _ = request("/api/datasources", dict(DS, name="SYNTHETIC · isolated acceptance", access="proxy", jsonData={"auth_method": "none"}))
        assert status == 200, status
    status, _ = request("/api/dashboards/db", {"dashboard": dashboard, "overwrite": True})
    assert status == 200, status
    return dashboard, rows, topology


def verify():
    dashboard, rows, topology = prepare()
    evidence = {"stream": "SYNTHETIC", "runtime_untouched": True, "panels": []}
    for panel in dashboard["panels"]:
        if not panel.get("targets"):
            continue
        status, result = request("/api/ds/query", {"from": "now-1h", "to": "now", "queries": panel["targets"]}, identity="viewer")
        assert status == 200, (status, result)
        for ref, data in result["results"].items():
            assert not data.get("error"), (ref, data)
            assert data.get("frames"), (ref, data)
            for frame in data["frames"]:
                columns = {f["name"]: v for f, v in zip(frame["schema"]["fields"], frame["data"]["values"])}
                if panel["id"] == 10:
                    assert columns["numeric"] == [0, None, None, None, None], columns
                    assert columns["value"] == ["0", "false", None, None, None], columns
                elif ref == "A":
                    assert columns["mainStat"][:len(STATES)] == [n["display_state"] for n in topology["nodes"][:len(STATES)]], columns
                    assert columns["color"][:len(STATES)] == [COLORS.get(d, "#91a0b4") for d in STATES], columns
                evidence["panels"].append({"id": panel["id"], "ref": ref, "schema": frame["schema"], "values": columns})
    (ROOT.parents[3] / "evidence/synthetic-queries.json").write_text(json.dumps(evidence, indent=2) + "\n")
    print(json.dumps({"result": "PASS", "stream": "SYNTHETIC", "frames": len(evidence["panels"])}))


def cleanup():
    for path in ("/api/dashboards/uid/" + UID, "/api/datasources/uid/" + UID):
        assert request(path, method="DELETE")[0] in (200, 404)
    print("Synthetic dashboard and datasource removed")


if __name__ == "__main__":
    cleanup() if sys.argv[1:] == ["--cleanup"] else verify()
