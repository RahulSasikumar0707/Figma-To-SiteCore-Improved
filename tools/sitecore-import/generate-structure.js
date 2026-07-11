#!/usr/bin/env node
/**
 * Generate SiteCore structure JSON from Output_N folder
 * 
 * Reads component-map.json and generates a complete sitecore-structure.json
 * blueprint ready for import.
 * 
 * Usage:
 *   node generate-structure.js --input Output_1
 *   node generate-structure.js --input Output_1 --output my-structure.json
 *   node generate-structure.js --input Output_1 --page-name "About Us"
 */

import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const __dirname = path.dirname(fileURLToPath(import.meta.url));

// ══════════════════════════════════════════════════════════════════════════════
// Parse Arguments
// ══════════════════════════════════════════════════════════════════════════════

function parseArgs() {
  const args = {
    inputDir: null,
    outputFile: 'sitecore-structure.json',
    pageName: null
  };
  
  for (let i = 2; i < process.argv.length; i++) {
    const arg = process.argv[i];
    
    if (arg === '--input' && process.argv[i + 1]) {
      args.inputDir = process.argv[++i];
    } else if (arg === '--output' && process.argv[i + 1]) {
      args.outputFile = process.argv[++i];
    } else if (arg === '--page-name' && process.argv[i + 1]) {
      args.pageName = process.argv[++i];
    }
  }
  
  if (!args.inputDir) {
    console.error('❌ Missing required --input argument');
    console.error('Usage: node generate-structure.js --input Output_1 [--output structure.json] [--page-name "About Us"]');
    process.exit(1);
  }
  
  return args;
}

// ══════════════════════════════════════════════════════════════════════════════
// Generate Structure
// ══════════════════════════════════════════════════════════════════════════════

function generateGuid() {
  return '{' + 'xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx'.replace(/[xy]/g, c => {
    const r = Math.random() * 16 | 0;
    const v = c === 'x' ? r : (r & 0x3 | 0x8);
    return v.toString(16).toUpperCase();
  }) + '}';
}

function toSitecoreItemName(text) {
  return text
    .replace(/[^\w\s-]/g, '')
    .replace(/\s+/g, '-')
    .replace(/^-+|-+$/g, '');
}

function extractPageTitle(htmlPath) {
  try {
    const html = fs.readFileSync(htmlPath, 'utf8');
    const titleMatch = html.match(/<title>(.*?)<\/title>/i);
    if (titleMatch) {
      return titleMatch[1].trim();
    }
    
    const h1Match = html.match(/<h1[^>]*>(.*?)<\/h1>/i);
    if (h1Match) {
      return h1Match[1].replace(/<[^>]+>/g, '').trim();
    }
  } catch (err) {
    console.warn('⚠️  Could not extract page title from HTML');
  }
  
  return 'Generated Page';
}

function createDatasourceFromMapping(mapping, index) {
  const itemName = toSitecoreItemName(mapping.edsComponent + '-' + (index + 1));
  
  return {
    id: generateGuid(),
    name: itemName,
    path: null, // Will be set later when we know the parent path
    templateId: '{A87A00B1-E6DB-45AB-8B54-636FEC3B5523}', // Generic datasource template
    fields: {
      ComponentType: mapping.edsComponent,
      DesignSection: mapping.designSection,
      Modifiers: mapping.modifiers?.join(', ') || '',
      Confidence: mapping.confidence?.toString() || '0',
      Notes: mapping.notes || ''
    }
  };
}

function collectAssetsFromHtml(htmlPath) {
  const assets = [];
  
  try {
    const html = fs.readFileSync(htmlPath, 'utf8');
    
    // Images
    const imgMatches = html.matchAll(/<img[^>]+src=["']([^"']+)["']/gi);
    for (const match of imgMatches) {
      const src = match[1];
      if (!src.startsWith('http') && !src.startsWith('data:')) {
        assets.push({ type: 'image', src });
      }
    }
    
    // CSS backgrounds
    const bgMatches = html.matchAll(/background-image:\s*url\(['"]?([^'"()]+)['"]?\)/gi);
    for (const match of bgMatches) {
      const src = match[1];
      if (!src.startsWith('http') && !src.startsWith('data:')) {
        assets.push({ type: 'image', src });
      }
    }
    
    // SVG/Icons
    const svgMatches = html.matchAll(/<svg[^>]*>.*?<\/svg>/gis);
    for (const match of svgMatches) {
      // Inline SVG - might want to extract to file
      assets.push({ type: 'inline-svg', content: match[0] });
    }
  } catch (err) {
    console.warn('⚠️  Could not scan HTML for assets:', err.message);
  }
  
  return assets;
}

function generateStructure(inputDir, pageName) {
  const componentMapPath = path.join(inputDir, 'component-map.json');
  const htmlPath = path.join(inputDir, 'index.html');
  
  if (!fs.existsSync(componentMapPath)) {
    throw new Error(`component-map.json not found in ${inputDir}`);
  }
  
  if (!fs.existsSync(htmlPath)) {
    throw new Error(`index.html not found in ${inputDir}`);
  }
  
  const componentMap = JSON.parse(fs.readFileSync(componentMapPath, 'utf8'));
  const pageTitle = pageName || extractPageTitle(htmlPath);
  const pageItemName = toSitecoreItemName(pageTitle);
  
  console.log(`📄 Page: ${pageTitle} (${pageItemName})`);
  console.log(`📦 Components: ${componentMap.mappings?.length || 0}`);
  
  const structure = {
    metadata: {
      generatedFrom: inputDir,
      generatedAt: new Date().toISOString(),
      pageTitle,
      database: 'master',
      language: 'en'
    },
    
    page: {
      id: generateGuid(),
      name: pageItemName,
      path: `/sitecore/content/Home/${pageItemName}`,
      templateId: '{76036F5E-CBCE-46D1-AF0A-4143F9B557AA}',
      fields: {
        Title: pageTitle,
        MetaDescription: `${pageTitle} - Generated from Figma`,
        MetaKeywords: componentMap.mappings?.map(m => m.edsComponent).join(', ') || ''
      }
    },
    
    datasources: [],
    
    media: [],
    
    layout: {
      deviceId: '{FE5D7FDF-89C0-4D99-9AA3-B5FBD009C9F3}', // Default device
      renderings: []
    }
  };
  
  // Create Data folder path
  const dataFolderPath = `${structure.page.path}/Data`;
  
  // Create datasources from component map
  if (componentMap.mappings && Array.isArray(componentMap.mappings)) {
    componentMap.mappings.forEach((mapping, index) => {
      const datasource = createDatasourceFromMapping(mapping, index);
      datasource.path = `${dataFolderPath}/${datasource.name}`;
      structure.datasources.push(datasource);
      
      // Add to layout renderings
      structure.layout.renderings.push({
        id: generateGuid(),
        itemId: generateGuid(), // Rendering definition item
        placeholder: 'main',
        datasource: datasource.path,
        cacheable: false,
        varyByData: false,
        varyByDevice: false,
        varyByLogin: false,
        varyByParameters: false,
        varyByQueryString: false,
        varyByUser: false
      });
    });
  }
  
  // Collect media assets
  const assets = collectAssetsFromHtml(htmlPath);
  assets.forEach((asset, index) => {
    if (asset.type === 'image' && asset.src) {
      const fileName = path.basename(asset.src);
      structure.media.push({
        id: generateGuid(),
        name: toSitecoreItemName(fileName.replace(/\.[^.]+$/, '')),
        path: `/sitecore/media library/Project/VANDDMYO/${fileName}`,
        filePath: path.join(inputDir, asset.src),
        templateId: '{5C7D2D82-D5EA-4DA9-BE88-FCEBBF3FC815}' // UnversionedImage template
      });
    }
  });
  
  return structure;
}

// ══════════════════════════════════════════════════════════════════════════════
// Main
// ══════════════════════════════════════════════════════════════════════════════

function main() {
  console.log('🏗️  SiteCore Structure Generator\n');
  
  const args = parseArgs();
  
  // Resolve input directory
  const inputDir = path.isAbsolute(args.inputDir) 
    ? args.inputDir 
    : path.join(process.cwd(), args.inputDir);
  
  if (!fs.existsSync(inputDir)) {
    console.error(`❌ Input directory not found: ${inputDir}`);
    process.exit(1);
  }
  
  try {
    const structure = generateStructure(inputDir, args.pageName);
    
    // Write output - default to input directory, unless absolute path provided
    const outputPath = path.isAbsolute(args.outputFile)
      ? args.outputFile
      : path.join(inputDir, args.outputFile);
    
    fs.writeFileSync(outputPath, JSON.stringify(structure, null, 2));
    
    console.log(`\n✅ Generated: ${outputPath}`);
    console.log(`   📄 Page: ${structure.page.name}`);
    console.log(`   📦 Datasources: ${structure.datasources.length}`);
    console.log(`   🖼️  Media: ${structure.media.length}`);
    console.log(`   🎨 Renderings: ${structure.layout.renderings.length}`);
    
  } catch (err) {
    console.error(`\n❌ Generation failed: ${err.message}`);
    process.exit(1);
  }
}

main();
