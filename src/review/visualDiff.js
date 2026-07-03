import path from 'node:path';
import { pathToFileURL } from 'node:url';
import { writeFileEnsured } from '../utils/fsx.js';
import { log } from '../utils/log.js';

/**
 * Optional visual verification: renders the generated index.html in headless
 * Chrome (only if puppeteer is installed — `npm i puppeteer` to enable) and
 * computes a pixel mismatch % against the Figma reference render.
 * Everything degrades to null so the pipeline works without it.
 */
export async function renderGeneratedPage(outputDir, { width = 1440, scale = 1 } = {}) {
  let puppeteer;
  try {
    puppeteer = (await import('puppeteer')).default;
  } catch {
    log.warn('puppeteer not installed — skipping browser render + pixel diff (npm i puppeteer to enable).');
    return null;
  }
  let browser;
  try {
    browser = await puppeteer.launch({ headless: 'new' });
    const page = await browser.newPage();
    // deviceScaleFactor mirrors the scale the Figma reference PNG was rendered
    // at, so the pixel diff compares bitmaps in the same coordinate space.
    await page.setViewport({ width: Math.round(width), height: 900, deviceScaleFactor: scale });
    await page.goto(pathToFileURL(path.join(outputDir, 'index.html')).href, { waitUntil: 'networkidle0', timeout: 60000 });
    await new Promise((r) => setTimeout(r, 800)); // fonts settle
    // The vision API rejects images over 8000px on a side; the Figma-derived
    // scale doesn't know the page's actual rendered height, so clamp against it.
    const pageH = await page.evaluate(() => document.documentElement.scrollHeight);
    const effScale = Math.min(scale, 7800 / Math.max(Math.round(width), pageH));
    if (effScale < scale) {
      log.warn(`Rendered page is ${pageH}px tall — reducing capture scale ${scale.toFixed(2)} → ${effScale.toFixed(2)} to stay inside vision API limits.`);
      await page.setViewport({ width: Math.round(width), height: 900, deviceScaleFactor: effScale });
      await new Promise((r) => setTimeout(r, 300));
    }
    const png = Buffer.from(await page.screenshot({ fullPage: true, type: 'png' }));
    const jpg = Buffer.from(await page.screenshot({ fullPage: true, type: 'jpeg', quality: 70 }));
    writeFileEnsured(path.join(outputDir, 'reference', 'generated-render.png'), png);
    return { png, jpg };
  } catch (err) {
    log.warn(`Browser render failed: ${err.message}`);
    return null;
  } finally {
    await browser?.close().catch(() => {});
  }
}

/**
 * Deterministic responsiveness gate: loads the generated page at each given
 * viewport width and flags horizontal overflow — the most common responsive
 * failure, and one that doesn't need an LLM's visual judgment to catch.
 * Returns issues in the same shape reviewer.js uses, so index.js can merge
 * them straight into the fix list the generator receives.
 */
export async function checkResponsiveness(outputDir, widths = [390, 768]) {
  let puppeteer;
  try {
    puppeteer = (await import('puppeteer')).default;
  } catch {
    return [];
  }
  const issues = [];
  for (const width of widths) {
    let browser;
    try {
      browser = await puppeteer.launch({ headless: 'new' });
      const page = await browser.newPage();
      await page.setViewport({ width, height: 900 });
      await page.goto(pathToFileURL(path.join(outputDir, 'index.html')).href, { waitUntil: 'networkidle0', timeout: 60000 });
      await new Promise((r) => setTimeout(r, 500)); // fonts settle
      const result = await page.evaluate(() => {
        const viewportWidth = window.innerWidth;
        const docWidth = document.documentElement.scrollWidth;
        const overflowPx = docWidth - viewportWidth;
        const offenders = [];
        if (overflowPx > 1) {
          for (const el of document.body.querySelectorAll('*')) {
            const rect = el.getBoundingClientRect();
            if (rect.width > 0 && rect.right > viewportWidth + 1) {
              const label = el.id
                ? `#${el.id}`
                : typeof el.className === 'string' && el.className.trim()
                  ? `.${el.className.trim().split(/\s+/)[0]}`
                  : el.tagName.toLowerCase();
              offenders.push({ label, overflowBy: Math.round(rect.right - viewportWidth) });
            }
          }
          offenders.sort((a, b) => b.overflowBy - a.overflowBy);
        }
        return { docWidth, viewportWidth, overflowPx, offenders: offenders.slice(0, 5) };
      });
      if (result.overflowPx > 1) {
        const top = result.offenders.map((o) => `${o.label} (+${o.overflowBy}px)`).join(', ');
        issues.push({
          severity: 'critical',
          area: `Responsiveness @ ${width}px`,
          description: `Horizontal overflow of ${Math.round(result.overflowPx)}px at ${width}px viewport (scrollWidth ${result.docWidth}px vs viewport ${result.viewportWidth}px). Worst offenders: ${top || 'unknown — likely a deeply nested or overflow:hidden ancestor'}.`,
          fix: `At ${width}px, remove/relax the fixed px width causing this element to exceed the viewport — use max-width: 100%, fluid/percentage widths, or a media query that stacks the layout into a single column below ${width + 1}px.`,
        });
      }
    } catch (err) {
      log.warn(`Responsiveness check at ${width}px failed: ${err.message}`);
    } finally {
      await browser?.close().catch(() => {});
    }
  }
  return issues;
}

export async function pixelMismatch(figmaPng, renderPng, outputDir = null) {
  try {
    const { PNG } = await import('pngjs');
    const pixelmatch = (await import('pixelmatch')).default;
    const a = PNG.sync.read(figmaPng);
    const b = PNG.sync.read(renderPng);
    const width = Math.min(a.width, b.width);
    const height = Math.min(a.height, b.height);
    const crop = (img) => {
      const out = new PNG({ width, height });
      PNG.bitblt(img, out, 0, 0, width, height, 0, 0);
      return out;
    };
    const diff = new PNG({ width, height });
    const mismatched = pixelmatch(crop(a).data, crop(b).data, diff.data, width, height, { threshold: 0.12 });
    const pct = (mismatched / (width * height)) * 100;
    // penalize large height differences (missing/extra content)
    const heightSkew = Math.abs(a.height - b.height) / Math.max(a.height, b.height);

    // The heatmap (red = mismatched pixels) localizes errors for the agents.
    let diffPng = null;
    if (outputDir) {
      diffPng = PNG.sync.write(diff);
      writeFileEnsured(path.join(outputDir, 'reference', 'pixel-diff.png'), diffPng);
    }
    return { pct: pct + heightSkew * 10, diffPng };
  } catch (err) {
    log.warn(`Pixel diff failed: ${err.message}`);
    return null;
  }
}
