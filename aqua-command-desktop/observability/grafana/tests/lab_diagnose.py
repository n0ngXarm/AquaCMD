"""Read-only Lab transport/isolation diagnostics; no secret values are printed."""
import http.client
import json
import os
import socket
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from lab_config import PRIVATE, socket_directory
from lab_start import NETWORK, podman


class Unix(http.client.HTTPConnection):
    def connect(self):
        self.sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        self.sock.settimeout(2)
        self.sock.connect(str(socket_directory() / "api.sock"))


def main():
    path = socket_directory() / "api.sock"
    info = path.stat()
    result = {"host_socket": {"uid": info.st_uid, "mode": oct(info.st_mode & 0o777),
        "selinux": os.getxattr(path, "security.selinux").decode().strip("\x00")}}
    client = Unix("localhost")
    try:
        client.request("GET", "/v1/runtime/health", headers={"Authorization": "Bearer " + (PRIVATE / "projection-token").read_text().strip()})
        response = client.getresponse()
        result["host_unix"] = {"status": response.status, "state": json.loads(response.read())["state"]}
    except Exception as error:
        result["host_unix"] = {"error_type": type(error).__name__}
    finally:
        client.close()
    code = """import json,os,socket
from observability.proxy import UnixConnection
r={'uid':os.getuid(),'socket_exists':os.path.exists('/run/aqua/api.sock'),
 'process_label':open('/proc/self/attr/current').read().strip()}
st=os.stat('/run/aqua/api.sock')
r.update(socket_uid=st.st_uid,socket_mode=oct(st.st_mode & 0o777))
try:
 c=UnixConnection('/run/aqua/api.sock')
 token=open('/run/secrets/projection-token').read().strip()
 c.request('GET','/v1/runtime/health',headers={'Authorization':'Bearer '+token})
 response=c.getresponse()
 r.update(status=response.status,state=json.loads(response.read()).get('state'))
except Exception as e:
 r.update(error_type=type(e).__name__,errno=getattr(e,'errno',None))
r['default_route']=any(line.split()[1]=='00000000' for line in open('/proc/net/route').read().splitlines()[1:])
print(json.dumps(r))
"""
    result["container_unix"] = json.loads(podman("exec", "aqua-hybrid-projection", "python3", "-c", code))
    network = json.loads(podman("network", "inspect", NETWORK))[0]
    result["network_internal"] = network["internal"]
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
