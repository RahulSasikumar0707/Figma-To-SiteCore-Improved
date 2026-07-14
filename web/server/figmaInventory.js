/**
 * Figma content inventory — tries the local Figma Dev Mode MCP server first
 * (same as the main converter), then falls back to the REST API.
 *
 * MCP path: Figma desktop app must be open with the file loaded.
 *           Works even when the REST token lacks access to the file.
 * REST path: requires FIGMA_TOKEN with access to the file.
 */
import { FigmaRest } from '../../src/figma/restClient.js';
import { FigmaMcp } from '../../src/figma/mcpClient.js';
import { log } from '../../src/utils/log.js';

const MAX_TEXTS = 400;

function isHidden(node) {
  return node.visible === false;
}

/** Depth-first walk collecting visible TEXT nodes and image/asset markers. */
function walk(node, out, breadcrumb) {
  if (!node || isHidden(node)) return;
  const trail = breadcrumb ? `${breadcrumb} > ${node.name}` : node.name;

  if (node.type === 'TEXT' && node.characters && out.texts.length < MAX_TEXTS) {
    const style = node.style || {};
    out.texts.push({
      id: node.id,
      section: breadcrumb || node.name,
      text: node.characters.replace(/\u2028|\u2029/g, '\n').trim(),
      fontSize: style.fontSize,
      fontWeight: style.fontWeight,
    });
  }

  const hasImageFill = Array.isArray(node.fills) && node.fills.some((f) => f.type === 'IMAGE' && f.visible !== false);
  if (hasImageFill) {
    out.images.push({ id: node.id, name: node.name, section: breadcrumb || '' });
  }

  for (const child of node.children || []) walk(child, out, trail);
}

export async function collectFigmaInventory(figmaToken, fileKey, nodeId, { scale = 1 } = {}) {
  if (!figmaToken) throw new Error('FIGMA_TOKEN is not configured — set it in .env.');

  const mcpUrl = process.env.FIGMA_MCP_URL || 'http://127.0.0.1:3845/mcp';
  const figmaSource = (process.env.FIGMA_SOURCE || 'auto').toLowerCase();

  // ── Try MCP first (same policy as the main converter) ───────────────────
  // MCP works regardless of REST token scope — it reads directly from the
  // Figma desktop app, which must be running with the file open.
  let mcpScreenshot = null;
  let mcpTexts = null;

  if (figmaSource !== 'rest') {
    const mcp = await FigmaMcp.tryConnect(mcpUrl);
    if (mcp) {
      try {
        // Get screenshot from MCP
        mcpScreenshot = await mcp.getScreenshot(nodeId);
        // Get design context (contains all text content)
        const ctx = await mcp.getDesignContext(nodeId);
        if (ctx) mcpTexts = ctx;
        log.ok('Figma data retrieved via MCP (desktop app).');
      } catch (err) {
        log.warn(`MCP data fetch failed (${err.message}); will fall back to REST.`);
      } finally {
        await mcp.close();
      }
    }
  }

  // ── REST API ─────────────────────────────────────────────────────────────
  const rest = new FigmaRest(figmaToken);

  let nodes;
  try {
    nodes = await rest.getNodes(fileKey, nodeId);
  } catch (err) {
    if (/-> 404/.test(err.message)) {
      // If MCP gave us a screenshot we can proceed with limited data.
      if (mcpScreenshot) {
        log.warn(`REST API returned 404 for file ${fileKey} but MCP screenshot is available — continuing with MCP data only.`);
        return {
          name: nodeId,
          width: 1440,
          height: 1024,
          texts: [],
          images: [],
          screenshotPng: mcpScreenshot,
          mcpContextText: mcpTexts || '',
        };
      }
      throw new Error(
        `Figma file ${fileKey} returned 404 from the REST API, and the Figma desktop app ` +
        `MCP server is not reachable at ${mcpUrl}.\n\n` +
        `Fix options:\n` +
        `  1. Open the Figma desktop app, load the file, and enable Dev Mode MCP server ` +
        `(Figma menu → Preferences → Enable Dev Mode MCP server). The tool will use it automatically.\n` +
        `  2. Replace FIGMA_TOKEN in .env with a token from an account that has access to this file.`
      );
    }
    throw err;
  }

  const entry = nodes?.[nodeId];
  if (!entry?.document) throw new Error(`Figma node ${nodeId} not found in file ${fileKey}.`);
  const doc = entry.document;

  const out = { texts: [], images: [] };
  walk(doc, out, '');

  // Screenshot: prefer MCP (higher quality, already rendered), fall back to REST render.
  let png = mcpScreenshot;
  if (!png) {
    const box = doc.absoluteBoundingBox || { width: 1440, height: 1024 };
    const maxSide = Math.max(box.width || 1, box.height || 1);
    const effScale = Math.min(scale, 7800 / maxSide, 2);
    const urls = await rest.renderImages(fileKey, [nodeId], { format: 'png', scale: Math.max(effScale, 0.1) });
    const url = urls?.[nodeId];
    if (!url) throw new Error('Figma refused to render the node (images API returned null).');
    png = await rest.download(url);
  }

  const bbox = doc.absoluteBoundingBox || { width: 1440, height: 1024 };
  return {
    name: doc.name,
    width: Math.round(bbox.width || 0),
    height: Math.round(bbox.height || 0),
    texts: out.texts,
    images: out.images,
    screenshotPng: png,
    mcpContextText: mcpTexts || '',
  };
}

/** Compact text digest of the Figma content for the LLM prompt. */
export function figmaInventoryToPrompt(inv) {
  const lines = [`FRAME: ${inv.name} (${inv.width}x${inv.height})`];
  for (const t of inv.texts) {
    if (!t.text) continue;
    const clipped = t.text.length > 600 ? `${t.text.slice(0, 600)}…` : t.text;
    const meta = [t.fontSize ? `size ${t.fontSize}` : '', t.fontWeight ? `weight ${t.fontWeight}` : ''].filter(Boolean).join(', ');
    lines.push(`TEXT [${t.section}]${meta ? ` (${meta})` : ''}: ${JSON.stringify(clipped)}`);
  }
  if (inv.images.length) {
    lines.push(`IMAGES (${inv.images.length}):`);
    for (const img of inv.images.slice(0, 40)) lines.push(`  - ${img.name}${img.section ? ` [${img.section}]` : ''}`);
  }
  // MCP context (when REST was 404-blocked) carries the full design text.
  if (inv.mcpContextText) {
    lines.push('\nMCP DESIGN CONTEXT (from Figma desktop app):');
    const clipped = inv.mcpContextText.length > 3000 ? `${inv.mcpContextText.slice(0, 3000)}…` : inv.mcpContextText;
    lines.push(clipped);
  }
  return lines.join('\n');
}
