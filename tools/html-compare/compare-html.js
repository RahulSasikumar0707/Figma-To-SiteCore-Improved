#!/usr/bin/env node
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import dotenv from 'dotenv';

import { makeClient, resolveModel, complete, parseJsonLoose } from '../../src/llm/anthropicClient.js';
import { log } from '../../src/utils/log.js';

// Load the project's .env (repo root is two levels up from this tool).
const __dirname = path.dirname(fileURLToPath(import.meta.url));
const repoRoot = path.resolve(__dirname, '..', '..');
dotenv.config({ path: path.join(repoRoot, '.env'), override: true });

const USAGE = `Compare a live Gilead page against a generated output folder's index.html.

Usage:
  node tools/html-compare/compare-html.js --url <gilead-url> --output <folder> [options]

Required:
  --url <url>        Live Gilead page URL to fetch (the "source of truth").
  --output <folder>  Output folder to compare (e.g. Output_2, or a full path).
                     The tool reads <folder>/index.html.

Options:
  --file <name>      HTML file name inside the output folder (default: index.html).
  --out <dir>        Where to write the comparison report
                     (default: tools/html-compare/results/<timestamp>).
  --model <id>       Anthropic model id (default: ANTHROPIC_MODEL or claude-fable-5).
  --help             Show this help.

Environment:
  ANTHROPIC_API_KEY_1 (or ANTHROPIC_API_KEY)  API key used for the comparison.
  ANTHROPIC_MODEL                             Default model id.
`;

const SYSTEM = `You are a meticulous web QA analyst. You compare two HTML documents of the same web page:
1. LIVE — the authoritative live page fetched from a Gilead site.
2. GENERATED — a reconstructed/generated version from an output folder.

Your job is to list the DIFFERENCES between them so a developer can bring the generated version in line with the live page. Focus on content and structure that a reader/QA would notice — ignore incidental differences that don't change the page (e.g. attribute ordering, whitespace, comments, CDN/query-string variations, absolute-vs-relative asset paths that point at equivalent files, framework boilerplate).

Compare, in priority order:
1. Sections present/missing/extra (and their order).
2. Headings and body copy (report missing, truncated, placeholder ("FPO", "...", "Lorem"), or reworded text — quote the exact expected vs actual).
3. Links & CTAs (labels, destinations).
4. Images/media (missing, extra, or clearly different assets — by alt text / filename intent).
5. Lists, tables, form fields, and interactive components (accordions, flip cards, tabs).
6. Structural/semantic differences that change meaning.

Return ONLY a JSON object in this exact shape:
{
  "summary": "<one short paragraph overview of how closely they match>",
  "matchPercent": <0-100 integer estimate of content fidelity>,
  "differences": [
    {
      "severity": "critical|major|minor",
      "area": "<section or component name>",
      "type": "missing|extra|mismatch|truncated|placeholder|link|image|order",
      "live": "<what the LIVE page has — quote exactly, or 'n/a'>",
      "generated": "<what the GENERATED page has — quote exactly, or 'n/a'>",
      "recommendation": "<concrete fix for the generated file>"
    }
  ]
}
Be specific and quantitative. If the two are effectively identical in content, return an empty differences array.`;

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

/** Strip <script>/<style> and collapse whitespace to keep the token cost down while preserving content + structure. */
function condenseHtml(html) {
  return String(html)
    .replace(/<!--[\s\S]*?-->/g, ' ')
    .replace(/<script\b[^>]*>[\s\S]*?<\/script>/gi, ' ')
    .replace(/<style\b[^>]*>[\s\S]*?<\/style>/gi, ' ')
    .replace(/\r\n/g, '\n')
    .replace(/[ \t]+/g, ' ')
    .replace(/\n{3,}/g, '\n\n')
    .trim();
}

async function fetchLiveHtml(url) {
  log.step(`Fetching live page: ${url}`);
  const res = await fetch(url, {
    headers: {
      'User-Agent': 'Mozilla/5.0 (compatible; html-compare/1.0)',
      Accept: 'text/html,application/xhtml+xml',
    },
    redirect: 'follow',
  });
  if (!res.ok) throw new Error(`Live page fetch failed: HTTP ${res.status} ${res.statusText}`);
  const html = await res.text();
  log.ok(`Fetched ${html.length.toLocaleString()} bytes.`);
  return html;
}

function resolveOutputHtmlPath(outputArg, fileName) {
  // Accept either a bare folder name (resolved against repo root) or a full path.
  const base = path.isAbsolute(outputArg) ? outputArg : path.resolve(repoRoot, outputArg);
  // If the arg already points at an .html file, use it directly.
  if (/\.html?$/i.test(base) && fs.existsSync(base)) return base;
  return path.join(base, fileName);
}

function renderMarkdown(url, verdict, meta) {
  const lines = [];
  lines.push(`# HTML Comparison Report`);
  lines.push('');
  lines.push(`- **Live URL:** ${url}`);
  lines.push(`- **Generated file:** ${meta.generatedPath}`);
  lines.push(`- **Model:** ${meta.model}`);
  lines.push(`- **Generated at:** ${meta.timestamp}`);
  lines.push(`- **Estimated content match:** ${verdict.matchPercent ?? 'n/a'}%`);
  lines.push('');
  lines.push(`## Summary`);
  lines.push('');
  lines.push(verdict.summary || '(none)');
  lines.push('');

  const diffs = Array.isArray(verdict.differences) ? verdict.differences : [];
  lines.push(`## Differences (${diffs.length})`);
  lines.push('');
  if (!diffs.length) {
    lines.push('No meaningful content differences found. 🎉');
  } else {
    const order = { critical: 0, major: 1, minor: 2 };
    diffs.sort((a, b) => (order[a.severity] ?? 3) - (order[b.severity] ?? 3));
    for (const [i, d] of diffs.entries()) {
      lines.push(`### ${i + 1}. [${(d.severity || 'minor').toUpperCase()}] ${d.area || 'General'} — ${d.type || 'mismatch'}`);
      lines.push('');
      if (d.live) lines.push(`- **Live:** ${d.live}`);
      if (d.generated) lines.push(`- **Generated:** ${d.generated}`);
      if (d.recommendation) lines.push(`- **Fix:** ${d.recommendation}`);
      lines.push('');
    }
  }
  return lines.join('\n');
}

async function main() {
  const args = parseArgs(process.argv.slice(2));
  if (args.help || (!args.url && !args.output)) {
    console.log(USAGE);
    process.exit(args.help ? 0 : 1);
  }
  if (!args.url) throw new Error('Missing --url <gilead-url>.');
  if (!args.output) throw new Error('Missing --output <folder>.');

  const apiKey = process.env.ANTHROPIC_API_KEY_1 || process.env.ANTHROPIC_API_KEY || '';
  if (!apiKey) throw new Error('ANTHROPIC_API_KEY_1 (or ANTHROPIC_API_KEY) is required in the environment/.env.');

  const fileName = typeof args.file === 'string' ? args.file : 'index.html';
  const generatedPath = resolveOutputHtmlPath(args.output, fileName);
  if (!fs.existsSync(generatedPath)) {
    throw new Error(`Generated HTML not found: ${generatedPath}`);
  }

  const [liveHtmlRaw, generatedHtmlRaw] = await Promise.all([
    fetchLiveHtml(args.url),
    Promise.resolve(fs.readFileSync(generatedPath, 'utf8')),
  ]);

  const liveHtml = condenseHtml(liveHtmlRaw);
  const generatedHtml = condenseHtml(generatedHtmlRaw);

  const client = makeClient(apiKey);
  const preferred = (typeof args.model === 'string' && args.model) || process.env.ANTHROPIC_MODEL || 'claude-fable-5';
  const model = await resolveModel(client, preferred);

  log.step(`Comparing with ${model}…`);
  const { text, usage } = await complete({
    client,
    model,
    system: SYSTEM,
    maxTokens: 8000,
    messages: [
      {
        role: 'user',
        content:
          `Compare these two HTML documents of the same page and list the differences per your instructions.\n\n` +
          `===== LIVE (source of truth) =====\n${liveHtml}\n\n` +
          `===== GENERATED (${path.basename(path.dirname(generatedPath))}/${path.basename(generatedPath)}) =====\n${generatedHtml}`,
      },
    ],
  });

  let verdict;
  try {
    verdict = parseJsonLoose(text);
  } catch {
    log.warn('Could not parse structured JSON from the model — saving raw response instead.');
    verdict = { summary: text, matchPercent: null, differences: [] };
  }

  const timestamp = new Date().toISOString();
  const outDir = typeof args.out === 'string'
    ? path.resolve(repoRoot, args.out)
    : path.join(__dirname, 'results', timestamp.replace(/[:.]/g, '-'));
  fs.mkdirSync(outDir, { recursive: true });

  const meta = { generatedPath, model, timestamp };
  const md = renderMarkdown(args.url, verdict, meta);
  const jsonPath = path.join(outDir, 'comparison.json');
  const mdPath = path.join(outDir, 'comparison.md');
  fs.writeFileSync(jsonPath, JSON.stringify({ url: args.url, ...meta, ...verdict }, null, 2));
  fs.writeFileSync(mdPath, md);

  const diffs = Array.isArray(verdict.differences) ? verdict.differences : [];
  log.ok(`Found ${diffs.length} difference(s). Estimated match: ${verdict.matchPercent ?? 'n/a'}%.`);
  if (usage) log.info(`Tokens — in: ${usage.input_tokens}, out: ${usage.output_tokens}`);
  log.ok(`Report: ${mdPath}`);
  log.info(`JSON:   ${jsonPath}`);

  console.log('\n' + md);
}

main().catch((err) => {
  log.error(err?.message || String(err));
  process.exit(1);
});
