"""SIMULATED test endpoint: real loopback TCP listener, separate test process."""
import json
import socket

with socket.socket() as listener:
    listener.bind(('127.0.0.1',0))
    listener.listen(1)
    listener.settimeout(10)
    print(json.dumps({'source':'sim','label':'SIMULATED','host':listener.getsockname()[0],'port':listener.getsockname()[1]}),flush=True)
    with listener.accept()[0]:
        pass
