"""Prepare this Lab's private files; never touch the user's application profile."""
import json
import os
import secrets
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent
PRIVATE = ROOT / "private"


def secret(name, *, binary=False):
    path = PRIVATE / name
    if not path.exists():
        data = secrets.token_bytes(32) if binary else secrets.token_urlsafe(36).encode()
        descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(descriptor, "wb") as output:
            output.write(data)
    return path


def prepare():
    PRIVATE.mkdir(mode=0o700, exist_ok=True)
    if PRIVATE.stat().st_mode & 0o077:
        raise PermissionError("Lab private directory must be mode 0700")
    for name in ("data", "provisioning", "provisioning/dashboards", "provisioning/datasources", "provisioning/plugins", "provisioning/alerting", "socket", "profile"):
        (PRIVATE / name).mkdir(mode=0o700, exist_ok=True)
    for name in ("admin-password", "grafana-key", "projection-token", "viewer-password"):
        secret(name)
    secret("id-key", binary=True)
    template = (ROOT / "datasources/runtime.template.json").read_text()
    template = template.replace("${AQUA_PROJECTION_URL}", "http://aqua-projection:8080")
    template = template.replace("${AQUA_PROJECTION_TOKEN}", secret("projection-token").read_text())
    # Grafana scans datasource provisioning only for .yaml/.yml (JSON is valid YAML).
    target = PRIVATE / "provisioning/datasources/runtime.yaml"
    target.write_text(template)
    target.chmod(0o600)
    (PRIVATE / "provisioning/dashboards/aqua.yaml").write_text((ROOT / "provisioning/dashboards/aqua.yaml").read_text())


def socket_directory():
    # AF_UNIX paths are limited to 107 bytes on Linux; the review worktree is longer.
    location = PRIVATE / "socket-location"
    if not location.exists():
        location.write_text(tempfile.mkdtemp(prefix="aqua-grafana-socket-", dir="/tmp"))
        location.chmod(0o600)
    path = Path(location.read_text().strip())
    if path.parent != Path("/tmp") or not path.name.startswith("aqua-grafana-socket-") or path.is_symlink():
        raise PermissionError("Invalid Lab socket location")
    path.mkdir(mode=0o700, exist_ok=True)
    info = path.stat()
    if not path.is_dir() or info.st_uid != os.getuid() or info.st_mode & 0o077 or len(str(path / "api.sock").encode()) > 107:
        raise PermissionError("Invalid private Lab socket directory")
    return path


def save_state(state):
    path = PRIVATE / "state.json"
    path.write_text(json.dumps(state, indent=2) + "\n")
    path.chmod(0o600)


def enable_owner(url):
    config = {"enabled": True, "grafana_url": url, "socket_path": str(socket_directory() / "api.sock"),
        "id_key_file": str(PRIVATE / "id-key"), "projection_token_file": str(PRIVATE / "projection-token")}
    target = PRIVATE / "owner.json"
    target.write_text(json.dumps(config, indent=2) + "\n")
    target.chmod(0o600)


if __name__ == "__main__":
    prepare()
    print("Private Lab configuration prepared; no secret values printed")
