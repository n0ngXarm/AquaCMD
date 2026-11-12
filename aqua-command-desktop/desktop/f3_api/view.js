const ST = {
  OK:{t:'ปกติ',i:'✓',c:'--ok',w:0}, FAIL:{t:'ไม่ตอบ',i:'✕',c:'--fail',w:5},
  BLOCKED:{t:'ตรวจไม่ได้ เพราะทางผ่านล่ม',i:'⊘',c:'--blocked',w:4}, STALE:{t:'ข้อมูลเก่า',i:'◔',c:'--stale',w:3},
  UNVERIFIED:{t:'ยังไม่ตรวจ',i:'?',c:'--unv',w:2}, NOT_BUILT:{t:'ยังไม่สร้าง',i:'–',c:'--nb',w:1}
};
const ICON={
 scada:`<rect x='3' y='5' width='18' height='14' rx='2'/><circle cx='7.5' cy='10' r='1'/><circle cx='7.5' cy='14' r='1'/><path d='M11 10h6M11 14h6'/>`,
 sw:`<rect x='2' y='10' width='20' height='8' rx='1.5'/><path d='M6 14h.01M10 14h.01M14 14h.01M18 14h.01M6 10V6M12 10V6M18 10V6'/>`,
 poll:`<circle cx='12' cy='12' r='8.5'/><path d='M12 7v5l3.5 2'/>`,
 opc:`<path d='M10 14a4 4 0 0 0 5.7 0l3-3a4 4 0 0 0-5.7-5.7l-1 1'/><path d='M14 10a4 4 0 0 0-5.7 0l-3 3a4 4 0 0 0 5.7 5.7l1-1'/>`,
 store:`<ellipse cx='12' cy='6' rx='7.5' ry='3'/><path d='M4.5 6v6c0 1.7 3.4 3 7.5 3s7.5-1.3 7.5-3V6M4.5 12v6c0 1.7 3.4 3 7.5 3s7.5-1.3 7.5-3v-6'/>`,
 task:`<rect x='4' y='3.5' width='16' height='17' rx='2'/><path d='M8 9l1.5 1.5L12 8M8 15l1.5 1.5L12 14M14.5 9.5h3M14.5 15.5h3'/>`,
 outbox:`<path d='M3 13l2.5-7h13L21 13v6H3z'/><path d='M3 13h5l1.5 2.5h5L16 13h5'/>`,
 router:`<rect x='3' y='14' width='18' height='6' rx='1.5'/><path d='M7 17h.01M11 17h.01M8.5 11a5 5 0 0 1 7 0M6 8.5a8.5 8.5 0 0 1 12 0'/>`,
 relay:`<path d='M12 3l7.5 3v5.5c0 4.5-3.2 8-7.5 9.5-4.3-1.5-7.5-5-7.5-9.5V6z'/><path d='M8.5 12h7M13 9.5l2.5 2.5-2.5 2.5'/>`,
 tg:`<path d='M21 3L3 10.5l6 2.2L11.5 20l3-4.5 4.5 3.5z'/><path d='M9 12.7L21 3'/>`
};

const $ = id => document.getElementById(id);
const escapeHTML = value => String(value ?? '').replace(/[&<>"']/g, char =>
  ({'&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;'})[char]);
const motion = matchMedia('(prefers-reduced-motion: reduce)');
const origin = location.origin;
const ns = 'http://www.w3.org/2000/svg';
const subtitles = {
  poll: 'กำหนดจังหวะอ่านค่า', opc: 'อ่านค่าและตรวจคุณภาพ',
  store: 'เก็บผลตรวจพร้อมเวลา', task: 'ประเมินเงื่อนไขแจ้งเตือน',
  outbox: 'จัดคิวข้อความก่อนส่ง', relay: 'Authorized Relay', tg: 'ปลายทางแจ้งเตือน',
  scada: 'ต้นทาง OPC UA', switch: 'ทางผ่าน OT', router: 'ทางออก WAN',
};
const operations = {
  poll: 'เมื่อเริ่มตัวเก็บข้อมูล ระบบจะอ่านตามรอบที่กำหนด สถานะการทำงานของรอบอ่านยังไม่มี heartbeat ให้ยืนยัน',
  opc: 'อ่านค่าจากจุดที่ตั้งไว้ใน SCADA ผ่าน OPC UA แบบอ่านอย่างเดียว พร้อมตรวจคุณภาพของค่าที่ได้รับ',
  store: 'บันทึกเวลา แหล่งที่มา และผลตรวจลง SQLite ในเครื่อง หน้านี้อ่านหลักฐานที่บันทึกแล้วมาแสดง',
  task: 'ขั้นที่วางไว้สำหรับประเมินเงื่อนไขจากข้อมูลที่อ่านได้ เมื่อเข้าเงื่อนไขจึงสร้างรายการแจ้งเตือน',
  outbox: 'ขั้นที่วางไว้สำหรับเก็บรายการแจ้งเตือนรอส่ง ก่อนส่งต่อไปยังปลายทางที่ได้รับอนุญาต',
};
const iconName = node => node.kind === 'scada' ? 'scada' :
  node.kind === 'switch' ? 'sw' : node.kind === 'router' ? 'router' : node.id;
let snapshot = null;
let results = new Map();
let active = /^http:\/\/127\.0\.0\.1:\d+$/.test(origin);
let transport = false;
let busy = false;
let stream = null;
let timer;
let selected;
let lastSeen = 0;
const pending = new Map();
const paths = new Map();
const statusColor = key => `var(${ST[key].c})`;
const ageLabel = age => age < 90 ? `${Math.floor(age)} วินาที` : `${Math.floor(age / 60)} นาที`;
const dialog = $('pop');
let demo = document.body.dataset.demo === '1';
let demoStarting = false;
let fetchError = false;
let streamError = false;
let demoError = document.body.dataset.demoError;
let toastTimer;

function announceSignal(state, message = '') {
  if (document.body.dataset.signal === state && $('f3-toast').textContent === message) return;
  document.body.dataset.signal = state;
  const notice = $('f3-toast');
  notice.textContent = message;
  notice.classList.toggle('shown', Boolean(message));
  clearTimeout(toastTimer);
  if (message && state !== 'pending') {
    toastTimer = setTimeout(() => notice.classList.remove('shown'), 5500);
  }
}

function updateSignal(nodes) {
  if (demoError) {
    announceSignal('error', demoError);
    return;
  }
  if (demoStarting) {
    announceSignal('pending', 'กำลังเริ่ม OPC UA จำลอง…');
    return;
  }
  if (fetchError || streamError) {
    announceSignal('error', fetchError ? 'อ่านหลักฐานการสื่อสารไม่สำเร็จ · ' + fetchError : 'การรับเหตุการณ์ขาดการเชื่อมต่อ · ยังไม่ได้รับรหัสสาเหตุ');
    return;
  }
  const failed = nodes.find(node => {
    const result = results.get(node.id);
    return result.k === 'BLOCKED' || (result.k === 'FAIL' && !result.historical && !result.clock);
  });
  if (failed) {
    const result = results.get(failed.id);
    announceSignal('error', result.k === 'BLOCKED' ?
      `ตรวจ ${failed.label} ไม่ได้ เพราะทางผ่านไม่ตอบ` :
      `${failed.label} · ${failed.last?.detail || 'ตรวจไม่สำเร็จ'}`);
    return;
  }
  const read = nodes.find(node => node.kind === 'scada' &&
    node.last?.method === 'ua_read' && results.get(node.id).k === 'OK');
  if (demo && snapshot?.demo_delivery) {
    const delivery = nodes.find(node => node.id === 'tg');
    if (delivery && results.get('tg').k === 'OK') {
      announceSignal('success', 'SIMULATED · ' + delivery.last.detail);
    } else if (delivery?.last?.ok) {
      announceSignal('pending', 'SIMULATED · รอบนี้ส่งแล้ว · ' + delivery.last.detail);
    } else if (delivery?.last) {
      announceSignal('error', delivery.last.detail);
    } else {
      announceSignal('pending', read ? 'SIMULATED · อ่านค่าแล้ว กำลังรอผลส่ง Telegram' :
        'SIMULATED · รอผลอ่านค่า OPC UA');
    }
    return;
  }
  if (read) {
    announceSignal('success', demo ? 'SIMULATED · อ่านค่า OPC UA และบันทึก SQLite สำเร็จ' :
      'อ่านค่า OPC UA สำเร็จ · พบหลักฐานล่าสุด');
    return;
  }
  announceSignal('pending', demo ? 'SIMULATED · รอผลอ่านค่า OPC UA' : '');
}

if (demo) {
  $('f3-demo').textContent = 'หยุดจำลอง';
  $('host-routes').hidden = true;
}

function renderHostRoutes(network) {
  for (const role of ['OT', 'WAN']) {
    const field = $('route-' + role.toLowerCase());
    const path = network?.paths?.[role];
    const status = path?.status ?? network?.state;
    const target = path?.target ? ' · ปลายทาง ' + path.target : '';
    let text = ({
      STALE: 'ข้อมูลเก่า', NO_ROUTE: 'ไม่มีเส้นทาง', LOCAL: 'ปลายทางเป็น IP เครื่องนี้',
      OBSERVED_LOCAL: 'ไม่พบปลายทางเดียวในผัง',
    })[status] ?? 'ยังไม่ทราบเส้นทาง';
    if (status === 'ROUTE') {
      text = `${path.source_ip} → ${path.target}`;
      if (path.via) text += ` · ผ่าน GW ${path.via}`;
    } else {
      text += target;
    }
    field.textContent = text;
    field.title = path?.device ? `เส้นทางจาก Fedora ผ่าน ${path.device} · ใช้ดู IP ต้นทางและปลายทาง` : '';
  }
}


function failureReason(detail) {
  const raw = String(detail ?? '');
  const labels = {TIMEOUT: 'หมดเวลารอ', NO_ROUTE: 'ไม่มีเส้นทาง', REFUSED: 'ถูกปฏิเสธ',
    CERT_ERROR: 'ใบรับรองผิดพลาด', DNS_ERROR: 'ค้นหาชื่อไม่ได้', NETWORK_ERROR: 'เครือข่ายขัดข้อง'};
  const code = Object.keys(labels).find(key => raw.includes(key));
  return code ? `${labels[code]} · ${code}` : raw;
}

function render() {
  if (!demo) renderHostRoutes(transport ? snapshot?.local_network : null);
  const nodes = snapshot?.nodes ?? [];
  const now = Date.now();
  const byId = new Map(nodes.map(node => [node.id, node]));
  results = new Map(nodes.map(node => {
    const via = byId.get(node.via);
    const pathResult = via && detect(via, null, now, snapshot.stale_ms);
    // An expired timeout stays in history and cannot assert a current path outage.
    const viaStatus = transport && pathResult && !pathResult.historical && !pathResult.clock ? pathResult.k : null;
    const effective = transport ? node : {...node, last: null};
    return [node.id, detect(effective, viaStatus, now, snapshot.stale_ms)];
  }));
  const zone = node => ({
    scada: 'zA1', switch: 'zA2', router: 'zC', external: 'zC', internal: 'zB',
  })[node.kind];
  const focused = document.activeElement?.dataset.n;
  for (const name of ['zA1', 'zA2', 'zB', 'zC']) {
    $(name).innerHTML = nodes.filter(node => zone(node) === name).map(node => {
      const result = results.get(node.id);
      const state = ST[result.k];
      const label = result.historical || (result.k === 'FAIL' && result.clock) ? 'ผลตรวจเดิม: ไม่ตอบ' : state.t;
      const age = result.clock ? ' · เวลาหลักฐานอยู่ในอนาคต' :
        result.age == null ? '' : ` · ข้อมูลล่าสุดเมื่อ ${ageLabel(result.age)}ก่อน`;
      const id = escapeHTML(node.id);
      const reason = result.k === 'FAIL' && node.last ? failureReason(node.last.detail) : '';
      const groups = transport ? taskGroupLabel(node.last) : '';
      return `<button type="button" class="node ${result.k === 'NOT_BUILT' ? 'nb' : ''}"
        id="n-${id}" data-n="${id}" data-state="${result.k}" aria-haspopup="dialog"
        aria-pressed="${dialog.open && selected === node.id}" aria-label="${escapeHTML(node.label || node.id)}: ${escapeHTML(label)}" title="${escapeHTML(node.last?.detail ?? 'ยังไม่มีหลักฐาน')}" style="--c:${statusColor(result.k)}">
        <svg class="ic" viewBox="0 0 24 24" aria-hidden="true">${ICON[iconName(node)]}</svg>
        <strong>${escapeHTML(node.label)}</strong><small>${escapeHTML(subtitles[iconName(node)] ?? subtitles[node.kind])}</small>
        <span class="st"><span class="status-icon" aria-hidden="true">${state.i}</span> ${label}<span class="age">${age}</span></span>
        ${reason ? `<span class="failure-reason" title="${escapeHTML(node.last.detail)}">${escapeHTML(reason)}</span>` : ''}
        ${groups ? `<span class="task-groups" title="${escapeHTML(groups)}">${escapeHTML(groups)}</span>` : ''}</button>`;
    }).join('');
  }
  if (focused && !dialog.open) $('n-' + focused)?.focus({preventScroll: true});
  const current = [...results.values()];
  const degraded = current.some(result => result.k === 'BLOCKED' || (result.k === 'FAIL' && !result.historical && !result.clock));
  const allKnown = current.some(result => result.k === 'OK') && current.every(result => ['OK', 'NOT_BUILT'].includes(result.k));
  const heading = !transport ? 'ไม่ได้รับข้อมูลจาก backend · ยังไม่ยืนยันสถานะ' :
    degraded ? 'มีจุดตรวจไม่สำเร็จหรือมีทางผ่านที่ไม่ตอบ' :
    allKnown ? 'ทุกจุดที่สร้างแล้วตอบปกติ ด้วยหลักฐานภายใน 60 วินาที' :
    'ยังยืนยันไม่ได้ว่าระบบทำงานครบทุกจุด';
  $('f3-next-action').hidden = !transport || nodes.some(node => node.kind === 'scada' && node.last);
  $('banner').textContent = (snapshot?.simulated ? 'SIMULATED · ' : '') + heading;
  $('banner').style.borderLeftColor = statusColor(degraded ? 'FAIL' : allKnown ? 'OK' : 'UNVERIFIED');
  updateSignal(nodes);
  if (dialog.open) renderDetail();
  drawLines(nodes);
}

function taskGroupNames(item) {
  return (item?.task_groups ?? []).map(group => group.name).join(' · ');
}

function taskGroupLabel(last) {
  const names = taskGroupNames(last);
  if (!names) return '';
  return (last.method === 'ua_read' ? 'Task ที่ผูกกับ Tag · ' : 'กลุ่ม Task · ') + names;
}

function renderDetail() {
  const node = snapshot?.nodes.find(item => item.id === selected);
  if (!node) return;
  const last = node.last;
  const result = results.get(node.id);
  const fields = {
    'หน้าที่': operations[node.id] ?? subtitles[iconName(node)] ?? subtitles[node.kind],
    'แหล่งหลักฐาน': last ? `probe_evidence #${last.id} · ${last.source === 'sim' ? 'SIMULATED' : 'SQLite'}` : '—',
    'เวลาที่บันทึก': last?.ts ?? '—',
    'วิธีตรวจ': last?.method ?? '—',
    'ผลครั้งล่าสุด': last?.detail ?? '—',
    ...(last && !last.ok ? {'สาเหตุ': failureReason(last.detail)} : {}),
    ...(taskGroupNames(last) ? {
      [last.method === 'ua_read' ? 'Task ที่ผูกกับ Tag' : 'กลุ่ม Task ของหลักฐานนี้']: taskGroupNames(last),
    } : {}),
    'สถานะปัจจุบัน': result.historical || result.clock ? 'ยังไม่ยืนยัน · แสดงผลครั้งก่อน' : ST[result.k].t,
  };
  $('detail').innerHTML = `<h3 id="ptitle">${escapeHTML(node.label)}</h3><dl>` +
    Object.entries(fields).map(([label, value]) => `<dt>${label}</dt><dd>${escapeHTML(value)}</dd>`).join('') + '</dl>';
}

function drawLines(nodes) {
  const diagram = $('dia').getBoundingClientRect();
  const bounds = id => $('n-' + id)?.getBoundingClientRect();
  const links = nodes.filter(node => node.via).map(node => [node.id, node.via]);
  for (const node of nodes) {
    if (node.kind === 'switch') links.push([node.id, 'opc']);
    if (node.kind === 'router') links.push(['outbox', node.id], [node.id, 'relay']);
  }
  links.push(['poll', 'opc'], ['opc', 'store'], ['store', 'task'], ['task', 'outbox'], ['relay', 'tg']);
  $('lines').setAttribute('viewBox', `0 0 ${diagram.width} ${diagram.height}`);
  paths.clear();
  $('tr').replaceChildren();
  for (const [from, to] of links) {
    const a = bounds(from), b = bounds(to);
    if (!a || !b) continue;
    const ax = a.right - diagram.left, ay = a.top + a.height / 2 - diagram.top;
    const bx = b.left - diagram.left, by = b.top + b.height / 2 - diagram.top;
    const mid = (ax + bx) / 2;
    const d = Math.abs(a.left - b.left) < 10 ?
      `M${ax - a.width / 2} ${a.bottom - diagram.top} V${b.top - diagram.top}` :
      `M${ax} ${ay} H${mid} V${by} H${bx}`;
    const stateForEdge = id => {
      const result = results.get(id);
      return result.historical || result.clock ? 'STALE' : result.k;
    };
    const states = [stateForEdge(from), stateForEdge(to)];
    const worst = states.sort((first, second) => ST[second].w - ST[first].w)[0];
    const path = document.createElementNS(ns, 'path');
    path.setAttribute('d', d);
    path.setAttribute('fill', 'none');
    path.setAttribute('stroke-width', '2');
    if (worst !== 'OK') path.setAttribute('stroke-dasharray', '5 6');
    path.style.stroke = statusColor(worst);
    $('tr').append(path);
    paths.set(from + '>' + to, path);
  }
}

function onEvent(node, row) {
  if (!active || !transport || motion.matches || document.hidden || innerWidth <= 700) return;
  const card = $('n-' + node.id);
  const diagram = $('dia').getBoundingClientRect(), box = card.getBoundingClientRect();
  const color = statusColor(row.result === 'ok' ? 'OK' : 'FAIL');
  const ring = document.createElement('div');
  ring.className = 'rip';
  ring.dataset.evidenceId = row.id;
  ring.style.cssText = `left:${box.left + box.width / 2 - diagram.left}px;top:${box.top + box.height / 2 - diagram.top}px;width:60px;height:60px;--rc:${color}`;
  $('dia').append(ring);
  ring.addEventListener('animationend', () => ring.remove(), {once: true});
  const stagePath = {demo_task: 'store>task', demo_outbox: 'task>outbox', demo_telegram: 'relay>tg'};
  const groups = row.task_groups ?? (node.last?.id === row.id ? node.last.task_groups : null);
  const readPath = node.kind === 'scada' && results.get(node.id)?.k !== 'BLOCKED';
  const stage = demo && row.source === 'sim' && row.result === 'ok' && groups?.length;
  const route = readPath ? node.id + '>' + node.via : stage ? stagePath[row.check] : '';
  const path = paths.get(route);
  if (!path) return;
  const dot = document.createElementNS(ns, 'circle');
  dot.dataset.evidenceId = row.id;
  dot.setAttribute('r', '4');
  dot.style.fill = color;
  $('pt').append(dot);
  let caption, captionWidth, captionOffset = 0;
  if (groups?.length) {
    caption = document.createElementNS(ns, 'text');
    caption.classList.add('packet-task');
    caption.dataset.evidenceId = row.id;
    caption.dataset.route = route;
    const occupied = new Set([...$('pt').querySelectorAll('.packet-task')]
      .filter(label => label.dataset.route === route).map(label => Number(label.dataset.lane)));
    let lane = 0;
    while (occupied.has(lane)) lane++;
    caption.dataset.lane = lane;
    captionOffset = Math.ceil(lane / 2) * (lane % 2 ? -16 : 16);
    const names = groups.slice(0, 2).map(({name}) => name.length > 26 ? name.slice(0, 25) + '…' : name);
    caption.textContent = (readPath ? 'Task ที่ผูก · ' : 'Task · ') + names.join(' · ') +
      (groups.length > names.length ? ` +${groups.length - names.length}` : '');
    $('pt').append(caption);
    captionWidth = caption.getComputedTextLength();
  }
  const length = path.getTotalLength(), start = performance.now();
  function frame(now) {
    const progress = Math.min(1, (now - start) / (caption ? 1600 : 700));
    if (!dot.isConnected || motion.matches || progress === 1) {
      dot.remove();
      caption?.remove();
      return;
    }
    const point = path.getPointAtLength(length * (row.result === 'ok' ? progress : 1 - progress));
    dot.setAttribute('cx', point.x);
    dot.setAttribute('cy', point.y);
    if (caption) {
      caption.setAttribute('x', Math.max(5, Math.min(diagram.width - captionWidth - 5, point.x + 9)));
      caption.setAttribute('y', Math.max(14, Math.min(diagram.height - 5, point.y - 8 + captionOffset)));
    }
    requestAnimationFrame(frame);
  }
  requestAnimationFrame(frame);
}

function openStream() {
  stream = new EventSource(origin + '/api/stream');
  stream.onopen = () => {
    streamError = false;
    updateSignal(snapshot?.nodes ?? []);
  };
  stream.addEventListener('evidence', event => {
    try {
      const row = JSON.parse(event.data);
      if (!Number.isSafeInteger(row.id) || String(row.id) !== event.lastEventId || row.id <= lastSeen) return;
      lastSeen = row.id;
      if (!transport || motion.matches || document.hidden || pending.size >= 32) return;
      pending.set(row.id, row);
      refresh();
    } catch {
      // Keep the snapshot authoritative when a malformed event arrives.
    }
  });
  stream.onerror = () => {
    if (!active) return;
    streamError = true;
    updateSignal(snapshot?.nodes ?? []);
    pending.clear();
    clearMotion();
  };
}

function clearMotion() {
  $('pt').replaceChildren();
  $('dia').querySelectorAll('.rip').forEach(ring => ring.remove());
}

async function refresh() {
  if (!active || busy) return;
  busy = true;
  try {
    const response = await fetch(origin + '/api/f3/evidence', {cache: 'no-store', signal: AbortSignal.timeout(3500)});
    if (!response.ok) throw Error('HTTP ' + response.status);
    const next = await response.json();
    if (!active) return;
    if (!Array.isArray(next.nodes) || !Number.isSafeInteger(next.last_event_id)) throw Error('Invalid evidence payload');
    if (!transport) {
      lastSeen = next.last_event_id;
      pending.clear();
    }
    snapshot = next;
    fetchError = false;
    transport = true;
    render();
    for (const [id, row] of pending) {
      if (id > next.last_event_id) continue;
      pending.delete(id);
      const node = next.nodes.find(item => item.id === row.host && (
        (item.last?.id === id && item.last.source === row.source) ||
        (item.kind === 'scada' && item.last?.ok && item.last.source === row.source &&
         row.check === 'ua_read' && row.result === 'ok' && row.task_groups?.length)
      ));
      const elapsed = Date.now() - Date.parse(row.ts);
      if (node && elapsed >= 0 && elapsed <= next.stale_ms) onEvent(node, row);
    }
    if (!stream) openStream();
  } catch (error) {
    if (!active) return;
    fetchError = error?.message || 'ไม่ได้รับรายละเอียดสาเหตุ';
    transport = false;
    pending.clear();
    clearMotion();
    render();
  } finally {
    busy = false;
  }
}

$('f3-next-action').addEventListener('click', () => {
  window.webkit?.messageHandlers?.f3navigation?.postMessage(JSON.stringify({key: 'F6'}));
});

$('f3-demo').addEventListener('click', () => {
  window.webkit?.messageHandlers?.f3navigation?.postMessage(JSON.stringify({action: 'open-demo'}));
});

$('dia').addEventListener('click', event => {
  const button = event.target.closest('[data-n]');
  if (!button) return;
  selected = button.dataset.n;
  renderDetail();
  dialog.showModal();
});
dialog.addEventListener('click', event => {
  if (event.target === dialog || event.target.closest('[data-close]')) dialog.close();
});
dialog.addEventListener('close', () => $('n-' + selected)?.focus({preventScroll: true}));
document.addEventListener('keydown', event => {
  const settingsShortcut = event.ctrlKey && (event.key === ',' || event.code === 'Comma');
  const key = settingsShortcut ? 'F6' : event.key;
  if (/^F[1-9]$/.test(key) && window.webkit?.messageHandlers?.f3navigation) {
    event.preventDefault();
    window.webkit.messageHandlers.f3navigation.postMessage(JSON.stringify({key}));
  }
});
addEventListener('resize', () => drawLines(snapshot?.nodes ?? []));
motion.addEventListener('change', () => {
  pending.clear();
  clearMotion();
});
$('legend').innerHTML = Object.values(ST).map(state => `<span style="color:var(${state.c})"><i>${state.i}</i> ${state.t}</span>`).join('') +
  '<span>เส้นประ = ผังเส้นทาง · จุดวิ่งอ้างอิงแถวหลักฐานใหม่</span>';
window.F3 = {refresh, startingDemo() {
  demoError = '';
  demoStarting = true;
  document.body.dataset.demo = '1';
  $('f3-demo').textContent = 'หยุดจำลอง';
  this.pause();
  updateSignal([]);
}, pause() {
  active = false;
  clearInterval(timer);
  stream?.close();
  pending.clear();
  clearMotion();
}};
render();
if (active) {
  refresh();
  timer = setInterval(refresh, 2000);
}
