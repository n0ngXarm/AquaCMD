/** Actual-use local role owner. No fixtures, network scans, remote controls or UI listener. */
import fs from 'node:fs';import path from 'node:path';import {isIP} from 'node:net';import {createSecureContext} from 'node:tls';import {randomBytes,randomUUID} from 'node:crypto';
import {createAgent,createGateway,retainedExport} from '../backend/src/lan/services.js';
import {CsvReadonlySource,assertStorageOutsideInput} from '../backend/src/lan/csv-source.js';
import {assertOwnedStorage} from '../backend/src/lan/storage-boundary.js';
import {endpoint,digest,encode} from '../backend/src/lan/protocol.js';
const key=v=>typeof v==='string'&&/^[a-f0-9]{64}$/.test(v);
const member=v=>/^PC-0[123]$/.test(v);
const privateIPv4=v=>isIP(v)===4&&(v.startsWith('10.')||v.startsWith('192.168.')||v.startsWith('172.')&&Number(v.split('.')[1])>=16&&Number(v.split('.')[1])<=31);
const ownHost=v=>v==='127.0.0.1'||privateIPv4(v);
export function validateDeployment(value){
 if(!value||typeof value!=='object'||Array.isArray(value))throw Error('Explicit deployed role required');
 const c={...value};if(Object.keys(c).some(k=>!['role','id','listenHost','listenPort','certFile','keyFile','peers','gatewayUrl','gatewaySecret','caFile','telegramMode'].includes(k)))throw Error('Unsupported deployment setting');
 if(c.role==='agent'&&c.telegramMode===undefined)c.telegramMode='dry-run';
 if(!['agent','gateway'].includes(c.role)||!Number.isSafeInteger(c.listenPort)||c.listenPort<1024||c.listenPort>65535||!['dry-run','telegram'].includes(c.telegramMode))throw Error('Invalid explicit deployed role/listener');
 if(c.role==='agent'){
  if(!member(c.id)||c.listenHost!=='127.0.0.1'||!key(c.gatewaySecret)||(c.caFile!==undefined&&typeof c.caFile!=='string'))throw Error('Agent requires local-only control and approved peer trust');
  const u=endpoint(c.gatewayUrl,{allowLan:true});if(u.protocol!=='https:')throw Error('Actual Gateway requires TLS');
 }else{
  if(c.id!=='PC-04'||!ownHost(c.listenHost)||typeof c.certFile!=='string'||!c.certFile.length||typeof c.keyFile!=='string'||!c.keyFile.length||!c.peers||typeof c.peers!=='object'||Array.isArray(c.peers)||!Object.keys(c.peers).length||Object.keys(c.peers).length>3||Object.entries(c.peers).some(([id,secret])=>!member(id)||!key(secret))||new Set(Object.values(c.peers)).size!==Object.keys(c.peers).length)throw Error('Gateway requires explicit bind, TLS and enrolled exporters');
 }
 return c;
}
export async function startDeployedHost({dataRoot,sourceSettings={},emit=()=>{},gatewayOptions={}}){
 if(!dataRoot)throw Error('Separate owned AQUA storage required');
 if(Object.keys(sourceSettings).some(k=>!['deployment','sourceDirectory','tags','timezoneOffset','mappingConfirmed'].includes(k)))throw Error('Unsupported actual source setting');
 const d=validateDeployment(sourceSettings.deployment),root=path.resolve(dataRoot);assertOwnedStorage(root);
 const roleDir=path.join(root,d.id),isGateway=d.role==='gateway',approvedCA=!isGateway&&d.caFile?Buffer.from(fs.readFileSync(d.caFile)):undefined;
 if(!isGateway){if(!sourceSettings.sourceDirectory)throw Error('Actual Agent requires an explicitly selected Runtime CSV source; no simulated fallback');if(!fs.statSync(sourceSettings.sourceDirectory).isDirectory())throw Error('Actual CSV directory unavailable');assertStorageOutsideInput(sourceSettings.sourceDirectory,root);new CsvReadonlySource({dataDir:roleDir,csv:{directory:sourceSettings.sourceDirectory,tags:sourceSettings.tags,timezoneOffset:sourceSettings.timezoneOffset||'+07:00',mappingConfirmed:sourceSettings.mappingConfirmed===true,fixture:false}},null,d.id);}
 if(isGateway)createSecureContext({cert:fs.readFileSync(d.certFile),key:fs.readFileSync(d.keyFile)});
 const cfg={id:d.id,role:d.role,listen:{host:d.listenHost,port:d.listenPort},dataDir:roleDir,allowLan:true,readOnly:true,realOnly:true,requireConsent:true,intervalMs:5000,storage:{realOnly:true}};
 let app;
 if(isGateway){Object.assign(cfg,{tls:{certFile:d.certFile,keyFile:d.keyFile},keys:{...d.peers,DASHBOARD:randomBytes(32).toString('hex')},internetMode:'real',internetOnline:true,requireReceiveConsent:true,storeFirst:true});app=createGateway(cfg,{...gatewayOptions,...(gatewayOptions.telegram?{}:{env:d.telegramMode==='telegram'?{...process.env,TELEGRAM_ENABLED:'true'}:{}})});}
 else{Object.assign(cfg,{secret:d.gatewaySecret,gatewayUrl:d.gatewayUrl,caData:approvedCA,sourceAdapter:'wincc-csv',csv:{directory:sourceSettings.sourceDirectory,tags:sourceSettings.tags,timezoneOffset:sourceSettings.timezoneOffset||'+07:00',mappingConfirmed:sourceSettings.mappingConfirmed===true,fixture:false,captureRevision:digest(encode({directory:fs.realpathSync(sourceSettings.sourceDirectory),tags:sourceSettings.tags,timezoneOffset:sourceSettings.timezoneOffset||'+07:00',mappingConfirmed:sourceSettings.mappingConfirmed===true,goodQualityCodes:[128]}))}});app=createAgent(cfg)}
 try{app.store.acquireOwner(d.id);
  if(!isGateway&&app.store.get('captureRevision')!==cfg.csv.captureRevision)app.store.tx(()=>{
   // Capture revisions share one durable source sequence. Old pending records and cursor namespaces remain immutable.
   app.store.set('runtimePrevious',{});app.store.set('runtimeObservations',{});app.store.set('pumps',Object.fromEntries(sourceSettings.tags.map(tag=>[tag,null])));app.store.set('runtimeObservedAt',null);app.store.set('lastExport',null);app.store.set('captureRevision',cfg.csv.captureRevision);
  });
  await app.start()}catch(e){try{await app.close()}catch{}throw e}
 let stopped=false;
 const metadata={role:d.role,id:d.id,listenHost:d.listenHost,listenPort:d.listenPort,configuredEndpoint:`${isGateway?'https':'http'}://${d.listenHost}:${d.listenPort}`,gatewayUrl:isGateway?null:d.gatewayUrl,telegramMode:d.telegramMode,peerIds:isGateway?Object.keys(d.peers):[]};
 function remoteSources(){
  if(!isGateway)return [];
  return Object.keys(d.peers).flatMap(id=>{
   const row=app.store.db.prepare("SELECT payload FROM records WHERE source=? AND kind='SNAPSHOT' ORDER BY seq DESC LIMIT 1").get(id);if(!row)return [];
   const e=JSON.parse(row.payload);if(e.simulated!==false)return [];
   return [{id,sourceAdapter:e.source_adapter||'wincc-csv',simulated:false,observedAt:e.observed_at,readAt:e.read_at||null,lastReceivedAt:app.store.get('receivedAt:'+id),lastExport:e.at,observations:e.observations,pumps:e.values,lastEventId:e.event_id}];
  });
 }
 const status=()=>{
  const now=new Date().toISOString(),{latest:retainedPayload,...ownFields}=app.status(),own={...ownFields,online:true,lastSeen:now},counts=isGateway?app.store.db.prepare("SELECT count(*) archiveCount,sum(CASE WHEN kind='SNAPSHOT' THEN 1 ELSE 0 END) archiveSnapshots FROM records").get():null,gateway=isGateway?{...own,internetOnline:own.egress?.status==='VERIFIED',archiveOnly:true,archiveCount:Number(counts.archiveCount),archiveSnapshots:Number(counts.archiveSnapshots||0),retainedRecords:Number(counts.archiveCount)}:null;
  return {deployment:metadata,profile:'deployed',simulation:false,readOnly:true,frontend:'native-gtk4',webUiEnabled:false,time:now,exportIntervalSeconds:5,agents:isGateway?[]:[own],remoteSources:remoteSources(),gateway,central:null,captureAllowed:isGateway?app.receiveAllowed:app.captureAllowed,transferAllowed:app.transferAllowed,snapshots:isGateway?null:own.snapshots,scadaQueueCount:isGateway?null:own.pending,gatewayQueueCount:isGateway?own.pending:null,acked:isGateway?null:own.acked,delivered:null,notificationSent:isGateway?own.notificationSent:null,notificationPending:isGateway?own.notificationPending:null,notificationMode:isGateway?own.notificationMode:'NOT_CONFIGURED',gatewayConnected:isGateway?true:own.gatewayAuthenticated===true,internetStatus:isGateway?own.egress?.status||'NOT_MEASURED':'NOT_MEASURED',internetMode:'real',events:(own.logs||[]).map(e=>({...e,id:d.id+':'+e.id,message:d.id+' · '+e.message}))};
 };
 async function setTransfer(running){if(running&&approvedCA&&digest(fs.readFileSync(d.caFile))!==digest(approvedCA))throw Error('TLS trust changed; restart reviewed configuration');app.transferAllowed=running;app.transferGeneration++;if(!running){if(!isGateway){app.session=null;app.gatewayAuthenticated=false}if(app.busy)await app.busy.catch(()=>{})}}
 async function exportCsv(){
  const result=retainedExport(app.store),lines=['recorded_at;observed_at;source_id;tag_name;raw_value;quality_code;read_error;quality;source_timestamp'];
  for(const e of result.records.filter(e=>[2,3].includes(e.schema_version)&&e.kind==='SNAPSHOT'))for(const [tag,o] of Object.entries(e.observations))lines.push([e.at,e.observed_at,e.source_id,tag,o.raw_value??'',o.quality_code??'',o.read_error,o.quality,o.source_timestamp??''].join(';'));
  const directory=path.join(root,'exports');if(sourceSettings.sourceDirectory)assertStorageOutsideInput(sourceSettings.sourceDirectory,directory);assertOwnedStorage(root);fs.mkdirSync(directory,{recursive:true,mode:0o700});
  const file=path.join(directory,`AQUA-${Date.now()}-${randomUUID().slice(0,8)}.csv`),fd=fs.openSync(file,'wx',0o600);try{fs.writeFileSync(fd,lines.join('\r\n')+'\r\n');fs.fsyncSync(fd)}finally{fs.closeSync(fd)}return {path:file,rows:lines.length-1,truncated:result.truncated,totalRecords:result.totalRecords};
 }
 const timer=setInterval(()=>{if(!stopped)emit({type:'status',data:status()})},1000);
 return {app,status,async request(m){
  if(!m||typeof m.id!=='string'||!m.id.length||m.id.length>80)return {id:null,ok:false,error:{code:'INVALID_REQUEST'}};
  if(stopped)return {id:m.id,ok:false,error:{code:'CLOSING'}};
  if(!['status','recording','transfer','export_csv'].includes(m.command)||Object.keys(m).some(k=>!['id','command',...(['recording','transfer'].includes(m.command)?['running','approved']:[])].includes(k)))return {id:m.id,ok:false,error:{code:'READ_ONLY',message:'Only own local capture/receive, outbound permission and saved-data export are supported'}};
  if(['recording','transfer'].includes(m.command)&&m.running===true&&m.approved!==true)return {id:m.id,ok:false,error:{code:'CONSENT_REQUIRED'}};
  try{
   if(['recording','transfer'].includes(m.command)&&typeof m.running!=='boolean')throw Error('Boolean required');
   if(m.command==='recording'){
    if(isGateway)app.receiveAllowed=m.running;
    else{app.captureAllowed=m.running;app.store.set('recordingPaused',!m.running)}
   }else if(m.command==='transfer')await setTransfer(m.running);
   else if(m.command==='export_csv')return {id:m.id,ok:true,result:await exportCsv()};
   return {id:m.id,ok:true,result:status()};
  }catch{return {id:m.id,ok:false,error:{code:'LOCAL_OPERATION_FAILED',message:'Check selected source, private storage and approved peer configuration'}}}
 },async close(){if(stopped)return;stopped=true;clearInterval(timer);if(isGateway)app.receiveAllowed=false;else app.captureAllowed=false;await setTransfer(false);await app.close()}};
}
