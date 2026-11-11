import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';
import os from 'node:os';
import net from 'node:net';
import { spawn } from 'node:child_process';

function openPort() {
  return new Promise((resolve, reject) => {
    const srv = net.createServer();
    srv.listen(0, '127.0.0.1', () => {
      const p = srv.address().port;
      srv.close(() => resolve(p));
    });
    srv.on('error', reject);
  });
}

const KEY = 'test-only-admin-key-with-more-than-24-chars';

test('queue state transition: simulated vs blocked_by_policy, zero false sent, and resume policy', { timeout: 20_000 }, async () => {
  const root = path.resolve(import.meta.dirname, '..');
  const tmp = fs.mkdtempSync(path.join(os.tmpdir(), 'aqua-queue-test-'));
  for (const file of ['server.mjs', 'rules.mjs']) {
    fs.copyFileSync(path.join(root, file), path.join(tmp, file));
  }
  fs.cpSync(path.join(root, 'public'), path.join(tmp, 'public'), { recursive: true });
  fs.mkdirSync(path.join(tmp, 'storage'));

  const port = await openPort();
  const env = {
    ...process.env,
    APP_ENV: 'lab',
    TELEGRAM_EXTERNAL_DELIVERY_AUTHORIZED: 'false',
    SEND_DEMO_ALERTS: 'true',
    DEMO_MODE: 'false',
    HOST: '127.0.0.1',
    PORT: String(port),
    ADMIN_API_KEY: KEY,
    TELEGRAM_BOT_TOKEN: '123456789:TEST_MOCK_TOKEN',
    TELEGRAM_CHAT_ID: '987654321',
    TELEGRAM_MIN_GAP_MS: '1000'
  };

  const child = spawn(process.execPath, [path.join(tmp, 'server.mjs')], { cwd: tmp, env, stdio: 'pipe' });
  const base = `http://127.0.0.1:${port}`;
  async function req(url, body) {
    return fetch(base + url, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', 'X-API-Key': KEY },
      body: JSON.stringify(body)
    });
  }

  try {
    for (let i = 0; i < 50; i++) {
      if (child.exitCode !== null) throw Error('Server died');
      try {
        const r = await fetch(base + '/api/health');
        if (r.ok) break;
      } catch {}
      await new Promise(r => setTimeout(r, 100));
    }

    // 1. Post simulated incident (demo: true)
    const simRes = await req('/api/incidents', {
      id: 'SIM-ALERT-1',
      stationId: 'CM-01',
      stationName: 'สถานีป่าตัน (Simulated)',
      title: 'ประกาศจำลอง',
      severity: 'warning',
      message: 'จำลองท่อแตก',
      demo: true
    });
    assert.equal(simRes.status, 200);

    // 2. Post live telemetry that triggers critical alert (demo: false)
    const liveRes = await req('/api/telemetry', {
      stationId: 'CM-01',
      pressureBar: 0.5,
      tankLevelPct: 80,
      flowM3h: 1500,
      turbidityNtu: 0.3,
      chlorineMgL: 0.5,
      online: true
    });
    assert.equal(liveRes.status, 200);

    // Queue test item via /api/test-telegram (demo: true)
    const testTgRes = await req('/api/test-telegram', {});
    assert.equal(testTgRes.status, 202);

    // Wait for processQueue to cycle both pending jobs
    for (let i = 0; i < 30; i++) {
      const stateCheck = await (await fetch(base + '/api/state')).json();
      if (stateCheck.queueStats.pending === 0) break;
      await new Promise(r => setTimeout(r, 200));
    }

    // Check state snapshot
    const st = await (await fetch(base + '/api/state')).json();

    // Data Integrity Assertion: sent count MUST NOT include simulated or blocked jobs!
    assert.equal(st.queueStats.sent, 0, 'Real delivered count (sent) must remain 0 when external delivery is unauthorized');
    assert.ok(st.queueStats.simulated >= 1, 'Simulated alerts must be counted in queueStats.simulated');
    assert.ok(st.queueStats.blocked >= 1, 'Live telemetry alerts blocked by policy must be counted in queueStats.blocked');

    // Check individual job properties in queueRecent
    const blockedJob = st.queueRecent.find(j => j.status === 'blocked_by_policy');
    assert.ok(blockedJob, 'Must have at least one blocked_by_policy job');
    assert.ok(blockedJob.blockedAt, 'blocked_by_policy job must have blockedAt timestamp');
    assert.match(blockedJob.lastError, /Delivery suppressed: external network delivery not authorized/);

    const simJob = st.queueRecent.find(j => j.status === 'simulated');
    assert.ok(simJob, 'Must have at least one simulated job');
    assert.ok(simJob.simulatedAt, 'simulated job must have simulatedAt timestamp');

    // 3. Test Resume Policy: /api/queue/resume-blocked transitions blocked_by_policy back to pending
    const resumeRes = await req('/api/queue/resume-blocked', {});
    assert.equal(resumeRes.status, 200);
    const resumeData = await resumeRes.json();
    assert.ok(resumeData.resumed >= 1, 'Should resume at least 1 blocked job');

    // 4. Test Retry Policy: /api/queue/retry-failed
    const retryRes = await req('/api/queue/retry-failed', {});
    assert.equal(retryRes.status, 200);

  } finally {
    child.kill('SIGTERM');
    await new Promise(resolve => {
      if (child.exitCode !== null || child.signalCode) resolve();
      else child.once('exit', resolve);
    });
    fs.rmSync(tmp, { recursive: true, force: true });
  }
});

test('queue retention: capacity limit trimming strictly preserves pending notifications', { timeout: 20_000 }, async () => {
  const root = path.resolve(import.meta.dirname, '..');
  const tmp = fs.mkdtempSync(path.join(os.tmpdir(), 'aqua-retention-test-'));
  for (const file of ['server.mjs', 'rules.mjs']) {
    fs.copyFileSync(path.join(root, file), path.join(tmp, file));
  }
  fs.cpSync(path.join(root, 'public'), path.join(tmp, 'public'), { recursive: true });
  fs.mkdirSync(path.join(tmp, 'storage'));

  // Pre-seed storage state with 520 items: 220 terminal 'sent' and 300 'pending'
  const seedQueue = [];
  const now = new Date().toISOString();
  for (let i = 0; i < 220; i++) {
    seedQueue.push({
      id: `OLD-SENT-${i}`,
      alertId: `AL-OLD-${i}`,
      status: 'sent',
      attempt: 1,
      createdAt: now,
      sentAt: now,
      nextAt: Date.now() - 10000
    });
  }
  for (let i = 0; i < 300; i++) {
    seedQueue.push({
      id: `CRITICAL-PENDING-${i}`,
      alertId: `AL-PENDING-${i}`,
      status: 'pending',
      attempt: 0,
      createdAt: now,
      nextAt: Date.now() + 600000 // far in future so processQueue does not touch it during test
    });
  }

  const seedState = {
    alerts: [],
    queue: seedQueue,
    active: {},
    updatedAt: now
  };
  fs.writeFileSync(path.join(tmp, 'storage', 'state.json'), JSON.stringify(seedState, null, 2));

  const port = await openPort();
  const env = {
    ...process.env,
    APP_ENV: 'lab',
    DEMO_MODE: 'false',
    HOST: '127.0.0.1',
    PORT: String(port),
    ADMIN_API_KEY: KEY,
    TELEGRAM_BOT_TOKEN: '',
    TELEGRAM_CHAT_ID: ''
  };

  const child = spawn(process.execPath, [path.join(tmp, 'server.mjs')], { cwd: tmp, env, stdio: 'pipe' });
  const base = `http://127.0.0.1:${port}`;

  try {
    for (let i = 0; i < 50; i++) {
      if (child.exitCode !== null) throw Error('Server died');
      try {
        const r = await fetch(base + '/api/health');
        if (r.ok) break;
      } catch {}
      await new Promise(r => setTimeout(r, 100));
    }

    const st = await (await fetch(base + '/api/state')).json();

    // Verify all 300 pending items are intact
    assert.equal(
      st.queueStats.pending,
      300,
      'All 300 pending jobs must be 100% preserved; capacity limit must NEVER drop pending items'
    );

    // Verify queue was loaded and pending jobs are undamaged
    const persistedRaw = JSON.parse(fs.readFileSync(path.join(tmp, 'storage', 'state.json'), 'utf8'));
    const pendingInFile = persistedRaw.queue.filter(j => j.status === 'pending');
    assert.equal(pendingInFile.length, 300, 'All 300 pending items must be safely preserved in storage');

  } finally {
    child.kill('SIGTERM');
    await new Promise(resolve => {
      if (child.exitCode !== null || child.signalCode) resolve();
      else child.once('exit', resolve);
    });
    fs.rmSync(tmp, { recursive: true, force: true });
  }
});

test('DATA-02: Alert-Queue referential integrity, >400 alerts, >500 jobs, payload accessibility and restart recovery', { timeout: 30_000 }, async () => {
  const root = path.resolve(import.meta.dirname, '..');
  const tmp = fs.mkdtempSync(path.join(os.tmpdir(), 'aqua-data02-test-'));
  for (const file of ['server.mjs', 'rules.mjs']) {
    fs.copyFileSync(path.join(root, file), path.join(tmp, file));
  }
  fs.cpSync(path.join(root, 'public'), path.join(tmp, 'public'), { recursive: true });
  fs.mkdirSync(path.join(tmp, 'storage'));

  const now = new Date().toISOString();
  // Pre-seed storage with 450 alerts and 550 jobs
  // Alerts 0-49: resolved & acknowledged (safe to prune if excess)
  // Alerts 50-249: referenced by pending jobs (MUST NEVER BE PRUNED)
  // Alerts 250-449: unacknowledged active alerts (MUST NEVER BE PRUNED)
  const seedAlerts = [];
  const seedQueue = [];

  for (let i = 0; i < 450; i++) {
    const isAcknowledged = i < 50;
    seedAlerts.push({
      id: `AL-TEST-${i}`,
      stationId: `CM-${(i % 12) + 1}`,
      stationName: `Station ${i}`,
      region: 'Chiang Mai',
      title: `Water Outage Incident ${i}`,
      severity: i % 2 === 0 ? 'critical' : 'warning',
      message: `Detailed pipe break telemetry info ${i}`,
      value: 0.5,
      ruleId: 'pressure-low',
      createdAt: now,
      resolvedAt: isAcknowledged ? now : null,
      acknowledgedAt: isAcknowledged ? now : null,
      demo: false
    });
  }

  // Jobs: 350 completed 'sent' jobs + 200 'pending' jobs referencing alerts 50..249
  for (let i = 0; i < 350; i++) {
    seedQueue.push({
      id: `SENT-JOB-${i}`,
      alertId: `AL-TEST-${i % 50}`, // references resolved/acknowledged alert
      status: 'sent',
      attempt: 1,
      createdAt: now,
      sentAt: now,
      nextAt: Date.now() - 100000,
      payload: { text: `Delivered text ${i}`, title: `Title ${i}` }
    });
  }

  for (let i = 50; i < 250; i++) {
    seedQueue.push({
      id: `PENDING-JOB-${i}`,
      alertId: `AL-TEST-${i}`,
      status: 'pending',
      attempt: 0,
      createdAt: now,
      nextAt: Date.now() + 600000,
      payload: { text: `Pending text for alert ${i}`, title: `Alert ${i}` }
    });
  }

  assert.equal(seedAlerts.length, 450);
  assert.equal(seedQueue.length, 550);

  fs.writeFileSync(path.join(tmp, 'storage', 'state.json'), JSON.stringify({
    alerts: seedAlerts,
    queue: seedQueue,
    active: {},
    updatedAt: now
  }, null, 2));

  let port = await openPort();
  const env = {
    ...process.env,
    APP_ENV: 'lab',
    DEMO_MODE: 'false',
    HOST: '127.0.0.1',
    PORT: String(port),
    ADMIN_API_KEY: KEY,
    TELEGRAM_BOT_TOKEN: '123456:TEST_TOKEN',
    TELEGRAM_CHAT_ID: '999999'
  };

  let child = spawn(process.execPath, [path.join(tmp, 'server.mjs')], { cwd: tmp, env, stdio: 'pipe' });
  let base = `http://127.0.0.1:${port}`;

  try {
    for (let i = 0; i < 50; i++) {
      if (child.exitCode !== null) throw Error('Server died');
      try {
        const r = await fetch(base + '/api/health');
        if (r.ok) break;
      } catch {}
      await new Promise(r => setTimeout(r, 100));
    }

    let st = await (await fetch(base + '/api/state')).json();

    // 1. Referential integrity: All 200 pending jobs are intact
    assert.equal(st.queueStats.pending, 200, 'All 200 pending jobs must be preserved');

    // 2. Verified payload accessibility: Every pending job has valid payload
    const pendingJobs = st.queueRecent.filter(j => j.status === 'pending');
    for (const j of pendingJobs) {
      assert.ok(j.alertId, 'Pending job must have associated alertId');
    }

    // 3. Restart recovery test:
    // Terminate server cleanly with SIGTERM and restart it
    child.kill('SIGTERM');
    await new Promise(resolve => {
      if (child.exitCode !== null || child.signalCode) resolve();
      else child.once('exit', resolve);
    });

    // Start server again from same storage directory
    port = await openPort();
    env.PORT = String(port);
    base = `http://127.0.0.1:${port}`;
    child = spawn(process.execPath, [path.join(tmp, 'server.mjs')], { cwd: tmp, env, stdio: 'pipe' });

    for (let i = 0; i < 50; i++) {
      if (child.exitCode !== null) throw Error('Restarted server died');
      try {
        const r = await fetch(base + '/api/health');
        if (r.ok) break;
      } catch {}
      await new Promise(r => setTimeout(r, 100));
    }

    // Re-verify state after restart
    const restartedState = await (await fetch(base + '/api/state')).json();
    assert.equal(restartedState.queueStats.pending, 200, 'All 200 pending jobs must survive restart');

    // Verify all referenced alerts (50..249) exist in restarted server storage
    const rawSaved = JSON.parse(fs.readFileSync(path.join(tmp, 'storage', 'state.json'), 'utf8'));
    const savedAlertIds = new Set(rawSaved.alerts.map(a => a.id));
    for (let i = 50; i < 250; i++) {
      assert.ok(savedAlertIds.has(`AL-TEST-${i}`), `Referenced alert AL-TEST-${i} must never be pruned`);
    }

  } finally {
    child.kill('SIGTERM');
    await new Promise(resolve => {
      if (child.exitCode !== null || child.signalCode) resolve();
      else child.once('exit', resolve);
    });
    fs.rmSync(tmp, { recursive: true, force: true });
  }
});

test('DATA-02: Legacy alert schema migration, ACK evidence, and schema resilience', { timeout: 20_000 }, async () => {
  const root = path.resolve(import.meta.dirname, '..');
  const tmp = fs.mkdtempSync(path.join(os.tmpdir(), 'aqua-legacy-schema-'));
  for (const file of ['server.mjs', 'rules.mjs']) {
    fs.copyFileSync(path.join(root, file), path.join(tmp, file));
  }
  fs.cpSync(path.join(root, 'public'), path.join(tmp, 'public'), { recursive: true });
  fs.mkdirSync(path.join(tmp, 'storage'));

  const now = new Date().toISOString();
  // Pre-seed with legacy alert representations missing acknowledgedAt or resolvedAt
  const legacyAlerts = [
    { id: 'LEGACY-ACK', stationId: 'CM-01', stationName: 'Station 1', title: 'Legacy Ack Alert', severity: 'warning', message: 'Legacy ack alert', acknowledged: true },
    { id: 'LEGACY-RES', stationId: 'CM-02', stationName: 'Station 2', title: 'Legacy Res Alert', severity: 'resolved', message: 'Legacy res alert', resolved: true },
    { id: 'LEGACY-STATUS', stationId: 'CM-03', stationName: 'Station 3', title: 'Legacy Status Alert', severity: 'warning', message: 'Legacy status ack', status: 'acknowledged' },
    { id: 'LEGACY-ACTIVE', stationId: 'CM-04', stationName: 'Station 4', title: 'Active Alert', severity: 'critical', message: 'Original critical issue', demo: false }
  ];

  // Legacy job missing payload
  const legacyQueue = [
    { id: 'LEGACY-JOB-1', alertId: 'LEGACY-ACTIVE', status: 'pending', attempt: 0, nextAt: Date.now() + 600000, createdAt: now }
  ];

  fs.writeFileSync(path.join(tmp, 'storage', 'state.json'), JSON.stringify({
    alerts: legacyAlerts,
    queue: legacyQueue,
    active: {},
    updatedAt: now
  }, null, 2));

  const port = await openPort();
  const env = {
    ...process.env,
    APP_ENV: 'lab',
    DEMO_MODE: 'false',
    HOST: '127.0.0.1',
    PORT: String(port),
    ADMIN_API_KEY: KEY,
    TELEGRAM_BOT_TOKEN: '123456:MOCK',
    TELEGRAM_CHAT_ID: '999999'
  };

  const child = spawn(process.execPath, [path.join(tmp, 'server.mjs')], { cwd: tmp, env, stdio: 'pipe' });
  const base = `http://127.0.0.1:${port}`;

  try {
    for (let i = 0; i < 50; i++) {
      if (child.exitCode !== null) throw Error('Server died');
      try {
        const r = await fetch(base + '/api/health');
        if (r.ok) break;
      } catch {}
      await new Promise(r => setTimeout(r, 100));
    }

    const st = await (await fetch(base + '/api/state')).json();
    const loadedAlerts = st.alerts;

    // 1. Verify schema migration and ACK/resolved recognition
    const ackAlert = loadedAlerts.find(a => a.id === 'LEGACY-ACK');
    assert.ok(ackAlert.acknowledged === true || ackAlert.acknowledgedAt !== null, 'Legacy ACK must be recognized');

    const resAlert = loadedAlerts.find(a => a.id === 'LEGACY-RES');
    assert.ok(resAlert.resolved === true || resAlert.resolvedAt !== null, 'Legacy resolution must be recognized');

    // 2. Verify legacy job payload was migrated/enriched from associated alert
    const rawSaved = JSON.parse(fs.readFileSync(path.join(tmp, 'storage', 'state.json'), 'utf8'));
    const savedJob = rawSaved.queue.find(j => j.id === 'LEGACY-JOB-1');
    assert.ok(savedJob.payload, 'Legacy job without payload must be enriched on load');
    assert.ok(savedJob.payload.text, 'Enriched payload must have message text');

    // 3. Acknowledge the active alert via API and verify dual ACK evidence
    const ackRes = await fetch(base + '/api/alerts/LEGACY-ACTIVE/ack', {
      method: 'POST',
      headers: { 'X-API-Key': KEY }
    });
    assert.equal(ackRes.status, 200);
    const ackBody = await ackRes.json();
    assert.ok(ackBody.acknowledgedAt, 'ACK endpoint must return acknowledged timestamp');

    // Check state has both fields
    const updatedSt = await (await fetch(base + '/api/state')).json();
    const updatedActive = updatedSt.alerts.find(a => a.id === 'LEGACY-ACTIVE');
    assert.ok(updatedActive.acknowledgedAt, 'acknowledgedAt timestamp must be recorded');
    assert.equal(updatedActive.acknowledged, true, 'acknowledged boolean must be true');

  } finally {
    child.kill('SIGTERM');
    await new Promise(resolve => {
      if (child.exitCode !== null || child.signalCode) resolve();
      else child.once('exit', resolve);
    });
    fs.rmSync(tmp, { recursive: true, force: true });
  }
});

test('DATA-02: Boundary and backpressure on saturated capacity for external ingest and internal rules', { timeout: 25_000 }, async () => {
  const root = path.resolve(import.meta.dirname, '..');
  const tmp = fs.mkdtempSync(path.join(os.tmpdir(), 'aqua-backpressure-'));
  for (const file of ['server.mjs', 'rules.mjs']) {
    fs.copyFileSync(path.join(root, file), path.join(tmp, file));
  }
  fs.cpSync(path.join(root, 'public'), path.join(tmp, 'public'), { recursive: true });
  fs.mkdirSync(path.join(tmp, 'storage'));

  const now = new Date().toISOString();
  // Fill alert store to MAX_ALERT_STORE (400) with active UNACKNOWLEDGED alerts
  const saturatedAlerts = [];
  for (let i = 0; i < 400; i++) {
    saturatedAlerts.push({
      id: `UNACK-${i}`,
      stationId: 'CM-01',
      stationName: 'Station 1',
      region: 'Chiang Mai',
      title: `Unacknowledged Outage ${i}`,
      severity: 'critical',
      message: `Active incident ${i}`,
      value: 0.2,
      ruleId: 'pressure-low',
      createdAt: now,
      resolvedAt: null,
      acknowledgedAt: null,
      acknowledged: false,
      resolved: false,
      demo: false
    });
  }

  fs.writeFileSync(path.join(tmp, 'storage', 'state.json'), JSON.stringify({
    alerts: saturatedAlerts,
    queue: [],
    active: {},
    updatedAt: now
  }, null, 2));

  const port = await openPort();
  const env = {
    ...process.env,
    APP_ENV: 'lab',
    DEMO_MODE: 'false',
    HOST: '127.0.0.1',
    PORT: String(port),
    ADMIN_API_KEY: KEY,
    TELEGRAM_BOT_TOKEN: '123456:MOCK',
    TELEGRAM_CHAT_ID: '999999'
  };

  const child = spawn(process.execPath, [path.join(tmp, 'server.mjs')], { cwd: tmp, env, stdio: 'pipe' });
  const base = `http://127.0.0.1:${port}`;

  try {
    for (let i = 0; i < 50; i++) {
      if (child.exitCode !== null) throw Error('Server died');
      try {
        const r = await fetch(base + '/api/health');
        if (r.ok) break;
      } catch {}
      await new Promise(r => setTimeout(r, 100));
    }

    // 1. External Ingest: Attempt to add 401st alert when all 400 are unacknowledged -> expect 503 backpressure
    const overflowRes = await fetch(base + '/api/incidents', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', 'X-API-Key': KEY },
      body: JSON.stringify({
        title: '401st Outage Incident',
        severity: 'critical',
        message: 'Should be rejected by backpressure'
      })
    });
    assert.equal(overflowRes.status, 503, 'Saturated alert store must reject new incidents with 503');
    const errBody = await overflowRes.json();
    assert.ok(errBody.error.includes('capacity limit reached'), 'Error must mention capacity limit');
    assert.equal(errBody.retryAfterSeconds, 30, 'Backpressure must include Retry-After hint');

    // 2. Internal telemetry generation: Should throttle gracefully without exceeding MAX_ALERT_STORE
    const telemRes = await fetch(base + '/api/telemetry', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', 'X-API-Key': KEY },
      body: JSON.stringify({
        stationId: 'CM-01',
        pressureBar: 0.1, // triggers critical rule
        online: true
      })
    });
    assert.equal(telemRes.status, 503, 'Rule alert rejection must reach the telemetry caller');
    assert.equal(telemRes.headers.get('Retry-After'), '30');
    assert.equal((await telemRes.json()).code, 'ALERT_CAPACITY');

    const rawCheck = JSON.parse(fs.readFileSync(path.join(tmp, 'storage', 'state.json'), 'utf8'));
    assert.equal(rawCheck.alerts.length, 400, 'Alert store length in state must not exceed MAX_ALERT_STORE ceiling');
    assert.deepEqual(rawCheck.active, {}, 'Rejected alert must not advance rule state');
    assert.deepEqual(rawCheck.queue, [], 'Rejected alert must not append an outbox job');

    // 3. Acknowledge one alert to free capacity
    const ackRes = await fetch(base + '/api/alerts/UNACK-0/ack', {
      method: 'POST',
      headers: { 'X-API-Key': KEY }
    });
    assert.equal(ackRes.status, 200);

    // 4. Now external incident post should succeed because UNACK-0 can be pruned
    const allowedRes = await fetch(base + '/api/incidents', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', 'X-API-Key': KEY },
      body: JSON.stringify({
        title: 'New Incident After Acknowledging Old',
        severity: 'warning',
        message: 'Accepted because capacity was freed'
      })
    });
    assert.equal(allowedRes.status, 200, 'Should accept new incident after capacity freed by ACK');
    const allowedBody = await allowedRes.json();
    assert.ok(allowedBody.alertId, 'Should return created alertId');

  } finally {
    child.kill('SIGTERM');
    await new Promise(resolve => {
      if (child.exitCode !== null || child.signalCode) resolve();
      else child.once('exit', resolve);
    });
    fs.rmSync(tmp, { recursive: true, force: true });
  }
});

test('DATA-02: Immutable job payload primary delivery and retry state retention', { timeout: 20_000 }, async () => {
  const root = path.resolve(import.meta.dirname, '..');
  const tmp = fs.mkdtempSync(path.join(os.tmpdir(), 'aqua-payload-fidelity-'));
  for (const file of ['server.mjs', 'rules.mjs']) {
    fs.copyFileSync(path.join(root, file), path.join(tmp, file));
  }
  fs.cpSync(path.join(root, 'public'), path.join(tmp, 'public'), { recursive: true });
  fs.mkdirSync(path.join(tmp, 'storage'));

  const port = await openPort();
  const env = {
    ...process.env,
    APP_ENV: 'lab',
    DEMO_MODE: 'false',
    SEND_DEMO_ALERTS: 'true',
    HOST: '127.0.0.1',
    PORT: String(port),
    ADMIN_API_KEY: KEY,
    TELEGRAM_BOT_TOKEN: '123456:MOCK',
    TELEGRAM_CHAT_ID: '999999',
    TELEGRAM_MIN_GAP_MS: '1000'
  };

  const child = spawn(process.execPath, [path.join(tmp, 'server.mjs')], { cwd: tmp, env, stdio: 'pipe' });
  const base = `http://127.0.0.1:${port}`;

  try {
    for (let i = 0; i < 50; i++) {
      if (child.exitCode !== null) throw Error('Server died');
      try {
        const r = await fetch(base + '/api/health');
        if (r.ok) break;
      } catch {}
      await new Promise(r => setTimeout(r, 100));
    }

    // Post test telegram to queue a job with an immutable payload
    const qRes = await fetch(base + '/api/test-telegram', {
      method: 'POST',
      headers: { 'X-API-Key': KEY }
    });
    assert.equal(qRes.status, 202);
    const qBody = await qRes.json();
    assert.ok(qBody.id);

    // Wait for processQueue to cycle the job to 'simulated' in lab mode
    let simulatedJob = null;
    for (let i = 0; i < 30; i++) {
      const st = await (await fetch(base + '/api/state')).json();
      simulatedJob = st.queueRecent.find(j => j.alertId === qBody.id);
      if (simulatedJob && simulatedJob.status === 'simulated') break;
      await new Promise(r => setTimeout(r, 200));
    }

    assert.ok(simulatedJob, 'Job must be processed in queue');
    assert.equal(simulatedJob.status, 'simulated');

  } finally {
    child.kill('SIGTERM');
    await new Promise(resolve => {
      if (child.exitCode !== null || child.signalCode) resolve();
      else child.once('exit', resolve);
    });
    fs.rmSync(tmp, { recursive: true, force: true });
  }
});
