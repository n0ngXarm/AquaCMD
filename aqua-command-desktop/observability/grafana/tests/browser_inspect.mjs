// Actual local Chrome/Playwright inspection; CUA browser host was unavailable.
import { createRequire } from 'node:module';
import { readFile } from 'node:fs/promises';
import { fileURLToPath } from 'node:url';
import path from 'node:path';

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const require = createRequire(import.meta.url);
const { chromium } = require(path.join(root, 'private/browser/node_modules/playwright'));
const { url } = JSON.parse(await readFile(path.join(root, 'private/state.json'), 'utf8'));
const browser = await chromium.launch({ executablePath: '/usr/bin/google-chrome', headless: true, chromiumSandbox: true,
  args: ['--disable-background-networking', '--disable-component-update', '--no-first-run'] });
try {
  const context = await browser.newContext({ viewport: { width: 1366, height: 768 } });
  await context.route('**/*', route => {
    const target = new URL(route.request().url());
    return target.origin === url || ['data:', 'blob:'].includes(target.protocol) ? route.continue() : route.abort('blockedbyclient');
  });
  const page = await context.newPage();
  await page.goto(url + '/login', { waitUntil: 'domcontentloaded' });
  await page.getByRole('textbox').first().waitFor({ state: 'visible', timeout: 30000 });
  console.log((await page.locator('body').ariaSnapshot()).slice(0, 12000));
} finally {
  await browser.close();
}
