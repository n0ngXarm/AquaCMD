// Actual browser acceptance of separate synthetic fixtures and runtime history context.
import assert from 'node:assert/strict';
import { createRequire } from 'node:module';
import { readFile, writeFile } from 'node:fs/promises';
import { fileURLToPath } from 'node:url';
import path from 'node:path';

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const evidence = path.resolve(root, '../../../../evidence');
const require = createRequire(import.meta.url);
const { chromium } = require(path.join(root, 'private/browser/node_modules/playwright'));
const { url } = JSON.parse(await readFile(path.join(root, 'private/state.json'), 'utf8'));
const browser = await chromium.launch({ executablePath: '/usr/bin/google-chrome', headless: true, chromiumSandbox: true,
  args: ['--disable-background-networking', '--disable-component-update', '--no-first-run'] });
const results = { synthetic: [], history: [], renderedPanels: [], blocked: [], errors: [], queryErrors: [] };
try {
  const context = await browser.newContext({ viewport: { width: 1600, height: 900 }, timezoneId: 'UTC' });
  await context.route('**/*', route => {
    const target = new URL(route.request().url());
    if (target.origin === url || ['data:', 'blob:'].includes(target.protocol)) return route.continue();
    results.blocked.push(target.origin);
    return route.abort('blockedbyclient');
  });
  const page = await context.newPage();
  const historyResponses = [];
  page.on('pageerror', error => results.errors.push(error.message));
  page.on('response', async response => {
    if (new URL(response.url()).pathname !== '/api/ds/query') return;
    try {
      const data = await response.json();
      if (response.status() !== 200 || Object.values(data.results || {}).some(result => result.error))
        results.queryErrors.push({ status: response.status() });
      const queries = response.request().postDataJSON()?.queries || [];
      for (const query of queries.filter(item => item.url?.includes('/runtime/history?'))) {
        const frames = data.results?.[query.refId]?.frames || [];
        const payload = frames[0]?.schema?.meta?.custom?.data;
        historyResponses.push({ url: query.url, payload });
      }
    } catch { results.queryErrors.push({ status: response.status() }); }
  });
  await page.goto(url + '/login', { waitUntil: 'domcontentloaded' });
  await page.getByRole('textbox', { name: 'Email or username' }).fill('aqua-viewer');
  await page.getByRole('textbox', { name: 'Password', exact: true }).fill((await readFile(path.join(root, 'private/viewer-password'), 'utf8')).trim());
  await page.getByRole('button', { name: 'Log in', exact: true }).click();
  await page.waitForURL(current => !current.pathname.startsWith('/login'));
  await page.goto(url + '/d/aqua-synthetic-acceptance?timezone=utc', { waitUntil: 'domcontentloaded' });
  try {
    await page.getByRole('heading', { name: 'SYNTHETIC ACCEPTANCE ONLY', exact: true }).waitFor({ timeout: 10000 });
  } catch (error) {
    await page.screenshot({ path: path.join(evidence, 'screenshots/synthetic-load-failure.png'), fullPage: true });
    await writeFile(path.join(evidence, 'synthetic-load-failure-ax.txt'), await page.locator('body').ariaSnapshot());
    console.log(JSON.stringify({ failedUrl: page.url(), title: await page.title() }));
    throw error;
  }
  const table = page.getByRole('region', { name: 'SYNTHETIC · NULL / zero / false', exact: true });
  await table.getByText('GOOD_FALSE', { exact: true }).waitFor();
  const tableText = await table.innerText();
  assert.match(tableText, /false/);
  assert.match(tableText, /NO DATA/);
  await table.screenshot({ path: path.join(evidence, 'screenshots/synthetic-null-zero-false.png') });
  const topology = page.getByRole('region', { name: 'SYNTHETIC · State colors', exact: true });
  await topology.scrollIntoViewIfNeeded();
  await page.getByTestId('node-click-rect-synthetic-STALE').waitFor();
  if (process.argv.includes('--inspect')) {
    console.log((await page.getByTestId('node-click-rect-synthetic-STALE').evaluate(node => node.parentElement.outerHTML)).slice(0, 9000));
    console.log((await page.locator('body').ariaSnapshot()).slice(0, 6500));
  } else {
    const colors = { CONFIGURED: '#91a0b4', UNKNOWN: '#91a0b4', STALE: '#f0c36d', REACHABLE: '#8cc7d9', TCP_CONNECTED: '#a3afff',
      OPC_UA_CONNECTED: '#67baf5', READ_VERIFIED: '#56d9a2', ERROR: '#ed7f85' };
    for (const [state, color] of Object.entries(colors)) {
      const node = page.getByTestId('node-click-rect-synthetic-' + state);
      const markup = await node.evaluate(element => element.parentElement.outerHTML.toLowerCase());
      assert(markup.includes(color), state + ' does not render expected state color ' + color);
      results.synthetic.push({ state, expectedColor: color, rendered: true });
    }
    for (let step = 0; step <= 6; step++) {
      const bounds = await topology.boundingBox();
      const nodes = await page.locator('[data-testid^="node-click-rect-synthetic-"]').evaluateAll(elements =>
        elements.map(element => {
          const rect = element.parentElement.getBoundingClientRect();
          return { left: rect.left, right: rect.right, top: rect.top, bottom: rect.bottom };
        }));
      const fits = nodes.length === 8 && nodes.every(node => node.left >= bounds.x && node.right <= bounds.x + bounds.width &&
        node.top >= bounds.y + 30 && node.bottom <= bounds.y + bounds.height - 35);
      if (fits) { results.nativeZoomOutSteps = step; break; }
      assert(step < 6, 'Synthetic nodes remain clipped after native zoom controls');
      await topology.getByRole('button', { name: 'Zoom out', exact: true }).click();
      await topology.evaluate(() => new Promise(resolve => requestAnimationFrame(() => requestAnimationFrame(resolve))));
    }
    await topology.screenshot({ path: path.join(evidence, 'screenshots/synthetic-state-colors.png') });
    const native = JSON.parse(await readFile(path.join(root, 'private/native-link.json'), 'utf8'));
    assert.match(native.tag_id, /^tag-[a-f0-9]{20}$/);
    for (const [range, hours] of [['1h', 1], ['24h', 24], ['7d', 168]]) {
      historyResponses.length = 0;
      const target = new URL(native.url);
      target.searchParams.set('from', 'now-' + range);
      await page.goto(target.toString(), { waitUntil: 'domcontentloaded' });
      const trend = page.getByRole('region', { name: 'Recorded history · selected time range', exact: true });
      await trend.scrollIntoViewIfNeeded();
      try {
        await trend.getByText(/no data/i).first().waitFor({ timeout: 10000 });
      } catch (error) {
        await page.screenshot({ path: path.join(evidence, 'screenshots/history-context-failure.png'), fullPage: true });
        await writeFile(path.join(evidence, 'history-context-failure-ax.txt'), await page.locator('body').ariaSnapshot());
        throw error;
      }
      const boundary = page.getByRole('region', { name: 'History read boundary / coverage', exact: true });
      await boundary.scrollIntoViewIfNeeded();
      await boundary.getByText('UNBOUND_LOCAL_RUNTIME', { exact: true }).waitFor();
      const matching = historyResponses.find(item => item.url.includes('tag_id=' + native.tag_id) && item.payload?.range_start);
      assert(matching, 'Missing actual history response for native F5 context ' + range);
      const duration = (Date.parse(matching.payload.range_end) - Date.parse(matching.payload.range_start)) / 3600000;
      assert(Math.abs(duration - hours) < 0.02, JSON.stringify({ range, duration }));
      assert.equal(matching.payload.stream, 'RUNTIME');
      assert.equal(matching.payload.observations.length, 0);
      await boundary.screenshot({ path: path.join(evidence, `screenshots/f1-history-${range}.png`) });
      results.history.push({ range, durationHours: duration, nativeF5TagContext: true, state: matching.payload.state, rows: 0 });
    }
    for (const [uid, names] of [
      ['aqua-f4', ['CPU · host / AQUA process', 'Disk I/O', 'NIC counters · all-interface aggregate', 'Existing polling worker']],
      ['aqua-f2', ['Delivery attempts / failure history', 'Notification queue · existing durable outbox']],
    ]) {
      await page.goto(url + '/d/' + uid + '?timezone=utc', { waitUntil: 'domcontentloaded' });
      for (const name of names) {
        const region = page.getByRole('region', { name, exact: true });
        await region.scrollIntoViewIfNeeded();
        if (uid === 'aqua-f4' && name !== 'Existing polling worker') await region.locator('canvas').first().waitFor();
        else if (name === 'Existing polling worker') await region.getByText('STOPPED', { exact: true }).waitFor();
        else await region.getByText(/no data/i).first().waitFor();
        await region.screenshot({ path: path.join(evidence, `screenshots/belowfold-${uid}-${results.renderedPanels.length}.png`) });
        results.renderedPanels.push({ dashboard: uid, panel: name, rendered: true });
      }
    }
  }
  await writeFile(path.join(evidence, 'browser-acceptance.json'), JSON.stringify(results, null, 2));
  assert.equal(results.errors.length, 0);
  assert.equal(results.queryErrors.length, 0);
  assert.equal(results.blocked.length, 0);
  console.log(JSON.stringify({ result: 'PASS', syntheticStates: results.synthetic.length, historyRanges: results.history.length,
    belowFoldPanels: results.renderedPanels.length, pageErrors: results.errors.length, queryErrors: results.queryErrors.length }));
} finally {
  await browser.close();
}
