/**
 * Builds css/tokens.css from the normalized design + (optionally) real Figma
 * variable definitions from the MCP server. Every color, font size, spacing,
 * radius and shadow the generator uses MUST come from these custom properties,
 * which is what keeps the generated CSS from drifting away from the design.
 */

function slug(s) {
  return String(s).toLowerCase().replace(/[^a-z0-9]+/g, '-').replace(/^-+|-+$/g, '');
}

export function buildDesignTokens(tokens, figmaVariables = null) {
  const lines = [];
  const map = { colors: {}, fonts: {}, text: {}, spacing: {}, radius: {}, shadows: {} };

  lines.push('/* Design tokens extracted from Figma — single source of truth for the generated CSS. */');
  lines.push(':root {');

  // --- colors ---
  lines.push('  /* colors (ordered by frequency in the design) */');
  tokens.palette.forEach((p, i) => {
    const name = `--fig-color-${i === 0 ? 'primary' : i === 1 ? 'secondary' : slug(p.hex.replace('#', 'c-'))}`;
    lines.push(`  ${name}: ${p.hex}; /* used ${p.count}x */`);
    map.colors[p.hex] = name;
  });

  // --- typography ---
  lines.push('  /* typography */');
  tokens.fontFamilies.forEach((f, i) => {
    const name = i === 0 ? '--fig-font-primary' : `--fig-font-${slug(f)}`;
    lines.push(`  ${name}: '${f}', sans-serif;`);
    map.fonts[f] = name;
  });
  const seenSizes = new Set();
  tokens.textStyles.forEach((t) => {
    if (!t.size || seenSizes.has(t.size)) return;
    seenSizes.add(t.size);
    const name = `--fig-text-${String(t.size).replace('.', '_')}`;
    lines.push(`  ${name}: ${t.size}px;${t.lineHeight ? ` /* line-height ~${t.lineHeight}px */` : ''}`);
    map.text[t.size] = name;
  });

  // --- spacing scale ---
  lines.push('  /* spacing scale */');
  tokens.spacingScale.forEach((s) => {
    const name = `--fig-space-${s}`;
    lines.push(`  ${name}: ${s}px;`);
    map.spacing[s] = name;
  });

  // --- radii ---
  if (tokens.radii.length) {
    lines.push('  /* border radii */');
    tokens.radii.forEach((r) => {
      const name = `--fig-radius-${r}`;
      lines.push(`  ${name}: ${r}px;`);
      map.radius[r] = name;
    });
  }

  // --- shadows ---
  if (tokens.shadows.length) {
    lines.push('  /* shadows */');
    tokens.shadows.forEach((s, i) => {
      const name = `--fig-shadow-${i + 1}`;
      lines.push(`  ${name}: ${s};`);
      map.shadows[s] = name;
    });
  }

  // --- real Figma variables (from the local MCP server), highest fidelity ---
  if (figmaVariables && typeof figmaVariables === 'object') {
    lines.push('  /* Figma variable definitions (Dev Mode MCP) */');
    const used = new Map();
    for (const [key, value] of Object.entries(flatten(figmaVariables))) {
      let name = `--fig-var-${slug(key)}`;
      if (used.has(name)) {
        if (used.get(name) === String(value)) continue; // exact duplicate
        let i = 2;
        while (used.has(`${name}-${i}`)) i++;
        name = `${name}-${i}`;
      }
      used.set(name, String(value));
      lines.push(`  ${name}: ${cssSafeValue(value)};`);
    }
  }

  lines.push('}');
  return { css: lines.join('\n') + '\n', map };
}

/**
 * Values coming from Figma variables are untrusted text; a stray '}' or '/*'
 * would structurally corrupt tokens.css. Numbers and simple CSS-safe strings
 * pass through; anything else is serialized as a quoted CSS string (where
 * braces and comment openers are inert).
 */
function cssSafeValue(value) {
  if (typeof value === 'number') return value;
  const s = String(value);
  if (/^[^;{}"'\\]*$/.test(s) && !s.includes('/*')) return s;
  return `"${s.replace(/\\/g, '\\\\').replace(/"/g, '\\"').replace(/\r?\n/g, '\\a ')}"`;
}

function flatten(obj, prefix = '', out = {}) {
  for (const [k, v] of Object.entries(obj)) {
    const key = prefix ? `${prefix}-${k}` : k;
    if (v && typeof v === 'object' && !Array.isArray(v)) flatten(v, key, out);
    else if (typeof v === 'string' || typeof v === 'number') out[key] = v;
  }
  return out;
}
