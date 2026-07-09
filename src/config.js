import dotenv from 'dotenv';
import path from 'node:path';

// override:true makes the project's .env the source of truth — otherwise a
// stale FIGMA_NODE_ID exported in the shell (or set as a Windows user env
// var) silently wins and the converter keeps extracting the previous design.
dotenv.config({ override: true });

const cwd = process.cwd();

function bool(v, dflt = false) {
  if (v === undefined || v === '') return dflt;
  return ['1', 'true', 'yes', 'on'].includes(String(v).toLowerCase());
}

function num(v, dflt) {
  // Number('') === 0, so an empty env line must fall back to the default.
  if (v === undefined || String(v).trim() === '') return dflt;
  const n = Number(v);
  return Number.isFinite(n) ? n : dflt;
}

/** Figma node ids appear as "68569:2790" in the API and "68569-2790" in URLs. */
export function normalizeNodeId(id) {
  return String(id || '').trim().replace(/-/g, ':');
}

export function loadConfig(argv = []) {
  const args = parseArgs(argv);

  const cfg = {
    // --- Anthropic (two keys: generator + reviewer) ---
    anthropicKeyGenerator: process.env.ANTHROPIC_API_KEY_1 || process.env.ANTHROPIC_API_KEY || '',
    anthropicKeyReviewer: process.env.ANTHROPIC_API_KEY_2 || process.env.ANTHROPIC_API_KEY_1 || process.env.ANTHROPIC_API_KEY || '',
    model: process.env.ANTHROPIC_MODEL || 'claude-fable-5',
    maxOutputTokens: num(process.env.LLM_MAX_TOKENS, 32000),

    // --- Figma sources ---
    figmaToken: process.env.FIGMA_TOKEN || '',
    fileKey: args.file || process.env.FIGMA_FILE_KEY || '',
    nodeId: normalizeNodeId(args.node || process.env.FIGMA_NODE_ID || ''),
    mcpUrl: process.env.FIGMA_MCP_URL || 'http://127.0.0.1:3845/mcp',
    // auto = try MCP first, fall back to REST; or force "mcp" / "rest"
    figmaSource: (args.source || process.env.FIGMA_SOURCE || 'auto').toLowerCase(),

    // --- EDS / Bootstrap ---
    edsManifestPath: path.resolve(cwd, process.env.EDS_MANIFEST_PATH || 'eds-manifest.json'),
    edsStorybookBase: process.env.EDS_STORYBOOK_BASE || 'https://affinitycmpd103.gilead.com',
    edsNativeCssPath: process.env.EDS_NATIVE_CSS_PATH || '',
    bootstrapCssUrl: process.env.BOOTSTRAP_CSS_URL || 'https://cdn.jsdelivr.net/npm/bootstrap@5.1.3/dist/css/bootstrap.min.css',
    bootstrapJsUrl: process.env.BOOTSTRAP_JS_URL || 'https://cdn.jsdelivr.net/npm/bootstrap@5.1.3/dist/js/bootstrap.bundle.min.js',

    // --- Review loop ---
    // The loop accepts only when the reviewer reports <= targetIssues issues
    // (default 0 — iterate until the issue list is empty or the cap is hit).
    matchThreshold: num(process.env.MATCH_THRESHOLD, 95),
    targetIssues: num(process.env.REVIEW_TARGET_ISSUES, 0),
    maxReviewIterations: num(process.env.MAX_REVIEW_ITERATIONS, 8),
    visualDiff: bool(process.env.VISUAL_DIFF, true),

    // --- Output ---
    outputPrefix: process.env.OUTPUT_PREFIX || 'Output',
    outputRoot: path.resolve(cwd, process.env.OUTPUT_ROOT || '.'),

    // --- CLI flags ---
    manifestOnly: !!args['manifest-only'],
    skipReview: !!args['skip-review'],
    cwd,
  };

  return cfg;
}

export function validateConfig(cfg) {
  const errors = [];
  if (!cfg.manifestOnly) {
    if (!cfg.anthropicKeyGenerator) errors.push('ANTHROPIC_API_KEY_1 is required (generator agent).');
    if (!cfg.fileKey) errors.push('FIGMA_FILE_KEY is required (or pass --file <key>).');
    if (!cfg.nodeId) errors.push('FIGMA_NODE_ID is required (or pass --node <id>).');
    if (cfg.figmaSource === 'rest' && !cfg.figmaToken) errors.push('FIGMA_TOKEN is required when FIGMA_SOURCE=rest.');
    if (cfg.figmaSource === 'auto' && !cfg.figmaToken) {
      errors.push('FIGMA_TOKEN is missing: the REST fallback (and asset export) needs it.');
    }
  }
  if (cfg.maxOutputTokens < 1) errors.push(`LLM_MAX_TOKENS must be >= 1 (got ${cfg.maxOutputTokens}).`);
  if (!(cfg.matchThreshold > 0 && cfg.matchThreshold <= 100)) errors.push(`MATCH_THRESHOLD must be in (0, 100] (got ${cfg.matchThreshold}).`);
  if (cfg.maxReviewIterations < 1) errors.push(`MAX_REVIEW_ITERATIONS must be >= 1 (got ${cfg.maxReviewIterations}); use --skip-review to disable the review loop.`);
  return errors;
}

function parseArgs(argv) {
  const out = {};
  for (let i = 0; i < argv.length; i++) {
    const a = argv[i];
    if (!a.startsWith('--')) continue;
    const key = a.slice(2);
    const next = argv[i + 1];
    if (next && !next.startsWith('--')) {
      out[key] = next;
      i++;
    } else {
      out[key] = true;
    }
  }
  return out;
}
