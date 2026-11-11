import test from 'node:test';
import assert from 'node:assert/strict';
import { once } from 'node:events';
import fs from 'node:fs';
import path from 'node:path';
import os from 'node:os';
import net from 'node:net';
import { spawn } from 'node:child_process';

const key = 'lab-only-key-long-enough-for-test';
const packet = {stationId: 'CM-01', pressureBar: 0.5, online: true};

async function lab(t, seed = {alerts: [], queue: [], active: {}}) {
  const tmp = fs.mkdtempSync(path.join(os.tmpdir(), 'aqua-data04-'));
  const state = path.join(tmp, 'storage', 'state.json');
  fs.mkdirSync(path.dirname(state));
  for (const file of ['server.mjs', 'rules.mjs']) {
    fs.copyFileSync(path.resolve(import.meta.dirname, '..', file), path.join(tmp, file));
  }
  fs.writeFileSync(state, JSON.stringify(seed));
  let child;
  let base;
  async function stop() {
    if (child && child.exitCode === null && child.signalCode === null) {
      const exited = once(child, 'exit');
      child.kill('SIGKILL');
      await exited;
    }
  }
  t.after(async () => {
    await stop();
    fs.rmSync(tmp, {recursive: true, force: true});
  });
  async function start() {
    const listener = net.createServer();
    listener.listen(0, '127.0.0.1');
    await once(listener, 'listening');
    const {port} = listener.address();
    await new Promise(resolve => listener.close(resolve));
    base = `http://127.0.0.1:${port}`;
    child = spawn(process.execPath, ['server.mjs'], {cwd: tmp, stdio: 'ignore', env: {
      PATH: process.env.PATH, HOME: tmp, HOST: '127.0.0.1', PORT: String(port), DEMO_MODE: 'false',
      APP_ENV: 'lab', TELEGRAM_EXTERNAL_DELIVERY_AUTHORIZED: 'false', ADMIN_API_KEY: key,
      TELEGRAM_BOT_TOKEN: 'lab-token', TELEGRAM_CHAT_ID: '1',
    }});
    for (let n = 0; n < 100; n++) {
      if (child.exitCode !== null) throw new Error(`LAB server exited ${child.exitCode}`);
      try {
        if ((await fetch(base + '/api/health')).ok) return;
      } catch {}
      await new Promise(resolve => setTimeout(resolve, 25));
    }
    throw new Error('LAB server did not become ready');
  }
  await start();
  return {
    state, start, stop,
    snapshot: () => JSON.parse(fs.readFileSync(state, 'utf8')),
    telemetry: (values = packet) => fetch(base + '/api/telemetry', {
      method: 'POST', headers: {'X-API-Key': key, 'Content-Type': 'application/json'},
      body: JSON.stringify(values),
    }),
  };
}

test('DATA-04: a full outbox rejects telemetry without changing existing state', {timeout: 10000}, async t => {
  const queue = Array.from({length: 500}, (_, i) => ({
    id: `job-${i}`, alertId: `alert-${i}`, status: 'pending', attempt: 0,
    nextAt: Date.now() + 600000, payload: {text: 'synthetic alert'},
  }));
  const seed = {alerts: [], queue, active: {}};
  const app = await lab(t, seed);
  const response = await app.telemetry();
  assert.equal(response.status, 503);
  assert.equal((await response.json()).code, 'ALERT_CAPACITY');
  assert.deepEqual(app.snapshot(), seed);
});

test('DATA-04: failed rename leaves old state intact and retry survives abrupt restart', {timeout: 10000}, async t => {
  const seed = {alerts: [], queue: [], active: {}};
  const app = await lab(t, seed);
  const backup = app.state + '.baseline';
  fs.renameSync(app.state, backup);
  fs.mkdirSync(app.state);
  try {
    const rejected = await app.telemetry();
    assert.equal(rejected.status, 503);
    assert.equal((await rejected.json()).code, 'ALERT_PERSISTENCE');
    assert.equal(fs.readFileSync(backup, 'utf8'), JSON.stringify(seed));
    assert.deepEqual(fs.readdirSync(path.dirname(app.state)).sort(), ['state.json', 'state.json.baseline']);
  } finally {
    fs.rmdirSync(app.state);
    fs.renameSync(backup, app.state);
  }

  const accepted = await app.telemetry();
  assert.equal(accepted.status, 200);
  await app.stop(); // SIGKILL rules out saving via the shutdown handler.
  const durable = app.snapshot();
  assert.equal(durable.alerts.length, 1);
  assert.equal(durable.queue.length, 1);
  assert.equal(durable.queue[0].alertId, durable.alerts[0].id);
  assert.equal(durable.active['CM-01:pressure-low'].severity, 'critical');

  await app.start();
  assert.equal((await app.telemetry()).status, 200);
  const recovered = app.snapshot();
  assert.deepEqual(recovered.alerts, durable.alerts);
  assert.deepEqual(recovered.active, durable.active);
  assert.equal(recovered.queue.length, 1);
  assert.equal(recovered.queue[0].id, durable.queue[0].id);
});

test('DATA-04: an update triggering two rules cannot use just one free outbox slot', {timeout: 10000}, async t => {
  const queue = Array.from({length: 499}, (_, i) => ({
    id: `job-${i}`, alertId: `alert-${i}`, status: 'pending', attempt: 0,
    nextAt: Date.now() + 600000, payload: {text: 'synthetic alert'},
  }));
  const seed = {alerts: [], queue, active: {}};
  const app = await lab(t, seed);
  const response = await app.telemetry({...packet, tankLevelPct: 10});
  assert.equal(response.status, 503);
  assert.equal((await response.json()).code, 'ALERT_CAPACITY');
  assert.deepEqual(app.snapshot(), seed);
  assert.equal((await app.telemetry()).status, 200);
  const durable = app.snapshot();
  assert.equal(durable.alerts.length, 1);
  assert.deepEqual(durable.queue.slice(0, 499), queue);
  assert.equal(durable.queue[499].alertId, durable.alerts[0].id);
  assert.deepEqual(Object.keys(durable.active), ['CM-01:pressure-low']);
});

test('DATA-04: an unreadable snapshot blocks startup and is left untouched', {timeout: 10000}, async t => {
  const app = await lab(t);
  await app.stop();
  const corrupt = '{"alerts": [';
  fs.writeFileSync(app.state, corrupt);
  await assert.rejects(app.start(), /LAB server exited 1/);
  assert.equal(fs.readFileSync(app.state, 'utf8'), corrupt);
});
