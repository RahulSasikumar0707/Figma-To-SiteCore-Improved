import fs from 'node:fs';
import path from 'node:path';

export function ensureDir(dir) {
  fs.mkdirSync(dir, { recursive: true });
  return dir;
}

export function writeFileEnsured(filePath, data) {
  ensureDir(path.dirname(filePath));
  fs.writeFileSync(filePath, data);
  return filePath;
}

/**
 * Requirement: first run stores results in Output_1, second in Output_2, ...
 * Scans the output root for existing "<prefix>_<n>" folders and atomically
 * creates the next one — a non-recursive mkdir fails with EEXIST if a
 * concurrent run grabbed the same number, in which case we advance to n+1.
 * (String matching instead of a RegExp keeps prefixes with metacharacters safe.)
 */
export function nextOutputDir(root, prefix = 'Output') {
  ensureDir(root);
  let max = 0;
  for (const entry of fs.readdirSync(root, { withFileTypes: true })) {
    if (!entry.isDirectory()) continue;
    if (!entry.name.startsWith(prefix + '_')) continue;
    const suffix = entry.name.slice(prefix.length + 1);
    if (/^\d+$/.test(suffix)) max = Math.max(max, parseInt(suffix, 10));
  }
  for (let n = max + 1; ; n++) {
    const dir = path.join(root, `${prefix}_${n}`);
    try {
      fs.mkdirSync(dir); // non-recursive: atomic, throws EEXIST on a race
      return dir;
    } catch (err) {
      if (err.code !== 'EEXIST') throw err;
    }
  }
}

/** Turn a Figma layer name into a safe unique file name. */
export function safeFileName(name, ext, taken = new Set()) {
  let base = String(name || 'asset')
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, '-')
    .replace(/^-+|-+$/g, '')
    .slice(0, 60) || 'asset';
  let candidate = `${base}.${ext}`;
  let i = 2;
  while (taken.has(candidate)) {
    candidate = `${base}-${i}.${ext}`;
    i++;
  }
  taken.add(candidate);
  return candidate;
}

/**
 * Returns null only when the file doesn't exist; a file that exists but can't
 * be parsed throws, so callers can tell "missing" from "corrupted" instead of
 * silently discarding curated data.
 */
export function readJsonIfExists(filePath) {
  let raw;
  try {
    raw = fs.readFileSync(filePath, 'utf8');
  } catch (err) {
    if (err.code === 'ENOENT') return null;
    throw err;
  }
  return JSON.parse(raw.replace(/^﻿/, ''));
}
