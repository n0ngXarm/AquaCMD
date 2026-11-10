import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';import os from 'node:os';import path from 'node:path';import net from 'node:net';import {execFileSync} from 'node:child_process';
import {startDeployedHost,validateDeployment} from '../../desktop/deployed-host.mjs';
import {requestJSON,digest} from '../src/lan/protocol.js';
import {Store} from '../src/lan/store.js';
const key='a'.repeat(64),peer={id:'PC-01',secret:key};
const temp=()=>fs.mkdtempSync(path.join(os.tmpdir(),'aqua-actual-test-'));
async function port(){const s=net.createServer();await new Promise(r=>s.listen(0,'127.0.0.1',r));const p=s.address().port;await new Promise(r=>s.close(r));return p}
function certificate(d,name='server'){const cert=path.join(d,name+'.crt'),privateKey=path.join(d,name+'.key');execFileSync('openssl',['req','-x509','-newkey','rsa:2048','-nodes','-keyout',privateKey,'-out',cert,'-days','1','-subj','/CN=127.0.0.1','-addext','subjectAltName=IP:127.0.0.1'],{stdio:'ignore'});return {certFile:cert,keyFile:privateKey}}
function event(seq=1){const at=new Date().toISOString();return {event_id:'PC-01:runtime-'+seq,schema:'aqua.runtime.v3',schema_version:3,source_id:'PC-01',sequence:seq,kind:'SNAPSHOT',at,simulated:false,source_adapter:'wincc-opc-da',read_at:at,observed_at:at,values:{'PUMP.RUN':true},observations:{'PUMP.RUN':{raw_value:1,quality_code:192,read_error:0,quality:'GOOD',source_timestamp:'2026-10-28T01:00:00.000Z'}}}}

test('actual profile rejects implicit trust, wildcard/public/non-TLS Gateway and simulation settings before storage',()=>{
 const base={role:'agent',id:'PC-01',listenHost:'127.0.0.1',listenPort:4181,gatewayUrl:'https://192.168.50.4:4174',gatewaySecret:key,caFile:'/approved/ca.crt',telegramMode:'dry-run'};
 assert.equal(validateDeployment(base).role,'agent');const {telegramMode,caFile,...systemTrust}=base;assert.equal(validateDeployment(systemTrust).telegramMode,'dry-run');assert.throws(()=>validateDeployment({role:'gateway',id:'PC-04',listenHost:'127.0.0.1',listenPort:4174,certFile:'/owned/cert',keyFile:'/owned/key',telegramMode:'dry-run',peers:{'PC-01':key,'PC-02':key}}));
 for(const changes of [{listenHost:'0.0.0.0'},{listenHost:'192.168.50.1'},{gatewayUrl:'http://192.168.50.4:4174'},{gatewayUrl:'https://8.8.8.8:443'},{gatewaySecret:''},{caFile:123},{simulated:true},{role:'unknown'}])assert.throws(()=>validateDeployment({...base,...changes}));
});

test('real-only v3 preserves source time/quality and rejects simulated or contradictory GOOD states',()=>{
 const d=temp(),s=new Store(d,{realOnly:true});try{
  const e=event();s.ingest('PC-01',[e]);assert.equal(s.stats().received,1);assert.ok(s.get('receivedAt:PC-01'));
  for(const mutation of [e=>e.simulated=true,e=>e.observations['PUMP.RUN'].quality_code=128,e=>e.observations['PUMP.RUN'].read_error=-1,e=>e.observations['PUMP.RUN'].source_timestamp='invalid',e=>e.read_at='invalid']){const b=event(2);mutation(b);assert.throws(()=>s.ingest('PC-01',[b]));}
  const uncertain=event(2);uncertain.values['PUMP.RUN']=null;uncertain.observations['PUMP.RUN'].quality='UNCERTAIN';uncertain.observations['PUMP.RUN'].quality_code=64;s.ingest('PC-01',[uncertain]);assert.equal(s.stats().received,2);
 }finally{s.close();fs.rmSync(d,{recursive:true,force:true})}
});

test('OPC DA Analog keeps scalar, quality and source time without becoming a pump transition',()=>{
 const d=temp(),s=new Store(d,{realOnly:true,notifications:true});
 try {
  const frame=event();
  frame.values['TANK.LEVEL']=null;
  frame.observations['TANK.LEVEL']={value_type:'analog',raw_value:73.25,quality_code:192,read_error:0,
   quality:'GOOD',source_timestamp:'2026-10-28T01:00:01.000Z'};
  const receipt=s.ingest('PC-01',[frame]);
  assert.equal(receipt[0].sha256,digest(JSON.stringify(frame)));
  const stored=JSON.parse(s.stats().latest);
  assert.deepEqual(stored.observations['TANK.LEVEL'],frame.observations['TANK.LEVEL']);
  assert.equal(stored.values['TANK.LEVEL'],null);
  assert.equal(s.notificationStats().notificationPending,0);

  for(const mutate of [
   e=>e.values['TANK.LEVEL']=true,
   e=>e.observations['TANK.LEVEL'].raw_value=null,
   e=>e.observations['TANK.LEVEL'].raw_value='73.25',
   e=>e.observations['TANK.LEVEL'].raw_value=Infinity,
   e=>e.observations['TANK.LEVEL'].quality_code=64,
   e=>e.observations['TANK.LEVEL'].read_error=1,
   e=>e.observations['TANK.LEVEL'].value_type='other',
   e=>Object.assign(e,{kind:'STATE_CHANGE',tag_name:'TANK.LEVEL',before:false,value:true})
  ]) {
   const invalid=structuredClone(frame);invalid.sequence=2;invalid.event_id='PC-01:analog-invalid';
   mutate(invalid);
   assert.throws(()=>s.ingest('PC-01',[invalid]),{status:400});
  }
 } finally {s.close();fs.rmSync(d,{recursive:true,force:true})}
});

test('deployed HTTPS Gateway requires local receive approval, preserves lost ACK/dedup/restart and never probes before outbound approval',async t=>{
 const dir=temp(),tls=certificate(dir),wrong=certificate(dir,'wrong'),p=await port(),sourceSettings={deployment:{role:'gateway',id:'PC-04',listenHost:'127.0.0.1',listenPort:p,...tls,peers:{'PC-01':key},telegramMode:'telegram'}};let h,probes=0,sends=0;
 const gatewayOptions={telegram:{mode:'telegram',configured:true,probe:async()=>{probes++;return true},send:async()=>{sends++;return 1}}};
 t.after(async()=>{if(h)await h.close();fs.rmSync(dir,{recursive:true,force:true})});
 h=await startDeployedHost({dataRoot:path.join(dir,'data'),sourceSettings,gatewayOptions});const base=`https://127.0.0.1:${p}`,opts={caFile:tls.certFile};
 assert.equal(h.status().captureAllowed,false);assert.equal(h.status().transferAllowed,false);await new Promise(r=>setTimeout(r,250));assert.equal(probes,0);
 let hello=await requestJSON(base,'/v1/handshake',peer,{clientNonce:'b'.repeat(40)},opts);assert.equal(hello.ready,false);
 assert.equal((await h.request({id:'deny',command:'recording',running:true})).error.code,'CONSENT_REQUIRED');
 assert.equal((await h.request({id:'receive',command:'recording',running:true,approved:true})).ok,true);
 hello=await requestJSON(base,'/v1/handshake',peer,{clientNonce:'c'.repeat(40)},opts);assert.equal(hello.ready,true,'Durable receive readiness does not require Internet');
 const e=event();h.app.store.set('dropNextAck',true);await assert.rejects(requestJSON(base,'/v1/events',peer,{session:hello.session,events:[e]},opts));
 const reply=await requestJSON(base,'/v1/events',peer,{session:hello.session,events:[e]},opts);assert.deepEqual(reply.acks,[{event_id:e.event_id,sha256:digest(JSON.stringify(e))}]);assert.equal(h.app.status().received,1);assert.equal(h.app.status().duplicates,1);
 const source=h.status().remoteSources[0];assert.equal(source.sourceAdapter,'wincc-opc-da');assert.equal(source.observations['PUMP.RUN'].source_timestamp,e.observations['PUMP.RUN'].source_timestamp);assert.equal(source.readAt,e.read_at);assert.ok(source.lastReceivedAt);assert.equal(h.status().agents.length,0);
 const bad=event(2);bad.simulated=true;await assert.rejects(requestJSON(base,'/v1/events',peer,{session:hello.session,events:[bad]},opts));
 await assert.rejects(requestJSON(base,'/v1/handshake',{...peer,secret:'b'.repeat(64)},{clientNonce:'d'.repeat(40)},opts));
 await assert.rejects(requestJSON(base,'/v1/handshake',peer,{clientNonce:'e'.repeat(40)},{caFile:wrong.certFile}));
 assert.equal(probes,0);assert.equal(sends,0);
 assert.equal((await h.request({id:'send',command:'transfer',running:true,approved:true})).ok,true);await h.app.deliver();assert.ok(probes>0);assert.equal(h.status().gateway.egress.status,'VERIFIED');
 await h.close();h=await startDeployedHost({dataRoot:path.join(dir,'data'),sourceSettings,gatewayOptions});assert.equal(h.status().captureAllowed,false);assert.equal(h.status().transferAllowed,false);assert.equal(h.app.status().received,1);assert.equal(h.status().remoteSources[0].lastEventId,e.event_id);
 const before=probes;await h.app.deliver();assert.equal(probes,before);
});

async function wait(fn,ms=5000){const until=Date.now()+ms;while(Date.now()<until){if(fn())return;await new Promise(r=>setTimeout(r,25))}throw Error('Actual-use integration timeout')}
test('actual CSV Agent captures independently and resumes backlog without reading source when only transfer is allowed',async t=>{
 const dir=temp(),tls=certificate(dir),gp=await port(),ap=await port(),input=path.join(dir,'input');fs.mkdirSync(input);const file=path.join(input,'runtime_20261028.csv');fs.writeFileSync(file,'timestamp_local;tag_name;raw_value;quality_code;read_error\n2026-10-28T10:00:00;PUMP.RUN;1;128;0\n');const original=fs.readFileSync(file),mtime=fs.statSync(file).mtimeMs;let g,a,requests=0;
 t.after(async()=>{if(a)await a.close();if(g)await g.close();fs.rmSync(dir,{recursive:true,force:true})});
 g=await startDeployedHost({dataRoot:path.join(dir,'gateway'),sourceSettings:{deployment:{role:'gateway',id:'PC-04',listenHost:'127.0.0.1',listenPort:gp,...tls,peers:{'PC-01':key},telegramMode:'dry-run'}}});g.app.server.on('request',()=>requests++);await g.request({id:'receive',command:'recording',running:true,approved:true});
 const settings={sourceDirectory:input,tags:['PUMP.RUN'],timezoneOffset:'+07:00',mappingConfirmed:true,deployment:{role:'agent',id:'PC-01',listenHost:'127.0.0.1',listenPort:ap,gatewayUrl:`https://127.0.0.1:${gp}`,gatewaySecret:key,caFile:tls.certFile}};
 a=await startDeployedHost({dataRoot:path.join(dir,'agent'),sourceSettings:settings});assert.equal(a.status().captureAllowed,false);assert.equal(a.status().transferAllowed,false);assert.equal(a.app.server.address().address,'127.0.0.1');
 await a.request({id:'read',command:'recording',running:true,approved:true});await wait(()=>a.status().snapshots===1);await new Promise(r=>setTimeout(r,250));assert.equal(requests,0,'Capture alone must never contact Gateway');assert.equal(g.app.status().received,0);
 await a.request({id:'stopread',command:'recording',running:false});await a.request({id:'send',command:'transfer',running:true,approved:true});await wait(()=>g.app.status().received===1&&a.app.status().pending===0);assert.equal(a.status().captureAllowed,false);assert.equal(a.app.status().snapshots,1);assert.ok(requests>0);assert.equal(g.status().gateway.egress.status,'BLOCKED');assert.deepEqual(fs.readFileSync(file),original);assert.equal(fs.statSync(file).mtimeMs,mtime);
});

test('large actual CSV backlog makes forward progress with byte-bounded HTTPS batches',async t=>{
 const dir=temp(),tls=certificate(dir),gp=await port(),ap=await port(),input=path.join(dir,'input');fs.mkdirSync(input);const tags=Array.from({length:100},(_,i)=>'PUMP_'+String(i).padStart(3,'0')+'_'+('X'.repeat(88)));let body='timestamp_local;tag_name;raw_value;quality_code;read_error\n';for(let n=0;n<32;n++)for(const tag of tags)body+=`2026-10-28T10:00:${String(n).padStart(2,'0')};${tag};1;128;0\n`;fs.writeFileSync(path.join(input,'runtime_20261028.csv'),body);let g,a,largest=0;
 t.after(async()=>{if(a)await a.close();if(g)await g.close();fs.rmSync(dir,{recursive:true,force:true})});
 g=await startDeployedHost({dataRoot:path.join(dir,'gateway'),sourceSettings:{deployment:{role:'gateway',id:'PC-04',listenHost:'127.0.0.1',listenPort:gp,...tls,peers:{'PC-01':key},telegramMode:'dry-run'}}});g.app.server.on('request',req=>{let bytes=0;req.on('data',p=>bytes+=p.length);req.on('end',()=>{largest=Math.max(largest,bytes)})});await g.request({id:'receive',command:'recording',running:true,approved:true});
 a=await startDeployedHost({dataRoot:path.join(dir,'agent'),sourceSettings:{sourceDirectory:input,tags,timezoneOffset:'+07:00',mappingConfirmed:true,deployment:{role:'agent',id:'PC-01',listenHost:'127.0.0.1',listenPort:ap,gatewayUrl:`https://127.0.0.1:${gp}`,gatewaySecret:key,caFile:tls.certFile}}});await a.request({id:'capture',command:'recording',running:true,approved:true});await wait(()=>a.status().snapshots===32);await a.request({id:'stop-capture',command:'recording',running:false});assert.ok(a.app.store.pending().reduce((n,r)=>n+Buffer.byteLength(r.payload),0)>512*1024);await a.request({id:'transfer',command:'transfer',running:true,approved:true});await wait(()=>g.app.status().received===32&&a.app.status().pending===0,10000);assert.ok(largest<=500000);assert.equal(g.status().gateway.archiveCount,32);assert.equal(g.status().gateway.archiveSnapshots,32);
});

test('capture revisions retain one source sequence and immutable backlog across changed folders and Tag selections',async t=>{
 const dir=temp(),tls=certificate(dir),gp=await port(),ap=await port(),roots=['one','two','three'].map(n=>path.join(dir,n));for(const d of roots)fs.mkdirSync(d);
 const write=(n,tag,time,value)=>fs.writeFileSync(path.join(roots[n],'runtime_20261028.csv'),`timestamp_local;tag_name;raw_value;quality_code;read_error\n2026-10-28T${time};${tag};${value};128;0\n`);write(0,'PUMP.A','10:00:00',1);write(1,'PUMP.B','09:00:00',0);write(2,'PUMP.B','08:00:00',1);let g,a;
 t.after(async()=>{if(a)await a.close();if(g)await g.close();fs.rmSync(dir,{recursive:true,force:true})});
 g=await startDeployedHost({dataRoot:path.join(dir,'gateway'),sourceSettings:{deployment:{role:'gateway',id:'PC-04',listenHost:'127.0.0.1',listenPort:gp,...tls,peers:{'PC-01':key},telegramMode:'dry-run'}}});await g.request({id:'receive',command:'recording',running:true,approved:true});
 const settings=n=>({sourceDirectory:roots[n],tags:[n===0?'PUMP.A':'PUMP.B'],timezoneOffset:'+07:00',mappingConfirmed:true,deployment:{role:'agent',id:'PC-01',listenHost:'127.0.0.1',listenPort:ap,gatewayUrl:`https://127.0.0.1:${gp}`,gatewaySecret:key,caFile:tls.certFile}}),dataRoot=path.join(dir,'stable-agent');
 a=await startDeployedHost({dataRoot,sourceSettings:settings(0)});await a.request({id:'read-1',command:'recording',running:true,approved:true});await wait(()=>a.app.status().snapshots===1);await a.request({id:'send-1',command:'transfer',running:true,approved:true});await wait(()=>g.app.status().received===1&&a.app.status().pending===0);const first=g.app.store.db.prepare('SELECT payload FROM records WHERE seq=1').get().payload;await a.close();a=null;
 a=await startDeployedHost({dataRoot,sourceSettings:settings(1)});assert.deepEqual(a.app.status().observations,{});await a.request({id:'read-2',command:'recording',running:true,approved:true});await wait(()=>a.app.status().snapshots===2);assert.equal(a.app.status().sequence,2);assert.equal(a.app.status().pending,1);const pending=a.app.store.pending()[0].payload;await a.close();a=null;
 a=await startDeployedHost({dataRoot,sourceSettings:settings(2)});assert.deepEqual(a.app.status().observations,{});await a.request({id:'read-3',command:'recording',running:true,approved:true});await wait(()=>a.app.status().snapshots===3);assert.equal(a.app.status().sequence,3,'New capture revision must not synthesize a cross-origin transition');assert.equal(a.app.status().pending,2);assert.equal(a.app.store.pending()[0].payload,pending);await a.request({id:'send-3',command:'transfer',running:true,approved:true});await wait(()=>g.app.status().received===3&&a.app.status().pending===0);assert.equal(g.app.store.db.prepare('SELECT payload FROM records WHERE seq=1').get().payload,first);assert.equal(g.status().remoteSources[0].pumps['PUMP.B'],true);
});

test('approved actual Agent uses immutable custom CA trust while files change',async t=>{
 const dir=temp(),first=certificate(dir),second=certificate(dir,'second'),ca=path.join(dir,'agent-ca.crt'),gp=await port(),ap=await port(),input=path.join(dir,'input');fs.copyFileSync(first.certFile,ca);fs.mkdirSync(input);const file=path.join(input,'runtime_20261028.csv');fs.writeFileSync(file,'timestamp_local;tag_name;raw_value;quality_code;read_error\n2026-10-28T10:00:00;PUMP.RUN;1;128;0\n');let g,a;
 t.after(async()=>{if(a)await a.close();if(g)await g.close();fs.rmSync(dir,{recursive:true,force:true})});
 const gateway=tls=>({deployment:{role:'gateway',id:'PC-04',listenHost:'127.0.0.1',listenPort:gp,...tls,peers:{'PC-01':key},telegramMode:'dry-run'}}),gdata=path.join(dir,'gateway');g=await startDeployedHost({dataRoot:gdata,sourceSettings:gateway(first)});await g.request({id:'receive',command:'recording',running:true,approved:true});
 a=await startDeployedHost({dataRoot:path.join(dir,'agent'),sourceSettings:{sourceDirectory:input,tags:['PUMP.RUN'],timezoneOffset:'+07:00',mappingConfirmed:true,deployment:{role:'agent',id:'PC-01',listenHost:'127.0.0.1',listenPort:ap,gatewayUrl:`https://127.0.0.1:${gp}`,gatewaySecret:key,caFile:ca}}});await a.request({id:'read',command:'recording',running:true,approved:true});await wait(()=>a.app.status().snapshots===1);await a.request({id:'send',command:'transfer',running:true,approved:true});await wait(()=>g.app.status().received===1&&a.app.status().pending===0);
 await g.close();g=null;fs.copyFileSync(second.certFile,ca);g=await startDeployedHost({dataRoot:gdata,sourceSettings:gateway(second)});await g.request({id:'receive-2',command:'recording',running:true,approved:true});fs.appendFileSync(file,'2026-10-28T10:00:01;PUMP.RUN;1;128;0\n');a.app.sample();a.app.nextRetry=0;await a.app.step({sample:false});assert.equal(a.app.status().pending,1,'New CA must not be trusted by changing the approved file during active transfer');assert.equal(g.app.status().received,1);
 await a.request({id:'revoke-send',command:'transfer',running:false});assert.equal((await a.request({id:'new-send',command:'transfer',running:true,approved:true})).ok,false,'Changed trust requires restarting reviewed configuration');assert.equal(a.app.transferAllowed,false);
});
