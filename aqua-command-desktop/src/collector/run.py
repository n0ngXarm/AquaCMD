"""Manually started sequential transport/OPC UA collector with an explicit optional interval."""
import argparse
import asyncio
import json
import signal
import socket
import sqlite3
import sys
import threading
import time
from importlib.metadata import version
from pathlib import Path

from .probe_once import EvidenceStore,collect_transport,load_settings
from .opcua_read import read_target

IP_FORWARD_PATH=Path('/proc/sys/net/ipv4/ip_forward')


def ip_forward_check(path=IP_FORWARD_PATH):
    started=time.perf_counter();detail={'path':str(path)}
    try:
        detail['raw']=path.read_text()
        value=int(detail['raw'].strip())
        if value not in (0,1):raise ValueError('Kernel ip_forward value is not 0 or 1')
        detail['value']=value
        return 'ok',None,(time.perf_counter()-started)*1000,detail
    except (OSError,ValueError) as error:
        return 'ERROR',str(error),(time.perf_counter()-started)*1000,detail


def run(config_path,db_path,output=print,*,loop=False,stop_event=None):
    settings=load_settings(config_path)
    if loop and settings['interval_s'] is None:raise ValueError('Loop mode requires an explicit interval_s in private configuration')
    stop=stop_event if stop_event is not None else threading.Event()
    store=EvidenceStore(db_path)
    emit=lambda row:output(json.dumps(row,ensure_ascii=False))
    try:
        hostname=socket.gethostname()
        emit(store.record(hostname,'ip_forward',ip_forward_check()))
        started=time.perf_counter();library_version=version('asyncua')
        emit(store.record(hostname,'ua_client',('ok',None,(time.perf_counter()-started)*1000,{'library':'asyncua','version':library_version,
            'mode':'read-only','interval_s':settings['interval_s'],'loop_requested':loop})))
        while not stop.is_set():
            started=time.monotonic()
            collect_transport(settings,store,output)
            for target in settings['targets']:
                if stop.is_set():break
                if 'ua' in target:asyncio.run(read_target(target,settings['tcp_timeout_s'],store,output))
            if not loop:break
            if stop.wait(max(0,settings['interval_s']-(time.monotonic()-started))):break
    finally:
        store.close()


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--config',type=Path,default=Path.home()/'.config/aqua-command/probe_targets.json')
    parser.add_argument('--db',type=Path,default=Path.home()/'.local/share/aqua-command/probe/data.db')
    parser.add_argument('--loop',action='store_true')
    options=parser.parse_args(argv)
    stop=threading.Event()
    for number in (signal.SIGINT,signal.SIGTERM):signal.signal(number,lambda *_:stop.set())
    try:run(options.config,options.db,loop=options.loop,stop_event=stop)
    except (OSError,ValueError,KeyError,sqlite3.Error) as error:
        print(f'{type(error).__name__}: {error}',file=sys.stderr);return 1
    return 0


if __name__=='__main__':sys.exit(main())
