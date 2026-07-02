import fs from 'node:fs';
import path from 'node:path';
import { readJsonIfExists } from '../utils/fsx.js';
import { log } from '../utils/log.js';

/**
 * Loads the EDS component manifest.
 * Preferred source: eds-manifest.json (deep, pre-analyzed metadata for all 37
 * components). Fallback: a programmatic scan of the eds-components folder that
 * extracts eds-* classes, documented modifiers and a trimmed snippet per
 * component, so the converter still works without the curated file.
 */
export function loadEdsManifest({ edsManifestPath, edsComponentsDir }) {
  let curated = null;
  try {
    curated = readJsonIfExists(edsManifestPath);
  } catch (err) {
    log.warn(`eds-manifest.json exists at ${edsManifestPath} but could not be parsed (${err.message}) — falling back to a programmatic scan.`);
  }
  if (curated?.components?.length) {
    // Normalize entries at the boundary so downstream code can trust name/folder.
    const components = curated.components
      .filter((c) => c && typeof c === 'object' && (typeof c.name === 'string' || typeof c.folder === 'string'))
      .map((c) => ({ ...c, name: c.name ?? c.folder, folder: c.folder ?? c.name }));
    const dropped = curated.components.length - components.length;
    if (dropped) log.warn(`Dropped ${dropped} malformed entr${dropped === 1 ? 'y' : 'ies'} from eds-manifest.json.`);
    if (components.length) {
      log.ok(`Loaded curated EDS manifest (${components.length} components) from ${path.basename(edsManifestPath)}`);
      return components;
    }
  }
  log.warn('Curated eds-manifest.json not usable — building manifest by scanning the eds-components folder.');
  return scanEdsComponents(edsComponentsDir);
}

export function scanEdsComponents(dir) {
  const components = [];
  for (const entry of fs.readdirSync(dir, { withFileTypes: true })) {
    if (!entry.isDirectory()) continue;
    const folder = path.join(dir, entry.name);
    const htmlFiles = fs.readdirSync(folder).filter((f) => f.endsWith('.html'));
    if (!htmlFiles.length) continue;

    const edsClasses = new Set();
    const bootstrapFeatures = new Set();
    let snippet = '';

    for (const file of htmlFiles) {
      const html = fs.readFileSync(path.join(folder, file), 'utf8');
      for (const m of html.matchAll(/\beds-[a-z0-9-]+\b/g)) {
        if (!m[0].startsWith('eds-btn') || m[0] === 'eds-btn') edsClasses.add(m[0]);
      }
      for (const m of html.matchAll(/data-bs-(toggle|ride|target)="([a-z-]+)"?/g)) {
        bootstrapFeatures.add(m[2] || m[1]);
      }
      if (!snippet) snippet = extractSnippet(html);
    }
    edsClasses.delete('eds-wrapper');
    edsClasses.delete('eds-header');
    edsClasses.delete('eds-main');
    edsClasses.delete('eds-footer');

    components.push({
      name: entry.name,
      folder: entry.name,
      edsClasses: [...edsClasses],
      bootstrapFeatures: [...bootstrapFeatures],
      description: `EDS ${entry.name.replace(/-/g, ' ')} component`,
      whenToUse: '',
      keywords: entry.name.split('-'),
      structureOutline: '',
      snippet: snippet.slice(0, 4000),
    });
  }
  log.info(`Scanned ${components.length} EDS component folders.`);
  return components;
}

/** Pulls the first real component block (class="component eds-...") out of a demo page. */
function extractSnippet(html) {
  const idx = html.search(/<\w+[^>]*class="[^"]*\bcomponent eds-[a-z0-9-]+/);
  if (idx === -1) return '';
  // crude but effective: take a few hundred lines after the component root
  return html
    .slice(idx, idx + 6000)
    .split('\n')
    .slice(0, 90)
    .join('\n');
}

/** Compact one-line-per-component catalog for LLM prompts. */
export function manifestCatalog(components) {
  return components
    .map((c) => {
      const cls = (c.edsClasses || []).slice(0, 4).join(' ');
      const kw = (c.keywords || []).slice(0, 10).join(', ');
      return `- ${c.name} [${cls}] — ${c.description || ''} ${c.whenToUse ? `Use when: ${c.whenToUse}` : ''} (keywords: ${kw})`;
    })
    .join('\n');
}
