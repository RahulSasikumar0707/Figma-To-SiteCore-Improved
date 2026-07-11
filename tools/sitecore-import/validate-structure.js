#!/usr/bin/env node
/**
 * Validate SiteCore structure JSON before import
 * 
 * Checks:
 * - JSON is valid and parseable
 * - All required fields are present
 * - Paths are well-formed
 * - Template/Item GUIDs are valid format
 * - No duplicate item names/paths
 * - Referenced files exist
 * 
 * Usage:
 *   node validate-structure.js sitecore-structure.json
 *   node validate-structure.js path/to/structure.json --verbose
 */

import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const __dirname = path.dirname(fileURLToPath(import.meta.url));

// ══════════════════════════════════════════════════════════════════════════════
// Configuration
// ══════════════════════════════════════════════════════════════════════════════

const GUID_REGEX = /^\{[A-F0-9]{8}-[A-F0-9]{4}-[A-F0-9]{4}-[A-F0-9]{4}-[A-F0-9]{12}\}$/i;
const PATH_REGEX = /^\/sitecore\/.+/;

let verbose = false;

// ══════════════════════════════════════════════════════════════════════════════
// Validation Results
// ══════════════════════════════════════════════════════════════════════════════

class ValidationError {
  constructor(category, message, severity = 'error') {
    this.category = category;
    this.message = message;
    this.severity = severity;
  }
}

const errors = [];
const warnings = [];
const info = [];

function error(category, message) {
  errors.push(new ValidationError(category, message, 'error'));
}

function warn(category, message) {
  warnings.push(new ValidationError(category, message, 'warning'));
}

function note(category, message) {
  if (verbose) {
    info.push(new ValidationError(category, message, 'info'));
  }
}

// ══════════════════════════════════════════════════════════════════════════════
// Validators
// ══════════════════════════════════════════════════════════════════════════════

function validateGuid(guid, context) {
  if (!guid) {
    error('GUID', `Missing GUID in ${context}`);
    return false;
  }
  if (!GUID_REGEX.test(guid)) {
    error('GUID', `Invalid GUID format in ${context}: ${guid}`);
    return false;
  }
  return true;
}

function validatePath(pathStr, context) {
  if (!pathStr) {
    error('Path', `Missing path in ${context}`);
    return false;
  }
  if (!PATH_REGEX.test(pathStr)) {
    error('Path', `Invalid SiteCore path in ${context}: ${pathStr}`);
    return false;
  }
  return true;
}

function validateItemName(name, context) {
  if (!name || name.trim() === '') {
    error('ItemName', `Empty item name in ${context}`);
    return false;
  }
  if (/[^a-zA-Z0-9 _\-]/.test(name)) {
    warn('ItemName', `Item name contains special characters in ${context}: "${name}"`);
  }
  return true;
}

function validateMetadata(structure) {
  console.log('\n📋 Validating metadata...');
  
  if (!structure.metadata) {
    warn('Metadata', 'Missing metadata section');
    return;
  }
  
  const meta = structure.metadata;
  
  if (meta.database && meta.database !== 'master' && meta.database !== 'web') {
    warn('Metadata', `Unusual database: "${meta.database}"`);
  }
  
  if (meta.language && !/^[a-z]{2}(-[A-Z]{2})?$/.test(meta.language)) {
    warn('Metadata', `Language format may be incorrect: "${meta.language}"`);
  }
  
  note('Metadata', `Database: ${meta.database || 'not specified'}, Language: ${meta.language || 'not specified'}`);
}

function validatePage(structure) {
  console.log('\n📄 Validating page item...');
  
  if (!structure.page) {
    error('Page', 'Missing page definition');
    return;
  }
  
  const page = structure.page;
  
  validatePath(page.path, 'page.path');
  validateGuid(page.templateId || page.template, 'page.templateId');
  validateItemName(page.name || page.itemName, 'page.name');
  
  if (!page.fields || Object.keys(page.fields).length === 0) {
    warn('Page', 'Page has no fields defined');
  }
  
  note('Page', `Path: ${page.path}`);
}

function validateDatasources(structure) {
  console.log('\n📦 Validating datasources...');
  
  if (!structure.datasources || !Array.isArray(structure.datasources)) {
    warn('Datasources', 'No datasources defined (this is okay if page has no components)');
    return;
  }
  
  const datasources = structure.datasources;
  const names = new Set();
  const paths = new Set();
  
  datasources.forEach((ds, index) => {
    const context = `datasource[${index}]`;
    const name = ds.name || ds.itemName;
    const templateId = ds.templateId || ds.template;
    
    validatePath(ds.path, `${context}.path`);
    validateGuid(templateId, `${context}.templateId`);
    validateItemName(name, `${context}.name`);
    
    // Check for duplicates
    if (names.has(name)) {
      error('Datasources', `Duplicate datasource name: "${name}"`);
    }
    names.add(name);
    
    if (paths.has(ds.path)) {
      error('Datasources', `Duplicate datasource path: "${ds.path}"`);
    }
    paths.add(ds.path);
    
    // Check fields
    if (!ds.fields || Object.keys(ds.fields).length === 0) {
      warn('Datasources', `Datasource "${name}" has no fields`);
    }
  });
  
  note('Datasources', `Found ${datasources.length} datasource items`);
}

function validateMedia(structure, structureDir) {
  console.log('\n🖼️  Validating media items...');
  
  if (!structure.media || !Array.isArray(structure.media)) {
    note('Media', 'No media items defined');
    return;
  }
  
  const mediaItems = structure.media;
  
  mediaItems.forEach((item, index) => {
    const context = `media[${index}]`;
    const name = item.name || item.itemName;
    
    validatePath(item.path, `${context}.path`);
    validateGuid(item.templateId || item.template, `${context}.templateId`);
    validateItemName(name, `${context}.name`);
    
    // Check if source files exist
    if (item.filePath) {
      let sourcePath = item.filePath;
      
      // If relative, resolve from structure file directory
      if (!path.isAbsolute(sourcePath)) {
        sourcePath = path.join(structureDir, sourcePath);
      }
      
      if (!fs.existsSync(sourcePath)) {
        warn('Media', `Source file not found: ${item.filePath}`);
      }
    }
  });
  
  note('Media', `Found ${mediaItems.length} media item definitions`);
}

function validateLayout(structure) {
  console.log('\n🎨 Validating layout...');
  
  if (!structure.layout) {
    warn('Layout', 'No layout definition found');
    return;
  }
  
  const layout = structure.layout;
  
  if (layout.deviceId) {
    validateGuid(layout.deviceId, 'layout.deviceId');
  }
  
  if (!layout.renderings || !Array.isArray(layout.renderings)) {
    warn('Layout', 'No renderings defined in layout');
    return;
  }
  
  layout.renderings.forEach((rendering, index) => {
    const context = `rendering[${index}]`;
    
    if (rendering.id) {
      validateGuid(rendering.id, `${context}.id`);
    }
    
    if (rendering.itemId) {
      validateGuid(rendering.itemId, `${context}.itemId`);
    }
    
    if (!rendering.placeholder) {
      warn('Layout', `${context}: Missing placeholder name`);
    }
    
    if (rendering.datasource && !validatePath(rendering.datasource, `${context}.datasource`)) {
      // Already logged
    }
  });
  
  note('Layout', `Found ${layout.renderings.length} renderings`);
}

// ══════════════════════════════════════════════════════════════════════════════
// Main Validation
// ══════════════════════════════════════════════════════════════════════════════

function validateStructure(filePath) {
  console.log(`\n🔍 Validating: ${filePath}\n`);
  
  // Read and parse JSON
  let structure;
  try {
    const content = fs.readFileSync(filePath, 'utf8');
    structure = JSON.parse(content);
  } catch (err) {
    console.error(`❌ Failed to read/parse JSON: ${err.message}`);
    return false;
  }
  
  const structureDir = path.dirname(filePath);
  
  // Run validators
  validateMetadata(structure);
  validatePage(structure);
  validateDatasources(structure);
  validateMedia(structure, structureDir);
  validateLayout(structure);
  
  // Print summary
  console.log('\n' + '═'.repeat(60));
  console.log('📊 VALIDATION SUMMARY');
  console.log('═'.repeat(60));
  
  if (errors.length > 0) {
    console.log(`\n❌ ERRORS (${errors.length}):`);
    errors.forEach(e => console.log(`   [${e.category}] ${e.message}`));
  }
  
  if (warnings.length > 0) {
    console.log(`\n⚠️  WARNINGS (${warnings.length}):`);
    warnings.forEach(w => console.log(`   [${w.category}] ${w.message}`));
  }
  
  if (verbose && info.length > 0) {
    console.log(`\nℹ️  INFO (${info.length}):`);
    info.forEach(i => console.log(`   [${i.category}] ${i.message}`));
  }
  
  console.log();
  
  if (errors.length === 0) {
    console.log('✅ Validation passed! Structure is ready for import.');
    if (warnings.length > 0) {
      console.log(`   (${warnings.length} warning${warnings.length !== 1 ? 's' : ''} - review recommended)`);
    }
    return true;
  } else {
    console.log(`❌ Validation failed with ${errors.length} error${errors.length !== 1 ? 's' : ''}.`);
    console.log('   Fix errors before importing to SiteCore.');
    return false;
  }
}

// ══════════════════════════════════════════════════════════════════════════════
// CLI
// ══════════════════════════════════════════════════════════════════════════════

function main() {
  const args = process.argv.slice(2);
  
  if (args.includes('--verbose') || args.includes('-v')) {
    verbose = true;
    args.splice(args.indexOf(args.includes('--verbose') ? '--verbose' : '-v'), 1);
  }
  
  if (args.length === 0) {
    console.error('❌ Missing structure file path');
    console.error('\nUsage: node validate-structure.js <structure-file.json> [--verbose]');
    console.error('Example: node validate-structure.js sitecore-structure.json');
    process.exit(1);
  }
  
  const filePath = path.resolve(args[0]);
  
  if (!fs.existsSync(filePath)) {
    console.error(`❌ File not found: ${filePath}`);
    process.exit(1);
  }
  
  const isValid = validateStructure(filePath);
  process.exit(isValid ? 0 : 1);
}

main();
