"""One explicit route/ping/TCP pass; every completed check is committed to SQLite."""
import argparse
import errno
import hashlib
import ipaddress
import json
import math
import os
import socket
import ssl
import sqlite3
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlsplit


def load_settings(path):
    config = json.loads(Path(path).read_text())
    if not isinstance(config, dict) or set(config)-{'targets','ping_timeout_s','tcp_timeout_s','ot_subnet','internet','interval_s'}:
        raise ValueError('Unsupported configuration keys')
    entries = config.get('targets')
    if not isinstance(entries, list) or not 1 <= len(entries) <= 64:
        raise ValueError('Select between 1 and 64 explicit targets')
    targets, seen = [], set()
    for item in entries:
        if not isinstance(item, dict) or set(item)-{'host','port','sim','kind','ua'}:
            raise ValueError('Unsupported target keys')
        if 'sim' in item and type(item['sim']) is not bool:
            raise ValueError('Target sim flag must be a boolean')
        if not isinstance(item.get('host'),str):
            raise ValueError('Target host must be an explicit IPv4 string')
        address = ipaddress.ip_address(item['host'])
        port = item.get('port')
        kind = item.get('kind','device')
        if kind not in ('device','router'):
            raise ValueError('Target kind must be device or router')
        if address.version != 4 or address.is_multicast or address.is_unspecified or str(address)=='255.255.255.255' or \
                kind=='device' and (type(port) is not int or not 1 <= port <= 65535):
            raise ValueError('An explicit IPv4 address and TCP port are required')
        if kind=='router' and port is not None:
            raise ValueError('Router checks are ICMP/ARP only; remove its TCP port')
        key = (str(address), port)
        if key in seen:
            raise ValueError('Duplicate target')
        seen.add(key)
        target={'host':key[0],'port':port,'kind':kind,'source':'sim' if item.get('sim',False) else 'real'}
        if 'ua' in item:
            target['ua']=validate_ua(item['ua'],target)
        targets.append(target)
    ua_hosts=[target['host'] for target in targets if 'ua' in target]
    if any(sum(target['host']==host for target in targets)>1 for host in ua_hosts):
        raise ValueError('One explicit OPC UA endpoint per host is required for evidence binding')
    for key in ('ping_timeout_s','tcp_timeout_s'):
        value = config.get(key)
        if isinstance(value, bool) or not isinstance(value, (int,float)) or not math.isfinite(value) or not 0 < value <= 10:
            raise ValueError('Explicit finite positive timeouts no greater than 10 seconds are required')
    subnet = config.get('ot_subnet')
    if subnet is not None:
        if not isinstance(subnet,str):raise ValueError('OT subnet must be an IPv4 CIDR string')
        subnet = str(ipaddress.IPv4Network(subnet,strict=False))
    internet = config.get('internet')
    if internet is not None:
        if not isinstance(internet,dict) or set(internet)!={'host','port','timeout_s'} or \
                internet['host']!='api.telegram.org' or type(internet['port']) is not int or internet['port']!=443 or \
                isinstance(internet['timeout_s'],bool) or not isinstance(internet['timeout_s'],(int,float)) or \
                not math.isfinite(internet['timeout_s']) or not 0 < internet['timeout_s'] <= 10:
            raise ValueError('Internet check must explicitly select api.telegram.org:443 and a finite timeout <=10s')
    interval=config.get('interval_s')
    if interval is not None and (isinstance(interval,bool) or not isinstance(interval,(int,float)) or not math.isfinite(interval) or not 0<interval<=3600):
        raise ValueError('Collector interval must be finite, positive and <=3600 seconds')
    return dict(config,targets=targets,ot_subnet=subnet,internet=internet,interval_s=interval)


def validate_ua(value,target):
    if target['kind']!='device' or not isinstance(value,dict) or set(value)-{'endpoint','nodes','security_policy','pki_dir'}:
        raise ValueError('OPC UA settings are allowed only on an explicit device target')
    endpoint=value.get('endpoint')
    if not isinstance(endpoint,str):raise ValueError('An explicit OPC UA endpoint is required')
    parsed=urlsplit(endpoint)
    if parsed.scheme!='opc.tcp' or parsed.hostname!=target['host'] or parsed.port!=target['port'] or \
            parsed.username is not None or parsed.password is not None or parsed.query or parsed.fragment:
        raise ValueError('OPC UA URL must match the configured numeric host/port and contain no credentials')
    if target['source']=='sim' and (target['host']!='127.0.0.1' or target['port']!=4850) or \
            target['host']=='127.0.0.1' and target['port']==4850 and target['source']!='sim':
        raise ValueError('The simulator is only 127.0.0.1:4850 and requires sim:true')
    nodes=value.get('nodes')
    if not isinstance(nodes,dict) or not 1<=len(nodes)<=256 or any(not isinstance(tag,str) or not 1<=len(tag)<=128 or not isinstance(node,str) or not 1<=len(node)<=512 for tag,node in nodes.items()):
        raise ValueError('Configure 1–256 explicit tag-to-NodeId strings')
    from asyncua import ua
    for node in nodes.values():
        try:ua.NodeId.from_string(node)
        except (ValueError,ua.UaError) as error:raise ValueError('Invalid configured NodeId: '+str(error)) from error
    if value.get('security_policy') not in ('None','Basic256Sha256'):
        raise ValueError('Explicit None or Basic256Sha256 security policy is required')
    if 'pki_dir' in value and (not isinstance(value['pki_dir'],str) or not Path(value['pki_dir']).is_absolute()):
        raise ValueError('PKI directory must be an absolute private local path')
    return dict(value)


def load_config(path):
    settings=load_settings(path)
    return [(target['host'],target['port'],target['source']) for target in settings['targets']],settings['ping_timeout_s'],settings['tcp_timeout_s']


def os_result(error):
    if isinstance(error, TimeoutError):
        return 'TIMEOUT'
    if getattr(error, 'errno', None) in (errno.ENETUNREACH, errno.EHOSTUNREACH):
        return 'NO_ROUTE'
    if getattr(error, 'errno', None) == errno.ECONNREFUSED:
        return 'REFUSED'
    return 'ERROR'


def command(argv, timeout):
    started = time.perf_counter()
    environment = dict(os.environ, LC_ALL='C')
    try:
        response = subprocess.run(argv, capture_output=True, text=True, timeout=timeout, env=environment)
        detail = {'argv':argv, 'returncode':response.returncode, 'stdout':response.stdout, 'stderr':response.stderr}
    except subprocess.TimeoutExpired as error:
        decode = lambda text: text.decode(errors='replace') if isinstance(text,bytes) else text or ''
        detail = {'argv':argv, 'returncode':None, 'stdout':decode(error.stdout), 'stderr':decode(error.stderr),
                  'exception':type(error).__name__, 'exception_text':str(error)}
    except OSError as error:
        detail = {'argv':argv, 'returncode':None, 'stdout':'', 'stderr':str(error),
                  'exception':type(error).__name__, 'errno':error.errno}
    return detail, (time.perf_counter()-started)*1000


def command_error(detail):
    return detail.get('exception_text') or detail.get('stderr') or detail.get('stdout') or f"Process exit status {detail.get('returncode')}"


def ip_check(argv):
    detail, elapsed = command(argv, 2.0)
    if detail['returncode'] == 0:
        try:
            parsed = json.loads(detail['stdout'])
            if not isinstance(parsed, list) or not all(isinstance(item,dict) for item in parsed):
                raise ValueError('Expected an OS JSON array of route/interface objects')
            detail['parsed'] = parsed
            if 'get' in argv and (not parsed or parsed[0].get('type') in ('unreachable','blackhole','prohibit')):
                return 'NO_ROUTE', detail['stdout'], elapsed, detail
            return 'ok', None, elapsed, detail
        except (ValueError,TypeError) as error:
            return 'ERROR', str(error), elapsed, detail
    message = command_error(detail)
    lowered = message.lower()
    result = 'NO_ROUTE' if 'unreachable' in lowered or 'no route' in lowered else 'ERROR'
    return result, message, elapsed, detail


def ping_check(host, timeout):
    # Numeric target, one packet; no reverse lookup or target discovery.
    argv = ['ping','-n','-c','1','-W',str(timeout),'-w',str(math.ceil(timeout)),host]
    detail, elapsed = command(argv, timeout+0.5)
    if detail['returncode'] == 0:
        return 'ok', None, elapsed, detail
    message = command_error(detail)
    lowered = message.lower()
    if detail.get('exception') == 'TimeoutExpired' or '100% packet loss' in lowered and 'unreachable' not in lowered:
        result = 'TIMEOUT'
    elif 'unreachable' in lowered or 'no route' in lowered:
        result = 'NO_ROUTE'
    else:
        result = 'UNREACHABLE' if detail['returncode'] == 1 else 'ERROR'
    return result, message, elapsed, detail


def tcp_check(host, port, timeout):
    started = time.perf_counter()
    detail = {'port':port,'timeout_s':timeout}
    try:
        with socket.socket(socket.AF_INET,socket.SOCK_STREAM) as connection:
            connection.settimeout(timeout)
            connection.connect((host,port))
        result, error = 'ok', None
    except OSError as failure:
        result, error = os_result(failure), str(failure)
        detail.update(exception=type(failure).__name__,errno=failure.errno)
    return result, error, (time.perf_counter()-started)*1000, detail


def arp_check(host):
    detail,elapsed=command(['ip','-j','neigh','show','to',host],2.0)
    if detail['returncode']!=0:
        return 'ERROR',command_error(detail),elapsed,detail
    try:
        neighbors=json.loads(detail['stdout'])
        if not isinstance(neighbors,list) or any(not isinstance(item,dict) for item in neighbors):
            raise ValueError('Expected neighbor objects from the OS')
        detail.update(parsed=neighbors,passive=True)
        entries=[item for item in neighbors if item.get('dst')==host]
        if not entries:
            return 'NO_ENTRY','No neighbor entry returned by ip neigh',elapsed,detail
        for entry in entries:
            states=entry.get('state',[])
            if isinstance(states,str):states=[states]
            if 'REACHABLE' in states:
                return 'ok',None,elapsed,detail
        return 'UNVERIFIED_NEIGHBOR','Neighbor state: '+json.dumps(entries,ensure_ascii=False),elapsed,detail
    except (ValueError,TypeError) as error:
        return 'ERROR',str(error),elapsed,detail


def internet_check(host,port,timeout):
    started=time.perf_counter()
    detail={'host':host,'port':port,'application_request_sent':False,'stage':'dns'}
    dns,_=command(['getent','ahosts',host],timeout)
    detail['dns']=dns
    if dns['returncode']!=0:
        result='TIMEOUT' if dns.get('exception')=='TimeoutExpired' else 'DNS_ERROR'
        return result,command_error(dns),(time.perf_counter()-started)*1000,detail
    addresses=[]
    for line in dns['stdout'].splitlines():
        try:address=str(ipaddress.ip_address(line.split()[0]))
        except (ValueError,IndexError):continue
        if address not in addresses:addresses.append(address)
    detail['resolved_ips']=addresses
    if not addresses:
        return 'DNS_ERROR','OS resolver returned no IP addresses',(time.perf_counter()-started)*1000,detail
    address=next((item for item in addresses if ipaddress.ip_address(item).version==4),addresses[0])
    detail['attempted_ip']=address
    try:
        context=ssl.create_default_context()
        detail['stage']='tcp'
        with socket.create_connection((address,port),timeout=timeout) as raw:
            detail['stage']='tls'
            with context.wrap_socket(raw,server_hostname=host) as tls:
                certificate=tls.getpeercert()
                detail.update(tls_version=tls.version(),cipher=tls.cipher(),
                    certificate={'subject':certificate.get('subject'),'issuer':certificate.get('issuer'),
                                 'not_before':certificate.get('notBefore'),'not_after':certificate.get('notAfter'),
                                 'sha256':hashlib.sha256(tls.getpeercert(binary_form=True)).hexdigest()})
                detail['stage']='completed'
        return 'ok',None,(time.perf_counter()-started)*1000,detail
    except ssl.SSLCertVerificationError as error:
        return 'CERT_ERROR',str(error),(time.perf_counter()-started)*1000,detail
    except ssl.SSLError as error:
        return 'TLS_ERROR',str(error),(time.perf_counter()-started)*1000,detail
    except OSError as error:
        detail.update(errno=error.errno,exception=type(error).__name__)
        return os_result(error),str(error),(time.perf_counter()-started)*1000,detail


class EvidenceStore:
    def __init__(self, path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.connection = sqlite3.connect(str(self.path), timeout=2.0)
        self.connection.row_factory = sqlite3.Row
        self.connection.execute('PRAGMA foreign_keys=ON')
        try:
            self.connection.execute('BEGIN IMMEDIATE')
            self.connection.execute('''CREATE TABLE IF NOT EXISTS probe_evidence (
                id INTEGER PRIMARY KEY AUTOINCREMENT, host TEXT NOT NULL, "check" TEXT NOT NULL,
                result TEXT NOT NULL, error TEXT, latency_ms REAL NOT NULL, ts TEXT NOT NULL, detail TEXT NOT NULL,
                source TEXT NOT NULL DEFAULT 'real' CHECK (source IN ('real','sim'))
            )''')
            columns = {row[1]: row for row in self.connection.execute('PRAGMA table_info(probe_evidence)')}
            if not {'id','host','check','result','error','latency_ms','ts','detail'}.issubset(columns) or \
                    columns['id'][2].upper() != 'INTEGER' or columns['id'][5] != 1:
                raise ValueError('Existing database has an incompatible evidence schema; select a separate database')
            if 'source' not in columns:
                self.connection.execute("ALTER TABLE probe_evidence ADD COLUMN source TEXT NOT NULL DEFAULT 'real' CHECK (source IN ('real','sim'))")
            if self.connection.execute("SELECT 1 FROM probe_evidence WHERE source IS NULL OR source NOT IN ('real','sim') LIMIT 1").fetchone():
                raise ValueError('Existing evidence contains an unsupported source')
            self.connection.execute('''CREATE TABLE IF NOT EXISTS tag_samples (
                id INTEGER PRIMARY KEY AUTOINCREMENT,host TEXT NOT NULL,tag TEXT NOT NULL,node_id TEXT NOT NULL,
                value TEXT NOT NULL,quality TEXT NOT NULL,ts TEXT NOT NULL,
                evidence_id INTEGER NOT NULL REFERENCES probe_evidence(id))''')
            self.connection.commit()
            self.path.chmod(0o600)
        except Exception:
            self.connection.close()
            raise

    def record(self, host, check, observation, source='real', *, commit=True):
        if source not in ('real','sim'):
            raise ValueError('Evidence source must be real or sim')
        result, error, latency, detail = observation
        detail=dict(detail)
        detail.setdefault('observer',socket.gethostname())
        ts = datetime.now(timezone.utc).isoformat()
        cursor = self.connection.execute('INSERT INTO probe_evidence(host,"check",result,error,latency_ms,ts,detail,source) VALUES(?,?,?,?,?,?,?,?)',
                                         (host,check,result,error,latency,ts,json.dumps(detail,ensure_ascii=False),source))
        if commit:self.connection.commit()
        return dict(self.connection.execute('SELECT * FROM probe_evidence WHERE id=?',(cursor.lastrowid,)).fetchone())

    def record_read(self,host,tag,node_id,observation,value,quality,source='real'):
        encoded=json.dumps(value,ensure_ascii=False,allow_nan=False)
        try:
            self.connection.execute('BEGIN IMMEDIATE')
            row=self.record(host,'ua_read',observation,source,commit=False)
            self.connection.execute('INSERT INTO tag_samples(host,tag,node_id,value,quality,ts,evidence_id) VALUES(?,?,?,?,?,?,?)',
                                    (host,tag,node_id,encoded,quality,row['ts'],row['id']))
            self.connection.commit()
            return row
        except BaseException:
            self.connection.rollback()
            raise

    def close(self):
        self.connection.close()


def collect_transport(settings,storage,output=print):
    ping_timeout,tcp_timeout=settings['ping_timeout_s'],settings['tcp_timeout_s']
    hostname = socket.gethostname()
    for name, argv in (('local_nic',['ip','-j','addr']),('route_inventory',['ip','-j','route'])):
        observation=ip_check(argv)
        if name=='local_nic':
            observation[3]['ot_subnet']=settings['ot_subnet']
            for interface in observation[3].get('parsed',[]):
                interface['wireless']=(Path('/sys/class/net')/interface.get('ifname','')/'wireless').is_dir()
        output(json.dumps(storage.record(hostname,name,observation),ensure_ascii=False))
    for target in settings['targets']:
        host,port,source=target['host'],target['port'],target['source']
        final=('arp',lambda:arp_check(host)) if target['kind']=='router' else ('tcp',lambda:tcp_check(host,port,tcp_timeout))
        for name, check in (
            ('route', lambda:ip_check(['ip','-j','route','get',host])),
            ('ping', lambda:ping_check(host,ping_timeout)),
            final):
            output(json.dumps(storage.record(host,name,check(),source=source),ensure_ascii=False))
    if settings['internet']:
        internet=settings['internet']
        output(json.dumps(storage.record(internet['host'],'internet',
            internet_check(internet['host'],internet['port'],internet['timeout_s'])),ensure_ascii=False))


def run(config_path, db_path, output=print):
    settings=load_settings(config_path)
    storage=EvidenceStore(db_path)
    try:
        collect_transport(settings,storage,output)
    finally:
        storage.close()


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--config',type=Path,default=Path.home()/'.config/aqua-command/probe_targets.json')
    parser.add_argument('--db',type=Path,default=Path.home()/'.local/share/aqua-command/probe/data.db')
    options = parser.parse_args(argv)
    try:
        run(options.config,options.db)
    except (OSError,ValueError,KeyError,sqlite3.Error) as error:
        print(f'{type(error).__name__}: {error}',file=sys.stderr)
        return 1
    return 0


if __name__ == '__main__':
    sys.exit(main())
