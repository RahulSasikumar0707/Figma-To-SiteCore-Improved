#!/usr/bin/env node
/**
 * Figma → Sitecore EDS converter.
 *
 * Pipeline:
 *  1. Extract the target node — Figma Dev Mode MCP server first (design
 *     context + variables + screenshot), Figma REST API for the structured
 *     tree, asset export and reference render.
 *  2. Normalize the tree into a compact design spec + asset plan + token inputs.
 *  3. Download every image / icon / vector into Output_N/assets.
 *  4. Emit css/tokens.css design tokens.
 *  5. Match design sections against the 37-component EDS manifest.
 *  6. Generator agent (ANTHROPIC_API_KEY_1) writes HTML/CSS/JS on Bootstrap 5 + EDS.
 *  7. Reviewer agent (ANTHROPIC_API_KEY_2) audits vs the design (with optional
 *     headless-Chrome pixel diff) and the generator fixes its findings — looped
 *     until the score clears MATCH_THRESHOLD.
 *  8. Everything lands in an auto-incrementing Output_N folder with a report.
 */
import fs from 'node:fs';
import path from 'node:path';
import { pathToFileURL } from 'node:url';
import { loadConfig, validateConfig } from './config.js';
import { log, c } from './utils/log.js';
import { nextOutputDir, writeFileEnsured } from './utils/fsx.js';
import { FigmaRest } from './figma/restClient.js';
import { FigmaMcp } from './figma/mcpClient.js';
import { normalizeDesign, compactSpec } from './figma/normalize.js';
import { downloadAssets, downloadReferenceScreenshot } from './assets/downloader.js';
import { buildDesignTokens } from './tokens/designTokens.js';
import { loadEdsManifest, scanEdsComponents } from './eds/manifest.js';
import { matchSections, shortlistedComponents } from './eds/matcher.js';
import { makeClient, resolveModel } from './llm/anthropicClient.js';
import { generate, refine } from './llm/generator.js';
import { review } from './llm/reviewer.js';
import { renderGeneratedPage, pixelMismatch } from './review/visualDiff.js';
import { findEdsNativeCss, writeGeneratedFiles, writeReport } from './output/writer.js';

async function main() {
  const cfg = loadConfig(process.argv.slice(2));
  const errors = validateConfig(cfg);
  if (errors.length) {
    errors.forEach((e) => log.error(e));
    process.exit(1);
  }

  if (cfg.manifestOnly) {
    const components = scanEdsComponents(cfg.edsComponentsDir);
    writeFileEnsured(cfg.edsManifestPath, JSON.stringify({ generatedAt: new Date().toISOString(), source: 'programmatic scan', componentCount: components.length, components }, null, 2));
    log.ok(`eds-manifest.json rebuilt with ${components.length} components.`);
    return;
  }

  const warnings = [];
  console.log(c.bold('\n╔══ Figma → Sitecore EDS Converter ══╗\n'));
  log.info(`File: ${cfg.fileKey}  Node: ${cfg.nodeId}  Model: ${cfg.model}`);

  // ── 1. Extract ────────────────────────────────────────────────────────────
  log.step('Extracting design from Figma…');
  let mcp = null;
  let mcpDesignContext = null;
  let figmaVariables = null;
  let mcpScreenshot = null;
  if (cfg.figmaSource !== 'rest') {
    mcp = await FigmaMcp.tryConnect(cfg.mcpUrl);
    if (mcp) {
      mcpDesignContext = await mcp.getDesignContext(cfg.nodeId);
      figmaVariables = await mcp.getVariableDefs(cfg.nodeId);
      mcpScreenshot = await mcp.getScreenshot(cfg.nodeId);
      log.ok(`MCP extraction: design context ${mcpDesignContext ? '✓' : '—'}, variables ${figmaVariables ? '✓' : '—'}, screenshot ${mcpScreenshot ? '✓' : '—'}`);
    } else if (cfg.figmaSource === 'mcp') {
      log.error('FIGMA_SOURCE=mcp but the local Figma MCP server is not reachable. Start the Figma desktop app → Preferences → Enable Dev Mode MCP server.');
      process.exit(1);
    }
  }
  if (!cfg.figmaToken) {
    log.error('FIGMA_TOKEN missing — the REST API is required for the node tree and asset export.');
    process.exit(1);
  }
  const rest = new FigmaRest(cfg.figmaToken);
  const nodes = await rest.getNodes(cfg.fileKey, cfg.nodeId);
  const entry = nodes?.[cfg.nodeId];
  if (!entry?.document) {
    log.error(`Node ${cfg.nodeId} not found in file ${cfg.fileKey}.`);
    process.exit(1);
  }
  const designName = entry.document.name;
  log.ok(`Fetched node tree for "${designName}" (${entry.document.type})`);

  // ── 2. Normalize ──────────────────────────────────────────────────────────
  log.step('Normalizing design (layout semantics, colors, typography, asset plan)…');
  const design = normalizeDesign(entry.document);
  if (!design.root) {
    // Checked before nextOutputDir so a doomed run doesn't consume an Output_N.
    log.error(`Node ${cfg.nodeId} ("${designName}") is hidden in Figma (visible: false). Unhide the layer or pass a visible node id via --node.`);
    process.exit(1);
  }
  log.ok(`Spec ready — ${design.assets.length} assets detected, ${design.tokens.palette.length} colors, ${design.tokens.textStyles.length} text styles`);

  // ── 3. Output folder + assets ────────────────────────────────────────────
  const outputDir = nextOutputDir(cfg.outputRoot, cfg.outputPrefix);
  log.step(`Output folder: ${outputDir}`);
  const assetManifest = await downloadAssets({ rest, fileKey: cfg.fileKey, assets: design.assets, outputDir });
  let reference = null;
  try {
    reference = await downloadReferenceScreenshot({ rest, fileKey: cfg.fileKey, nodeId: cfg.nodeId, nodeSize: design.rootSize, outputDir });
  } catch (err) {
    warnings.push(`Reference screenshot unavailable: ${err.message}`);
  }
  const figmaImage = reference?.jpg
    ? { buffer: reference.jpg, mediaType: 'image/jpeg' }
    : reference?.png
      ? { buffer: reference.png, mediaType: 'image/png' }
      : mcpScreenshot
        ? { buffer: mcpScreenshot, mediaType: 'image/png' }
        : null;

  // ── 4. Design tokens ──────────────────────────────────────────────────────
  log.step('Building design tokens (css/tokens.css)…');
  const { css: tokensCss } = buildDesignTokens(design.tokens, figmaVariables);
  writeFileEnsured(path.join(outputDir, 'css', 'tokens.css'), tokensCss);

  // eds-native.css: copy it next to tokens if we can find it
  const edsNativePath = findEdsNativeCss(cfg);
  if (edsNativePath) {
    fs.copyFileSync(edsNativePath, path.join(outputDir, 'css', 'eds-native.css'));
    log.ok(`eds-native.css copied from ${edsNativePath}`);
  } else {
    warnings.push('eds-native.css was not found on this machine (set EDS_NATIVE_CSS_PATH). Generated styles.css carries the full styling instead.');
    log.warn(warnings.at(-1));
  }

  // ── 5. EDS component matching ────────────────────────────────────────────
  log.step('Matching design sections against the 37 EDS components…');
  const components = loadEdsManifest(cfg);
  const matches = matchSections(design.root, components);
  const shortlist = shortlistedComponents(matches, components);
  matches.forEach((m) => {
    const top = m.candidates[0];
    log.info(`  section "${m.section}" → ${top ? `${top.name} (score ${top.score})` : 'no strong candidate'}`);
  });

  // ── 6. Generate ───────────────────────────────────────────────────────────
  const genClient = makeClient(cfg.anthropicKeyGenerator);
  const revClient = makeClient(cfg.anthropicKeyReviewer);
  cfg.model = await resolveModel(genClient, cfg.model);
  log.info(`Using model: ${cfg.model}`);
  const ctx = {
    designName,
    rootSize: design.rootSize,
    specJson: compactSpec(design.root, 140000),
    specJsonSmall: compactSpec(design.root, 60000),
    tokensCss,
    assetManifest,
    allComponents: components,
    matches,
    shortlist,
    mcpDesignContext,
    bootstrapCssUrl: cfg.bootstrapCssUrl,
    bootstrapJsUrl: cfg.bootstrapJsUrl,
    edsNativeAvailable: !!edsNativePath,
  };

  let files = await generate({ client: genClient, model: cfg.model, maxTokens: cfg.maxOutputTokens, ctx });
  writeGeneratedFiles(outputDir, files);

  // ── 7. Review loop (two-agent exact-match convergence) ───────────────────
  const iterations = [];
  let finalScore = null;
  let lastReview = null;
  let lastPixel = null;

  if (!cfg.skipReview) {
    for (let iter = 1; iter <= cfg.maxReviewIterations; iter++) {
      let render = null;
      if (cfg.visualDiff) {
        render = await renderGeneratedPage(outputDir, {
          width: design.rootSize?.w || 1440,
          scale: reference?.pngScale ?? 1,
        });
      }
      const diff = render?.png && reference?.png ? await pixelMismatch(reference.png, render.png, outputDir) : null;
      lastPixel = diff?.pct ?? null;
      if (lastPixel != null) log.info(`Pixel mismatch vs Figma: ${lastPixel.toFixed(2)}%`);
      const renderImage = render?.jpg ? { buffer: render.jpg, mediaType: 'image/jpeg' } : null;
      const diffImage = diff?.diffPng ? { buffer: diff.diffPng, mediaType: 'image/png' } : null;

      lastReview = await review({
        client: revClient,
        model: cfg.model,
        ctx,
        files,
        figmaImage,
        renderImage,
        diffImage,
        pixelMismatchPct: lastPixel,
      });
      const sev = (s) => lastReview.issues.filter((i) => i.severity === s).length;
      iterations.push({ score: lastReview.score, issueCount: lastReview.issues.length, critical: sev('critical'), major: sev('major'), minor: sev('minor') });
      finalScore = lastReview.score;

      // Acceptance is issue-count driven: iterate until the reviewer has
      // nothing actionable left (<= REVIEW_TARGET_ISSUES, default 0).
      if (lastReview.issues.length <= cfg.targetIssues) {
        log.ok(`${lastReview.issues.length} issue(s) ≤ target ${cfg.targetIssues} — accepted at score ${lastReview.score}/100.`);
        break;
      }
      if (iter === cfg.maxReviewIterations) {
        log.warn(`Max review iterations (${cfg.maxReviewIterations}) reached — ${lastReview.issues.length} issue(s) remain at score ${lastReview.score}. Raise MAX_REVIEW_ITERATIONS to keep going.`);
        break;
      }
      files = await refine({
        client: genClient,
        model: cfg.model,
        maxTokens: cfg.maxOutputTokens,
        ctx,
        files,
        review: lastReview,
        pixelMismatchPct: lastPixel,
        figmaImage,
        renderImage,
        diffImage,
      });
      writeGeneratedFiles(outputDir, files);
    }
  }

  // ── 8. Report ─────────────────────────────────────────────────────────────
  let componentMap = null;
  try {
    componentMap = JSON.parse(files['component-map.json'] || 'null');
    if (!Array.isArray(componentMap?.mappings)) componentMap = null;
    else componentMap.mappings = componentMap.mappings.filter((m) => m && typeof m === 'object');
  } catch {
    warnings.push('component-map.json produced by the generator was not valid JSON.');
  }
  writeReport(outputDir, {
    design: { name: designName, fileKey: cfg.fileKey, nodeId: cfg.nodeId, source: mcp ? 'MCP + REST' : 'REST' },
    generatedAt: new Date().toISOString(),
    finalScore,
    threshold: cfg.matchThreshold,
    pixelMismatchPct: lastPixel,
    iterations,
    componentMap,
    assets: assetManifest,
    warnings,
    remainingIssues: lastReview?.issues || [],
  });

  await mcp?.close();
  console.log(c.bold(`\n╚══ Done → ${outputDir} ══╝`));
  console.log(`   Open ${path.join(outputDir, 'index.html')} in a browser.`);
}

// Run only when invoked directly (node src/index.js), not when imported.
if (process.argv[1] && import.meta.url === pathToFileURL(process.argv[1]).href) {
  main().catch((err) => {
    log.error(err.stack || err.message);
    process.exit(1);
  });
}
