"""Opt-in owner bridge. Importing this module performs no I/O or starts any worker."""
import json
import os
import stat
from pathlib import Path
from urllib.parse import urlencode, urlsplit


def private_file(path, *, binary=False):
    with os.fdopen(os.open(path, os.O_RDONLY | os.O_NOFOLLOW), "rb") as handle:
        info = os.fstat(handle.fileno())
        if info.st_uid != os.getuid() or not stat.S_ISREG(info.st_mode) or stat.S_IMODE(info.st_mode) & 0o077:
            raise PermissionError("Observability configuration and secrets must be private owned files")
        data = handle.read(8193)
        if len(data) > 8192:
            raise ValueError("Configuration too large")
    return data if binary else data.decode().strip()


def local_url(url):
    parsed = urlsplit(url)
    if parsed.scheme != "http" or parsed.hostname not in ("127.0.0.1", "::1", "localhost") or not parsed.port or parsed.username or parsed.password or parsed.query or parsed.fragment or parsed.path not in ("", "/"):
        raise ValueError("Grafana URL must be a loopback HTTP origin")
    return url.rstrip("/")


class Integration:
    def __init__(self, owner, settings, scheduler=None):
        from .adapter import OwnerProjection
        from .contract import Contract
        from .history import History
        from .service import ProjectionService
        self.owner, self.state, self.timer = owner, "STARTING", None
        self.url = local_url(settings["grafana_url"])
        contract = Contract(private_file(settings["id_key_file"], binary=True))
        token = private_file(settings["projection_token_file"])
        self.projection = OwnerProjection(contract)
        self.service = ProjectionService(settings["socket_path"], token, contract,
                                         History(owner.durable_storage.db_path, contract))
        self.service.start()
        try:
            self.capture()
            if scheduler is None:
                from gi.repository import GLib
                scheduler = GLib.timeout_add_seconds
            self.timer = scheduler(5, self.capture)
        except Exception:
            self.service.stop()
            raise

    def capture(self):
        try:
            self.service.publish(self.projection.capture(self.owner))
            self.state = "AVAILABLE"
        except Exception:
            self.state = "ERROR"
        return True

    def record_refresh(self, count):
        try:
            self.projection.record_refresh(count)
        except Exception:
            self.state = "ERROR"

    def link(self, page="network", tag=None):
        uid = {"overview": "aqua-f1", "tasks": "aqua-f2", "network": "aqua-f3", "machine": "aqua-f4",
               "tags": "aqua-f1", "alarms": "aqua-diagnostics", "refresh": "aqua-diagnostics", "utilities": "aqua-diagnostics"}.get(page, "aqua-diagnostics")
        params = {"from": "now-1h", "to": "now", "timezone": "utc"}
        if tag:
            params["var-tag"] = self.projection.contract.identity("tag", tag)
        return self.url + "/d/" + uid + "?" + urlencode(params)

    def stop(self):
        try:
            if self.timer:
                from gi.repository import GLib
                GLib.source_remove(self.timer)
                self.timer = None
            self.service.stop()
            self.state = "STOPPED"
        except Exception:
            self.state = "ERROR"


def start_optional(owner, *, environment=None, scheduler=None):
    environment = os.environ if environment is None else environment
    path = environment.get("AQUA_OBSERVABILITY_CONFIG")
    if not path:
        return None
    try:
        settings = json.loads(private_file(Path(path)))
        if settings.get("enabled") is not True:
            return None
        return Integration(owner, settings, scheduler)
    except Exception:
        # Do not propagate paths, credentials or optional startup errors into core behavior.
        return None
