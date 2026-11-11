import test from 'node:test';
import assert from 'node:assert/strict';
import {once} from 'node:events';
import fs from 'node:fs';
import path from 'node:path';
import os from 'node:os';
import http from 'node:http';
import net from 'node:net';
import {spawn} from 'node:child_process';

const key = 'lab-only-ambiguous-delivery-key';
const pause = ms => new Promise(resolve => setTimeout(resolve, ms));

async function waitFor(read, predicate) {
  const deadline = Date.now() + 8000;
  while (Date.now() < deadline) {
    const value = await read();
    if (predicate(value)) return value;
    await pause(25);
  }
  assert.fail('LAB condition was not reached');
}

async function deliveryLab(t, firstOutcome, legacyJob = {}) {
  const dir = fs.mkdtempSync(path.join(os.tmpdir(), 'aqua-delivery-lab-'));
  const state = path.join(dir, 'storage', 'state.json');
  fs.mkdirSync(path.dirname(state));
  const job = () => JSON.parse(fs.readFileSync(state, 'utf8')).queue[0];
  const requests = [];
  let child;
  const sink = http.createServer(async (req, res) => {
    const parts = [];
    for await (const chunk of req) parts.push(chunk);
    requests.push({body: JSON.parse(Buffer.concat(parts)), durableStatus: job().status});
    if (requests.length === 1) {
      if (firstOutcome === '429') {
        res.writeHead(429, {'Content-Type': 'application/json'});
        res.end(JSON.stringify({ok: false, error_code: 429, parameters: {retry_after: 3}}));
        return;
      }
      if (firstOutcome === 'crash') child.kill('SIGKILL');
      req.socket.destroy();
      return;
    }
    res.end(JSON.stringify({ok: true, result: {message_id: 101}}));
  });
  sink.listen(0, '127.0.0.1');
  await once(sink, 'listening');
  async function stop() {
    if (child && child.exitCode === null && child.signalCode === null) {
      const exited = once(child, 'exit');
      child.kill('SIGKILL');
      await exited;
    }
  }
  t.after(async () => {
    await stop();
    await new Promise(resolve => sink.close(resolve));
    fs.rmSync(dir, {recursive: true, force: true});
  });
  for (const file of ['server.mjs', 'rules.mjs']) {
    fs.copyFileSync(path.resolve(import.meta.dirname, '..', file), path.join(dir, file));
  }
  fs.writeFileSync(state, JSON.stringify({alerts: [], active: {}, queue: [{
    id: 'lab-job', alertId: 'lab-alert', status: 'pending', attempt: 0,
    nextAt: Date.now(), payload: {text: 'test-only receipt loss', demo: false}, ...legacyJob,
  }]}));
  const preload = path.join(dir, 'local-transport.mjs');
  const url = 'http://127.0.0.1:' + sink.address().port + '/local-delivery';
  fs.writeFileSync(preload, [
    'const nativeFetch = globalThis.fetch;',
    'globalThis.fetch = (url, options) => {',
    '  if (url !== "https://api.telegram.org/botlab-token/sendMessage") throw Error("Network target rejected by LAB harness");',
    '  return nativeFetch(' + JSON.stringify(url) + ', options);',
    '};',
  ].join('\n'));
  let base;
  async function start() {
    const socket = net.createServer();
    socket.listen(0, '127.0.0.1');
    await once(socket, 'listening');
    const {port} = socket.address();
    await new Promise(resolve => socket.close(resolve));
    base = 'http://127.0.0.1:' + port;
    child = spawn(process.execPath, ['--import', preload, 'server.mjs'], {cwd: dir, stdio: 'ignore', env: {
      PATH: process.env.PATH, HOME: dir, HOST: '127.0.0.1', PORT: String(port), DEMO_MODE: 'false',
      APP_ENV: 'production', TELEGRAM_EXTERNAL_DELIVERY_AUTHORIZED: 'true', ADMIN_API_KEY: key,
      TELEGRAM_BOT_TOKEN: 'lab-token', TELEGRAM_CHAT_ID: '1',
    }});
    await waitFor(async () => {
      if (child.exitCode !== null || child.signalCode !== null) throw Error('LAB server exited');
      try { return (await fetch(base + '/api/health')).ok; } catch { return false; }
    }, Boolean);
  }
  await start();
  return {job, requests, stop, start, state: () => fetch(base + '/api/state').then(res => res.json()),
    post: (route, body = {}, apiKey = key) => fetch(base + route, {
      method: 'POST', headers: {'X-API-Key': apiKey, 'Content-Type': 'application/json'},
      body: JSON.stringify(body),
    })};
}

test('lost reply is retained without an automatic duplicate, including after restart', {timeout: 20000}, async t => {
  const app = await deliveryLab(t, 'drop');
  await waitFor(app.job, job => job.status === 'delivery_unknown');
  assert.equal(app.requests[0].durableStatus, 'sending');
  assert.equal((await app.state()).queueStats.deliveryUnknown, 1);
  assert.equal((await app.post('/api/queue/retry-failed')).status, 200);
  await app.stop();
  await app.start();
  await pause(4400); // Beyond the previous automatic retry interval.
  assert.equal(app.requests.length, 1);
  assert.equal(app.job().id, 'lab-job');
  const route = '/api/queue/lab-job/retry-unknown';
  assert.equal((await app.post(route, {confirmDuplicateRisk: true}, '')).status, 401);
  assert.equal((await app.post(route)).status, 422);
  assert.equal((await app.post(route, {confirmDuplicateRisk: true})).status, 202);
  assert.equal((await app.post(route, {confirmDuplicateRisk: true})).status, 409);
  const sent = await waitFor(app.job, job => job.status === 'sent');
  assert.equal(sent.messageId, 101);
  assert.equal(sent.attempt, 2);
  assert.ok(sent.duplicateRiskAcceptedAt);
  assert.equal(app.requests.length, 2);
  assert.deepEqual(app.requests[0].body, app.requests[1].body);
});

test('SIGKILL after dispatch recovers a durable sending job as unknown', {timeout: 12000}, async t => {
  const app = await deliveryLab(t, 'crash');
  await waitFor(() => app.requests.length, n => n === 1);
  await app.stop();
  assert.equal(app.job().status, 'sending');
  await app.start();
  assert.equal(app.job().status, 'delivery_unknown');
  assert.equal(app.requests.length, 1);
});

test('explicit 429 rejection remains safely retryable', {timeout: 12000}, async t => {
  const app = await deliveryLab(t, '429');
  const delayed = await waitFor(app.job, job => job.status === 'retry_pending');
  assert.equal(delayed.attempt, 1);
  assert.ok(delayed.nextAt > Date.now());
  assert.equal(app.requests.length, 1);
  const sent = await waitFor(app.job, job => job.status === 'sent');
  assert.equal(sent.attempt, 2);
  assert.equal(app.requests.length, 2);
});

test('legacy exhausted ambiguous jobs stay held even through Retry Failed', {timeout: 10000}, async t => {
  const app = await deliveryLab(t, 'drop', {status: 'failed', attempt: 6, lastError: 'fetch failed'});
  assert.equal(app.job().status, 'delivery_unknown');
  const retry = await app.post('/api/queue/retry-failed');
  assert.equal((await retry.json()).retried, 0);
  await pause(1200);
  assert.equal(app.requests.length, 0);
  assert.equal(app.job().id, 'lab-job');
});
