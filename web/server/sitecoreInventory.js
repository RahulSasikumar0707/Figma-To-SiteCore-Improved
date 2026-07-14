/**
 * Sitecore content inventory — reads the page item and its datasource tree via
 * the ItemService REST API (ITEM_SERVICE_* env vars, same auth as the MCP
 * server) and reduces it to a compact, LLM-friendly content inventory.
 */
import { callSitecore, encodeSitecoreItem } from '../../src/sitecore/restClient.js';
import { log } from '../../src/utils/log.js';

const MAX_ITEMS = 250;
const MAX_DEPTH = 5;

/** Standard/system fields that carry no page content. */
function isSystemField(name) {
  return name.startsWith('__');
}

/** Strip Sitecore rich-text/HTML down to readable text for the LLM. */
export function htmlToText(value) {
  return String(value ?? '')
    .replace(/<style[\s\S]*?<\/style>/gi, ' ')
    .replace(/<script[\s\S]*?<\/script>/gi, ' ')
    .replace(/<br\s*\/?>/gi, '\n')
    .replace(/<\/(p|div|li|h[1-6]|tr)>/gi, '\n')
    .replace(/<[^>]+>/g, ' ')
    .replace(/&nbsp;/gi, ' ')
    .replace(/&amp;/gi, '&')
    .replace(/&lt;/gi, '<')
    .replace(/&gt;/gi, '>')
    .replace(/&#39;|&apos;/gi, "'")
    .replace(/&quot;/gi, '"')
    .replace(/[ \t]+/g, ' ')
    .replace(/\s*\n\s*/g, '\n')
    .trim();
}

async function getJson(path, query) {
  const raw = await callSitecore({ method: 'GET', path, query });
  const parsed = JSON.parse(raw);
  if (!parsed.ok) {
    const msg = typeof parsed.data === 'string' ? parsed.data.slice(0, 200) : JSON.stringify(parsed.data)?.slice(0, 200);
    const err = new Error(`Sitecore ${parsed.status} for ${path}: ${msg || 'request failed'}`);
    err.status = parsed.status;
    throw err;
  }
  return parsed.data;
}

async function getItemByPath(itemPath, { database = 'master', language = 'en' } = {}) {
  // This instance rejects the path-in-URL form ("Multiple actions were found",
  // HTTP 500) — the ?path= query form resolves items reliably.
  return getJson('/sitecore/api/ssc/item/', { path: itemPath, database, language });
}

async function getChildren(itemId, { database = 'master', language = 'en' } = {}) {
  const id = String(itemId).replace(/[{}]/g, '');
  return getJson(`/sitecore/api/ssc/item/${id}/children`, { database, language });
}

function contentFields(item) {
  const fields = {};
  for (const [key, value] of Object.entries(item)) {
    // ItemService flattens fields onto the object next to metadata keys.
    if (/^(ItemID|ItemName|ItemPath|ParentID|TemplateID|TemplateName|CloneSource|ItemLanguage|ItemVersion|DisplayName|HasChildren|ItemMedialUrl|ItemUrl)$/i.test(key)) continue;
    if (isSystemField(key)) continue;
    const text = htmlToText(value);
    if (!text) continue;
    fields[key] = { raw: String(value ?? ''), text };
  }
  return fields;
}

/**
 * Walk the page item + descendants (datasources usually live under the page
 * or its "Data" folder). Returns a flat list of items with content fields.
 */
export async function collectSitecoreInventory(itemPath, { database = 'master', language = 'en' } = {}) {
  const root = await getItemByPath(itemPath, { database, language });
  if (!root || !root.ItemID) throw new Error(`Sitecore item not found: ${itemPath}`);

  const items = [];
  const queue = [{ item: root, depth: 0 }];
  while (queue.length && items.length < MAX_ITEMS) {
    const { item, depth } = queue.shift();
    items.push({
      id: item.ItemID,
      name: item.ItemName,
      path: item.ItemPath,
      template: item.TemplateName,
      templateId: item.TemplateID,
      language: item.ItemLanguage || language,
      fields: contentFields(item),
    });
    if (depth >= MAX_DEPTH || String(item.HasChildren).toLowerCase() !== 'true') continue;
    try {
      const children = await getChildren(item.ItemID, { database, language });
      for (const child of Array.isArray(children) ? children : []) {
        queue.push({ item: child, depth: depth + 1 });
      }
    } catch (err) {
      log.warn(`Could not read children of ${item.ItemPath}: ${err.message}`);
    }
  }

  return { root: { id: root.ItemID, path: root.ItemPath, name: root.ItemName, template: root.TemplateName }, items };
}

/** Compact text digest of the inventory for the LLM prompt. */
export function inventoryToPrompt(inventory) {
  const lines = [];
  for (const item of inventory.items) {
    const fieldEntries = Object.entries(item.fields);
    if (!fieldEntries.length) continue;
    lines.push(`ITEM: ${item.path}`);
    lines.push(`  template: ${item.template}`);
    for (const [name, { text }] of fieldEntries) {
      const clipped = text.length > 600 ? `${text.slice(0, 600)}…` : text;
      lines.push(`  field "${name}": ${JSON.stringify(clipped)}`);
    }
  }
  return lines.join('\n');
}

/** Resolve a content path (or pass through a GUID) to a bare item ID. */
async function resolveItemId(itemPathOrId, { database = 'master', language = 'en' } = {}) {
  const s = String(itemPathOrId).trim();
  const guid = s.match(/^\{?([0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12})\}?$/i);
  if (guid) return guid[1];
  const item = await getItemByPath(s, { database, language });
  if (!item?.ItemID) throw new Error(`Sitecore item not found: ${s}`);
  return String(item.ItemID).replace(/[{}]/g, '');
}

/** PATCH field values on one item — the core "patch without disturbing the rest" op. */
export async function patchItemFields(itemPath, fields, { database = 'master', language = 'en' } = {}) {
  // Path-in-URL routes 500 on this instance ("Multiple actions were found"),
  // so resolve to the GUID and PATCH by ID.
  const id = await resolveItemId(itemPath, { database, language });
  const raw = await callSitecore({
    method: 'PATCH',
    path: `/sitecore/api/ssc/item/${id}`,
    query: { database, language },
    body: fields,
  });
  return JSON.parse(raw);
}

/** Create a new item (used when the design has content Sitecore lacks entirely). */
export async function createItem(parentPath, itemName, template, fields, { database = 'master', language = 'en' } = {}) {
  const id = await resolveItemId(parentPath, { database, language });
  const raw = await callSitecore({
    method: 'POST',
    path: `/sitecore/api/ssc/item/${id}`,
    query: { database, language },
    body: { ItemName: itemName, TemplateID: template, ...(fields ? { Fields: fields } : {}) },
  });
  return JSON.parse(raw);
}
