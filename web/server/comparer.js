/**
 * LLM comparison engine — hands Claude both screenshots (vision) plus the two
 * content inventories (text) and gets back a structured diff list where every
 * entry is either informational or patchable against a concrete Sitecore
 * item/field.
 */
import { makeClient, resolveModel, complete, imageBlock, parseJsonLoose } from '../../src/llm/anthropicClient.js';
import { log } from '../../src/utils/log.js';

const SYSTEM = `You are a meticulous content-QA agent comparing a Figma design (source of truth)
against a published Sitecore page. You receive:
1. The Figma design screenshot (image 1)
2. The rendered Sitecore page screenshot (image 2)
3. A text inventory of the Figma design content
4. A text inventory of the Sitecore page items and their field values

Identify every meaningful difference. Classify each as:
- "missing"  — content exists in Figma but not on the Sitecore page
- "extra"    — content exists on the Sitecore page but not in the Figma design
- "mismatch" — content exists in both but the value/wording/asset differs
- "visual"   — purely visual difference (layout, color, spacing, typography) not tied to a content field

For every difference, when the Sitecore inventory contains an item+field that should hold
the content, set "sitecoreItemPath" and "sitecoreField" and "patchable": true, and put the
exact value the field should contain (taken verbatim from the Figma design) in
"suggestedPatch". Preserve rich-text HTML structure if the current Sitecore field value is
HTML (wrap paragraphs in <p>, keep <sup>, <strong>, links). If no existing item/field can
hold the content (a whole component is missing), set "patchable": false and explain what
would need to be created in "patchNote".

Ignore: cookie banners, ISI/safety-info reflows caused by sticky behavior, scrollbars,
browser chrome, and content differences caused purely by viewport width.

Respond with ONLY a JSON object:
{
  "matchScore": <0-100 overall content parity>,
  "summary": "<2-3 sentence overview>",
  "differences": [
    {
      "id": "diff-1",
      "type": "missing" | "extra" | "mismatch" | "visual",
      "severity": "high" | "medium" | "low",
      "section": "<page region, e.g. Hero, ISI, Footer>",
      "description": "<what differs, precise>",
      "figmaValue": "<value in the design, or null>",
      "sitecoreValue": "<value on the page, or null>",
      "sitecoreItemPath": "<full /sitecore/content/... path or null>",
      "sitecoreField": "<field name or null>",
      "patchable": true | false,
      "suggestedPatch": "<exact new field value, or null>",
      "patchNote": "<only when not patchable: what manual step is needed>"
    }
  ]
}`;

export async function compareDesigns({ apiKey, model, figma, sitecore, maxTokens = 16000 }) {
  const client = makeClient(apiKey);
  const resolved = await resolveModel(client, model);
  log.step(`Comparing with ${resolved}…`);

  const messages = [
    {
      role: 'user',
      content: [
        { type: 'text', text: 'IMAGE 1 — Figma design (source of truth):' },
        imageBlock(figma.screenshotPng, 'image/png'),
        { type: 'text', text: 'IMAGE 2 — Rendered Sitecore page:' },
        imageBlock(sitecore.screenshotPng, 'image/png'),
        {
          type: 'text',
          text:
            `FIGMA CONTENT INVENTORY\n=======================\n${figma.prompt}\n\n` +
            `SITECORE CONTENT INVENTORY (page item + descendants)\n====================================================\n${sitecore.prompt}\n\n` +
            'Compare them and return the JSON verdict.',
        },
      ],
    },
  ];

  const res = await complete({ client, model: resolved, system: SYSTEM, messages, maxTokens });
  const verdict = parseJsonLoose(res.text);

  const differences = Array.isArray(verdict.differences) ? verdict.differences : [];
  differences.forEach((d, i) => {
    if (!d.id) d.id = `diff-${i + 1}`;
    d.patchable = Boolean(d.patchable && d.sitecoreItemPath && d.sitecoreField && d.suggestedPatch != null);
  });

  return {
    matchScore: Number(verdict.matchScore) || 0,
    summary: String(verdict.summary || ''),
    differences,
    usage: res.usage,
    model: resolved,
  };
}
