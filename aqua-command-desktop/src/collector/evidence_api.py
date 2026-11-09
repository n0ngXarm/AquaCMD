"""Explicit loopback read-only evidence API and row-driven event stream."""
import argparse
import ipaddress
import json
import select
import signal
import socket
import sqlite3
import sys
import threading
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

from .probe_once import load_settings

TARGET_CHECKS = ('route', 'ping', 'arp', 'tcp', 'ua_endpoints', 'ua_session', 'ua_read')
SUCCESS_LEVELS = {'tcp': (1, 'TCP_OPEN'), 'ua_session': (2, 'UA_OK'), 'ua_read': (3, 'READ_OK')}
FRESH_SECONDS = 60
POLL_SECONDS = 0.5


def timestamp(value):
    parsed = datetime.fromisoformat(value)
    if parsed.tzinfo is None:
        raise ValueError('Evidence timestamps must include a timezone')
    return parsed


def age_info(value,now):
    if value is None:return {'freshness':'UNKNOWN','age_seconds':None,'age_label':'ยังไม่มีหลักฐาน'}
    age=max(0,(now-timestamp(value)).total_seconds())
    stale=age>FRESH_SECONDS
    return {'freshness':'STALE' if stale else 'FRESH','age_seconds':age,
            'age_label':('STALE '+str(int(age//60))+' นาที') if stale else 'FRESH'}


def derive_state(rows, now, kind='device'):
    """Derive one host's transport/read state without I/O or invented evidence."""
    empty = {'state':'UNKNOWN','reason':None,'last_check_ts':None,'source':None,
             'freshness':'UNKNOWN','age_seconds':None,'age_label':'ยังไม่มีหลักฐาน',
             'result_check':None,'result_ts':None,'check_label':None,'check_summary':'ยังไม่มีหลักฐาน','checks':{}}
    allowed=('route','ping','arp') if kind=='router' else ('internet',) if kind=='internet' else TARGET_CHECKS
    relevant = sorted((dict(row) for row in rows if row['check'] in allowed), key=lambda row: row['id'])
    if not relevant:
        return empty
    if now.tzinfo is None:
        raise ValueError('The current time must include a timezone')
    latest = relevant[-1]
    if latest['source'] not in ('real', 'sim'):
        raise ValueError('Evidence source must be real or sim')
    observed = [row for row in relevant if row['source'] == latest['source']]
    checks={row['check']:row for row in observed}
    proof=None;state='UNKNOWN';reason=None
    if kind in ('router','internet'):
        start=max((row['id'] for row in observed if row['check']=='route'),default=0)
        active=[row for row in checks.values() if row['id']>=start and row['check']!='route']
        success=[row for row in active if row['result']=='ok']
        if success:
            proof=max(success,key=lambda row:row['id']);state='REACHABLE' if kind=='router' else 'DNS_TLS_OK'
        elif active:
            proof=max(active,key=lambda row:row['id']);state='UNREACHABLE';reason=proof['error'] or proof['result']
        elif checks.get('route',{}).get('result') not in (None,'ok'):
            proof=checks['route'];state='UNREACHABLE';reason=proof['error'] or proof['result']
    else:
        failures = [row for row in observed if row['result'] != 'ok']
        last_failure = failures[-1] if failures else None
        candidates=[row for row in observed if row['result']=='ok' and row['check'] in SUCCESS_LEVELS
                    and (last_failure is None or row['id']>last_failure['id'])]
        if candidates:
            proof=max(candidates,key=lambda row:(SUCCESS_LEVELS[row['check']][0],row['id']))
            state=SUCCESS_LEVELS[proof['check']][1]
        elif last_failure:
            proof=last_failure;state='UNREACHABLE';reason=proof['error'] or proof['result']
    proof=proof or latest
    labels={'ping':'ICMP','arp':'ARP cache','tcp':'TCP','route':'route','internet':'DNS + TLS',
            'ua_endpoints':'GetEndpoints','ua_session':'UA session','ua_read':'UA read'}
    label=labels[proof['check']]
    if proof['check'] in ('tcp','internet') and detail(proof).get('port'):
        label+=' :'+str(detail(proof)['port'])
    summary=' · '.join(labels[key]+': '+item['result'] for key,item in checks.items() if key!='route')
    return dict(empty,state=state,reason=reason,last_check_ts=latest['ts'],source=latest['source'],
                **age_info(proof['ts'],now),result_check=proof['check'],result_ts=proof['ts'],
                check_label=label,check_summary=summary or label,checks=checks)


def detail(row):
    try:
        value=json.loads(row['detail'])
        return value if isinstance(value,dict) else {}
    except (ValueError,TypeError):return {}


@contextmanager
def read_connection(path):
    connection = sqlite3.connect(Path(path).resolve().as_uri()+'?mode=ro', uri=True, timeout=0.5)
    try:
        connection.row_factory = sqlite3.Row
        connection.execute('PRAGMA query_only=ON')
        connection.execute('SELECT rowid,id,host,"check",result,error,latency_ms,ts,detail,source FROM probe_evidence LIMIT 0')
        yield connection
    finally:
        connection.close()


class EvidenceReader:
    def __init__(self, path, hosts=(), target_kinds=None, ot_subnet=None,ua_targets=None):
        self.path = Path(path)
        self.hosts = tuple(dict.fromkeys(hosts))
        self.kinds=dict(target_kinds or {})
        self.ua_targets=ua_targets
        self.ot_subnet=str(ipaddress.IPv4Network(ot_subnet,strict=False)) if ot_subnet else None
        with read_connection(self.path):
            pass

    def topology(self, now=None):
        now = now or datetime.now(timezone.utc)
        marks = ','.join('?' for _ in TARGET_CHECKS)
        with read_connection(self.path) as connection:
            connection.execute('BEGIN')
            counts = dict(connection.execute(f'''SELECT
                (SELECT COUNT(DISTINCT host) FROM probe_evidence WHERE "check" IN ({marks})) AS remote_hosts,
                (SELECT COUNT(*) FROM probe_evidence WHERE "check"='ua_session' AND result='ok') AS ua_sessions,
                (SELECT COUNT(*) FROM probe_evidence WHERE "check"='ua_read' AND result='ok') AS read_receipts,
                COUNT(*) AS committed_rows, COALESCE(MAX(rowid),0) AS last_event_id,MAX(ts) AS last_write_ts FROM probe_evidence''', TARGET_CHECKS).fetchone())
            routers=[host for host,kind in self.kinds.items() if kind=='router']
            router_marks=','.join('?' for _ in routers) or 'NULL'
            responding=connection.execute(f'''WITH rounds AS(
                SELECT host,COALESCE(MAX(CASE WHEN "check"='route' THEN id END),0) AS start_id
                FROM probe_evidence WHERE "check" IN ({marks}) GROUP BY host), current_checks AS(
                SELECT e.*,ROW_NUMBER() OVER(PARTITION BY e.host,e."check" ORDER BY e.id DESC) AS rank
                FROM probe_evidence e JOIN rounds r ON e.host=r.host WHERE e.id>=r.start_id
                AND e."check" IN ('ping','arp','tcp','ua_endpoints','ua_session','ua_read')
                AND e.source=(SELECT source FROM probe_evidence s WHERE s.host=e.host AND s."check" IN ({marks}) ORDER BY s.id DESC LIMIT 1))
                SELECT COUNT(DISTINCT host) FROM current_checks WHERE rank=1 AND result='ok'
                AND julianday(ts)>=julianday(?)
                AND (?=0 OR host NOT IN ({router_marks}) OR "check" IN ('ping','arp'))''',
                (*TARGET_CHECKS,*TARGET_CHECKS,(now-timedelta(seconds=FRESH_SECONDS)).isoformat(),len(routers),*routers)).fetchone()[0]
            counts['remote_responding']=responding
            rows = [dict(row) for row in connection.execute('SELECT * FROM probe_evidence ORDER BY id')]
            hosts = [row[0] for row in connection.execute(f'SELECT DISTINCT host FROM probe_evidence WHERE "check" IN ({marks}) ORDER BY host', TARGET_CHECKS)]
            samples=[]
            if connection.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='tag_samples'").fetchone():
                samples=[dict(row) for row in connection.execute('''SELECT s.*,e.source,e.result FROM tag_samples s
                    JOIN probe_evidence e ON s.evidence_id=e.id ORDER BY s.id''')]
        grouped = {}
        for row in rows:
            grouped.setdefault(row['host'], []).append(row)
        nodes = [dict(host=host,kind=self.kinds.get(host,'device'), **derive_state(grouped.get(host, []), now,self.kinds.get(host,'device')))
                 for host in dict.fromkeys((*self.hosts, *hosts))]
        internet_rows=[row for row in rows if row['check']=='internet']
        for host in dict.fromkeys(row['host'] for row in internet_rows):
            nodes.append(dict(host=host,kind='internet',**derive_state(grouped.get(host,[]),now,'internet')))
        latest_samples={(item['host'],item['tag']):item for item in samples}
        by_id={row['id']:row for row in rows}
        for node in nodes:
            evidence=[row for row in grouped.get(node['host'],[]) if row['check'] in TARGET_CHECKS and row['source']==node['source']]
            last_failure=max((row['id'] for row in evidence if row['result']!='ok'),default=0)
            round_start=max((row['id'] for row in evidence if row['check'] in ('route','ua_session')),default=0)
            node['samples']=[]
            for (host,tag),item in latest_samples.items():
                if host!=node['host']:continue
                if self.ua_targets is not None:
                    binding=self.ua_targets.get(host,{})
                    if binding.get('nodes',{}).get(tag)!=item['node_id'] or \
                            binding.get('endpoint')!=detail(by_id[item['evidence_id']]).get('endpoint'):continue
                age=age_info(item['ts'],now)
                available=item['result']=='ok' and node['state']=='READ_OK' and item['source']==node['source'] and \
                          item['evidence_id']>last_failure and item['evidence_id']>=round_start and age['freshness']=='FRESH'
                node['samples'].append({'tag':tag,'node_id':item['node_id'],'value':json.loads(item['value']) if available else None,
                    'quality':item['quality'],'ts':item['ts'],'evidence_id':item['evidence_id'],'source':item['source'],
                    'available':available,**age})
        cursor = counts.pop('last_event_id')
        last_write=counts.pop('last_write_ts')
        components=self.components(rows,now,counts['committed_rows'],last_write)
        edges=[];observer=components['collector'].get('observer')
        for node in nodes:
            eligible=('ping',) if node['kind']=='router' else ('internet',) if node['kind']=='internet' else ('ping','tcp','ua_endpoints','ua_session','ua_read')
            paired=[row for row in grouped.get(node['host'],[]) if row['check'] in eligible
                    and observer and detail(row).get('observer')==observer
                    and (row['check']!='internet' or detail(row).get('attempted_ip'))]
            if paired:
                row=paired[-1]
                edges.append({'source':'collector','target':'host:'+node['host'],'check':row['check'],
                              'result':row['result'],'evidence_id':row['id'],'port':detail(row).get('port'),
                              'state':node['state'],'source_kind':row['source']})
        local=[row for row in rows if observer and detail(row).get('observer')==observer]
        if local:
            edges.append({'source':'collector','target':'sqlite','check':'committed_row','result':'ok',
                          'evidence_id':local[-1]['id'],'state':'OBSERVED_LOCAL','source_kind':'real'})
        os_rows=[row for row in rows if row['check'] in ('local_nic','nic_inventory','ip_forward') and row['host']==observer]
        if os_rows:
            row=os_rows[-1]
            edges.append({'source':'os','target':'collector','check':row['check'],'result':row['result'],
                          'evidence_id':row['id'],'state':components['collector']['state'],'source_kind':row['source']})
        return {'nodes':nodes,'components':components,'edges':edges,'counters':counts,
                'last_event_id':cursor,'generated_at':now.isoformat()}

    def components(self,rows,now,count,last_write):
        local_rows=[row for row in rows if row['check'] in ('local_nic','nic_inventory')]
        row=local_rows[-1] if local_rows else None
        first_observer=next((item['host'] for item in reversed(rows) if item['check']=='ip_forward' and detail(item).get('observer')==item['host']),None)
        local={'state':'UNKNOWN','reason':None,'interfaces':[],'routes':[],'ot_subnet':self.ot_subnet,
               'configuration_state':'UNKNOWN','observer':row['host'] if row else first_observer,
               'last_check_ts':row['ts'] if row else None,'source':row['source'] if row else None}
        local.update(age_info(local['last_check_ts'],now))
        if row:
            local['state']='OBSERVED_LOCAL' if row['result']=='ok' else 'ERROR';local['reason']=row['error']
            for interface in detail(row).get('parsed',[]):
                local['interfaces'].append({'name':interface.get('ifname'),'wireless':interface.get('wireless'),
                    'operstate':interface.get('operstate'),'flags':interface.get('flags',[]),
                    'cidrs':[address['local']+'/'+str(address['prefixlen']) for address in interface.get('addr_info',[])
                             if address.get('family')=='inet']})
        route_rows={item['host']:item for item in rows if item['check']=='route' and self.kinds.get(item['host'])!='router' and item['source']=='real'
                    and (not local['observer'] or detail(item).get('observer')==local['observer'])}
        compared=[]
        for host,item in route_rows.items():
            parsed=detail(item).get('parsed',[]);route=parsed[0] if parsed else {}
            entry={'host':host,'result':item['result'],'error':item['error'],'dev':route.get('dev'),
                   'src':route.get('prefsrc') or route.get('src'),'gateway':route.get('gateway'),
                   'ts':item['ts'],'evidence_id':item['id'],'raw':detail(item).get('stdout')}
            cidrs=next((interface['cidrs'] for interface in local['interfaces'] if interface['name']==entry['dev']),[])
            if self.ot_subnet and cidrs:
                matched=any(str(ipaddress.IPv4Interface(cidr).network)==self.ot_subnet for cidr in cidrs)
                entry['subnet_match']=matched;compared.append(matched)
            local['routes'].append(entry)
        if compared:local['configuration_state']='SUBNET MATCH' if all(compared) else 'CONFIGURATION MISMATCH'
        forwarding=[item for item in rows if item['check']=='ip_forward' and (not local['observer'] or item['host']==local['observer'])]
        forwarding=forwarding[-1] if forwarding else None
        local['ip_forward']=detail(forwarding).get('value') if forwarding and forwarding['result']=='ok' else None
        local['ip_forward_evidence_id']=forwarding['id'] if forwarding else None
        local['warning']='IP forwarding = 1 · เครื่องนี้เปิดการส่งต่อ IPv4' if local['ip_forward']==1 else None
        local['ip_forward_error']=forwarding['error'] if forwarding else None
        result={'collector':local,'sqlite':{'state':'OBSERVED_LOCAL','committed_rows':count,'last_write_ts':last_write,
                                          'last_check_ts':now.isoformat(),'source':'real',**age_info(last_write,now)}}
        ua_rows=[item for item in rows if item['check'] in ('ua_endpoints','ua_session','ua_read')]
        client={'state':'UNKNOWN','last_check_ts':None,'source':None,'reason':'Implemented; no OPC UA attempt recorded',
                'implemented':True,'last_target':None,'security_policy':None}
        if ua_rows:
            last=ua_rows[-1]
            client.update(derive_state([item for item in rows if item['host']==last['host']],now))
            client.update(last_target=last['host'],security_policy=detail(last).get('security_policy'))
        result['client']=client
        for key in ('task','outbox','telegram','mobile'):
            result[key]={'state':'NOT_BUILT','last_check_ts':None,'source':None,'reason':'Not implemented in this evidence pipeline'}
        return result

    def evidence(self, host=None, limit=100):
        with read_connection(self.path) as connection:
            where = ' WHERE host=?' if host is not None else ''
            arguments = (host, limit) if host is not None else (limit,)
            rows = connection.execute('SELECT * FROM probe_evidence'+where+' ORDER BY id DESC LIMIT ?', arguments)
            return {'rows': [dict(row) for row in rows]}

    def latest_id(self):
        with read_connection(self.path) as connection:
            return connection.execute('SELECT COALESCE(MAX(rowid),0) FROM probe_evidence').fetchone()[0]

    def after(self, cursor):
        with read_connection(self.path) as connection:
            return [dict(row) for row in connection.execute('SELECT * FROM probe_evidence WHERE rowid>? ORDER BY rowid LIMIT 256', (cursor,))]


class EvidenceHandler(BaseHTTPRequestHandler):
    protocol_version = 'HTTP/1.1'

    def json_response(self, status, body):
        payload = json.dumps(body, ensure_ascii=False).encode('utf-8')
        self.send_response(status)
        self.send_header('Content-Type', 'application/json; charset=utf-8')
        self.send_header('Content-Length', str(len(payload)))
        self.send_header('Cache-Control', 'no-store')
        self.send_header('X-Content-Type-Options', 'nosniff')
        self.send_header('Connection', 'close')
        self.end_headers()
        self.close_connection = True
        self.wfile.write(payload)

    def do_GET(self):
        hosts = (f'127.0.0.1:{self.server.server_port}', f'localhost:{self.server.server_port}')
        if self.headers.get('Host') not in hosts or self.headers.get('Origin') not in (None, *(f'http://{host}' for host in hosts)):
            self.json_response(403, {'error': 'Only the local API origin is allowed'})
            return
        try:
            target = urlsplit(self.path)
            query = parse_qs(target.query, keep_blank_values=True, max_num_fields=8)
            if any(len(value) != 1 for value in query.values()):
                raise ValueError('Duplicate query parameters are not allowed')
            f3_projection = getattr(self.server.reader, 'f3_evidence', None)
            if target.path not in ('/api/topology', '/api/evidence', '/api/stream') and not (
                    target.path == '/api/f3/evidence' and callable(f3_projection)):
                self.json_response(404, {'error': 'Unknown API path'})
                return
            allowed = {'host', 'limit'} if target.path == '/api/evidence' else set()
            if set(query)-allowed:
                raise ValueError('Unsupported query parameter')
            host = query.get('host', [None])[0]
            if host is not None and (not host or len(host) > 255):
                raise ValueError('A nonempty host of at most 255 characters is required')
            value = query.get('limit', ['100'])[0]
            if not value.isascii() or not value.isdecimal() or not 1 <= int(value) <= 1000:
                raise ValueError('limit must be an integer between 1 and 1000')
            limit = int(value)
            last_id = self.headers.get('Last-Event-ID')
            if last_id is not None and (not last_id.isascii() or not last_id.isdecimal() or len(last_id) > 19):
                raise ValueError('Last-Event-ID must be a nonnegative rowid')
        except ValueError as error:
            self.json_response(400, {'error': str(error)})
            return
        try:
            if target.path == '/api/topology':
                self.json_response(200, self.server.reader.topology())
            elif target.path == '/api/evidence':
                self.json_response(200, self.server.reader.evidence(host, limit))
            elif target.path == '/api/f3/evidence':
                self.json_response(200, f3_projection())
            else:
                latest = self.server.reader.latest_id()
                if last_id is not None and int(last_id) > latest:
                    self.json_response(400, {'error': 'Last-Event-ID is beyond the committed evidence'})
                    return
                self.stream(latest if last_id is None else int(last_id))
        except (sqlite3.Error, ValueError, OSError) as error:
            self.json_response(503, {'error': f'{type(error).__name__}: {error}'})

    def stream(self, cursor):
        self.close_connection = True
        self.connection.settimeout(2.0)
        self.send_response(200)
        self.send_header('Content-Type', 'text/event-stream; charset=utf-8')
        self.send_header('Cache-Control', 'no-store')
        self.send_header('Connection', 'close')
        self.end_headers()
        self.wfile.flush()
        try:
            while not self.server.stop_event.is_set():
                readable, _, _ = select.select([self.connection], [], [], 0)
                if readable and not self.connection.recv(1, socket.MSG_PEEK):
                    break
                rows = self.server.reader.after(cursor)
                for row in rows:
                    payload = json.dumps(row, ensure_ascii=False)
                    self.wfile.write(f'id: {row["id"]}\nevent: evidence\ndata: {payload}\n\n'.encode('utf-8'))
                    self.wfile.flush()
                    cursor = row['id']
                if len(rows) < 256:
                    self.server.stop_event.wait(POLL_SECONDS)
        except (OSError, sqlite3.Error, ValueError) as error:
            # Close on a read/transport error; never turn it into an evidence event.
            self.log_error('Event stream closed: %s', error)

    def reject_write(self):
        self.json_response(405, {'error': 'This API supports GET only'})

    do_POST = do_PUT = do_PATCH = do_DELETE = do_OPTIONS = do_HEAD = reject_write


def make_server(db_path, hosts=(), bind='127.0.0.1', port=0, settings=None):
    if bind != '127.0.0.1' or type(port) is not int or not 0 <= port <= 65535:
        raise ValueError('Select 127.0.0.1 and a TCP port between 0 and 65535')
    configured=settings is not None
    settings=settings or {}
    reader = EvidenceReader(db_path,hosts,target_kinds={target['host']:target['kind'] for target in settings.get('targets',[])},
                            ot_subnet=settings.get('ot_subnet'),
                            ua_targets={target['host']:target['ua'] for target in settings.get('targets',[]) if 'ua' in target} if configured else None)
    server = ThreadingHTTPServer((bind, port), EvidenceHandler)
    server.reader = reader
    server.stop_event = threading.Event()
    return server


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--config', type=Path, default=Path.home()/'.config/aqua-command/probe_targets.json')
    parser.add_argument('--db', type=Path, default=Path.home()/'.local/share/aqua-command/probe/data.db')
    parser.add_argument('--port', type=int, default=0)
    options = parser.parse_args(argv)
    try:
        settings=load_settings(options.config)
        server = make_server(options.db,hosts=[target['host'] for target in settings['targets']],port=options.port,settings=settings)
    except (sqlite3.Error, OSError, ValueError, KeyError) as error:
        print(f'{type(error).__name__}: {error}', file=sys.stderr)
        return 1

    def stop(signum, frame):
        raise KeyboardInterrupt

    signal.signal(signal.SIGTERM, stop)
    print(json.dumps({'listen': f'http://127.0.0.1:{server.server_port}', 'db': str(options.db)}), flush=True)
    try:
        server.serve_forever(poll_interval=0.25)
    except KeyboardInterrupt:
        pass
    finally:
        server.stop_event.set()
        server.server_close()
    return 0


if __name__ == '__main__':
    sys.exit(main())
