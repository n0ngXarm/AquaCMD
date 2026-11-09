import http.client
import socket
import tempfile
import threading
import unittest
from pathlib import Path

from observability.transport import UnixServer


class UnixConnection(http.client.HTTPConnection):
    def __init__(self, path):
        super().__init__("localhost", timeout=2)
        self.path = str(path)

    def connect(self):
        self.sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        self.sock.settimeout(2)
        self.sock.connect(self.path)


class TransportTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix="aqua-http-")
        self.addCleanup(self.tmp.cleanup)
        self.path = Path(self.tmp.name) / "api.sock"
        self.calls = []
        def project(path, params):
            self.calls.append((path, params))
            if path != "/v1/runtime/snapshot":
                raise KeyError(path)
            return {"state": "AVAILABLE"}
        self.server = UnixServer(self.path, "k" * 40, project)
        self.thread = threading.Thread(target=self.server.serve_forever, kwargs={"poll_interval": 0.05}, daemon=True)
        self.thread.start()
        self.addCleanup(self.close_server)

    def close_server(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(1)

    def request(self, path, *, method="GET", auth=True):
        connection = UnixConnection(self.path)
        self.addCleanup(connection.close)
        headers = {"Authorization": "Bearer " + "k" * 40} if auth else {}
        connection.request(method, path, headers=headers)
        response = connection.getresponse()
        return response.status, response.read(), dict(response.getheaders())

    def test_authentication_readonly_paths_and_no_cache(self):
        status, _, _ = self.request("/v1/runtime/snapshot", auth=False)
        self.assertEqual(status, 401)
        self.assertEqual(self.calls, [])
        for method in ("POST", "PUT", "PATCH", "DELETE"):
            self.assertEqual(self.request("/v1/runtime/snapshot", method=method)[0], 405)
        self.assertEqual(self.calls, [])
        status, body, headers = self.request("/v1/runtime/snapshot")
        self.assertEqual(status, 200)
        self.assertIn(b"AVAILABLE", body)
        self.assertEqual(headers["Cache-Control"], "no-store")
        self.assertEqual(self.request("/v1/synthetic/snapshot")[0], 404)
        self.assertEqual(self.request("/../private-file")[0], 404)

    def test_unsafe_duplicate_and_unbounded_queries_are_rejected(self):
        for path in ("/v1/runtime/snapshot?window=1h&window=7d", "/v1/runtime/snapshot?url=http://example.invalid",
                     "http://example.invalid/v1/runtime/snapshot", "/" + "a" * 2048):
            self.assertEqual(self.request(path)[0], 400)
        self.assertEqual(self.calls, [])


if __name__ == "__main__":
    unittest.main()
