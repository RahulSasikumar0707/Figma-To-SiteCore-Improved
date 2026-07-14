/**
 * Figma ↔ Sitecore comparison API + static host for the React UI.
 *
 *   npm run ui          → API on http://localhost:3900 (serves web/client/dist)
 *   npm run ui:dev      → run this + `npm run ui:client` (Vite dev proxy)
 *
 * Endpoints:
 *   POST /api/compare                 { figmaUrl, sitecoreUrl } → { sessionId }
 *   GET  /api/compare/:id             → { phase, progress[], result?, error? }
 *   GET  /api/compare/:id/image/:which  which = figma | sitecore  → image/png
 *   POST /api/compare/:id/patch       { diffIds: [], dryRun? } → { results[] }
 *   POST /api/compare/:id/publish     → publish the page item to web
 */
import express from 'express';
import path from 'node:path';
import crypto from 'node:crypto';
import { fileURLToPath } from 'node:url';
import dotenv from 'dotenv';

import { parseFigmaUrl, parseSitecoreUrl } from './urlParse.js';
import { collectFigmaInventory, figmaInventoryToPrompt } from './figmaInventory.js';
import { collectSitecoreInventory, inventoryToPrompt } from './sitecoreInventory.js';
import { screenshotSitecorePage } from './sitecoreScreenshot.js';
import { compareDesigns } from './comparer.js';
import { applyPatches } from './patcher.js';
import { callSitecore } from '../../src/sitecore/restClient.js';
import { log } from '../../src/utils/log.js';

dotenv.config({ override: true });

// Internal CM hosts routinely use self-signed certs; the REST client uses
// global fetch which has no per-call TLS toggle, so honor an env opt-out.
if (['1', 'true', 'yes'].includes(String(process.env.SITECORE_INSECURE_TLS || '').toLowerCase())) {
  process.env.NODE_TLS_REJECT_UNAUTHORIZED = '0';
}

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const PORT = Number(process.env.UI_PORT) || 3900;

const app = express();
app.use(express.json({ limit: '2mb' }));

/** In-memory session store: sessionId → job state. */
const sessions = new Map();

function newSession(input) {
  const id = crypto.randomUUID();
  const session = {
    id,
    input,
    phase: 'queued',
    progress: [],
    result: null,
    error: null,
    figma: null,       // { inventory, prompt, screenshotPng }
    sitecore: null,    // { inventory, prompt, screenshotPng, itemPath, pageUrl }
    createdAt: Date.now(),
  };
  sessions.set(id, session);
  // Keep memory bounded.
  if (sessions.size > 20) {
    const oldest = [...sessions.values()].sort((a, b) => a.createdAt - b.createdAt)[0];
    sessions.delete(oldest.id);
  }
  return session;
}

function push(session, phase, message) {
  session.phase = phase;
  session.progress.push({ at: new Date().toISOString(), phase, message });
  log.info(`[${session.id.slice(0, 8)}] ${message}`);
}

function llmConfig() {
  const apiKey = process.env.ANTHROPIC_API_KEY_1 || process.env.ANTHROPIC_API_KEY || '';
  if (!apiKey) throw new Error('ANTHROPIC_API_KEY_1 is not configured in .env.');
  return { apiKey, model: process.env.ANTHROPIC_MODEL || 'claude-fable-5' };
}

async function runCompare(session) {
  const { figmaUrl, sitecoreUrl } = session.input;
  try {
    const llm = llmConfig();
    const figmaRef = parseFigmaUrl(figmaUrl);
    const scRef = parseSitecoreUrl(sitecoreUrl);

    push(session, 'figma', `Fetching Figma ${figmaRef.fileKey} node ${figmaRef.nodeId}…`);
    const figmaInv = await collectFigmaInventory(process.env.FIGMA_TOKEN, figmaRef.fileKey, figmaRef.nodeId);
    session.figma = {
      inventory: figmaInv,
      prompt: figmaInventoryToPrompt(figmaInv),
      screenshotPng: figmaInv.screenshotPng,
    };
    push(session, 'sitecore', `Reading Sitecore content tree at ${scRef.itemPath}…`);

    const [inventory, shot] = await Promise.all([
      collectSitecoreInventory(scRef.itemPath),
      screenshotSitecorePage(scRef.pageUrl).catch((err) => {
        push(session, 'sitecore', `Page screenshot failed (${err.message}) — comparing content inventories only.`);
        return null;
      }),
    ]);

    session.sitecore = {
      inventory,
      prompt: inventoryToPrompt(inventory),
      screenshotPng: shot?.png || null,
      itemPath: scRef.itemPath,
      pageUrl: scRef.pageUrl,
      rootId: inventory.root.id,
    };

    if (!session.sitecore.screenshotPng) {
      // The comparer requires two images; fall back to a 1px placeholder so the
      // vision block is well-formed while the text inventory drives the diff.
      session.sitecore.screenshotPng = Buffer.from(
        '89504e470d0a1a0a0000000d4948445200000001000000010806000000' +
        '1f15c4890000000d49444154789c626001000000ffff03000006000557' +
        'bfabd40000000049454e44ae426082',
        'hex'
      );
    }

    push(session, 'llm', 'Asking Claude to compare design vs page…');
    const verdict = await compareDesigns({
      apiKey: llm.apiKey,
      model: llm.model,
      figma: { screenshotPng: session.figma.screenshotPng, prompt: session.figma.prompt },
      sitecore: { screenshotPng: session.sitecore.screenshotPng, prompt: session.sitecore.prompt },
    });

    session.result = {
      matchScore: verdict.matchScore,
      summary: verdict.summary,
      differences: verdict.differences,
      model: verdict.model,
      figma: { name: figmaInv.name, width: figmaInv.width, height: figmaInv.height, fileKey: figmaRef.fileKey, nodeId: figmaRef.nodeId },
      sitecore: { itemPath: scRef.itemPath, pageUrl: scRef.pageUrl, items: inventory.items.length, rootId: inventory.root.id },
    };
    push(session, 'done', `Comparison finished — ${verdict.differences.length} difference(s), score ${verdict.matchScore}.`);
  } catch (err) {
    session.error = err.message;
    push(session, 'error', `Failed: ${err.message}`);
    log.error(err.stack || err.message);
  }
}

// ── API ───────────────────────────────────────────────────────────────────────

app.post('/api/compare', (req, res) => {
  const { figmaUrl, sitecoreUrl } = req.body || {};
  try {
    // Validate up front so the user gets an immediate 400 for bad URLs.
    parseFigmaUrl(figmaUrl);
    parseSitecoreUrl(sitecoreUrl);
  } catch (err) {
    return res.status(400).json({ error: err.message });
  }
  const session = newSession({ figmaUrl, sitecoreUrl });
  push(session, 'queued', 'Comparison queued.');
  runCompare(session); // fire and forget — client polls
  res.json({ sessionId: session.id });
});

app.get('/api/compare/:id', (req, res) => {
  const session = sessions.get(req.params.id);
  if (!session) return res.status(404).json({ error: 'Unknown session.' });
  res.json({
    phase: session.phase,
    progress: session.progress,
    result: session.result,
    error: session.error,
  });
});

app.get('/api/compare/:id/image/:which', (req, res) => {
  const session = sessions.get(req.params.id);
  if (!session) return res.status(404).end();
  const png = req.params.which === 'figma' ? session.figma?.screenshotPng : session.sitecore?.screenshotPng;
  if (!png) return res.status(404).end();
  res.set('Content-Type', 'image/png').send(png);
});

app.post('/api/compare/:id/patch', async (req, res) => {
  const session = sessions.get(req.params.id);
  if (!session?.result) return res.status(404).json({ error: 'Run a comparison first.' });

  const { diffIds, dryRun } = req.body || {};
  if (!Array.isArray(diffIds) || !diffIds.length) {
    return res.status(400).json({ error: 'diffIds must be a non-empty array.' });
  }
  const chosen = session.result.differences.filter((d) => diffIds.includes(d.id));
  if (!chosen.length) return res.status(400).json({ error: 'No matching differences for those ids.' });

  try {
    const results = await applyPatches(chosen, llmConfig(), { dryRun: Boolean(dryRun) });
    const patched = results.filter((r) => r.ok && !r.dryRun).length;
    if (patched) push(session, 'patched', `Patched ${patched} field(s) in Sitecore.`);
    res.json({ results });
  } catch (err) {
    log.error(err.stack || err.message);
    res.status(500).json({ error: err.message });
  }
});

app.post('/api/compare/:id/publish', async (req, res) => {
  const session = sessions.get(req.params.id);
  if (!session?.result) return res.status(404).json({ error: 'Run a comparison first.' });
  try {
    const raw = await callSitecore({
      method: 'POST',
      path: '/sitecore/api/ssc/publish',
      body: {
        ItemID: session.result.sitecore.rootId,
        Mode: 'SingleItem',
        Subitems: true,
        Targets: ['web'],
        Languages: ['en'],
      },
    });
    const parsed = JSON.parse(raw);
    if (!parsed.ok) return res.status(502).json({ error: `Publish returned HTTP ${parsed.status}`, detail: parsed.data });
    push(session, 'published', 'Publish job triggered.');
    res.json({ ok: true, data: parsed.data });
  } catch (err) {
    res.status(500).json({ error: err.message });
  }
});

// ── Static React build ────────────────────────────────────────────────────────

const dist = path.resolve(__dirname, '../client/dist');
app.use(express.static(dist));
app.get(/^\/(?!api\/).*/, (_req, res) => {
  res.sendFile(path.join(dist, 'index.html'), (err) => {
    if (err) res.status(200).send('<h3>UI not built yet — run <code>npm run ui:build</code> (or use <code>npm run ui:dev</code>).</h3>');
  });
});

app.listen(PORT, () => {
  log.ok(`Figma ↔ Sitecore comparison UI on http://localhost:${PORT}`);
});
