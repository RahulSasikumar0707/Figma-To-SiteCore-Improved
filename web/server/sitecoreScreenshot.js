/**
 * Renders the Sitecore page in headless Chrome and captures a full-page PNG.
 * Reuses the ITEM_SERVICE_* credentials as HTTP Basic auth (CM boxes are
 * usually behind it) and tolerates self-signed certs on internal hosts.
 */
import { getConfig, buildAuthHeader } from '../../src/sitecore/restClient.js';
import { log } from '../../src/utils/log.js';

export async function screenshotSitecorePage(pageUrl, { width = 1440 } = {}) {
  let puppeteer;
  try {
    puppeteer = (await import('puppeteer')).default;
  } catch {
    throw new Error('puppeteer is not installed — run `npm i puppeteer`.');
  }

  let authHeader = null;
  try {
    authHeader = buildAuthHeader(getConfig());
  } catch {
    log.warn('ITEM_SERVICE_* not configured — loading the Sitecore page without auth.');
  }

  let browser;
  try {
    browser = await puppeteer.launch({
      headless: 'new',
      acceptInsecureCerts: true,
      args: ['--ignore-certificate-errors', '--no-sandbox'],
    });
    const page = await browser.newPage();
    if (authHeader) await page.setExtraHTTPHeaders({ Authorization: authHeader });
    await page.setViewport({ width, height: 900, deviceScaleFactor: 1 });
    await page.goto(pageUrl, { waitUntil: 'networkidle2', timeout: 90000 });
    await new Promise((r) => setTimeout(r, 1200)); // fonts/lazy images settle

    // Vision API rejects images >8000px on a side; shrink the capture instead
    // of cropping content (same trick as src/review/visualDiff.js).
    const pageH = await page.evaluate(() => document.documentElement.scrollHeight);
    const effScale = Math.min(1, 7800 / Math.max(width, pageH));
    if (effScale < 1) {
      await page.setViewport({ width, height: 900, deviceScaleFactor: effScale });
      await new Promise((r) => setTimeout(r, 400));
    }

    const png = Buffer.from(await page.screenshot({ fullPage: true, type: 'png' }));
    const title = await page.title().catch(() => '');
    return { png, title, height: pageH };
  } finally {
    await browser?.close().catch(() => {});
  }
}
