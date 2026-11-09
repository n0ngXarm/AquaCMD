"""Container-only HTTP-to-Unix proxy. The only outgoing connection is AF_UNIX."""
import argparse
import http.client
import json
import os
import socket
import threading
from http.server import HTTPServer
from urllib.parse import urlencode

from .integration import private_file
from .transport import BoundedThreads, Handler


class UnixConnection(http.client.HTTPConnection):
    def __init__(self, path):
        super().__init__("localhost", timeout=2)
        self.path = path

    def connect(self):
        self.sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        self.sock.settimeout(2)
        self.sock.connect(self.path)


class ProxyServer(BoundedThreads, HTTPServer):
    def __init__(self, address, token, socket_path):
        self.token, self.socket_path, self.slots = token, socket_path, threading.BoundedSemaphore(8)
        super().__init__(address, Handler)

    def project(self, path, params):
        if not path.startswith("/v1/runtime/"):
            raise KeyError(path)
        connection = UnixConnection(self.socket_path)
        try:
            target = path + ("?" + urlencode(params) if params else "")
            connection.request("GET", target, headers={"Authorization": "Bearer " + self.token})
            response = connection.getresponse()
            body = response.read(8 * 1024 * 1024 + 1)
            if len(body) > 8 * 1024 * 1024:
                raise ValueError("Projection size exceeded")
            if response.status == 404:
                raise KeyError(path)
            if response.status == 400:
                raise ValueError("Invalid request")
            if response.status != 200:
                raise RuntimeError("Producer unavailable")
            return json.loads(body)
        finally:
            connection.close()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--token-file", required=True)
    parser.add_argument("--socket-path", required=True)
    args = parser.parse_args()
    if os.environ.get("AQUA_PROXY_CONTAINER") != "1":
        raise SystemExit("Run only inside the isolated Lab container")
    server = ProxyServer(("0.0.0.0", 8080), private_file(args.token_file), args.socket_path)
    try:
        server.serve_forever(poll_interval=0.1)
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
