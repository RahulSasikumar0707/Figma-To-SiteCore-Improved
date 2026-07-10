import { completeWithContinuation, imageBlock } from './anthropicClient.js';
import { manifestCatalog } from '../eds/manifest.js';
import { log } from '../utils/log.js';

/**
 * Generator agent (ANTHROPIC_API_KEY_1): turns the normalized design spec into
 * EDS-structured, Bootstrap-responsive HTML/CSS/JS. Also produces
 * component-map.json documenting which EDS component each design section maps to.
 */

const FILE_DELIM_RE = /^===FILE:\s*(.+?)\s*===\s*$/gm;

export function parseGeneratedFiles(text, { truncated = false } = {}) {
  // Everything after ===END=== is trailing prose, not file content.
  const endMatch = text.match(/^===END===\s*$/m);
  const sawEnd = !!endMatch;
  if (sawEnd) text = text.slice(0, endMatch.index);

  const files = {};
  const matches = [...text.matchAll(FILE_DELIM_RE)];
  for (let i = 0; i < matches.length; i++) {
    const name = matches[i][1].trim();
    const start = matches[i].index + matches[i][0].length;
    const end = i + 1 < matches.length ? matches[i + 1].index : text.length;
    // When the response was cut off at max_tokens (and ===END=== never came),
    // the final file block is incomplete — drop it rather than shipping (or
    // merging over a previously complete version with) a truncated file.
    if (truncated && !sawEnd && i === matches.length - 1) {
      log.warn(`Response hit max_tokens — dropping incomplete final file "${name}".`);
      continue;
    }
    let content = text.slice(start, end).trim();
    // strip an accidental surrounding code fence
    const fence = content.match(/^```[a-z]*\n([\s\S]*?)\n```$/);
    if (fence) content = fence[1];
    files[name] = content + '\n';
  }
  return files;
}

function headTemplate(ctx) {
  const eds = ctx.edsNativeAvailable
    ? '  <link href="css/eds-native.css" rel="stylesheet" />'
    : '  <!-- eds-native.css not found on this machine; styles.css must carry the full component styling -->';
  return `<head>
  <meta charset="UTF-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1.0" />
  <title>{page title from the design}</title>
  <link href="${ctx.bootstrapCssUrl}" rel="stylesheet" />
${eds}
  <link rel="preconnect" href="https://fonts.googleapis.com">
  <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin="">
  <link href="https://fonts.googleapis.com/css2?family=Inter:ital,opsz,wght@0,14..32,100..900;1,14..32,100..900&family=Material+Symbols+Outlined&family=Material+Symbols+Rounded&display=swap" rel="stylesheet" />
  {ADD Google Fonts links for every font family in the design tokens that is not Inter}
  <link href="css/tokens.css" rel="stylesheet" />
  <link href="css/styles.css" rel="stylesheet" />
</head>`;
}

function systemPrompt() {
  return `You are an elite Sitecore EDS front-end engineer. You convert Figma design specifications into pixel-accurate, production-quality, responsive HTML/CSS/JS built on Bootstrap 5.1.3 and the Sitecore EDS component library.

NON-NEGOTIABLE RULES
1. EXACT VISUAL MATCH. Reproduce the design spec exactly: colors, font families/sizes/weights/line-heights, spacing (gaps/paddings/margins), border radii, shadows, alignment and stacking order. Never invent, "improve" or approximate values that exist in the spec.
2. DESIGN TOKENS. css/tokens.css (provided) defines CSS custom properties for every color, font size, spacing, radius and shadow in the design. In css/styles.css, ALWAYS reference these tokens (var(--fig-...)) instead of hardcoding values. Only hardcode a value if no token exists for it.
3. EDS COMPONENT STRUCTURE. Each design section must be built with the DOM structure of its mapped EDS component (snippets provided). Keep EDS class names intact (component eds-<name>, modifiers, inner class hierarchy). Wrap the page in:
   <div id="eds-wrapper"><header id="eds-header">...</header><main id="eds-main">...</main><footer id="eds-footer">...</footer></div>
   (omit header/footer wrappers only if the design has no such section).
4. BOOTSTRAP 5. Use the Bootstrap grid (container-fluid / row / col-*) for layout and Bootstrap behaviors (data-bs-* for collapse, carousel, modal, dropdown, tabs) instead of writing custom JS where Bootstrap covers it. No jQuery.
5. ASSETS. Use ONLY the image/icon/vector files listed in the asset manifest, via their exact relative paths (assets/...). Every image visible in the design must appear in the HTML (or as a CSS background when the spec marks it bgImage). Set width/height or aspect-ratio to prevent layout shift, alt text from the layer name, img-fluid where appropriate. For large banner/hero images use the EDS <picture> pattern with (min-width:992px) / (min-width:768px) / (min-width:0px) sources.
6. RESPONSIVE. Mobile-first. The spec's frame geometry describes the desktop layout; derive tablet (>=768px) and mobile (<768px) behavior from the auto-layout semantics (row layouts stack into columns on mobile unless they are small inline groups; grids of N cards become 2-up on tablet and 1-up on mobile via col-12 col-md-6 col-lg-*). Nothing may overflow the viewport at 375px, 768px or 1440px.
7. CSS QUALITY. styles.css loads AFTER eds-native.css, so your rules override EDS defaults when the design differs — override deliberately and minimally, scoped to the component (e.g. .eds-hero-banner .hero-title { ... }). Do not use !important unless a Bootstrap utility must be beaten.
8. The layout semantics in the spec map directly: layout.mode=row -> display:flex;flex-direction:row, mode=column -> flex-direction:column, gap -> gap, padding -> padding, justify/align -> justify-content/align-items, sizing fill -> flex:1/width:100%, hug -> fit-content, fixed -> exact px (desktop only; relax responsively).

OUTPUT FORMAT — CRITICAL
Return ONLY the files, each introduced by a delimiter line, no other prose:
===FILE: index.html===
<complete file>
===FILE: css/styles.css===
<complete file>
===FILE: js/script.js===
<complete file>
===FILE: component-map.json===
{"mappings":[{"designSection":"...","edsComponent":"...","modifiers":["..."],"confidence":0-100,"notes":"..."}]}
===END===`;
}

export function buildGeneratorContext(ctx) {
  const parts = [];
  parts.push(`# TASK\nConvert the following Figma design ("${ctx.designName}", desktop frame ${ctx.rootSize?.w}x${ctx.rootSize?.h}px) into EDS + Bootstrap responsive code.`);
  parts.push(`# REQUIRED <head> TEMPLATE (use exactly, substituting the placeholders)\n${headTemplate(ctx)}\n\nBefore </body> include:\n<script src="${ctx.bootstrapJsUrl}"></script>\n<script src="js/script.js"></script>`);
  parts.push(`# DESIGN SPEC (normalized Figma node tree; coordinates in px relative to parent)\n${ctx.specJson}`);
  parts.push(`# DESIGN TOKENS (css/tokens.css — already written to disk; reference these variables)\n${ctx.tokensCss}`);
  parts.push(`# ASSET MANIFEST (the ONLY allowed asset paths; "role" tells you how the node is used)\n${JSON.stringify(ctx.assetManifest.map(({ id, name, kind, file, w, h }) => ({ id, name, kind, file, w, h })), null, 1)}\nAsset ids referenced in the spec via "asset"/"bgImage" correspond to "id" here.`);
  parts.push(`# EDS COMPONENT CATALOG (all 37 components)\n${manifestCatalog(ctx.allComponents)}`);
  parts.push(`# ALGORITHMIC SECTION->COMPONENT PRE-MATCHING (heuristic shortlist; you make the final mapping)\n${JSON.stringify(ctx.matches, null, 1)}`);
  const snippets = ctx.shortlist
    .map((c) => `## ${c.name} (classes: ${(c.edsClasses || []).join(' ')})\nStructure:\n${c.structureOutline || 'n/a'}\nModifiers: ${(c.modifiers || []).map((m) => `${m.cls} (${m.purpose || ''})`).join('; ') || 'none'}\nCanonical snippet:\n${c.snippet || 'n/a'}`)
    .join('\n\n');
  parts.push(`# EDS COMPONENT REFERENCE SNIPPETS (authoritative DOM structures — follow them)\n${snippets}`);
  if (ctx.mcpDesignContext) {
    parts.push(`# FIGMA DEV MODE CONTEXT (Figma's own representation of this node — use it to resolve ambiguity)\n${ctx.mcpDesignContext.slice(0, 30000)}`);
  }
  return parts.join('\n\n');
}

export async function generate({ client, model, maxTokens, maxContinuations, ctx }) {
  log.step('Generator (API key 1): producing EDS + Bootstrap code from the design spec…');
  const { text, usage, stopReason } = await completeWithContinuation({
    client,
    model,
    maxTokens,
    maxContinuations,
    system: systemPrompt(),
    messages: [{ role: 'user', content: buildGeneratorContext(ctx) }],
  });
  log.info(`Generator tokens — in: ${usage?.input_tokens}, out: ${usage?.output_tokens}`);
  const files = parseGeneratedFiles(text, { truncated: stopReason === 'max_tokens' });
  assertFiles(files);
  return files;
}

export async function refine({ client, model, maxTokens, maxContinuations, ctx, files, review, pixelMismatchPct, figmaImage, renderImage, diffImage }) {
  log.step(`Generator (API key 1): applying ${review.issues?.length ?? 0} review fixes…`);
  const fileDump = Object.entries(files)
    .map(([name, content]) => `===FILE: ${name}===\n${content}`)
    .join('\n');
  const prompt = [
    `Your previous conversion is below. The independent design reviewer compared it against the original Figma design and scored it ${review.score}/100${typeof pixelMismatchPct === 'number' ? ` (pixel mismatch vs Figma render: ${pixelMismatchPct.toFixed(2)}%)` : ''}.`,
    `# REVIEWER ISSUES (fix EVERY one; do not regress anything that is already correct)\n${JSON.stringify(review.issues, null, 1)}`,
    `# CURRENT FILES\n${fileDump}`,
    `# DESIGN SPEC (ground truth)\n${ctx.specJson}`,
    `# ASSET MANIFEST\n${JSON.stringify(ctx.assetManifest.map(({ id, name, file, w, h }) => ({ id, name, file, w, h })), null, 1)}`,
    `Return ALL files complete and updated in the exact ===FILE: ...=== format (index.html, css/styles.css, js/script.js, component-map.json). No prose.`,
  ].join('\n\n');

  // Vision-guided fixing: seeing the target, the current render and the diff
  // heatmap converges far faster than repairing from an issue list alone.
  const content = [];
  if (figmaImage?.buffer) {
    content.push({ type: 'text', text: 'TARGET — the Figma design you must match:' });
    content.push(imageBlock(figmaImage.buffer, figmaImage.mediaType));
  }
  if (renderImage?.buffer) {
    content.push({ type: 'text', text: 'CURRENT STATE — browser render of your code as it stands:' });
    content.push(imageBlock(renderImage.buffer, renderImage.mediaType));
  }
  if (diffImage?.buffer) {
    content.push({ type: 'text', text: 'PIXEL-DIFF HEATMAP — red/pink marks where your render deviates from the design:' });
    content.push(imageBlock(diffImage.buffer, diffImage.mediaType));
  }
  content.push({ type: 'text', text: prompt });

  const { text, usage, stopReason } = await completeWithContinuation({
    client,
    model,
    maxTokens,
    maxContinuations,
    system: systemPrompt(),
    messages: [{ role: 'user', content }],
  });
  log.info(`Refine tokens — in: ${usage?.input_tokens}, out: ${usage?.output_tokens}`);
  // A max_tokens-truncated final file is dropped by the parser, so the merge
  // below keeps the previous complete version instead of a cut-off one.
  const updated = parseGeneratedFiles(text, { truncated: stopReason === 'max_tokens' });
  // keep any file the model failed to re-emit
  const merged = { ...files, ...updated };
  assertFiles(merged);
  return merged;
}

function assertFiles(files) {
  const required = ['index.html', 'css/styles.css'];
  const missing = required.filter((f) => !files[f]);
  if (missing.length) {
    throw new Error(`Generator response missing required file(s): ${missing.join(', ')} — got: ${Object.keys(files).join(', ') || 'none'}`);
  }
}
