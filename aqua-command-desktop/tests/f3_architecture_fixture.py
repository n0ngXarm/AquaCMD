"""UI-only evidence fixtures: temporary tests DB, original API, no collector/network probes."""
import json,sqlite3,sys,tempfile,threading
from datetime import datetime,timedelta,timezone
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from collector.evidence_api import EvidenceHandler,make_server
from collector.probe_once import EvidenceStore
from desktop.f3_api_view import build_html
from desktop.f3_projection import F3Projection

flags={'topology_error':False,'stream_error':False}
class Handler(EvidenceHandler):
 def do_GET(self):
  if self.path.startswith('/api/topology') and flags['topology_error']:
   self.json_response(503,{'error':'Controlled UI test outage'});return
  super().do_GET()

with tempfile.TemporaryDirectory(prefix='.f3-simple-',dir=ROOT/'tests') as temporary:
 directory=Path(temporary);store=EvidenceStore(directory/'data.db')
 stations=[f'192.0.2.{number}' for number in range(11,15)];switch='192.0.2.254';old_router='198.51.100.1';observer='test-collector'
 hosts=stations+[switch,old_router]
 metadata={host:{'label':'สถานีสูบน้ำ '+str(index+1),'kind':'wincc','zone':'SCADA_OT'} for index,host in enumerate(stations)}
 metadata[switch]={'label':'LAN Switch','kind':'switch','zone':'SCADA_OT'}
 metadata[old_router]={'label':'Configured old router','kind':'router','zone':'EXTERNAL_WAN'}
 (directory/'page.html').write_text(build_html(metadata))
 def record(host,check='tcp',result='ok',error=None,detail=None,age=0):
  data={'observer':observer,'test':'UI-only sample under tests/'};data.update(detail or {})
  row=store.record(host,check,(result,error,.45,data),source='sim')
  if age:
   store.connection.execute('UPDATE probe_evidence SET ts=? WHERE id=?',((datetime.now(timezone.utc)-timedelta(seconds=age)).isoformat(),row['id']));store.connection.commit()
   row=dict(store.connection.execute('SELECT * FROM probe_evidence WHERE id=?',(row['id'],)).fetchone())
  return row
 def route(gateway):return record(observer,'route_inventory',detail={'parsed':[{'dst':'default','gateway':gateway,'dev':'test0','metric':20}]})
 record(observer,'local_nic',detail={'parsed':[{'ifname':'test0','addr_info':[{'family':'inet','local':'198.51.100.88','prefixlen':24}]}]})
 route('198.51.100.254')
 record(observer,'ip_forward',detail={'path':'test-only field','value':1})
 record(stations[0],result='TIMEOUT',error='timed out <img src=x onerror=alert(1)>',detail={'port':4840})
 record(stations[1],detail={'port':4840})
 record(stations[2],result='REFUSED',error='old refusal',detail={'port':4840},age=960)
 record(switch,detail={'port':4840})
 record(old_router,'ping',result='TIMEOUT',error='old configured router is not the default')
 record('api.telegram.org','internet',detail={'attempted_ip':'203.0.113.10','port':443,'stage':'completed','application_request_sent':False})
 settings={'targets':[{'host':host,'kind':'router' if host==old_router else 'device'} for host in hosts],'ot_subnet':'192.0.2.0/24'}
 def start(port=0):
  server=make_server(store.path,hosts=hosts,port=port,settings=settings);server.reader=F3Projection(server.reader,settings,metadata);server.RequestHandlerClass=Handler
  original=server.reader.after
  def after(cursor):
   if flags['stream_error']:raise sqlite3.OperationalError('Controlled test stream outage')
   return original(cursor)
  server.reader.after=after;worker=threading.Thread(target=server.serve_forever,daemon=True);worker.start();return server,worker
 server,worker=start();port=server.server_port
 print(json.dumps({'ready':True,'url':f'http://127.0.0.1:{port}','html':str(directory/'page.html')}),flush=True)
 try:
  for line in sys.stdin:
   command=json.loads(line);answer={'request':command['request'],'ok':True}
   try:
    action=command['action']
    if action=='insert':answer['row']=record(command.get('host',stations[1]),command.get('check','tcp'),command.get('result','ok'),command.get('error'),command.get('detail'))
    elif action=='route':answer['row']=route(command['gateway'])
    elif action=='internet':
     result=command['result'];answer['row']=record('api.telegram.org','internet',result,command.get('error'),
        {'port':443,'attempted_ip':'203.0.113.10','stage':'completed' if result=='ok' else 'tls','application_request_sent':False})
    elif action=='many':
     for n in range(20,60):metadata[f'192.0.2.{n}']={'label':f'192.0.2.{n}','kind':'wincc'}
    elif action=='snapshot':
     answer['topology']=server.reader.topology();answer['rows']=[dict(row) for row in store.connection.execute('SELECT * FROM probe_evidence ORDER BY id')]
    elif action in ('topology_error','stream_error'):flags[action]=bool(command['value'])
    elif action=='age':
     store.connection.execute('UPDATE probe_evidence SET ts=?',((datetime.now(timezone.utc)-timedelta(seconds=960)).isoformat(),));store.connection.commit()
    elif action=='stop_api':server.stop_event.set();server.shutdown();server.server_close();worker.join(timeout=3)
    elif action=='start_api':server,worker=start(port)
    elif action=='quit':
     print(json.dumps(answer),flush=True);break
    else:raise ValueError('Unknown UI test command')
   except Exception as error:answer.update(ok=False,error=type(error).__name__+': '+str(error))
   print(json.dumps(answer),flush=True)
 finally:
  server.stop_event.set();server.shutdown();server.server_close();worker.join(timeout=3);store.close()
