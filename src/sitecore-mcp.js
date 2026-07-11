#!/usr/bin/env node
/**
 * Sitecore MCP Server — entry point
 *
 * Modelled on the Sitecore-mcp reference app. Config is read from
 * ITEM_SERVICE_* env vars lazily per call — no client instance to construct.
 *
 * Usage (stdio — Claude Desktop / VS Code Copilot):
 *   node src/sitecore-mcp.js
 *
 * Usage (HTTP — network or in-process clients):
 *   node src/sitecore-mcp.js --http [port]
 *
 * Required environment variables (via .env or shell):
 *   ITEM_SERVICE_SERVER_URL   Base URL, e.g. https://sitecore.example.com/sitecore
 *   ITEM_SERVICE_USERNAME     Sitecore username
 *   ITEM_SERVICE_PASSWORD     Sitecore password
 *
 * Optional:
 *   ITEM_SERVICE_DOMAIN       Domain prefix, e.g. "sitecore"
 *   SITECORE_MCP_PORT         HTTP port when using --http (default: 3847)
 */

import 'dotenv/config';
import { startStdio, startHttp } from './sitecore/mcpServer.js';

const useHttp = process.argv.includes('--http');
const httpFlagIdx = process.argv.indexOf('--http');
const port = parseInt(process.env.SITECORE_MCP_PORT || (httpFlagIdx !== -1 ? process.argv[httpFlagIdx + 1] : '') || '3847', 10);

async function main() {
  if (useHttp) {
    await startHttp(port);
  } else {
    await startStdio();
  }
}

main().catch((err) => {
  process.stderr.write(`[sitecore-mcp] Fatal: ${err.message}\n`);
  process.exit(1);
});

