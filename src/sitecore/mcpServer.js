/**
 * Sitecore MCP Server — modelled on the Sitecore-mcp reference app.
 *
 * Auth and config come from ITEM_SERVICE_* env vars read lazily per call
 * (no client instance to construct). Credentials can be rotated without
 * restarting the server.
 *
 * Tools:
 *   sitecore_request           — Generic pass-through to any Sitecore endpoint
 *   sitecore_get_item          — Get item fields by path or GUID
 *   sitecore_search_items      — Search by keyword / template / root path
 *   sitecore_create_item       — Create item from a template
 *   sitecore_update_item_fields— Patch field values on an existing item
 *   sitecore_delete_item       — Delete item (requires confirmed=true)
 *   sitecore_download_media    — Download media blob as base64
 *   sitecore_upload_media      — Upload base64 content to a media item
 *   sitecore_get_layout        — Layout Service (JSS) page data
 *   sitecore_publish           — Trigger a publish job
 *   sitecore_push_rendering    — Push a generated EDS component as a rendering
 *
 * Transport:
 *   Default → stdio  (Claude Desktop, VS Code Copilot MCP extension)
 *   --http  → Streamable HTTP on SITECORE_MCP_PORT (default 3847)
 */

import { McpServer } from '@modelcontextprotocol/sdk/server/mcp.js';
import { StdioServerTransport } from '@modelcontextprotocol/sdk/server/stdio.js';
import { StreamableHTTPServerTransport } from '@modelcontextprotocol/sdk/server/streamableHttp.js';
import { z } from 'zod';
import http from 'node:http';
import { callSitecore, callSitecoreBinary, encodeSitecoreItem } from './restClient.js';

// ── Server factory ────────────────────────────────────────────────────────────

export function createSitecoreMcpServer() {
  const server = new McpServer({
    name: 'sitecore-local-mcp',
    version: '1.0.0',
  });

  // ── sitecore_request ──────────────────────────────────────────────────────
  server.tool(
    'sitecore_request',
    'Call any Sitecore endpoint using the ITEM_SERVICE_* credentials. Use this for operations not covered by dedicated tools.',
    {
      method: z.enum(['GET', 'POST', 'PUT', 'PATCH', 'DELETE']).default('GET').describe('HTTP method'),
      path: z.string().describe('Path relative to ITEM_SERVICE_SERVER_URL, e.g. /sitecore/api/ssc/item/search'),
      query: z.record(z.string()).optional().describe('Optional query-string parameters'),
      body: z.unknown().optional().describe('Optional JSON body'),
      headers: z.record(z.string()).optional().describe('Optional extra request headers'),
    },
    async ({ method, path, query, body, headers }) => {
      const output = await callSitecore({ method, path, query, body, headers });
      return { content: [{ type: 'text', text: output }] };
    },
  );

  // ── sitecore_get_item ─────────────────────────────────────────────────────
  server.tool(
    'sitecore_get_item',
    'Get a Sitecore item by ID or path. Returns all field values.',
    {
      item: z.string().describe('Item GUID (e.g. {110D559F-…}) or full Sitecore path'),
      database: z.string().default('master').describe('Sitecore database'),
      language: z.string().default('en').describe('Language version'),
      includeStandardTemplateFields: z.boolean().default(false).describe('Include standard template fields'),
    },
    async ({ item, database, language, includeStandardTemplateFields }) => {
      const itemPath = encodeSitecoreItem(item);
      const output = await callSitecore({
        method: 'GET',
        path: `/sitecore/api/ssc/item/${itemPath}`,
        query: { database, language, includeStandardTemplateFields: String(includeStandardTemplateFields) },
      });
      return { content: [{ type: 'text', text: output }] };
    },
  );

  // ── sitecore_search_items ─────────────────────────────────────────────────
  server.tool(
    'sitecore_search_items',
    'Search Sitecore items by keyword, template, or root path.',
    {
      term: z.string().describe('Search term'),
      page: z.number().int().min(1).default(1).describe('Page number (1-based)'),
      pageSize: z.number().int().min(1).max(100).default(20).describe('Results per page'),
      database: z.string().default('master').describe('Sitecore database'),
      language: z.string().default('en').describe('Language version'),
    },
    async ({ term, page, pageSize, database, language }) => {
      const output = await callSitecore({
        method: 'GET',
        path: '/sitecore/api/ssc/item/search',
        query: { term, page: String(page), pageSize: String(pageSize), database, language },
      });
      return { content: [{ type: 'text', text: output }] };
    },
  );

  // ── sitecore_create_item ──────────────────────────────────────────────────
  server.tool(
    'sitecore_create_item',
    'Create a new Sitecore item under a parent path using a specified template.',
    {
      parent: z.string().describe('Parent item full Sitecore path or GUID'),
      itemName: z.string().min(1).max(100).describe('Name for the new item'),
      template: z.string().describe('Template ID or path, e.g. {76036F5E-…}'),
      fields: z.record(z.unknown()).optional().describe('Optional initial field values as { fieldName: value }'),
      database: z.string().default('master').describe('Sitecore database'),
      language: z.string().default('en').describe('Language version'),
    },
    async ({ parent, itemName, template, fields, database, language }) => {
      const parentPath = encodeSitecoreItem(parent);
      const output = await callSitecore({
        method: 'POST',
        path: `/sitecore/api/ssc/item/${parentPath}`,
        query: { database, language },
        body: {
          ItemName: itemName,
          TemplateID: template,
          ...(fields ? { Fields: fields } : {}),
        },
      });
      return { content: [{ type: 'text', text: output }] };
    },
  );

  // ── sitecore_update_item_fields ───────────────────────────────────────────
  server.tool(
    'sitecore_update_item_fields',
    'Update one or more field values on an existing Sitecore item.',
    {
      item: z.string().describe('Item GUID or full Sitecore path'),
      fields: z.record(z.unknown()).describe('Field name → value map'),
      database: z.string().default('master').describe('Sitecore database'),
      language: z.string().default('en').describe('Language version'),
    },
    async ({ item, fields, database, language }) => {
      const itemPath = encodeSitecoreItem(item);
      const output = await callSitecore({
        method: 'PATCH',
        path: `/sitecore/api/ssc/item/${itemPath}`,
        query: { database, language },
        body: fields,
      });
      return { content: [{ type: 'text', text: output }] };
    },
  );

  // ── sitecore_delete_item ──────────────────────────────────────────────────
  server.tool(
    'sitecore_delete_item',
    'Delete a Sitecore item. Set confirmed=true to proceed — this is irreversible.',
    {
      item: z.string().describe('Item GUID or full Sitecore path'),
      confirmed: z.boolean().describe('Must be true to confirm deletion'),
      database: z.string().default('master').describe('Sitecore database'),
    },
    async ({ item, confirmed, database }) => {
      if (!confirmed) {
        return { content: [{ type: 'text', text: 'Error: Set confirmed=true to confirm deletion. This cannot be undone.' }], isError: true };
      }
      const itemPath = encodeSitecoreItem(item);
      const output = await callSitecore({
        method: 'DELETE',
        path: `/sitecore/api/ssc/item/${itemPath}`,
        query: { database },
      });
      return { content: [{ type: 'text', text: output }] };
    },
  );

  // ── sitecore_download_media ───────────────────────────────────────────────
  server.tool(
    'sitecore_download_media',
    'Download media bytes from a Sitecore media item, returned as a base64-encoded string.',
    {
      mediaItem: z.string().describe('Media item ID or path'),
      blobPathTemplate: z
        .string()
        .default('/sitecore/api/ssc/item/{item}/blob')
        .describe('Endpoint template — {item} is replaced with the encoded media item path'),
      database: z.string().default('master').describe('Sitecore database'),
      language: z.string().default('en').describe('Language version'),
    },
    async ({ mediaItem, blobPathTemplate, database, language }) => {
      const encoded = encodeSitecoreItem(mediaItem);
      const path = blobPathTemplate.replace('{item}', encoded);
      const output = await callSitecoreBinary({
        method: 'GET',
        path,
        query: { database, language },
      });
      return { content: [{ type: 'text', text: output }] };
    },
  );

  // ── sitecore_upload_media ─────────────────────────────────────────────────
  server.tool(
    'sitecore_upload_media',
    'Upload binary content to a Sitecore media item from a base64-encoded string.',
    {
      mediaItem: z.string().describe('Media item ID or path'),
      contentBase64: z.string().describe('Binary data encoded as base64'),
      contentType: z.string().default('application/octet-stream').describe('MIME type of the content'),
      blobPathTemplate: z
        .string()
        .default('/sitecore/api/ssc/item/{item}/blob')
        .describe('Endpoint template — {item} is replaced with the encoded media item path'),
      database: z.string().default('master').describe('Sitecore database'),
      language: z.string().default('en').describe('Language version'),
    },
    async ({ mediaItem, contentBase64, contentType, blobPathTemplate, database, language }) => {
      const encoded = encodeSitecoreItem(mediaItem);
      const path = blobPathTemplate.replace('{item}', encoded);

      let buffer;
      try {
        buffer = Buffer.from(contentBase64, 'base64');
      } catch {
        return {
          content: [{ type: 'text', text: JSON.stringify({ ok: false, error: 'contentBase64 is not valid base64' }) }],
          isError: true,
        };
      }

      const output = await callSitecoreBinary({
        method: 'PUT',
        path,
        query: { database, language },
        body: buffer,
        headers: { 'Content-Type': contentType },
      });
      return { content: [{ type: 'text', text: output }] };
    },
  );

  // ── sitecore_get_layout ───────────────────────────────────────────────────
  server.tool(
    'sitecore_get_layout',
    'Fetch Layout Service (JSS) rendering data for a Sitecore page — includes placeholders, components and datasource fields.',
    {
      itemPath: z.string().describe('Sitecore content path, e.g. /sitecore/content/MySite/Home'),
      site: z.string().default('website').describe('JSS site name'),
      language: z.string().default('en').describe('Language version'),
    },
    async ({ itemPath, site, language }) => {
      const output = await callSitecore({
        method: 'GET',
        path: '/sitecore/api/layout/render/jss',
        query: { item: itemPath, sc_site: site, sc_lang: language },
      });
      return { content: [{ type: 'text', text: output }] };
    },
  );

  // ── sitecore_publish ──────────────────────────────────────────────────────
  server.tool(
    'sitecore_publish',
    'Trigger a Sitecore publish job to push content to the web database.',
    {
      mode: z.enum(['SingleItem', 'Smart', 'Full']).default('SingleItem').describe('Publish mode'),
      itemId: z.string().optional().describe('Item GUID (required for SingleItem mode)'),
      targets: z.array(z.string()).default(['web']).describe('Publishing targets'),
      languages: z.array(z.string()).default(['en']).describe('Languages to publish'),
      subitems: z.boolean().default(false).describe('Include child items in the publish'),
    },
    async ({ mode, itemId, targets, languages, subitems }) => {
      const output = await callSitecore({
        method: 'POST',
        path: '/sitecore/api/ssc/publish/',
        body: {
          Mode: mode,
          PublishingTargets: targets,
          Languages: languages,
          ItemId: itemId,
          IncludeSubItems: subitems,
        },
      });
      return { content: [{ type: 'text', text: output }] };
    },
  );

  // ── sitecore_push_rendering ───────────────────────────────────────────────
  server.tool(
    'sitecore_push_rendering',
    `Register a generated EDS component as a Sitecore View Rendering definition item.
Searches for an existing rendering with the same name under renderingsRoot — updates it
if found, creates a new one if not. The combined HTML/CSS/JS is stored in the Description field.`,
    {
      componentName: z.string().min(1).max(80).describe('Component name, e.g. "Hero Banner"'),
      html: z.string().min(1).describe('Generated HTML markup'),
      css: z.string().optional().describe('Generated CSS'),
      js: z.string().optional().describe('Generated JavaScript'),
      renderingsRoot: z
        .string()
        .default('/sitecore/layout/Renderings/Feature')
        .describe('Path under which the rendering item will be created'),
      renderingTemplateId: z
        .string()
        .default('{99F8905D-4A87-4EB8-9F8B-A9BEBFB3ADD6}')
        .describe('View Rendering template GUID'),
      database: z.string().default('master').describe('Sitecore database'),
    },
    async ({ componentName, html, css, js, renderingsRoot, renderingTemplateId, database }) => {
      // Sanitise item name
      const itemName = componentName.replace(/[^a-zA-Z0-9 _\-]/g, '').trim() || 'EDS Component';

      // Combine all generated output into a single Description blob
      const parts = [`<!-- ${componentName} -->`, html];
      if (css) parts.push(`<style>\n${css}\n</style>`);
      if (js) parts.push(`<script>\n${js}\n</script>`);
      const combinedMarkup = parts.join('\n\n');

      // Check whether a rendering with this name already exists
      let existingId = null;
      try {
        const searchResult = await callSitecore({
          method: 'GET',
          path: '/sitecore/api/ssc/item/search',
          query: { term: itemName, rootPath: renderingsRoot, page: '1', pageSize: '5', database },
        });
        const parsed = JSON.parse(searchResult);
        const hits = Array.isArray(parsed?.data) ? parsed.data
          : Array.isArray(parsed?.data?.Results) ? parsed.data.Results
          : [];
        const match = hits.find((h) => (h.Name ?? h.ItemName) === itemName);
        if (match) existingId = match.ItemId ?? match.ID ?? match.Id;
      } catch {
        /* search failure is non-fatal — fall through to create */
      }

      if (existingId) {
        const updatePath = encodeSitecoreItem(existingId);
        const output = await callSitecore({
          method: 'PATCH',
          path: `/sitecore/api/ssc/item/${updatePath}`,
          query: { database },
          body: { Description: combinedMarkup },
        });
        return { content: [{ type: 'text', text: JSON.stringify({ action: 'updated', itemId: existingId, name: itemName, result: JSON.parse(output) }, null, 2) }] };
      }

      const parentPath = encodeSitecoreItem(renderingsRoot);
      const output = await callSitecore({
        method: 'POST',
        path: `/sitecore/api/ssc/item/${parentPath}`,
        query: { database },
        body: { ItemName: itemName, TemplateID: renderingTemplateId, Fields: { Description: combinedMarkup } },
      });
      return { content: [{ type: 'text', text: JSON.stringify({ action: 'created', name: itemName, result: JSON.parse(output) }, null, 2) }] };
    },
  );

  return server;
}

// ── Transport helpers ─────────────────────────────────────────────────────────

/** Start the server using stdio (Claude Desktop / VS Code Copilot). */
export async function startStdio() {
  const server = createSitecoreMcpServer();
  const transport = new StdioServerTransport();
  await server.connect(transport);
  process.stderr.write('[sitecore-mcp] Listening on stdio\n');
}

/** Start the server using Streamable HTTP on the given port. */
export async function startHttp(port = 3847) {
  const server = createSitecoreMcpServer();

  const httpServer = http.createServer(async (req, res) => {
    if (req.method === 'POST' && req.url === '/mcp') {
      const transport = new StreamableHTTPServerTransport({ sessionIdGenerator: undefined });
      res.on('close', () => transport.close());
      await server.connect(transport);
      await transport.handleRequest(req, res);
      return;
    }
    if (req.method === 'GET' && req.url === '/health') {
      res.writeHead(200, { 'Content-Type': 'application/json' });
      res.end(JSON.stringify({ status: 'ok', server: 'sitecore-mcp' }));
      return;
    }
    res.writeHead(404);
    res.end();
  });

  await new Promise((resolve, reject) => httpServer.listen(port, resolve).on('error', reject));
  process.stderr.write(`[sitecore-mcp] Listening on http://127.0.0.1:${port}/mcp\n`);
  return httpServer;
}
