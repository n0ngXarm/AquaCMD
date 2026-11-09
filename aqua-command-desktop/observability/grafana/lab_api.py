"""Authenticated calls scoped to this Lab; secrets never appear in command arguments."""
import base64
import json
import os
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from lab_config import PRIVATE


def request(path, data=None, *, method=None, identity="admin"):
    state = json.loads((PRIVATE / "state.json").read_text())
    assert state["url"].startswith("http://127.0.0.1:")
    headers = {"Accept": "application/json"}
    if identity == "service":
        headers["Authorization"] = "Bearer " + (PRIVATE / "mcp-token").read_text().strip()
    elif identity != "anonymous":
        login = "aqua-lab-admin" if identity == "admin" else "aqua-viewer"
        password = (PRIVATE / ("admin-password" if identity == "admin" else "viewer-password")).read_text().strip()
        headers["Authorization"] = "Basic " + base64.b64encode((login + ":" + password).encode()).decode()
    body = json.dumps(data).encode() if data is not None else None
    if body is not None:
        headers["Content-Type"] = "application/json"
    req = Request(state["url"] + path, body, headers=headers, method=method)
    try:
        with urlopen(req, timeout=10) as response:
            raw = response.read(16 * 1024 * 1024)
            return response.status, json.loads(raw) if raw else None
    except HTTPError as error:
        return error.code, json.loads(error.read())


def bootstrap():
    status, health = request("/api/health", identity="anonymous")
    assert status == 200 and health["database"] == "ok", (status, health)
    users = request("/api/org/users")[1]
    if not any(u["login"] == "aqua-viewer" for u in users):
        status, result = request("/api/admin/users", {"name": "AQUA Lab Operator", "login": "aqua-viewer",
            "password": (PRIVATE / "viewer-password").read_text().strip(), "OrgId": 1})
        assert status == 200, status
        assert request("/api/org/users/" + str(result["id"]), {"role": "Viewer"}, method="PATCH")[0] == 200
    if not (PRIVATE / "mcp-token").exists():
        status, account = request("/api/serviceaccounts", {"name": "aqua-lab-mcp-readonly", "role": "Viewer", "isDisabled": False})
        assert status == 201, (status, account)
        status, token = request("/api/serviceaccounts/" + str(account["id"]) + "/tokens", {"name": "codex-lab-readonly", "secondsToLive": 604800})
        assert status == 200, status
        descriptor = os.open(PRIVATE / "mcp-token", os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(descriptor, "w") as output:
            output.write(token["key"])
    role = next(u["role"] for u in request("/api/org/users")[1] if u["login"] == "aqua-viewer")
    assert role == "Viewer"
    print(json.dumps({"health": health, "operator_role": role, "mcp_role": "Viewer", "secrets": "PRIVATE_FILES_ONLY"}, indent=2))


if __name__ == "__main__":
    import sys
    if sys.argv[1:] == ["--reload"]:
        from lab_config import prepare
        prepare()
        for kind in ("datasources", "dashboards"):
            status, result = request("/api/admin/provisioning/" + kind + "/reload", method="POST")
            assert status == 200, (status, result)
        print("Lab provisioning reloaded")
    else:
        assert not sys.argv[1:]
        bootstrap()
