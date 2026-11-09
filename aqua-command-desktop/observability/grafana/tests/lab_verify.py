"""Real Viewer API/plugin/query checks. Fails on actual API and frame errors."""
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from lab_api import request
from lab_config import ROOT


def verify(uids):
    status, health = request("/api/health", identity="anonymous")
    assert status == 200 and health["database"] == "ok", (status, health)
    status, plugin = request("/api/plugins/yesoreyeram-infinity-datasource/settings", identity="viewer")
    assert status == 200 and plugin["signature"] == "valid", (status, plugin)
    status, datasources = request("/api/datasources", identity="viewer")
    assert status == 200 and any(d["uid"] == "aqua-runtime" for d in datasources), (status, datasources)
    status, source_health = request("/api/datasources/uid/aqua-runtime/health", identity="viewer")
    assert status == 200 and source_health["status"] == "OK", (status, source_health)
    results = {"grafana": health, "plugin": {"version": plugin["info"]["version"], "signature": plugin["signature"]},
        "datasource_health": source_health, "dashboards": []}
    for uid in uids:
        status, response = request("/api/dashboards/uid/" + uid, identity="viewer")
        assert status == 200, (status, response)
        assert response["meta"]["canEdit"] is False and response["meta"]["canSave"] is False
        panels = []
        for panel in response["dashboard"]["panels"]:
            if not panel.get("targets"):
                continue
            now = int(time.time() * 1000)
            queries = [dict(q, intervalMs=5000, maxDataPoints=720) for q in panel["targets"]]
            for query in queries:
                query["url"] = query["url"].replace("${window}", "1h").replace("${tag}", "").replace("${__from}", str(now - 3600000)).replace("${__to}", str(now))
            status, data = request("/api/ds/query", {"from": str(now - 3600000), "to": str(now), "queries": queries}, identity="viewer")
            assert status == 200, (uid, panel["id"], status, data)
            frames = []
            for ref, result in data["results"].items():
                assert not result.get("error"), (uid, panel["id"], ref, result)
                for frame in result.get("frames", []):
                    fields = frame["schema"]["fields"]
                    values = frame["data"]["values"]
                    frames.append({"ref": ref, "name": frame["schema"].get("name"),
                        "fields": [{"name": f["name"], "type": f["type"]} for f in fields],
                        "rows": len(values[0]) if values else 0, "meta": {k: v for k, v in
                            frame["schema"].get("meta", {}).items() if k not in ("custom", "executedQueryString")}})
            panels.append({"id": panel["id"], "type": panel["type"], "frames": frames})
        status, _ = request("/api/dashboards/db", {"dashboard": response["dashboard"], "overwrite": True}, identity="viewer")
        assert status == 403, ("Viewer edit unexpectedly permitted", uid, status)
        results["dashboards"].append({"uid": uid, "viewer_edit_status": status, "panels": panels})
    evidence = ROOT.parents[3] / "evidence"
    evidence.mkdir(exist_ok=True)
    (evidence / "grafana-queries.json").write_text(json.dumps(results, indent=2) + "\n")
    print(json.dumps({"result": "PASS", "grafana": health["version"], "plugin": results["plugin"],
        "datasource_health": source_health["status"], "dashboards": [{"uid": d["uid"],
        "panels_queried": len(d["panels"]), "viewer_edit_status": d["viewer_edit_status"]} for d in results["dashboards"]]}, indent=2))


if __name__ == "__main__":
    verify(sys.argv[1:] or ["aqua-f3"])
