import { complete, imageBlock, parseJsonLoose } from './anthropicClient.js';
import { log } from '../utils/log.js';

/**
 * Reviewer agent (ANTHROPIC_API_KEY_2) — an independent design-QA pass.
 * Compares the generated code against the design spec, the Figma reference
 * screenshot and (when puppeteer is installed) a real browser render of the
 * generated page. Returns a score and a concrete fix list; the loop in
 * index.js feeds those fixes back to the generator until the score clears
 * MATCH_THRESHOLD.
 */

const SYSTEM = `You are a ruthless design-QA reviewer for Figma-to-code conversions targeting Sitecore EDS + Bootstrap 5. You are a different agent from the developer and must not trust their work.

Compare the generated code against the ground truth (design spec + Figma reference screenshot). If a browser render of the generated page is provided, visually diff it against the Figma reference region by region.

Check, in priority order:
1. Layout accuracy (40 pts): section order, positions, column structure, alignment, sizes.
2. Typography (20 pts): family, size, weight, line-height, color, alignment of every text node.
3. Color fidelity (15 pts): backgrounds, gradients, borders — exact hex values from the spec/tokens.
4. Spacing (15 pts): paddings, gaps, margins vs the spec's auto-layout values.
5. Assets & responsiveness (10 pts): every design image/icon present with correct path from the manifest, sensible crops, EDS structure preserved, no horizontal overflow at 375/768/1440 px.

Also verify: design tokens (var(--fig-*)) are used instead of hardcoded values; EDS component DOM structures are respected; Bootstrap behaviors use data-bs-*.

WHAT COUNTS AS AN ISSUE — the goal is an EMPTY issues array once the code genuinely matches:
- Report ONLY defects that are actionable in the HTML/CSS/JS (a concrete change would fix them).
- Do NOT report: sub-pixel/anti-aliasing/font-hinting rendering differences, browser scrollbar artifacts, differences under ~2px that no CSS change can control, image compression noise, or anything the provided asset files make impossible to fix.
- Do NOT restate an issue that the code demonstrably already addresses.
- When every remaining visual difference falls into the unfixable categories above, return "issues": [] and score accordingly (>= 95).

Return ONLY a JSON object:
{
  "score": <0-100 overall fidelity>,
  "summary": "<one paragraph>",
  "issues": [
    {"severity": "critical|major|minor", "area": "<section/component>", "description": "<what is wrong, with exact expected vs actual values>", "fix": "<concrete instruction for the developer>"}
  ]
}
Be specific and quantitative in every issue.`;

export async function review({ client, model, ctx, files, figmaImage, renderImage, diffImage, pixelMismatchPct }) {
  log.step('Reviewer (API key 2): auditing generated code against the Figma design…');
  const content = [];

  if (figmaImage?.buffer) {
    content.push({ type: 'text', text: 'GROUND TRUTH — Figma design reference screenshot:' });
    content.push(imageBlock(figmaImage.buffer, figmaImage.mediaType));
  }
  if (renderImage?.buffer) {
    content.push({ type: 'text', text: `GENERATED PAGE — browser render of the candidate code${typeof pixelMismatchPct === 'number' ? ` (automated pixel mismatch: ${pixelMismatchPct.toFixed(2)}%)` : ''}:` });
    content.push(imageBlock(renderImage.buffer, renderImage.mediaType));
  }
  if (diffImage?.buffer) {
    content.push({ type: 'text', text: 'PIXEL-DIFF HEATMAP — red/pink pixels mark where the render deviates from the Figma design (use it to localize problems):' });
    content.push(imageBlock(diffImage.buffer, diffImage.mediaType));
  }

  const fileDump = Object.entries(files)
    .map(([name, c]) => `===FILE: ${name}===\n${c}`)
    .join('\n');

  content.push({
    type: 'text',
    text: [
      `# DESIGN SPEC (ground truth, normalized Figma tree)\n${ctx.specJsonSmall}`,
      `# DESIGN TOKENS AVAILABLE\n${ctx.tokensCss}`,
      `# ASSET MANIFEST (allowed paths)\n${JSON.stringify(ctx.assetManifest.map(({ name, file, w, h }) => ({ name, file, w, h })))}`,
      `# GENERATED CODE UNDER REVIEW\n${fileDump}`,
      `Review now and return the JSON verdict.`,
    ].join('\n\n'),
  });

  const { text, usage } = await complete({
    client,
    model,
    maxTokens: 8000,
    system: SYSTEM,
    messages: [{ role: 'user', content }],
  });
  log.info(`Reviewer tokens — in: ${usage?.input_tokens}, out: ${usage?.output_tokens}`);

  let verdict;
  try {
    verdict = parseJsonLoose(text);
  } catch {
    log.warn('Reviewer did not return valid JSON; treating as score 0 with a generic issue.');
    verdict = { score: 0, summary: text.slice(0, 400), issues: [{ severity: 'critical', area: 'review', description: 'Reviewer output unparseable', fix: 'Regenerate with strict adherence to the spec.' }] };
  }
  verdict.score = Math.max(0, Math.min(100, Number(verdict.score) || 0));
  verdict.issues = Array.isArray(verdict.issues) ? verdict.issues.filter((i) => i && typeof i === 'object') : [];
  log.ok(`Review score: ${verdict.score}/100 (${verdict.issues.length} issues)`);
  return verdict;
}
