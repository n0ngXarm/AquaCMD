import http from 'node:http';
import fs from 'node:fs';
import path from 'node:path';
import crypto from 'node:crypto';
import { fileURLToPath } from 'node:url';
import { RULES, severityOf, evaluateTelemetry, alertMessage } from './rules.mjs';

const ROOT = path.dirname(fileURLToPath(import.meta.url));
for (const line of (fs.existsSync(path.join(ROOT,'.env')) ? fs.readFileSync(path.join(ROOT,'.env'),'utf8') : '').split(/\r?\n/)) {
  const m = line.match(/^\s*([A-Z][A-Z0-9_]*)\s*=\s*(.*?)\s*$/);
  if (m && !Object.hasOwn(process.env,m[1])) process.env[m[1]] = m[2].replace(/^(['"])(.*)\1$/,'$2');
}
const HOST = process.env.HOST || '127.0.0.1';
const PORT = Number(process.env.PORT) || 8787;
const DEMO = process.env.DEMO_MODE !== 'false';
const SEND_DEMO = process.env.SEND_DEMO_ALERTS === 'true';
const BOT = process.env.TELEGRAM_BOT_TOKEN || '';
const CHAT = process.env.TELEGRAM_CHAT_ID || '';
const APP_ENV = (process.env.APP_ENV || 'lab').toLowerCase();
const TELEGRAM_DELIVERY_AUTHORIZED = APP_ENV === 'production' && process.env.TELEGRAM_EXTERNAL_DELIVERY_AUTHORIZED === 'true';
const SECRET = process.env.ADMIN_API_KEY || '';
const REMINDER_MS = Math.max(5, Number(process.env.REMINDER_MINUTES)||30)*60_000;
const SEND_GAP = Math.max(1000, Number(process.env.TELEGRAM_MIN_GAP_MS)||1400);
const STALE_AFTER_MS = Math.max(30,Number(process.env.STALE_AFTER_SECONDS)||120)*1000;
const DATA_PATH = path.join(ROOT,'storage','state.json');
const PUBLIC = path.join(ROOT,'public');
fs.mkdirSync(path.dirname(DATA_PATH), {recursive:true});
const now = () => new Date().toISOString();
const num = (n,d=1) => Math.round(n*10**d)/10**d;
const safeId = v => typeof v === 'string' && /^[\w-]{2,64}$/.test(v);
const stations = [
  {id:'CM-01',name:'สถานีผลิตน้ำป่าตัน',district:'เมืองเชียงใหม่',region:'อำเภอเมืองเชียงใหม่',zone:'โซนเมือง',pwaBranch:'กปภ.สาขาเชียงใหม่ (พ)',lat:18.824,lon:98.995,px:371.0,py:248.8,x:60.5,y:45.7,pressureBar:2.84,tankLevelPct:78,flowM3h:2860,turbidityNtu:0.48,chlorineMgL:0.54,online:true},
  {id:'CM-02',name:'ตัวอย่าง LAB',district:'เมืองเชียงใหม่',region:'อำเภอเมืองเชียงใหม่',zone:'โซนเมือง',pwaBranch:'กปภ.สาขาเชียงใหม่ (พ)',lat:18.790,lon:98.955,px:355.6,py:254.7,x:57.9,y:46.9,pressureBar:2.65,tankLevelPct:82,flowM3h:1950,turbidityNtu:0.38,chlorineMgL:0.51,online:true},
  {id:'CM-03',name:'สถานีผลิตน้ำแม่กวง',district:'สันทราย',region:'อำเภอสันทราย',zone:'โซนตะวันออก',pwaBranch:'กปภ.สาขาเชียงใหม่ (พ)',lat:18.855,lon:99.045,px:390.2,py:243.5,x:63.8,y:44.7,pressureBar:2.72,tankLevelPct:74,flowM3h:1820,turbidityNtu:0.42,chlorineMgL:0.48,online:true},
  {id:'CM-04',name:'สถานีผลิตน้ำแม่แฝก',district:'สันทราย',region:'อำเภอสันทราย',zone:'โซนเหนือ',pwaBranch:'กปภ.สาขาเชียงใหม่ (พ)',lat:19.005,lon:99.020,px:380.6,py:217.7,x:62.2,y:39.5,pressureBar:2.45,tankLevelPct:69,flowM3h:940,turbidityNtu:0.35,chlorineMgL:0.49,online:true},
  {id:'CM-05',name:'สถานีจ่ายน้ำแม่ริม',district:'แม่ริม',region:'อำเภอแม่ริม',zone:'โซนเหนือ',pwaBranch:'กปภ.สาขาแม่ริม',lat:18.915,lon:98.945,px:351.8,py:233.2,x:57.2,y:42.6,pressureBar:2.58,tankLevelPct:71,flowM3h:1420,turbidityNtu:0.44,chlorineMgL:0.46,online:true},
  {id:'CM-06',name:'สถานีผลิตน้ำสันกำแพง',district:'สันกำแพง',region:'อำเภอสันกำแพง',zone:'โซนตะวันออก',pwaBranch:'กปภ.สาขาสันกำแพง',lat:18.745,lon:99.120,px:419.1,py:262.4,x:68.8,y:48.5,pressureBar:2.35,tankLevelPct:65,flowM3h:1150,turbidityNtu:0.51,chlorineMgL:0.44,online:true},
  {id:'CM-07',name:'สถานีจ่ายน้ำหางดง',district:'หางดง',region:'อำเภอหางดง',zone:'โซนใต้',pwaBranch:'กปภ.สาขาเชียงใหม่ (พ)',lat:18.685,lon:98.915,px:340.2,py:272.8,x:55.2,y:50.5,pressureBar:2.48,tankLevelPct:68,flowM3h:1280,turbidityNtu:0.39,chlorineMgL:0.52,online:true},
  {id:'CM-08',name:'สถานีจ่ายน้ำสารภี',district:'สารภี',region:'อำเภอสารภี',zone:'โซนใต้',pwaBranch:'กปภ.สาขาเชียงใหม่ (พ)',lat:18.710,lon:99.035,px:386.4,py:268.5,x:63.2,y:49.7,pressureBar:2.61,tankLevelPct:77,flowM3h:1360,turbidityNtu:0.41,chlorineMgL:0.50,online:true},
  {id:'CM-09',name:'สถานีผลิตน้ำแม่แตง',district:'แม่แตง',region:'อำเภอแม่แตง',zone:'โซนเหนือ',pwaBranch:'กปภ.สาขาแม่แตง',lat:19.125,lon:98.940,px:349.8,py:197.0,x:56.9,y:35.4,pressureBar:2.38,tankLevelPct:64,flowM3h:880,turbidityNtu:0.45,chlorineMgL:0.47,online:true},
  {id:'CM-10',name:'สถานีผลิตน้ำจอมทอง',district:'จอมทอง',region:'อำเภอจอมทอง',zone:'โซนใต้',pwaBranch:'กปภ.สาขาจอมทอง',lat:18.420,lon:98.680,px:249.8,py:318.4,x:39.6,y:59.7,pressureBar:2.52,tankLevelPct:73,flowM3h:1020,turbidityNtu:0.40,chlorineMgL:0.45,online:true},
  {id:'CM-11',name:'สถานีผลิตน้ำฝาง',district:'ฝาง',region:'อำเภอฝาง',zone:'โซนเหนือสุด',pwaBranch:'กปภ.สาขาฝาง',lat:19.915,lon:99.210,px:453.7,py:61.0,x:74.8,y:8.2,pressureBar:2.42,tankLevelPct:66,flowM3h:950,turbidityNtu:0.43,chlorineMgL:0.43,online:true},
  {id:'CM-12',name:'สถานีผลิตน้ำฮอด',district:'ฮอด',region:'อำเภอฮอด',zone:'โซนใต้สุด',pwaBranch:'กปภ.สาขาฮอด',lat:18.190,lon:98.610,px:222.8,py:358.0,x:35.0,y:67.6,pressureBar:2.30,tankLevelPct:61,flowM3h:760,turbidityNtu:0.46,chlorineMgL:0.42,online:true}
];
const reservoirs = [
  {id:'RES-01',name:'เขื่อนแม่งัดสมบูรณ์ชล',nameEn:'Mae Ngat Somboon Chon Dam',district:'แม่แตง',capacityMcm:265.0,storageMcm:212.5,storagePct:80.2,inflowM3s:14.2,outflowM3s:8.5,status:'normal',statusText:'ปกติ (80.2%)'},
  {id:'RES-02',name:'เขื่อนแม่กวงอุดมธารา',nameEn:'Mae Kuang Udom Thara Dam',district:'ดอยสะเก็ด',capacityMcm:263.0,storageMcm:189.4,storagePct:72.0,inflowM3s:11.8,outflowM3s:6.2,status:'normal',statusText:'ปกติ (72.0%)'},
  {id:'RES-03',name:'จุดสูบน้ำดิบตัวอย่าง LAB (ป่าตัน)',nameEn:'Ping River Raw Water Intake',district:'เมืองเชียงใหม่',capacityMcm:null,waterLevelM:3.45,thresholdM:3.70,storagePct:93.2,status:'normal',statusText:'ระดับน้ำปกติ (3.45 ม.รทก.)'}
];
for (const s of stations) {
  s.hasTelemetry=DEMO;
  s.lastSeen=DEMO?now():null;
  if (!DEMO) for(const field of ['pressureBar','tankLevelPct','flowM3h','turbidityNtu','chlorineMgL']) s[field]=null;
  if (!DEMO) s.online=false;
}
const history = Array.from({length:96},(_,i)=>({
  time: new Date(Date.now()-(95-i)*15*60_000).toISOString(),
  pressure: num(2.62+Math.sin(i*.24)*.24+Math.sin(i*.07)*.12+Math.random()*.08,2),
  flow: Math.round(22.5+Math.sin(i*.16)*2.6+Math.cos(i*.39)*1.2+Math.random()*.7),
  tank: num(72+Math.sin(i*.11)*6+Math.random()*1.8,1)
}));
if (!DEMO) history.length=0;
function isAlertAcknowledged(alert) {
  if (!alert || typeof alert !== 'object') return false;
  return Boolean(
    alert.acknowledgedAt ||
    alert.acknowledged === true ||
    alert.ack === true ||
    alert.status === 'acknowledged' ||
    alert.acknowledged_at
  );
}

function isAlertResolved(alert) {
  if (!alert || typeof alert !== 'object') return false;
  return Boolean(
    alert.resolvedAt ||
    alert.resolved === true ||
    alert.severity === 'resolved' ||
    alert.status === 'resolved' ||
    alert.resolved_at ||
    alert.supersededAt
  );
}

function migrateLoadedAlert(a) {
  if (!a || typeof a !== 'object') return a;
  const isAck = isAlertAcknowledged(a);
  const isRes = isAlertResolved(a);
  return {
    ...a,
    createdAt: a.createdAt || now(),
    acknowledgedAt: a.acknowledgedAt || (isAck ? (a.updatedAt || a.createdAt || now()) : null),
    resolvedAt: a.resolvedAt || (isRes ? (a.updatedAt || a.createdAt || now()) : null),
    acknowledged: isAck,
    resolved: isRes
  };
}

let persistenceUncertain = false;
let store = {alerts:[], queue:[], active:{}, updatedAt:now()};
try {
  const previous = JSON.parse(fs.readFileSync(DATA_PATH, 'utf8'));
  if (!previous || typeof previous !== 'object' || Array.isArray(previous) ||
      ('alerts' in previous && !Array.isArray(previous.alerts)) ||
      ('queue' in previous && !Array.isArray(previous.queue)) ||
      ('active' in previous && (!previous.active || typeof previous.active !== 'object' || Array.isArray(previous.active)))) {
    throw new Error('Invalid alert state schema');
  }
  const prevAlerts = (previous.alerts||[]).map(migrateLoadedAlert);
  let migrated = false;
  const prevQueue = (previous.queue||[]).map(j => {
    if (!j.payload) {
      const al = prevAlerts.find(a => a.id === j.alertId);
      if (al) {
        migrated = true;
        j.payload = {
          text: alertMessage(al),
          title: al.title,
          severity: al.severity,
          stationName: al.stationName,
          region: al.region,
          message: al.message,
          value: al.value,
          demo: Boolean(al.demo),
          createdAt: al.createdAt
        };
      }
    }
    if (j.status === 'sending' ||
        (!j.deliveryProtocolVersion && ['pending', 'failed'].includes(j.status) && j.attempt > 0)) {
      migrated = true;
      return {...j, status: 'delivery_unknown', lastError: 'Previous delivery could not be confirmed'};
    }
    return j;
  });
  store={...store, alerts:prevAlerts, queue:prevQueue, active:previous.active||{}};
  if (migrated) persist(store);
}
catch (e) {
  if (e.code !== 'ENOENT') throw new Error('Cannot load alert state; existing storage was left intact', {cause: e});
}
const MAX_ALERT_STORE = 400;

function isAlertReferenced(draft, alertId) {
  return draft.queue.some(job => job.alertId === alertId && !['sent', 'simulated'].includes(job.status));
}

function canPruneAlert(draft, alert) {
  if (isAlertReferenced(draft, alert.id)) return false;
  if (!isAlertAcknowledged(alert) && !isAlertResolved(alert)) return false;
  return true;
}

function trimAlerts(draft, maxLimit) {
  const excess = draft.alerts.length - maxLimit;
  if (excess <= 0) return;
  const prunables = new Set();
  for (let i = draft.alerts.length - 1; i >= 0 && prunables.size < excess; i--) {
    const alert = draft.alerts[i];
    if (canPruneAlert(draft, alert)) prunables.add(alert);
  }
  draft.alerts = draft.alerts.filter(alert => !prunables.has(alert));
}

const MAX_QUEUE_SIZE = 500;
function trimQueue(draft = store, maxLimit = MAX_QUEUE_SIZE) {
  const excess = draft.queue.length - maxLimit;
  if (excess <= 0) return;
  const protectedAlerts = new Set(draft.alerts.filter(alert =>
    !isAlertAcknowledged(alert) && !isAlertResolved(alert)).map(alert => alert.id));
  const prunables = new Set();
  for (const job of draft.queue) {
    if (prunables.size >= excess) break;
    if (['sent', 'simulated'].includes(job.status) && !protectedAlerts.has(job.alertId)) {
      prunables.add(job);
    }
  }
  draft.queue = draft.queue.filter(job => !prunables.has(job));
}

function capacityError(message) {
  return Object.assign(new Error(message), {status: 503, code: 'ALERT_CAPACITY', retryAfterSeconds: 30});
}

function newOutboxJob(alert) {
  const {title, severity, stationName, region, message, value, demo, createdAt} = alert;
  const payload = {text: alertMessage(alert), title, severity, stationName, region, message, value, demo, createdAt};
  return {id: crypto.randomUUID(), alertId: alert.id, status: 'pending', deliveryProtocolVersion: 2, attempt: 0,
          nextAt: Date.now(), createdAt: now(), lastError: null, payload};
}

let saveTimer;
function saveSoon() {clearTimeout(saveTimer); saveTimer=setTimeout(saveNow,400);}
function persist(snapshot) {
  const dir = path.dirname(DATA_PATH);
  const temp = path.join(dir, `.${path.basename(DATA_PATH)}.${crypto.randomBytes(6).toString('hex')}.tmp`);
  let fd;
  let dirFd;
  let created = false;
  let renamed = false;
  try {
    dirFd = fs.openSync(dir, 'r');
    fd = fs.openSync(temp, 'wx', 0o600);
    created = true;
    fs.writeFileSync(fd, JSON.stringify(snapshot, null, 2), 'utf8');
    fs.fsyncSync(fd);
    fs.closeSync(fd);
    fd = undefined;
    fs.renameSync(temp, DATA_PATH);
    renamed = true;
    fs.fsyncSync(dirFd);
    persistenceUncertain = false;
  } catch (cause) {
    if (renamed) persistenceUncertain = true;
    const message = renamed ? 'Alert state commit durability is uncertain' : 'Could not persist alert state';
    throw Object.assign(new Error(message, {cause}), {
      status: renamed ? 500 : 503,
      code: renamed ? 'ALERT_COMMIT_UNKNOWN' : 'ALERT_PERSISTENCE',
      renamed,
    });
  } finally {
    if (fd !== undefined) try { fs.closeSync(fd); } catch {}
    if (dirFd !== undefined) try { fs.closeSync(dirFd); } catch {}
    if (created && !renamed) try { fs.unlinkSync(temp); } catch {}
  }
}

function saveNow() {
  try { persist(store); } catch (error) { console.error(error.message, error.cause?.code); }
}

function commitAlerts(update) {
  // Keep in-flight job objects shared: producers only append or remove queue entries.
  const draft = {...store, alerts: store.alerts.map(alert => ({...alert})),
                 queue: [...store.queue], active: {...store.active}};
  const addedAlerts = [];
  const addedJobs = [];
  function stageAlert(alert, notify = false) {
    addedAlerts.push(alert);
    if (notify) addedJobs.push(newOutboxJob(alert));
  }
  const result = update(draft, stageAlert);
  if (result === false && !persistenceUncertain) return;
  if (addedJobs.length) {
    trimQueue(draft, MAX_QUEUE_SIZE - addedJobs.length);
    if (draft.queue.length + addedJobs.length > MAX_QUEUE_SIZE) throw capacityError('Outbox capacity limit reached');
  }
  if (addedAlerts.length) {
    trimAlerts(draft, MAX_ALERT_STORE - addedAlerts.length);
    if (draft.alerts.length + addedAlerts.length > MAX_ALERT_STORE) {
      throw capacityError('Alert store capacity limit reached: active alerts require acknowledgement');
    }
  }
  draft.alerts.unshift(...addedAlerts.reverse());
  draft.queue.push(...addedJobs);
  try {
    persist(draft);
  } catch (error) {
    // After rename the file may already be visible. Never overwrite it with the old state.
    if (error.renamed) store = draft;
    throw error;
  }
  store = draft;
  return result;
}

function statusOf(s) {if (!s.hasTelemetry) return 'unknown';const a=evaluateTelemetry(s);return a.some(x=>x.severity==='critical')?'critical':a.some(x=>x.severity==='warning')?'warning':'normal';}
function snapshot() {
  const details=stations.map(s=>({...s,status:statusOf(s)}));
  const valid=details.filter(s=>s.hasTelemetry);
  const mean=field=>{const values=valid.map(s=>s[field]).filter(v=>typeof v==='number');return values.length?values.reduce((a,b)=>a+b,0)/values.length:0;};
  const alertCounts={critical:store.alerts.filter(a=>a.severity==='critical'&&!a.resolvedAt&&!a.supersededAt).length,warning:store.alerts.filter(a=>a.severity==='warning'&&!a.resolvedAt&&!a.supersededAt).length};
  const activeStationAlerts=details.filter(s=>s.status!=='normal').length;
  const resAvg=Math.round(reservoirs.reduce((a,r)=>a+(r.storagePct||0),0)/reservoirs.length*10)/10;
  return {
    province:'เชียงใหม่',
    serverTime:now(),
    mode:DEMO?'demo':'live-ingest',
    stations:details,
    reservoirs,
    history,
    alerts:store.alerts.slice(0,100),
    queueStats:{
      pending:store.queue.filter(x=>x.status==='pending').length,
      retryPending:store.queue.filter(x=>x.status==='retry_pending').length,
      sending:store.queue.filter(x=>x.status==='sending').length,
      deliveryUnknown:store.queue.filter(x=>x.status==='delivery_unknown').length,
      failed:store.queue.filter(x=>x.status==='failed').length,
      sent:store.queue.filter(x=>x.status==='sent').length,
      simulated:store.queue.filter(x=>x.status==='simulated').length,
      blocked:store.queue.filter(x=>x.status==='blocked_by_policy').length
    },
    queueUnknown:store.queue.filter(job => job.status === 'delivery_unknown')
      .map(({id, alertId, createdAt, attempt}) => ({id, alertId, createdAt, attempt})),
    queueRecent:store.queue.slice(-8).reverse().map(j=>({id:j.id,alertId:j.alertId,status:j.status,attempt:j.attempt,createdAt:j.createdAt,sentAt:j.sentAt||null,simulatedAt:j.simulatedAt||null,blockedAt:j.blockedAt||null,lastError:j.lastError||null})),
    metrics:{
      total:details.length,
      online:details.filter(x=>x.online).length,
      normal:details.filter(x=>x.status==='normal').length,
      warning:details.filter(x=>x.status==='warning').length,
      critical:details.filter(x=>x.status==='critical').length,
      activeStations:activeStationAlerts,
      pressure:num(mean('pressureBar'),2),
      tank:num(mean('tankLevelPct'),1),
      flow:Math.round(valid.reduce((a,s)=>a+(s.flowM3h||0),0)),
      turbidity:num(mean('turbidityNtu'),2),
      chlorine:num(mean('chlorineMgL'),2),
      reservoirAvgPct:resAvg,
      activeAlertCount:alertCounts.critical+alertCounts.warning
    },
    telegram:{configured:Boolean(BOT&&CHAT),demoForwarding:SEND_DEMO,reminderMinutes:REMINDER_MS/60},
    rules:RULES.map(({id,title,warning,critical,unit,direction})=>({id,title,warning,critical,unit,direction}))
  };
}
const clients = new Set();
function broadcast() {const message=`data: ${JSON.stringify(snapshot())}\n\n`;for(const c of clients) try{c.write(message);}catch{clients.delete(c);}}
const uid=()=>crypto.randomUUID().slice(0,8).toUpperCase();
function createAlert(stageAlert, station, rule, severity, value, {resolved = false, demo = DEMO} = {}) {
  const message = resolved ? `${rule.title} กลับสู่เกณฑ์ที่กำหนด (${value}${rule.unit})` :
    `${rule.title}: ${value}${rule.unit} / เกณฑ์เตือน ${rule.warning}${rule.unit}, วิกฤต ${rule.critical}${rule.unit}`;
  const timestamp = now();
  stageAlert({
    id: `AL-${crypto.randomUUID()}`,
    stationId: station.id,
    stationName: station.name,
    region: station.region,
    title: resolved ? `${rule.title} — กลับสู่ปกติ` : rule.title,
    severity: resolved ? 'resolved' : severity,
    message, value, ruleId: rule.id, createdAt: timestamp,
    resolvedAt: resolved ? timestamp : null, acknowledgedAt: null,
    acknowledged: false, resolved, demo,
  }, Boolean(BOT && CHAT && (!demo || SEND_DEMO)));
}

function processRules(draft, stageAlert, station, demo) {
  let changed = false;
  for (const rule of RULES) {
    const value = station[rule.field];
    const current = severityOf(rule, value);
    const key = station.id + ':' + rule.id;
    const prev = draft.active[key];
    if (current === (prev?.severity ?? null) && (!current || Date.now() - (prev.lastNotice || 0) <= REMINDER_MS)) {
      continue;
    }
    const timestamp = now();
    if (prev) {
      for (const alert of draft.alerts) {
        if (alert.stationId !== station.id || alert.ruleId !== rule.id || alert.resolvedAt) continue;
        if (current && !alert.supersededAt) alert.supersededAt = timestamp;
        if (!current && alert.severity !== 'resolved') alert.resolvedAt = timestamp;
      }
    }
    createAlert(stageAlert, station, rule, current, value, {resolved: !current, demo});
    if (current) draft.active[key] = {severity: current, lastNotice: Date.now()};
    else delete draft.active[key];
    changed = true;
  }
  return changed;
}

function applyTelemetry(updates, demo) {
  commitAlerts((draft, stageAlert) => {
    let changed = false;
    for (const [, station] of updates) {
      if (processRules(draft, stageAlert, station, demo)) changed = true;
    }
    return changed;
  });
  for (const [target, station] of updates) Object.assign(target, station);
}

function applyBackgroundTelemetry(station, next, demo) {
  try {
    applyTelemetry([[station, next]], demo);
    return true;
  } catch (error) {
    console.error('Alert update rejected:', error.message);
    return false;
  }
}

function seedAlerts() {
  if (!DEMO || store.alerts.length) return;
  try {
    commitAlerts((draft, stageAlert) => {
      for (const station of stations) processRules(draft, stageAlert, station, true);
    });
  } catch (error) {
    console.error('Could not seed demo alerts:', error.message);
  }
}
seedAlerts();
let lastTelegramSend=0,sending=false;
async function processQueue() {
  if(sending||persistenceUncertain||!BOT||!CHAT)return;
  const job = store.queue.find(item => ['pending', 'retry_pending'].includes(item.status) && item.nextAt <= Date.now());
  if (!job) return;
  const gap=Date.now()-lastTelegramSend;if(gap<SEND_GAP)return;
  const alert=store.alerts.find(x=>x.id===job.alertId);
  // Referential Integrity & Self-Contained Payload:
  // Primary delivery source: immutable job payload ensures message fidelity even if alert is mutated or pruned
  if(!alert && !job.payload){job.status='failed';job.lastError='Missing alert and payload';trimQueue();saveSoon();return;}
  const messageText = job.payload?.text || (alert ? alertMessage(alert) : 'AQUA COMMAND Alert');
  const isDemo = job.payload ? Boolean(job.payload.demo) : (alert ? Boolean(alert.demo) : Boolean(DEMO));
  if (!TELEGRAM_DELIVERY_AUTHORIZED) {
    if (isDemo) {
      job.status='simulated';job.simulatedAt=now();job.simulated=true;job.lastError=null;
    } else {
      job.status='blocked_by_policy';job.blockedAt=now();
      job.lastError=`Delivery suppressed: external network delivery not authorized in APP_ENV='${APP_ENV}' (REL-02)`;
    }
    trimQueue();saveSoon();broadcast();return;
  }
  sending = true;
  const attempt = job.attempt + 1;
  try {
    setDeliveryState(job.id, {status: 'sending', attempt, lastError: null});
    lastTelegramSend = Date.now();
    broadcast();
  } catch (error) {
    // No request was issued. A restart will conservatively hold a visible sending record.
    sending = false;
    console.error('Could not persist Telegram send intent:', error.message);
    return;
  }
  let outcome = {status: 'delivery_unknown', lastError: 'Telegram acceptance could not be confirmed'};
  try {
    const response = await fetch(`https://api.telegram.org/bot${BOT}/sendMessage`, {
      method: 'POST', redirect: 'error', headers: {'content-type': 'application/json'},
      body: JSON.stringify({chat_id: CHAT, text: messageText, disable_web_page_preview: true}),
      signal: AbortSignal.timeout(8000),
    });
    const answer = await response.json();
    if (response.ok && answer?.ok === true && Number.isSafeInteger(answer.result?.message_id)) {
      outcome = {status: 'sent', sentAt: now(), messageId: answer.result.message_id, lastError: null};
    } else if (response.status >= 400 && response.status < 500 && response.status !== 408 &&
               answer?.ok === false && answer.error_code === response.status) {
      outcome = {status: 'failed', lastError: `Telegram rejected the request (HTTP ${response.status})`};
      if (response.status === 429 && attempt < 6) {
        const retryAfter = answer.parameters?.retry_after;
        const seconds = Number.isSafeInteger(retryAfter) && retryAfter > 0 && retryAfter <= 86400 ? retryAfter : 0;
        const delay = Math.max(3 * 2 ** (attempt - 1), seconds);
        outcome = {...outcome, status: 'retry_pending', nextAt: Date.now() + delay * 1000};
      }
    }
  } catch {
    // A transport error can occur after the destination accepted the request.
  }
  try {
    setDeliveryState(job.id, outcome);
  } catch (error) {
    // Never repeat a request just because its outcome could not be persisted.
    const current = store.queue.find(item => item.id === job.id);
    if (current?.status === 'sending') {
      Object.assign(current, {status: 'delivery_unknown', lastError: 'Delivery outcome could not be persisted'});
      saveSoon();
    }
    console.error('Could not persist Telegram delivery outcome:', error.message);
  } finally {
    sending = false;
    broadcast();
  }
}

function setDeliveryState(id, changes) {
  commitAlerts(draft => {
    const index = draft.queue.findIndex(job => job.id === id);
    if (index < 0) throw new Error('Outbox job not found');
    draft.queue[index] = {...draft.queue[index], ...changes, deliveryProtocolVersion: 2};
    trimQueue(draft);
  });
}

setInterval(processQueue,950).unref();
// A silent station cannot send online=false itself. Detect stale telemetry centrally.
if (!DEMO) setInterval(() => {
  for (const station of stations) {
    if (station.hasTelemetry && station.online && Date.now() - new Date(station.lastSeen).getTime() > STALE_AFTER_MS) {
      if (applyBackgroundTelemetry(station, {...station, online: false}, false)) broadcast();
    }
  }
}, 10_000).unref();
if(DEMO) setInterval(()=>{
  const i=Math.floor(Math.random()*stations.length),s=stations[i];
  const next = {...s};
  next.pressureBar=num(Math.max(0,Math.min(6,s.pressureBar+(Math.random()-.5)*.065)),2);
  next.tankLevelPct=num(Math.max(0,Math.min(100,s.tankLevelPct+(Math.random()-.5)*.45)),1);
  next.flowM3h=Math.round(Math.max(0,s.flowM3h+(Math.random()-.5)*35));
  if (!applyBackgroundTelemetry(s, next, true)) return;
  history.push({time:now(),pressure:num(stations.reduce((a,b)=>a+b.pressureBar,0)/stations.length,2),flow:num(stations.reduce((a,b)=>a+b.flowM3h,0)/1000,2),tank:num(stations.reduce((a,b)=>a+b.tankLevelPct,0)/stations.length,1)});history.shift();broadcast();
},7500).unref();
const contentTypes={'.html':'text/html; charset=utf-8','.js':'text/javascript; charset=utf-8','.css':'text/css; charset=utf-8','.svg':'image/svg+xml','.json':'application/json; charset=utf-8','.ico':'image/x-icon'};
function reply(res,code,payload){res.writeHead(code,{'Content-Type':'application/json; charset=utf-8','Cache-Control':'no-store','X-Content-Type-Options':'nosniff'});res.end(JSON.stringify(payload));}
function checkKey(req){if(!SECRET||SECRET.length<24)return false;const supplied=req.headers['x-api-key'];return typeof supplied==='string' && supplied.length===SECRET.length && crypto.timingSafeEqual(Buffer.from(supplied),Buffer.from(SECRET));}
function isLoopback(req){const remote=req.socket.remoteAddress||'';return remote==='127.0.0.1'||remote==='::1'||remote==='::ffff:127.0.0.1';}
async function body(req){let length=0,chunks=[];for await(const c of req){length+=c.length;if(length>16_384)throw Object.assign(new Error('Body too large'),{status:413});chunks.push(c);}let parsed=JSON.parse(Buffer.concat(chunks).toString('utf8'));if(!parsed||typeof parsed!=='object'||Array.isArray(parsed))throw Error('Expected JSON object');return parsed;}
async function handler(req,res){
  const url=new URL(req.url,`http://${req.headers.host||'localhost'}`);const p=url.pathname;
  if(req.method==='GET'&&p==='/api/health')return reply(res,200,{ok:true,mode:DEMO?'demo':'live-ingest',telegramConfigured:Boolean(BOT&&CHAT),uptimeSeconds:Math.round(process.uptime())});
  if(req.method==='GET'&&p==='/api/state')return reply(res,200,snapshot());
  if(req.method==='GET'&&p==='/api/stream'){
    res.writeHead(200,{'Content-Type':'text/event-stream; charset=utf-8','Cache-Control':'no-cache, no-transform','Connection':'keep-alive','X-Accel-Buffering':'no','X-Content-Type-Options':'nosniff'});
    clients.add(res);res.write(`retry: 3000\ndata: ${JSON.stringify(snapshot())}\n\n`);const interval=setInterval(()=>res.write(': ping\n\n'),20000);req.on('close',()=>{clearInterval(interval);clients.delete(res);});return;
  }
  if(req.method==='GET'&&p==='/api/export/alerts'){
    if(!checkKey(req))return reply(res,401,{error:'Admin API key required'});
    const cols=['id','createdAt','stationId','stationName','region','title','severity','message','resolvedAt','acknowledgedAt','demo'];
    const csv=[cols.join(','),...store.alerts.map(a=>cols.map(k=>'"'+String(a[k]??'').replaceAll('"','""')+'"').join(','))].join('\r\n');
    res.writeHead(200,{'Content-Type':'text/csv; charset=utf-8','Content-Disposition':'attachment; filename="aqua-alerts.csv"','Cache-Control':'no-store'});return res.end('\ufeff'+csv);
  }
  if(req.method==='POST'&&p==='/api/telemetry'){
    if(!checkKey(req))return reply(res,401,{error:'Invalid admin API key'});
    let b=await body(req);const s=stations.find(x=>x.id===b.stationId);if(!s)return reply(res,404,{error:'Unknown station ID'});
    const fields={pressureBar:[0,12],tankLevelPct:[0,100],flowM3h:[0,100_000],turbidityNtu:[0,1000],chlorineMgL:[0,20]};
    if(!Object.keys(fields).some(k=>Object.hasOwn(b,k))&&!Object.hasOwn(b,'online'))return reply(res,422,{error:'At least one telemetry field is required'});
    for(const [k,[lo,hi]]of Object.entries(fields))if(Object.hasOwn(b,k)){
      if(typeof b[k]!=='number'||!Number.isFinite(b[k])||b[k]<lo||b[k]>hi)return reply(res,422,{error:`Invalid ${k}`});
    }
    if(Object.hasOwn(b,'online')&&typeof b.online!=='boolean')return reply(res,422,{error:'Invalid online'});
    const next = {...s, online: true, hasTelemetry: true, lastSeen: now()};
    for (const key of [...Object.keys(fields), 'online']) {
      if (Object.hasOwn(b, key)) next[key] = b[key];
    }
    applyTelemetry([[s, next]], false);
    const avg=field=>{const a=stations.map(s=>s[field]).filter(v=>typeof v==='number');return a.length?a.reduce((x,y)=>x+y,0)/a.length:0;};
    history.push({time:now(),pressure:num(avg('pressureBar'),2),flow:num(stations.reduce((a,s)=>a+(s.flowM3h||0),0)/1000,2),tank:num(avg('tankLevelPct'),1)});if(history.length>96)history.shift();
    broadcast();return reply(res,200,{ok:true,stationId:s.id,status:statusOf(s)});
  }
  if(req.method==='POST'&&p==='/api/incidents'){
    if(!checkKey(req))return reply(res,401,{error:'Invalid admin API key'});
    let b=await body(req);
    const isResolved = b.resolved === true || b.severity === 'resolved' || Boolean(b.resolvedAt);
    const isAck = b.acknowledged === true || Boolean(b.acknowledgedAt);
    const alert={
      id: b.id || `PWA-${uid()}`,
      stationId: b.stationId || 'PWA',
      stationName: b.stationName || 'กปภ.',
      region: b.region || 'ส่วนภูมิภาค',
      title: b.title || 'ประกาศหยุดจ่ายน้ำ',
      severity: b.severity || (isResolved ? 'resolved' : 'warning'),
      message: b.message || '',
      value: b.value !== undefined ? b.value : '-',
      ruleId: b.ruleId || 'pwa-outage',
      createdAt: b.createdAt || now(),
      resolvedAt: b.resolvedAt || (isResolved ? now() : null),
      acknowledgedAt: b.acknowledgedAt || (isAck ? now() : null),
      acknowledged: isAck,
      resolved: isResolved,
      demo: Boolean(b.demo)
    };
    commitAlerts((_, stageAlert) => stageAlert(alert));
    broadcast();
    return reply(res, 200, {ok: true, alertId: alert.id});
  }
  if(req.method==='POST'&&p==='/api/demo/incident'){
    if(!DEMO)return reply(res,403,{error:'Simulation disabled'});
    if(!isLoopback(req)&&!checkKey(req))return reply(res,401,{error:'Admin key required for remote demo actions'});
    const b=await body(req);const s=stations.find(x=>x.id===b.stationId)||stations.find(x=>x.id==='CM-01');
    const types={'pressure-low':{field:'pressureBar',value:0.64},'tank-low':{field:'tankLevelPct',value:12},'turbidity-high':{field:'turbidityNtu',value:5.8},'station-offline':{field:'online',value:false}};
    const preset=types[b.type]||types['pressure-low'];
    applyTelemetry([[s, {...s, [preset.field]: preset.value}]], true);
    broadcast();return reply(res,200,{ok:true,stationId:s.id,status:statusOf(s)});
  }
  if(req.method==='POST'&&p==='/api/demo/reset'){
    if(!DEMO)return reply(res,403,{error:'Simulation disabled'});
    if(!isLoopback(req)&&!checkKey(req))return reply(res,401,{error:'Admin key required'});
    const updates = stations.map(station => [station, {...station, pressureBar: 2.65,
      tankLevelPct: 75, turbidityNtu: .45, chlorineMgL: .52, online: true}]);
    applyTelemetry(updates, true);
    broadcast();return reply(res,200,{ok:true});
  }
  const retryUnknown = p.match(/^\/api\/queue\/([A-Za-z0-9-]+)\/retry-unknown$/);
  if (req.method === 'POST' && retryUnknown) {
    if (!checkKey(req)) return reply(res, 401, {error: 'Admin API key required'});
    if (!TELEGRAM_DELIVERY_AUTHORIZED || !BOT || !CHAT) {
      return reply(res, 403, {error: 'Telegram delivery is not authorized'});
    }
    const request = await body(req);
    if (request.confirmDuplicateRisk !== true) return reply(res, 422, {error: 'Confirm duplicate delivery risk'});
    const job = store.queue.find(item => item.id === retryUnknown[1]);
    if (!job) return reply(res, 404, {error: 'Outbox job not found'});
    if (job.status !== 'delivery_unknown') return reply(res, 409, {error: 'Delivery status has already changed'});
    setDeliveryState(job.id, {status: 'retry_pending', nextAt: Date.now(),
      duplicateRiskAcceptedAt: now()});
    broadcast();
    return reply(res, 202, {ok: true, id: job.id});
  }
  if(req.method==='POST'&&p==='/api/queue/retry-failed'){
    if(!checkKey(req))return reply(res,401,{error:'Admin API key required'});
    if(!BOT||!CHAT)return reply(res,422,{error:'Telegram not configured'});
    let count=0;for(const j of store.queue)if(j.status==='failed'||j.status==='blocked_by_policy'){j.status='pending';j.attempt=0;j.nextAt=Date.now();j.lastError=null;count++;}
    saveSoon();broadcast();return reply(res,200,{ok:true,retried:count});
  }
  if(req.method==='POST'&&p==='/api/queue/resume-blocked'){
    if(!checkKey(req))return reply(res,401,{error:'Admin API key required'});
    let count=0;for(const j of store.queue)if(j.status==='blocked_by_policy'){j.status='pending';j.attempt=0;j.nextAt=Date.now();j.lastError=null;count++;}
    saveSoon();broadcast();return reply(res,200,{ok:true,resumed:count});
  }
  if(req.method==='POST'&&p==='/api/test-telegram'){
    if(!checkKey(req))return reply(res,401,{error:'Admin API key required'});
    if(!BOT||!CHAT)return reply(res,422,{error:'Set TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID in .env'});
    const a={id:`TEST-${uid()}`,title:'ทดสอบการเชื่อมต่อ Telegram',severity:'info',stationName:'ศูนย์ควบคุม',region:'ทุกพื้นที่',message:'ข้อความทดสอบจาก AQUA COMMAND สำเร็จเมื่อ Telegram ยอมรับการส่ง',createdAt:now(),demo:true};
    commitAlerts((_, stageAlert) => stageAlert(a, true));
    broadcast();return reply(res,202,{ok:true,queued:true,id:a.id});
  }
  const ack=p.match(/^\/api\/alerts\/([A-Za-z0-9-]+)\/ack$/);
  if(req.method==='POST'&&ack){
    if(!checkKey(req))return reply(res,401,{error:'Admin API key required'});
    const a=store.alerts.find(x=>x.id===ack[1]);
    if(!a)return reply(res,404,{error:'Alert not found'});
    a.acknowledgedAt=now();
    a.acknowledged=true;
    saveSoon();
    broadcast();
    return reply(res,200,{ok:true,id:a.id,acknowledgedAt:a.acknowledgedAt});
  }
  if(p.startsWith('/api/'))return reply(res,404,{error:'API not found'});
  if(req.method!=='GET'&&req.method!=='HEAD')return reply(res,405,{error:'Method not allowed'});
  const safePath=path.resolve(PUBLIC,'.'+decodeURIComponent(p==='/'?'/index.html':p));
  if(!safePath.startsWith(PUBLIC+path.sep))return reply(res,403,{error:'Forbidden'});
  try{const stat=fs.statSync(safePath);if(!stat.isFile())throw Error('Not a file');res.writeHead(200,{'Content-Type':contentTypes[path.extname(safePath)]||'application/octet-stream','X-Content-Type-Options':'nosniff','Cache-Control':'public, max-age=300','Content-Security-Policy':"default-src 'self'; img-src 'self' data:; style-src 'self' 'unsafe-inline'; script-src 'self'; connect-src 'self'; base-uri 'none'; frame-ancestors 'none'",'Referrer-Policy':'no-referrer'});fs.createReadStream(safePath).pipe(res);}catch{return reply(res,404,{error:'Not found'});}
}
const server = http.createServer((req, res) => handler(req, res).catch(error => {
  const {code, retryAfterSeconds} = error;
  if (retryAfterSeconds) res.setHeader('Retry-After', String(retryAfterSeconds));
  return reply(res, error.status || 400, {
    error: error.message || 'Bad request',
    ...(code?.startsWith('ALERT_') ? {code} : {}),
    ...(retryAfterSeconds ? {retryAfterSeconds} : {}),
  });
}));
server.listen(PORT,HOST,()=>console.log(`AQUA COMMAND [${DEMO?'DEMO':'LIVE INGEST'}] http://${HOST}:${PORT} Telegram: ${BOT&&CHAT?'configured':'not configured'}`));
for(const signal of ['SIGTERM','SIGINT'])process.on(signal,()=>{saveNow();server.close();setTimeout(()=>process.exit(0),1000).unref();});
