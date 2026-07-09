import path from 'node:path';
import crypto from 'node:crypto';
import { writeFileEnsured, safeFileName } from '../utils/fsx.js';
import { log } from '../utils/log.js';

/**
 * Downloads every detected asset into <outputDir>/assets/{images|icons|vectors}.
 *  - image fills  -> original bitmap via the file's imageRef URLs (best quality)
 *  - icons/vector -> server-rendered SVG
 *  - fallback     -> PNG render at 2x
 * Deduplicates so the same asset is never stored twice:
 *  - nodeId    -> a node already handled (e.g. listed as both svg and png) is skipped
 *  - imageRef  -> the same bitmap fill shared by many nodes is downloaded once
 *  - md5 hash  -> byte-identical content (across formats/renders) maps to one file
 * Returns the asset manifest with relative paths the generated HTML must use.
 */
export async function downloadAssets({ rest, fileKey, assets, outputDir }) {
  if (!assets.length) return [];
  const taken = new Set();
  const manifest = [];
  const nodeToFile = new Map(); // nodeId   -> relative file path
  const refToFile = new Map(); // imageRef -> relative file path
  const hashToFile = new Map(); // md5      -> relative file path

  const store = (asset, buf, relFileFn) => {
    const h = crypto.createHash('md5').update(buf).digest('hex');
    let file = hashToFile.get(h);
    if (!file) {
      file = relFileFn();
      writeFileEnsured(path.join(outputDir, file), buf);
      hashToFile.set(h, file);
    }
    nodeToFile.set(asset.nodeId, file);
    if (asset.imageRef) refToFile.set(asset.imageRef, file);
    manifest.push({ ...asset, file });
    return file;
  };

  const byExport = {
    imageRef: assets.filter((a) => a.export === 'imageRef' && a.imageRef),
    svg: assets.filter((a) => a.export === 'svg'),
    png: assets.filter((a) => a.export === 'png' || (a.export === 'imageRef' && !a.imageRef)),
  };

  // 1) Original image fills
  let fillUrls = {};
  if (byExport.imageRef.length) {
    try {
      fillUrls = await rest.getImageFills(fileKey);
    } catch (err) {
      log.warn(`Could not fetch original image fills (${err.message}); falling back to PNG renders.`);
      byExport.png.push(...byExport.imageRef);
      byExport.imageRef = [];
    }
  }
  for (const asset of byExport.imageRef) {
    if (nodeToFile.has(asset.nodeId)) continue;
    // Same bitmap fill reused by several nodes -> reuse the already-saved file.
    const existing = refToFile.get(asset.imageRef);
    if (existing) {
      nodeToFile.set(asset.nodeId, existing);
      manifest.push({ ...asset, file: existing });
      continue;
    }
    const url = fillUrls[asset.imageRef];
    if (!url) {
      byExport.png.push(asset);
      continue;
    }
    try {
      const buf = await rest.download(url);
      const ext = sniffExt(buf, 'png');
      store(asset, buf, () => `assets/images/${safeFileName(asset.name, ext, taken)}`);
    } catch (err) {
      log.warn(`Image fill download failed for "${asset.name}": ${err.message}`);
      byExport.png.push(asset);
    }
  }

  // 2) SVG renders (icons & vector art)
  const svgPending = byExport.svg.filter((a) => !nodeToFile.has(a.nodeId));
  if (svgPending.length) {
    let urls = {};
    try {
      urls = await rest.renderImages(fileKey, svgPending.map((a) => a.nodeId), { format: 'svg' });
    } catch (err) {
      log.warn(`SVG render batch failed (${err.message}); falling back to PNG renders.`);
    }
    for (const asset of svgPending) {
      const url = urls[asset.nodeId];
      if (!url) {
        byExport.png.push(asset);
        continue;
      }
      try {
        const buf = await rest.download(url);
        const sub = asset.kind === 'icon' ? 'icons' : 'vectors';
        store(asset, buf, () => `assets/${sub}/${safeFileName(asset.name, 'svg', taken)}`);
      } catch (err) {
        log.warn(`SVG export failed for "${asset.name}": ${err.message}`);
        byExport.png.push(asset);
      }
    }
  }

  // 3) PNG fallback renders — nodes already saved (e.g. as SVG or imageRef) are skipped.
  const pngPending = byExport.png.filter((a) => !nodeToFile.has(a.nodeId));
  if (pngPending.length) {
    let urls = {};
    try {
      urls = await rest.renderImages(fileKey, pngPending.map((a) => a.nodeId), { format: 'png', scale: 2 });
    } catch (err) {
      log.warn(`PNG render batch failed (${err.message}); ${pngPending.length} asset(s) skipped.`);
    }
    for (const asset of pngPending) {
      const url = urls[asset.nodeId];
      if (!url) {
        log.warn(`Figma could not render "${asset.name}" (${asset.nodeId}); skipped.`);
        continue;
      }
      try {
        const buf = await rest.download(url);
        store(asset, buf, () => `assets/images/${safeFileName(asset.name, 'png', taken)}`);
      } catch (err) {
        log.warn(`PNG export failed for "${asset.name}": ${err.message}`);
      }
    }
  }

  log.ok(`Downloaded ${manifest.length}/${assets.length} assets into ${path.join(outputDir, 'assets')}`);
  return manifest;
}

/**
 * Exports the reference screenshot of the whole node for the review loop.
 * Claude vision rejects images over 8000px / ~5MB, and tall landing pages
 * easily exceed both at 2x — so the scale is fitted to the node size and a
 * compact JPEG is produced for the reviewer alongside the PNG used for
 * pixel-diffing.
 */
export async function downloadReferenceScreenshot({ rest, fileKey, nodeId, nodeSize, outputDir }) {
  const maxSide = Math.max(nodeSize?.w || 1440, nodeSize?.h || 1440);
  const pngScale = Math.min(1, 3800 / maxSide);
  const jpgScale = Math.min(1, 2800 / maxSide);

  const [pngUrls, jpgUrls] = await Promise.all([
    rest.renderImages(fileKey, [nodeId], { format: 'png', scale: pngScale }),
    rest.renderImages(fileKey, [nodeId], { format: 'jpg', scale: jpgScale }),
  ]);

  let png = null;
  let jpg = null;
  if (pngUrls[nodeId]) {
    png = await rest.download(pngUrls[nodeId]);
    writeFileEnsured(path.join(outputDir, 'reference', 'figma-design.png'), png);
  }
  if (jpgUrls[nodeId]) {
    jpg = await rest.download(jpgUrls[nodeId]);
  }
  return { png, jpg, pngScale };
}

function sniffExt(buf, dflt) {
  if (buf.length > 3 && buf[0] === 0xff && buf[1] === 0xd8) return 'jpg';
  if (buf.length > 7 && buf[1] === 0x50 && buf[2] === 0x4e && buf[3] === 0x47) return 'png';
  if (buf.length > 11 && buf.toString('ascii', 8, 12) === 'WEBP') return 'webp';
  if (buf.length > 4 && buf.toString('ascii', 0, 5) === '<?xml') return 'svg';
  if (buf.length > 3 && buf.toString('ascii', 0, 4) === 'GIF8') return 'gif';
  return dflt;
}
