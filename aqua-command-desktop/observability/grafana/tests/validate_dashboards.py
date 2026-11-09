"""Provisioning boundary checks, independent of a running Grafana instance."""
import json
import subprocess
from pathlib import Path
from urllib.parse import urlsplit


def validate(path):
    value = json.loads(path.read_text())
    assert value["editable"] is False, path
    assert value["timezone"] == "utc", path
    assert value["refresh"] == "5s", path
    assert value["uid"].startswith("aqua-"), path
    assert "secureJsonData" not in value, path
    positions, ids = [], set()
    for panel in value["panels"]:
        assert panel["id"] not in ids, path
        ids.add(panel["id"])
        grid = panel["gridPos"]
        assert 0 <= grid["x"] and grid["x"] + grid["w"] <= 24, path
        for other in positions:
            assert grid["x"] >= other["x"] + other["w"] or other["x"] >= grid["x"] + grid["w"] or grid["y"] >= other["y"] + other["h"] or other["y"] >= grid["y"] + grid["h"], path
        positions.append(grid)
        for target in panel.get("targets", []):
            assert target["source"] == "url" and target["type"] == "json", path
            assert target["parser"] == "backend" and target["url_options"] == {"method": "GET"}, path
            parsed = urlsplit(target["url"])
            assert parsed.scheme == "http" and parsed.netloc == "aqua-projection:8080", path
            assert parsed.path.startswith("/v1/runtime/"), path
            assert target["datasource"]["uid"] == "aqua-runtime", path
            assert not target.get("data"), path
        if panel["type"] == "nodeGraph":
            assert {t["format"] for t in panel["targets"]} == {"node-graph-nodes", "node-graph-edges"}, path
    return {"file": path.name, "uid": value["uid"], "panels": len(ids), "result": "PASS"}


if __name__ == "__main__":
    root = Path(__file__).resolve().parents[1]
    # Check every existing private file and representative paths before packaging.
    private_paths = list((root / "private").rglob("*")) + [root / "private/mcp-token", root / "private/state.json"]
    for private in private_paths:
        if not private.is_dir():
            assert subprocess.run(["git", "check-ignore", "--quiet", str(private)], cwd=root).returncode == 0, "Unignored private file"
    paths = sorted((root / "dashboards").glob("*.json"))
    assert paths, "No dashboards"
    print(json.dumps([validate(path) for path in paths], indent=2))
