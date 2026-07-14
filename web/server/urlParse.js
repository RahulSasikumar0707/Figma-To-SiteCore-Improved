/**
 * URL parsers for the comparison UI.
 *
 * - Figma URLs:   https://www.figma.com/design/<fileKey>/<name>?node-id=68569-2790
 *                 (also /file/ and /proto/ forms, and a "fileKey:nodeId" shorthand)
 * - Sitecore URLs: any URL whose path contains /sitecore/content/... — the item
 *                 path is extracted verbatim, the rest of the URL is kept as the
 *                 page URL to screenshot.
 */
import { normalizeNodeId } from '../../src/config.js';

export function parseFigmaUrl(input) {
  const raw = String(input || '').trim();
  if (!raw) throw new Error('Figma URL is required.');

  // Shorthand: "<fileKey>:<nodeId>" or "<fileKey> <nodeId>"
  const short = raw.match(/^([A-Za-z0-9]{10,})[\s:]+(\d+[-:]\d+)$/);
  if (short) return { fileKey: short[1], nodeId: normalizeNodeId(short[2]) };

  let url;
  try {
    url = new URL(raw);
  } catch {
    throw new Error(`Not a valid Figma URL: "${raw}"`);
  }
  if (!/figma\.com$/i.test(url.hostname.replace(/^www\./i, ''))) {
    throw new Error(`Not a figma.com URL: "${url.hostname}"`);
  }
  const m = url.pathname.match(/\/(?:file|design|proto|board)\/([A-Za-z0-9]+)/);
  if (!m) throw new Error('Could not find a file key in the Figma URL (expected /design/<key>/… or /file/<key>/…).');
  const fileKey = m[1];

  const nodeParam = url.searchParams.get('node-id') || url.searchParams.get('node_id') || '';
  const nodeId = normalizeNodeId(nodeParam);
  if (!nodeId) {
    throw new Error('The Figma URL has no node-id query parameter. Select the frame in Figma and use "Copy link to selection".');
  }
  return { fileKey, nodeId };
}

export function parseSitecoreUrl(input) {
  const raw = String(input || '').trim();
  if (!raw) throw new Error('Sitecore URL is required.');

  let url;
  try {
    url = new URL(raw);
  } catch {
    throw new Error(`Not a valid Sitecore URL: "${raw}"`);
  }

  // Collapse duplicate slashes (the CM host often produces "//sitecore/content/…").
  const cleanPath = decodeURIComponent(url.pathname).replace(/\/{2,}/g, '/').replace(/\/+$/, '');
  const idx = cleanPath.toLowerCase().indexOf('/sitecore/content/');
  if (idx === -1) {
    throw new Error(
      'Could not find "/sitecore/content/…" in the URL. Provide the content-path form, e.g. ' +
      'https://<cm-host>/sitecore/content/<Site>/Home/<Page>'
    );
  }
  const itemPath = cleanPath.slice(idx).replace(/\.aspx$/i, '');
  const pageUrl = `${url.origin}${cleanPath}${url.search || ''}`;
  return { origin: url.origin, itemPath, pageUrl };
}
