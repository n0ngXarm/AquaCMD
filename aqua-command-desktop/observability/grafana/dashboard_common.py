"""Deterministic provisioning helpers. Runtime queries never contain sample data."""
import json
from pathlib import Path

DS = {"type": "yesoreyeram-infinity-datasource", "uid": "aqua-runtime"}
ORIGIN = "http://aqua-projection:8080"


def query(route, fields, *, root="data", format="table", ref="A"):
    return {"refId": ref, "datasource": DS, "type": "json", "source": "url",
        "url": ORIGIN + "/v1/runtime/" + route, "url_options": {"method": "GET"},
        "parser": "backend", "format": format, "root_selector": root,
        "columns": [{"selector": name, "text": label or name, "type": kind}
                    for name, label, kind in fields]}


def panel(ident, title, kind, y, height, targets=(), *, width=24, x=0, description="", unit="none"):
    return {"id": ident, "title": title, "type": kind, "datasource": DS,
        "gridPos": {"x": x, "y": y, "w": width, "h": height},
        "description": description, "targets": list(targets),
        "fieldConfig": {"defaults": {"unit": unit, "noValue": "NO DATA",
            "color": {"mode": "palette-classic"}, "custom": {"spanNulls": False}}, "overrides": []},
        "options": {"showHeader": True, "cellHeight": "sm", "footer": {"show": False}}}


def text(ident, content, y=0, height=3):
    result = panel(ident, "", "text", y, height)
    result.pop("datasource")
    result["options"] = {"mode": "markdown", "content": content}
    return result


def dashboard(uid, title, panels, *, variables=()):
    return {"uid": uid, "title": title, "description": "AQUA COMMAND read-only Hybrid • RUNTIME • UTC",
        "editable": False, "schemaVersion": 41, "version": 1, "style": "dark",
        "tags": ["AQUA", "RUNTIME", "read-only"], "timezone": "utc", "refresh": "5s",
        "time": {"from": "now-1h", "to": "now"}, "timepicker": {"refresh_intervals": ["5s", "10s", "30s", "1m"]},
        "annotations": {"list": []}, "templating": {"list": list(variables)}, "panels": panels,
        "links": [{"title": label, "type": "link", "url": "/d/" + target,
                   "targetBlank": False, "includeVars": False, "keepTime": True}
                  for label, target in (("F1 Monitoring", "aqua-f1"), ("F2 Events", "aqua-f2"),
                    ("F3 Topology", "aqua-f3"), ("F4 Host", "aqua-f4"), ("Diagnostics", "aqua-diagnostics"))]}


def save(filename, value):
    path = Path(__file__).parent / "dashboards" / filename
    path.parent.mkdir(exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n")


def fields(*names):
    return [(name, "", "string") for name in names]
