"""Small authenticated GET-only HTTP transport. No request or credential logging."""
import hmac
import json
import socketserver
import threading
from http.server import BaseHTTPRequestHandler
from urllib.parse import parse_qs, urlsplit


class Handler(BaseHTTPRequestHandler):
    server_version = "AquaProjection"
    sys_version = ""

    def setup(self):
        self.request.settimeout(2)
        super().setup()

    def log_message(self, *_):
        pass

    def reply(self, status, payload):
        data = json.dumps(payload, allow_nan=False, separators=(",", ":")).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Connection", "close")
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self):
        supplied = self.headers.get("Authorization", "")
        expected = "Bearer " + self.server.token
        if not hmac.compare_digest(supplied.encode(), expected.encode()):
            return self.reply(401, {"state": "UNAUTHORIZED"})
        if len(self.path) > 2048:
            return self.reply(400, {"state": "INVALID_REQUEST"})
        parsed = urlsplit(self.path)
        params = parse_qs(parsed.query, keep_blank_values=True)
        if parsed.netloc or parsed.fragment or set(params) - {"window", "tag_id", "from", "to"} or any(len(v) != 1 for v in params.values()):
            return self.reply(400, {"state": "INVALID_REQUEST"})
        try:
            result = self.server.project(parsed.path, {k: v[0] for k, v in params.items()})
            return self.reply(200, result)
        except KeyError:
            return self.reply(404, {"state": "NOT_FOUND"})
        except ValueError:
            return self.reply(400, {"state": "INVALID_REQUEST"})
        except Exception:
            return self.reply(503, {"state": "UNAVAILABLE"})

    def reject_method(self):
        self.reply(405, {"state": "READ_ONLY"})

    do_POST = do_PUT = do_PATCH = do_DELETE = do_OPTIONS = do_HEAD = reject_method


class BoundedThreads(socketserver.ThreadingMixIn):
    daemon_threads = True
    request_queue_size = 4

    def process_request(self, request, client_address):
        if not self.slots.acquire(blocking=False):
            self.shutdown_request(request)
            return
        try:
            super().process_request(request, client_address)
        except Exception:
            self.slots.release()
            raise

    def process_request_thread(self, request, client_address):
        try:
            super().process_request_thread(request, client_address)
        finally:
            self.slots.release()

    def handle_error(self, *_):
        pass


class UnixServer(BoundedThreads, socketserver.UnixStreamServer):
    def __init__(self, path, token, project):
        self.token, self.project, self.slots = token, project, threading.BoundedSemaphore(8)
        super().__init__(str(path), Handler)
