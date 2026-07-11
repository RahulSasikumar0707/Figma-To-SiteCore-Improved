#!/usr/bin/env node
/**
 * Import generated HTML/CSS/JS to SiteCore via MCP Server
 * 
 * Reads a sitecore-structure.json file and creates the corresponding
 * SiteCore content structure using MCP server tools.
 * 
 * Prerequisites:
 * 1. SiteCore MCP server running (npm run sitecore-mcp or sitecore-mcp:http)
 * 2. ITEM_SERVICE_* credentials configured in .env
 * 
 * Usage:
 *   node import-to-sitecore.js --structure sitecore-structure.json --assets Output_1/assets
 *   node import-to-sitecore.js --structure structure.json --http http://localhost:3847/mcp
 */

import { Client } from '@modelcontextprotocol/sdk/client/index.js';
import { StdioClientTransport } from '@modelcontextprotocol/sdk/client/stdio.js';
import { StreamableHTTPClientTransport } from '@modelcontextprotocol/sdk/client/streamableHttp.js';
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const __dirname = path.dirname(fileURLToPath(import.meta.url));

// ══════════════════════════════════════════════════════════════════════════════
// Parse Arguments
// ══════════════════════════════════════════════════════════════════════════════

function parseArgs() {
  const args = {
    structureFile: null,
    assetsDir: null,
    httpUrl: null,
    useHttp: false,
    dryRun: false
  };
  
  for (let i = 2; i < process.argv.length; i++) {
    const arg = process.argv[i];
    
    if (arg === '--structure' && process.argv[i + 1]) {
      args.structureFile = process.argv[++i];
    } else if (arg === '--assets' && process.argv[i + 1]) {
      args.assetsDir = process.argv[++i];
    } else if (arg === '--http' && process.argv[i + 1]) {
      args.useHttp = true;
      args.httpUrl = process.argv[++i];
    } else if (arg === '--dry-run') {
      args.dryRun = true;
    }
  }
  
  if (!args.structureFile) {
    console.error('❌ Missing required --structure argument');
    console.error('\nUsage: node import-to-sitecore.js --structure <file.json> [options]');
    console.error('\nOptions:');
    console.error('  --structure <file>  Path to sitecore-structure.json (required)');
    console.error('  --assets <dir>      Path to assets directory (optional)');
    console.error('  --http <url>        Use HTTP MCP server instead of stdio');
    console.error('  --dry-run           Validate and preview without importing');
    console.error('\nExamples:');
    console.error('  node import-to-sitecore.js --structure sitecore-structure.json');
    console.error('  node import-to-sitecore.js --structure structure.json --assets Output_1/assets');
    console.error('  node import-to-sitecore.js --structure structure.json --http http://localhost:3847/mcp');
    process.exit(1);
  }
  
  return args;
}

// ══════════════════════════════════════════════════════════════════════════════
// MCP Client Setup
// ══════════════════════════════════════════════════════════════════════════════

async function connectToMcpServer(useHttp, httpUrl) {
  const client = new Client({
    name: 'sitecore-import-client',
    version: '1.0.0'
  }, {
    capabilities: {}
  });

  let transport;
  if (useHttp) {
    const url = httpUrl || 'http://127.0.0.1:3847/mcp';
    console.log(`📡 Connecting to HTTP MCP server: ${url}`);
    transport = new StreamableHTTPClientTransport(new URL(url));
  } else {
    console.log('📡 Starting stdio MCP server...');
    const mcpServerPath = path.resolve(__dirname, '..', '..', 'src', 'sitecore-mcp.js');
    transport = new StdioClientTransport({
      command: 'node',
      args: [mcpServerPath]
    });
  }

  await client.connect(transport);
  console.log('✅ Connected to SiteCore MCP server\n');
  
  return client;
}

// ══════════════════════════════════════════════════════════════════════════════
// Helper Functions
// ══════════════════════════════════════════════════════════════════════════════

async function callTool(client, toolName, args, dryRun = false) {
  const argsPreview = JSON.stringify(args, null, 2).substring(0, 150).replace(/\n/g, ' ');
  console.log(`🔧 ${toolName}: ${argsPreview}...`);
  
  if (dryRun) {
    console.log('   🔍 [DRY RUN] Would execute this call');
    return { ok: true, data: '[dry-run]' };
  }
  
  try {
    const result = await client.callTool({ name: toolName, arguments: args });
    const content = result.content[0]?.text || '';
    const parsed = JSON.parse(content);
    
    if (!parsed.ok) {
      console.error(`   ❌ Failed: ${parsed.data || 'Unknown error'}`);
      return null;
    }
    
    console.log(`   ✅ Success`);
    return parsed;
  } catch (error) {
    console.error(`   ❌ Error: ${error.message}`);
    return null;
  }
}

// ══════════════════════════════════════════════════════════════════════════════
// Import Functions
// ══════════════════════════════════════════════════════════════════════════════

async function createPageItem(client, structure, dryRun) {
  console.log('\n📄 STEP 1: Creating page item\n');
  
  const page = structure.page;
  const parentPath = page.path.substring(0, page.path.lastIndexOf('/'));
  const itemName = page.name || page.itemName;
  
  return await callTool(client, 'sitecore_create_item', {
    parent: parentPath,
    itemName: itemName,
    template: page.templateId || page.template,
    fields: page.fields || {},
    database: structure.metadata?.database || 'master',
    language: structure.metadata?.language || 'en'
  }, dryRun);
}

async function createDataFolder(client, structure, dryRun) {
  console.log('\n📁 STEP 2: Creating Data folder\n');
  
  return await callTool(client, 'sitecore_create_item', {
    parent: structure.page.path,
    itemName: 'Data',
    template: '{A87A00B1-E6DB-45AB-8B54-636FEC3B5523}', // Folder template
    database: structure.metadata?.database || 'master'
  }, dryRun);
}

async function createDatasources(client, structure, dryRun) {
  console.log('\n📦 STEP 3: Creating datasource items\n');
  
  if (!structure.datasources || structure.datasources.length === 0) {
    console.log('   ℹ️  No datasources to create');
    return;
  }
  
  console.log(`   Creating ${structure.datasources.length} datasource items...\n`);
  
  for (const datasource of structure.datasources) {
    const parentPath = datasource.path.substring(0, datasource.path.lastIndexOf('/'));
    const itemName = datasource.name || datasource.itemName;
    
    await callTool(client, 'sitecore_create_item', {
      parent: parentPath,
      itemName: itemName,
      template: datasource.templateId || datasource.template,
      fields: datasource.fields || {},
      database: structure.metadata?.database || 'master',
      language: structure.metadata?.language || 'en'
    }, dryRun);
  }
}

async function uploadMediaAssets(client, structure, assetsDir, dryRun) {
  console.log('\n🖼️  STEP 4: Uploading media assets\n');
  
  if (!structure.media || structure.media.length === 0) {
    console.log('   ℹ️  No media items to upload');
    return;
  }
  
  console.log(`   Processing ${structure.media.length} media items...\n`);
  
  for (const mediaItem of structure.media) {
    let filePath = mediaItem.filePath;
    
    // Resolve file path
    if (!path.isAbsolute(filePath)) {
      if (assetsDir) {
        filePath = path.join(assetsDir, path.basename(filePath));
      } else {
        console.warn(`   ⚠️  Skipping ${mediaItem.name}: no --assets directory specified`);
        continue;
      }
    }
    
    if (!fs.existsSync(filePath)) {
      console.warn(`   ⚠️  File not found: ${filePath}`);
      continue;
    }
    
    const fileBuffer = fs.readFileSync(filePath);
    const contentBase64 = fileBuffer.toString('base64');
    const ext = path.extname(filePath).toLowerCase();
    const contentType = 
      ext === '.svg' ? 'image/svg+xml' :
      ext === '.png' ? 'image/png' :
      ext === '.jpg' || ext === '.jpeg' ? 'image/jpeg' :
      ext === '.gif' ? 'image/gif' :
      ext === '.webp' ? 'image/webp' :
      'application/octet-stream';
    
    console.log(`   📄 ${mediaItem.name} (${Math.round(fileBuffer.length / 1024)}KB)`);
    
    if (!dryRun) {
      await callTool(client, 'sitecore_upload_media', {
        path: mediaItem.path,
        fileName: path.basename(filePath),
        contentBase64: contentBase64,
        contentType: contentType,
        database: structure.metadata?.database || 'master'
      }, dryRun);
    } else {
      console.log(`   🔍 [DRY RUN] Would upload to ${mediaItem.path}`);
    }
  }
}

async function assignLayout(client, structure, dryRun) {
  console.log('\n🎨 STEP 5: Assigning layout\n');
  
  if (!structure.layout || !structure.layout.renderings || structure.layout.renderings.length === 0) {
    console.log('   ℹ️  No layout to assign');
    return;
  }
  
  console.log(`   Assigning ${structure.layout.renderings.length} renderings...\n`);
  
  // In a real scenario, you'd use sitecore_update_item_fields to set the __Renderings field
  // or use a custom tool that updates the layout
  
  console.log('   ℹ️  Layout assignment requires custom implementation');
  console.log('   ℹ️  Use sitecore_update_item_fields with __Renderings field');
}

async function publishContent(client, structure, dryRun) {
  console.log('\n🚀 STEP 6: Publishing to web\n');
  
  const result = await callTool(client, 'sitecore_publish', {
    mode: 'Smart',
    targets: ['web'],
    languages: [structure.metadata?.language || 'en']
  }, dryRun);
  
  if (result) {
    console.log('   ✅ Publish job triggered');
  }
}

// ══════════════════════════════════════════════════════════════════════════════
// Main
// ══════════════════════════════════════════════════════════════════════════════

async function main() {
  console.log('\n╔══════════════════════════════════════════════════════════╗');
  console.log('║  SiteCore Import Tool - Structure → Content Tree        ║');
  console.log('╚══════════════════════════════════════════════════════════╝\n');
  
  const args = parseArgs();
  
  // Resolve paths
  const structureFile = path.resolve(args.structureFile);
  const assetsDir = args.assetsDir ? path.resolve(args.assetsDir) : null;
  
  // Validate files
  if (!fs.existsSync(structureFile)) {
    console.error(`❌ Structure file not found: ${structureFile}`);
    process.exit(1);
  }
  
  if (assetsDir && !fs.existsSync(assetsDir)) {
    console.error(`❌ Assets directory not found: ${assetsDir}`);
    process.exit(1);
  }
  
  // Load structure
  let structure;
  try {
    structure = JSON.parse(fs.readFileSync(structureFile, 'utf8'));
  } catch (err) {
    console.error(`❌ Failed to parse structure file: ${err.message}`);
    process.exit(1);
  }
  
  console.log(`📋 Structure: ${structureFile}`);
  console.log(`📄 Page: ${structure.page?.name || structure.page?.itemName}`);
  console.log(`📦 Datasources: ${structure.datasources?.length || 0}`);
  console.log(`🖼️  Media: ${structure.media?.length || 0}`);
  if (args.dryRun) {
    console.log(`🔍 Mode: DRY RUN (no changes will be made)\n`);
  }
  console.log();
  
  let client;
  try {
    // Connect to MCP server
    if (!args.dryRun) {
      client = await connectToMcpServer(args.useHttp, args.httpUrl);
    }
    
    // Execute import steps
    await createPageItem(client, structure, args.dryRun);
    await createDataFolder(client, structure, args.dryRun);
    await createDatasources(client, structure, args.dryRun);
    await uploadMediaAssets(client, structure, assetsDir, args.dryRun);
    await assignLayout(client, structure, args.dryRun);
    await publishContent(client, structure, args.dryRun);
    
    console.log('\n╔══════════════════════════════════════════════════════════╗');
    if (args.dryRun) {
      console.log('║           ✅ Dry Run Complete - No Changes Made          ║');
    } else {
      console.log('║                  ✅ Import Complete!                     ║');
    }
    console.log('╚══════════════════════════════════════════════════════════╝\n');
    
  } catch (error) {
    console.error('\n❌ Fatal error:', error.message);
    if (error.stack) {
      console.error(error.stack);
    }
    process.exit(1);
  } finally {
    if (client) {
      try {
        await client.close();
      } catch (err) {
        // Ignore close errors
      }
    }
  }
}

// Run if executed directly
main().catch(console.error);
