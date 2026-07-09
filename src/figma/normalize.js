/**
 * Normalizes a raw Figma REST node tree into:
 *  - a compact design spec (auto-layout -> flexbox semantics, colors as hex,
 *    typography, borders, shadows) sized for an LLM prompt
 *  - an asset plan: which nodes are images / icons / vector art and how to
 *    export each one (original image fill vs SVG vs PNG render)
 *  - token inputs: palette, text styles, spacing scale, radii, shadows
 */

const PURE_VECTOR_TYPES = new Set(['VECTOR', 'BOOLEAN_OPERATION', 'STAR', 'LINE', 'POLYGON', 'REGULAR_POLYGON']);
const SHAPE_TYPES = new Set([...PURE_VECTOR_TYPES, 'ELLIPSE', 'RECTANGLE']);
const CONTAINER_TYPES = new Set(['FRAME', 'GROUP', 'INSTANCE', 'COMPONENT', 'COMPONENT_SET', 'SECTION']);
const ICON_NAME_RE = /\b(icon|logo|glyph|vector|illustration|arrow|chevron|badge)\b/i;

export function rgbaToHex(color, opacity = 1) {
  if (!color) return null;
  const a = (color.a ?? 1) * opacity;
  const to255 = (v) => Math.round((v ?? 0) * 255);
  const hex = [color.r, color.g, color.b].map((v) => to255(v).toString(16).padStart(2, '0')).join('');
  if (a >= 0.999) return `#${hex}`;
  return `#${hex}${Math.round(a * 255).toString(16).padStart(2, '0')}`;
}

function visibleFills(node) {
  return (node.fills || []).filter((f) => f.visible !== false && f.type);
}

function hasImageFill(node) {
  return visibleFills(node).some((f) => f.type === 'IMAGE');
}

/** True when every visible node in the subtree is a shape (no text, no image fills). */
function isVectorOnlySubtree(node) {
  if (node.visible === false) return true;
  if (node.type === 'TEXT') return false;
  if (hasImageFill(node)) return false;
  if (SHAPE_TYPES.has(node.type)) return true;
  if (CONTAINER_TYPES.has(node.type) || node.type === 'GROUP') {
    const kids = node.children || [];
    if (!kids.length) return false;
    return kids.every(isVectorOnlySubtree);
  }
  return false;
}

function box(node) {
  const b = node.absoluteBoundingBox || node.absoluteRenderBounds;
  if (!b) return null;
  return { x: b.x, y: b.y, w: b.width, h: b.height };
}

const round = (v) => (typeof v === 'number' ? Math.round(v * 10) / 10 : v);

export function normalizeDesign(rootNode) {
  const assets = [];
  const assetByNode = new Map();
  const assetBySig = new Map(); // "kind|name|WxH" (or componentId) -> asset
  const palette = new Map(); // hex -> count
  const textStyles = new Map(); // signature -> {style, count, sample}
  const spacing = new Map(); // px -> count
  const radii = new Set();
  const shadows = new Set();
  const fontFamilies = new Map();

  let assetSeq = 0;
  function registerAsset(node, kind, exportAs, imageRef = null) {
    const existing = assetByNode.get(node.id);
    if (existing) return existing.id;
    const b = box(node) || { w: 0, h: 0 };
    // The same icon placed N times in the design is N distinct nodes whose
    // SVG renders differ by a few bytes (fractional coords), so byte-hash
    // dedup can't catch them. Dedup here by identity instead: the component
    // they're an instance of, or name + rendered size for plain vectors.
    let sig = null;
    if (exportAs === 'svg') {
      sig = node.componentId
        ? `cmp|${node.componentId}`
        : `${kind}|${(node.name || '').toLowerCase()}|${round(b.w)}x${round(b.h)}`;
      const dupe = assetBySig.get(sig);
      if (dupe) {
        assetByNode.set(node.id, dupe);
        return dupe.id;
      }
    }
    const asset = {
      id: `a${++assetSeq}`,
      nodeId: node.id,
      name: node.name || kind,
      kind, // image | icon | vector
      export: exportAs, // imageRef | svg | png
      imageRef,
      w: round(b.w),
      h: round(b.h),
    };
    assets.push(asset);
    assetByNode.set(node.id, asset);
    if (sig) assetBySig.set(sig, asset);
    return asset.id;
  }

  function noteColor(hex) {
    if (!hex) return;
    palette.set(hex, (palette.get(hex) || 0) + 1);
  }
  function noteSpacing(v) {
    if (typeof v === 'number' && v > 0) spacing.set(Math.round(v), (spacing.get(Math.round(v)) || 0) + 1);
  }

  function mapFills(node) {
    const out = [];
    for (const f of visibleFills(node)) {
      if (f.type === 'SOLID') {
        const hex = rgbaToHex(f.color, f.opacity ?? 1);
        noteColor(hex);
        out.push({ type: 'solid', hex });
      } else if (f.type.startsWith('GRADIENT')) {
        const stops = (f.gradientStops || []).map((s) => ({
          hex: rgbaToHex(s.color),
          pos: round(s.position),
        }));
        stops.forEach((s) => noteColor(s.hex));
        out.push({ type: f.type.replace('GRADIENT_', 'gradient-').toLowerCase(), stops });
      } else if (f.type === 'IMAGE') {
        out.push({ type: 'image', imageRef: f.imageRef, scaleMode: (f.scaleMode || 'FILL').toLowerCase() });
      }
    }
    return out;
  }

  function mapStroke(node) {
    const strokes = (node.strokes || []).filter((s) => s.visible !== false && s.type === 'SOLID');
    if (!strokes.length && node.cornerRadius === undefined && !node.rectangleCornerRadii) return null;
    const stroke = {};
    if (strokes.length) {
      stroke.color = rgbaToHex(strokes[0].color, strokes[0].opacity ?? 1);
      stroke.weight = round(node.strokeWeight ?? 1);
      noteColor(stroke.color);
    }
    const r = node.rectangleCornerRadii || (node.cornerRadius !== undefined ? [node.cornerRadius] : null);
    if (r) {
      stroke.radius = r.length === 1 || r.every((v) => v === r[0]) ? round(r[0]) : r.map(round);
      const rv = Array.isArray(stroke.radius) ? stroke.radius[0] : stroke.radius;
      if (rv > 0) radii.add(Math.round(rv));
    }
    return Object.keys(stroke).length ? stroke : null;
  }

  function mapEffects(node) {
    const fx = (node.effects || []).filter((e) => e.visible !== false);
    const out = [];
    for (const e of fx) {
      if (e.type === 'DROP_SHADOW' || e.type === 'INNER_SHADOW') {
        const s = `${e.type === 'INNER_SHADOW' ? 'inset ' : ''}${round(e.offset?.x ?? 0)}px ${round(e.offset?.y ?? 0)}px ${round(e.radius ?? 0)}px ${round(e.spread ?? 0)}px ${rgbaToHex(e.color)}`;
        shadows.add(s);
        out.push(s);
      } else if (e.type === 'LAYER_BLUR') {
        out.push(`blur(${round(e.radius)}px)`);
      } else if (e.type === 'BACKGROUND_BLUR') {
        out.push(`backdrop-blur(${round(e.radius)}px)`);
      }
    }
    return out.length ? out : null;
  }

  function mapLayout(node) {
    if (!node.layoutMode || node.layoutMode === 'NONE') return null;
    const justifyMap = { MIN: 'flex-start', CENTER: 'center', MAX: 'flex-end', SPACE_BETWEEN: 'space-between' };
    const alignMap = { MIN: 'flex-start', CENTER: 'center', MAX: 'flex-end', BASELINE: 'baseline' };
    const layout = {
      mode: node.layoutMode === 'HORIZONTAL' ? 'row' : 'column',
      gap: round(node.itemSpacing ?? 0),
      padding: [node.paddingTop, node.paddingRight, node.paddingBottom, node.paddingLeft].map((v) => round(v ?? 0)),
      justify: justifyMap[node.primaryAxisAlignItems] || 'flex-start',
      align: alignMap[node.counterAxisAlignItems] || 'flex-start',
    };
    if (node.layoutWrap === 'WRAP') layout.wrap = true;
    noteSpacing(layout.gap);
    layout.padding.forEach(noteSpacing);
    return layout;
  }

  function mapSizing(node) {
    const m = { FIXED: 'fixed', HUG: 'hug', FILL: 'fill' };
    const h = m[node.layoutSizingHorizontal];
    const v = m[node.layoutSizingVertical];
    const out = {};
    if (h) out.h = h;
    if (v) out.v = v;
    if (node.layoutGrow) out.grow = node.layoutGrow;
    if (node.layoutAlign === 'STRETCH') out.stretch = true;
    return Object.keys(out).length ? out : null;
  }

  function mapText(node) {
    const s = node.style || {};
    const fillHex = visibleFills(node).find((f) => f.type === 'SOLID');
    const color = fillHex ? rgbaToHex(fillHex.color, fillHex.opacity ?? 1) : null;
    noteColor(color);
    const text = {
      content: node.characters ?? '',
      font: s.fontFamily,
      weight: s.fontWeight,
      size: round(s.fontSize),
      lineHeight: s.lineHeightPx ? round(s.lineHeightPx) : undefined,
      letterSpacing: s.letterSpacing ? round(s.letterSpacing) : undefined,
      align: (s.textAlignHorizontal || 'LEFT').toLowerCase(),
      case: s.textCase && s.textCase !== 'ORIGINAL' ? s.textCase.toLowerCase() : undefined,
      decoration: s.textDecoration && s.textDecoration !== 'NONE' ? s.textDecoration.toLowerCase() : undefined,
      color,
    };
    if (s.fontFamily) fontFamilies.set(s.fontFamily, (fontFamilies.get(s.fontFamily) || 0) + 1);
    const sig = `${text.font}|${text.weight}|${text.size}|${text.lineHeight}`;
    const entry = textStyles.get(sig) || { ...text, count: 0, sample: text.content.slice(0, 40) };
    entry.count++;
    textStyles.set(sig, entry);
    return text;
  }

  /** Structural signature used to spot repeated siblings (card grids, list items...). */
  function signature(node) {
    const kids = node.children || [];
    return `${node.type}:${kids.length}:${kids.map((k) => k.type).join(',')}`;
  }

  function walk(node, parentBox) {
    if (node.visible === false) return null;
    const b = box(node);
    const spec = {
      name: node.name,
      type: node.type,
    };
    if (b) {
      spec.frame = {
        x: round(b.x - (parentBox?.x ?? b.x)),
        y: round(b.y - (parentBox?.y ?? b.y)),
        w: round(b.w),
        h: round(b.h),
      };
    }
    if (node.opacity !== undefined && node.opacity < 1) spec.opacity = round(node.opacity);

    // --- asset detection ---
    // TEXT is excluded: a TEXT node with an image paint (image-masked text)
    // must keep its characters/typography, not become a plain image asset.
    const isLeafImage = node.type !== 'TEXT' && hasImageFill(node) && !(node.children || []).length;
    if (isLeafImage) {
      const fills = mapFills(node);
      const img = fills.find((f) => f.type === 'image');
      spec.asset = registerAsset(node, 'image', img?.imageRef ? 'imageRef' : 'png', img?.imageRef ?? null);
      spec.role = 'image';
      // Fills stacked above the image (scrims/tints) and effects (shadows)
      // still matter — Figma paints fills bottom-to-top, so bg here is an overlay.
      const overlays = fills.filter((f) => f.type !== 'image');
      if (overlays.length) spec.bg = overlays;
      const stroke = mapStroke(node);
      if (stroke) spec.border = stroke;
      const fx = mapEffects(node);
      if (fx) spec.effects = fx;
      return spec;
    }
    if (SHAPE_TYPES.has(node.type) || CONTAINER_TYPES.has(node.type) || node.type === 'GROUP') {
      const vectorOnly = isVectorOnlySubtree(node);
      const small = b && b.w <= 96 && b.h <= 96;
      const named = ICON_NAME_RE.test(node.name || '');
      if (vectorOnly && (PURE_VECTOR_TYPES.has(node.type) || small || named || !(node.children || []).some((c) => c.type === 'TEXT'))) {
        // Export the whole subtree as one SVG; prune children from the spec.
        if (PURE_VECTOR_TYPES.has(node.type) || small || named) {
          spec.asset = registerAsset(node, small || named ? 'icon' : 'vector', 'svg');
          spec.role = small || named ? 'icon' : 'vector';
          return spec;
        }
      }
    }

    // --- visual properties ---
    const fills = mapFills(node);
    const imageFill = fills.find((f) => f.type === 'image');
    if (imageFill) {
      // container with a background image + real children: export the fill, keep children
      spec.bgImage = registerAsset(node, 'image', imageFill.imageRef ? 'imageRef' : 'png', imageFill.imageRef);
      spec.bgImageMode = imageFill.scaleMode;
    }
    const solidsAndGradients = fills.filter((f) => f.type !== 'image');
    if (solidsAndGradients.length) spec.bg = solidsAndGradients;

    const stroke = mapStroke(node);
    if (stroke) spec.border = stroke;
    const fx = mapEffects(node);
    if (fx) spec.effects = fx;

    const layout = mapLayout(node);
    if (layout) spec.layout = layout;
    const sizing = mapSizing(node);
    if (sizing) spec.sizing = sizing;
    if (node.clipsContent) spec.clips = true;

    if (node.type === 'TEXT') {
      spec.text = mapText(node);
      return spec;
    }

    // --- children ---
    // Signatures are collected in the same pass as the walk so invisible
    // (filtered-out) children can't misalign spec<->signature pairing.
    const kids = [];
    const sigs = [];
    for (const c of node.children || []) {
      const childSpec = walk(c, b);
      if (childSpec) {
        kids.push(childSpec);
        sigs.push(signature(c));
      }
    }
    if (kids.length) {
      spec.children = kids;
      // repeated-sibling hint (card grids, nav items, list rows)
      const counts = {};
      sigs.forEach((s) => (counts[s] = (counts[s] || 0) + 1));
      const [topSig, topCount] = Object.entries(counts).sort((a, b2) => b2[1] - a[1])[0] || [];
      if (topCount >= 3) spec.repeats = { count: topCount, of: topSig };
    }
    return spec;
  }

  const rootBox = box(rootNode);
  const spec = walk(rootNode, null);

  return {
    root: spec,
    rootSize: rootBox ? { w: round(rootBox.w), h: round(rootBox.h) } : null,
    assets,
    tokens: {
      palette: [...palette.entries()].sort((a, b) => b[1] - a[1]).map(([hex, count]) => ({ hex, count })),
      textStyles: [...textStyles.values()].sort((a, b) => b.count - a.count),
      fontFamilies: [...fontFamilies.entries()].sort((a, b) => b[1] - a[1]).map(([f]) => f),
      spacingScale: [...spacing.keys()].sort((a, b) => a - b),
      radii: [...radii].sort((a, b) => a - b),
      shadows: [...shadows],
    },
  };
}

/**
 * Serialize the spec within a character budget. Progressively lowers the depth
 * cap (replacing pruned subtrees with a summary) until the JSON fits — keeps
 * the LLM prompt bounded on huge designs.
 */
export function compactSpec(specRoot, budgetChars = 140000) {
  const clip = (node, depth, maxDepth) => {
    const out = { ...node };
    if (out.text?.content && out.text.content.length > 240) {
      out.text = { ...out.text, content: out.text.content.slice(0, 240) + '…' };
    }
    if (node.children) {
      if (depth >= maxDepth) {
        out.children = undefined;
        out.omitted = `${countNodes(node) - 1} descendant nodes omitted (depth cap)`;
      } else {
        out.children = node.children.map((c) => clip(c, depth + 1, maxDepth));
      }
    }
    return out;
  };
  const countNodes = (n) => 1 + (n.children || []).reduce((acc, c) => acc + countNodes(c), 0);

  for (let maxDepth = 24; maxDepth >= 2; maxDepth -= 2) {
    const json = JSON.stringify(clip(specRoot, 0, maxDepth), (k, v) => (v === undefined ? undefined : v));
    if (json.length <= budgetChars) return json;
  }
  return JSON.stringify(clip(specRoot, 0, 1));
}
