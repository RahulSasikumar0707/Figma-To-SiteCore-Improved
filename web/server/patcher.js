/**
 * Patch engine — applies the user-selected differences to Sitecore.
 *
 * Patchable diffs (item path + field + suggested value) go straight to the
 * ItemService PATCH endpoint, one item at a time, touching ONLY the selected
 * fields — nothing else on the page is modified. Multiple fields on the same
 * item are merged into a single PATCH call.
 *
 * If the current field value is rich text (HTML) and the suggested patch is
 * plain text, the LLM is asked to merge the new copy into the existing markup
 * so formatting (links, <sup>, classes) survives the patch.
 */
import { makeClient, resolveModel, complete, parseJsonLoose } from '../../src/llm/anthropicClient.js';
import { callSitecore } from '../../src/sitecore/restClient.js';
import { patchItemFields } from './sitecoreInventory.js';
import { log } from '../../src/utils/log.js';

const HTML_MERGE_SYSTEM = `You update Sitecore rich-text field values. You get the CURRENT field value
(HTML) and the NEW content the field must convey (from the approved design). Return ONLY a JSON object
{"value": "<updated HTML>"} where the HTML keeps the current markup conventions (tags, classes, links,
<sup> marks) but the visible text matches the NEW content exactly. If the current value is empty or
plain text, return the new content as simple semantic HTML (<p>…</p>) or plain text to match its style.`;

function looksLikeHtml(value) {
  return /<[a-z][\s\S]*>/i.test(String(value || ''));
}

async function getCurrentFieldValue(itemPath, field, { database, language }) {
  // ?path= form: the path-in-URL route 500s on this instance.
  const raw = await callSitecore({
    method: 'GET',
    path: '/sitecore/api/ssc/item/',
    query: { path: itemPath, database, language },
  });
  const parsed = JSON.parse(raw);
  if (!parsed.ok) throw new Error(`Cannot read ${itemPath} (HTTP ${parsed.status}).`);
  return parsed.data?.[field];
}

async function mergeIntoHtml({ apiKey, model }, currentHtml, newContent) {
  const client = makeClient(apiKey);
  const resolved = await resolveModel(client, model);
  const res = await complete({
    client,
    model: resolved,
    system: HTML_MERGE_SYSTEM,
    maxTokens: 4000,
    messages: [
      {
        role: 'user',
        content:
          `CURRENT VALUE:\n${currentHtml}\n\nNEW CONTENT (visible text must match this):\n${newContent}\n\nReturn the JSON.`,
      },
    ],
  });
  const parsed = parseJsonLoose(res.text);
  if (typeof parsed.value !== 'string' || !parsed.value.trim()) throw new Error('LLM merge returned no value.');
  return parsed.value;
}

/**
 * @param {Array} diffs      selected difference objects from the compare result
 * @param {object} llm       { apiKey, model }
 * @param {object} opts      { database, language, dryRun }
 * @returns per-diff results [{ diffId, ok, itemPath, field, appliedValue?, error?, skipped? }]
 */
export async function applyPatches(diffs, llm, { database = 'master', language = 'en', dryRun = false } = {}) {
  // Group by item path so one item gets one PATCH with all its field changes.
  const byItem = new Map();
  const results = [];

  for (const diff of diffs) {
    if (!diff.patchable || !diff.sitecoreItemPath || !diff.sitecoreField) {
      results.push({
        diffId: diff.id,
        ok: false,
        skipped: true,
        error: diff.patchNote || 'Not automatically patchable — requires manual authoring (e.g. new component/rendering).',
      });
      continue;
    }
    const key = diff.sitecoreItemPath;
    if (!byItem.has(key)) byItem.set(key, []);
    byItem.get(key).push(diff);
  }

  for (const [itemPath, itemDiffs] of byItem) {
    const fields = {};
    const fieldMeta = [];

    for (const diff of itemDiffs) {
      try {
        let value = String(diff.suggestedPatch ?? '');
        const current = await getCurrentFieldValue(itemPath, diff.sitecoreField, { database, language });
        // Keep rich-text structure: merge plain-text suggestions into existing HTML.
        if (looksLikeHtml(current) && !looksLikeHtml(value)) {
          log.info(`Merging new copy into existing HTML for ${itemPath} :: ${diff.sitecoreField}`);
          value = await mergeIntoHtml(llm, String(current), value);
        }
        fields[diff.sitecoreField] = value;
        fieldMeta.push({ diff, value });
      } catch (err) {
        results.push({ diffId: diff.id, ok: false, itemPath, field: diff.sitecoreField, error: err.message });
      }
    }

    if (!Object.keys(fields).length) continue;

    if (dryRun) {
      for (const { diff, value } of fieldMeta) {
        results.push({ diffId: diff.id, ok: true, dryRun: true, itemPath, field: diff.sitecoreField, appliedValue: value });
      }
      continue;
    }

    try {
      log.step(`PATCH ${itemPath} — fields: ${Object.keys(fields).join(', ')}`);
      const resp = await patchItemFields(itemPath, fields, { database, language });
      const ok = resp.ok;
      for (const { diff, value } of fieldMeta) {
        results.push({
          diffId: diff.id,
          ok,
          itemPath,
          field: diff.sitecoreField,
          appliedValue: value,
          ...(ok ? {} : { error: `Sitecore PATCH returned HTTP ${resp.status}` }),
        });
      }
    } catch (err) {
      for (const { diff } of fieldMeta) {
        results.push({ diffId: diff.id, ok: false, itemPath, field: diff.sitecoreField, error: err.message });
      }
    }
  }

  return results;
}
