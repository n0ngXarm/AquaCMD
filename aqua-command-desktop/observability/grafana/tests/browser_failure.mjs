// Observe actual source-down/recovery UI; lifecycle actions stay outside this script.
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
const mode = process.argv[2];
assert(['down', 'up'].includes(mode));
const browser = await chromium.launch({ executablePath: '/usr/bin/google-chrome', headless: true, chromiumSandbox: true,
  args: ['--disable-background-networking', '--disable-component-update', '--no-first-run'] });
const responses = [], blocked = [];
try {
  const context = await browser.newContext({ viewport: { width: 1366, height: 768 }, timezoneId: 'UTC' });
  await context.route('**/*', route => {
    const target = new URL(route.request().url());
    if (target.origin === url || ['data:', 'blob:'].includes(target.protocol)) return route.continue();
    blocked.push(target.origin);
    return route.abort('blockedbyclient');
  });
  const page = await context.newPage();
  await page.goto(url + '/login', { waitUntil: 'domcontentloaded' });
  await page.getByRole('textbox', { name: 'Email or username' }).fill('aqua-viewer');
  await page.getByRole('textbox', { name: 'Password', exact: true }).fill((await readFile(path.join(root, 'private/viewer-password'), 'utf8')).trim());
  await page.getByRole('button', { name: 'Log in', exact: true }).click();
  await page.waitForURL(current => !current.pathname.startsWith('/login'));
  page.on('response', async response => {
    if (new URL(response.url()).pathname !== '/api/ds/query') return;
    const body = await response.json();
    responses.push({ status: response.status(), errors: Object.values(body.results || {}).filter(r => r.error).length });
  });
  const query = page.waitForResponse(response => new URL(response.url()).pathname === '/api/ds/query');
  await page.goto(url + '/d/aqua-f3?timezone=utc', { waitUntil: 'domcontentloaded' });
  await query;
  const primary = page.getByRole('region', { name: 'F3 · OPC UA sources → local pipeline', exact: true });
  await primary.scrollIntoViewIfNeeded();
  if (mode === 'up') await primary.getByText('AQUA Collector', { exact: true }).waitFor();
  if (mode === 'down') {
    await primary.getByText('No data', { exact: true }).waitFor();
    await primary.getByRole('button', { name: 'Panel status', exact: true }).waitFor();
  }
  const snapshot = await primary.ariaSnapshot();
  await writeFile(path.join(evidence, `source-${mode}-ax.txt`), snapshot);
  await primary.screenshot({ path: path.join(evidence, `screenshots/source-${mode}.png`) });
  const result = { mode, responses, blocked, snapshot };
  if (mode === 'down') {
    assert(responses.some(r => r.status >= 400 && r.errors > 0), JSON.stringify(responses));
    assert.equal(await primary.getByText('AQUA Collector', { exact: true }).count(), 0);
  } else {
    assert(responses.length > 0 && responses.every(r => r.status === 200 && r.errors === 0), JSON.stringify(responses));
  }
  assert.equal(blocked.length, 0);
  await writeFile(path.join(evidence, `browser-source-${mode}.json`), JSON.stringify(result, null, 2));
  console.log(JSON.stringify(result));
} finally {
  await browser.close();
}
