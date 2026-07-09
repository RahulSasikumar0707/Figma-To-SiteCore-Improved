import path from 'node:path';
import { readJsonIfExists } from '../utils/fsx.js';
import { log } from '../utils/log.js';
import { scanStorybookComponents } from './storybook.js';

/**
 * Loads the EDS component manifest.
 * Preferred source: eds-manifest.json (deep, pre-analyzed metadata for all 37
 * components). Fallback: a live scan of the EDS redesign Storybook that
 * extracts eds-* classes and a trimmed snippet per component, so the converter
 * still works without the curated file.
 */
export async function loadEdsManifest({ edsManifestPath }) {
  let curated = null;
  try {
    curated = readJsonIfExists(edsManifestPath);
  } catch (err) {
    log.warn(`eds-manifest.json exists at ${edsManifestPath} but could not be parsed (${err.message}) — falling back to a Storybook scan.`);
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
  log.warn('Curated eds-manifest.json not usable — building manifest from the EDS Storybook.');
  return scanStorybookComponents();
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
