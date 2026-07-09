import fs from 'node:fs';
import path from 'node:path';
import { writeFileEnsured } from '../utils/fsx.js';
import { log } from '../utils/log.js';

/** Locations where the shared EDS stylesheet might live on this machine. */
export function findEdsNativeCss(cfg) {
  const candidates = [
    cfg.edsNativeCssPath,
    path.join(cfg.cwd, 'assets', 'eds', 'styles', 'eds-native.css'),
    path.join(cfg.cwd, 'eds-native.css'),
    path.join(cfg.cwd, '..', 'assets', 'eds', 'styles', 'eds-native.css'),
  ].filter(Boolean);
  for (const p of candidates) {
    try {
      if (fs.existsSync(p) && fs.statSync(p).isFile()) return p;
    } catch {
      /* keep looking */
    }
  }
  return null;
}

const WINDOWS_INVALID = /[<>:"|?*]/;
const RESERVED_NAMES = /^(con|prn|aux|nul|com\d|lpt\d)$/i;
const hasControlChars = (s) => [...s].some((ch) => ch.charCodeAt(0) < 32);

/** LLM-produced file names are untrusted: keep every write inside outputDir. */
function isSafeRelPath(outputDir, rel) {
  if (typeof rel !== 'string' || !rel.trim()) return false;
  const posix = rel.replace(/\\/g, '/');
  if (posix.startsWith('/') || /^[a-z]:/i.test(posix)) return false;
  const segments = posix.split('/');
  if (segments.some((s) => s === '..' || s === '' || WINDOWS_INVALID.test(s) || hasControlChars(s) || RESERVED_NAMES.test(s.split('.')[0]))) return false;
  const dest = path.resolve(outputDir, posix);
  return dest.startsWith(path.resolve(outputDir) + path.sep);
}

export function writeGeneratedFiles(outputDir, files) {
  let written = 0;
  for (const [rel, content] of Object.entries(files)) {
    if (!isSafeRelPath(outputDir, rel)) {
      log.warn(`Skipping generated file with unsafe path: "${rel}"`);
      continue;
    }
    writeFileEnsured(path.join(outputDir, rel.replace(/\\/g, '/')), content);
    written++;
  }
  log.ok(`Wrote ${written} generated files to ${outputDir}`);
}

export function writeReport(outputDir, report) {
  writeFileEnsured(path.join(outputDir, 'report.json'), JSON.stringify(report, null, 2));

  const md = [];
  md.push(`# Figma → EDS Conversion Report`);
  md.push(`- **Design:** ${report.design.name} (${report.design.fileKey} / node ${report.design.nodeId})`);
  md.push(`- **Source:** ${report.design.source}`);
  md.push(`- **Generated:** ${report.generatedAt}`);
  md.push(`- **Final score:** ${report.finalScore ?? 'n/a'}/100 (threshold ${report.threshold})${report.pixelMismatchPct != null ? ` — pixel mismatch ${report.pixelMismatchPct.toFixed(2)}%` : ''}`);
  md.push(`- **Review iterations:** ${report.iterations.length}`);
  md.push('');
  md.push(`## Score history`);
  report.iterations.forEach((it, i) => {
    md.push(`${i + 1}. score **${it.score}** — ${it.issueCount} issues (${it.critical} critical, ${it.major} major, ${it.minor} minor)`);
  });
  if (Array.isArray(report.componentMap?.mappings) && report.componentMap.mappings.length) {
    md.push('', `## EDS component mapping`);
    for (const m of report.componentMap.mappings) {
      if (!m || typeof m !== 'object') continue;
      md.push(`- **${m.designSection}** → \`${m.edsComponent}\`${Array.isArray(m.modifiers) && m.modifiers.length ? ` (${m.modifiers.join(', ')})` : ''} — confidence ${m.confidence}%${m.notes ? ` — ${m.notes}` : ''}`);
    }
  }
  md.push('', `## Assets (${report.assets.length})`);
  for (const a of report.assets) md.push(`- \`${a.file}\` — ${a.kind}, ${a.w}×${a.h} ("${a.name}")`);
  if (report.warnings?.length) {
    md.push('', `## Warnings`);
    report.warnings.forEach((w) => md.push(`- ⚠ ${w}`));
  }
  if (report.remainingIssues?.length) {
    md.push('', `## Remaining review issues`);
    report.remainingIssues.forEach((i) => {
      if (!i || typeof i !== 'object') return;
      md.push(`- **[${i.severity}] ${i.area}:** ${i.description}`);
    });
  }
  writeFileEnsured(path.join(outputDir, 'REPORT.md'), md.join('\n') + '\n');
  log.ok(`Report written: ${path.join(outputDir, 'REPORT.md')}`);
}
