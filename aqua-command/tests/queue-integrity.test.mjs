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
