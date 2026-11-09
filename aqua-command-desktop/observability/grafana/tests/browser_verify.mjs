// Real rendered Grafana UI with a Lab Viewer, no screenshots are synthesized.
import assert from 'node:assert/strict';
import { createRequire } from 'node:module';
import { chmod, mkdir, readFile, writeFile } from 'node:fs/promises';
import { fileURLToPath } from 'node:url';
import path from 'node:path';

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const evidence = path.resolve(root, '../../../../evidence');
const require = createRequire(import.meta.url);
const { chromium } = require(path.join(root, 'private/browser/node_modules/playwright'));
const { url } = JSON.parse(await readFile(path.join(root, 'private/state.json'), 'utf8'));
const output = path.join(evidence, 'screenshots');
await mkdir(output, { recursive: true });
const browser = await chromium.launch({ executablePath: '/usr/bin/google-chrome', headless: true, chromiumSandbox: true,
  args: ['--disable-background-networking', '--disable-component-update', '--no-first-run'] });
const results = [], blocked = [], errors = [], queryErrors = [];
const dashboards = [
  ['aqua-f3', 'F3 · OPC UA sources → local pipeline'],
  ['aqua-f4', 'CPU'],
  ['aqua-f1', 'Live values · GOOD values / explicit digital or analog type'],
  ['aqua-f2', 'Task events over time · one point per persisted event'],
  ['aqua-diagnostics', 'OPC UA / certificate evidence'],
];
try {
  const context = await browser.newContext({ viewport: { width: 1366, height: 768 }, timezoneId: 'UTC' });
  await context.route('**/*', route => {
    const target = new URL(route.request().url());
    if (target.origin === url || ['data:', 'blob:'].includes(target.protocol)) return route.continue();
    blocked.push(target.origin);
    return route.abort('blockedbyclient');
  });
  const page = await context.newPage();
  page.on('pageerror', error => errors.push(error.message));
  page.on('response', async response => {
    if (new URL(response.url()).pathname !== '/api/ds/query') return;
    try {
      const value = await response.json();
      if (response.status() !== 200 || Object.values(value.results || {}).some(result => result.error))
        queryErrors.push({ status: response.status(), error: Object.values(value.results || {}).map(result => result.error).filter(Boolean) });
    } catch { queryErrors.push({ status: response.status(), error: 'Unparseable query response' }); }
  });
  await page.goto(url + '/login', { waitUntil: 'domcontentloaded' });
  await page.getByRole('textbox', { name: 'Email or username' }).fill('aqua-viewer');
  await page.getByRole('textbox', { name: 'Password', exact: true }).fill((await readFile(path.join(root, 'private/viewer-password'), 'utf8')).trim());
  await page.getByRole('button', { name: 'Log in', exact: true }).click();
  await page.waitForURL(current => !current.pathname.startsWith('/login'));
  await context.storageState({ path: path.join(root, 'private/browser-auth.json') });
  await chmod(path.join(root, 'private/browser-auth.json'), 0o600);
  for (const [width, height] of [[1366, 768], [1600, 900], [1920, 1080]]) {
    await page.setViewportSize({ width, height });
    for (const [uid, primaryTitle] of dashboards) {
    await page.goto(url + '/d/' + uid + '?timezone=utc', { waitUntil: 'domcontentloaded' });
    const primary = page.getByRole('region', { name: primaryTitle, exact: true });
    await primary.scrollIntoViewIfNeeded();
    try {
      if (uid === 'aqua-f3') await page.getByText('AQUA Collector', { exact: true }).first().waitFor({ state: 'visible', timeout: 30000 });
      if (uid === 'aqua-f4') await primary.getByText(/\d+(?:\.\d+)?%/).first().waitFor({ state: 'visible', timeout: 30000 });
      if (uid === 'aqua-f1' || uid === 'aqua-f2') await primary.getByText(/no data/i).first().waitFor({ state: 'visible', timeout: 30000 });
      if (uid === 'aqua-diagnostics') await primary.getByText('CONFIGURED', { exact: true }).first().waitFor({ state: 'visible', timeout: 30000 });
    } catch (error) {
      await page.screenshot({ path: path.join(output, `${uid}-failure-${width}.png`), fullPage: true });
      await writeFile(path.join(evidence, 'browser-failure-ax.txt'), await page.locator('body').ariaSnapshot());
      throw error;
    }
    const layout = await page.evaluate(() => ({ width: innerWidth, height: innerHeight,
      scrollWidth: document.documentElement.scrollWidth, title: document.title }));
    assert(layout.scrollWidth <= width, JSON.stringify(layout));
    assert.equal(await page.getByRole('button', { name: 'Edit', exact: true }).count(), 0);
    await primary.screenshot({ path: path.join(output, `${uid}-primary-${width}.png`) });
    await primary.evaluate(element => {
      for (let parent = element.parentElement; parent; parent = parent.parentElement) {
        if (parent.scrollTop) parent.scrollTo(0, 0);
      }
      window.scrollTo(0, 0);
    });
    await page.screenshot({ path: path.join(output, `grafana-${uid.slice(5)}-${width}.png`), fullPage: true });
    await writeFile(path.join(evidence, `${uid}-${width}-ax.txt`), await page.locator('body').ariaSnapshot());
    results.push({ dashboard: uid, viewport: [width, height], layout,
      primary: uid === 'aqua-f4' ? 'ACTUAL_CPU_VALUE_VISIBLE' : uid === 'aqua-f1' || uid === 'aqua-f2' ? 'NO_DATA_VISIBLE' : 'ACTUAL_STATE_VISIBLE', viewerEditButton: false });
    }
  }
  await page.goto(url + '/d/aqua-f3?timezone=utc', { waitUntil: 'domcontentloaded' });
  await page.getByTestId('node-click-rect-collector').click();
  await page.getByText('OBSERVED_LOCAL', { exact: true }).first().waitFor({ state: 'visible' });
  await page.screenshot({ path: path.join(output, 'grafana-f3-inspector.png') });
  await writeFile(path.join(evidence, 'f3-inspector-ax.txt'), await page.locator('body').ariaSnapshot());
  await writeFile(path.join(evidence, 'browser-results.json'), JSON.stringify({ results, blocked, errors, queryErrors }, null, 2));
  assert.equal(errors.length, 0, JSON.stringify(errors));
  assert.equal(queryErrors.length, 0, JSON.stringify(queryErrors));
  assert.equal(blocked.length, 0, JSON.stringify(blocked));
  console.log(JSON.stringify({ result: 'PASS', dashboardViewports: results.length, blockedExternalRequests: blocked.length, pageErrors: errors.length, queryErrors: queryErrors.length }));
} finally {
  await browser.close();
}
