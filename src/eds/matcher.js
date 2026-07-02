/**
 * Algorithmic pre-matching between Figma design sections and the 37 EDS
 * components. Produces a scored shortlist per top-level design section; the
 * generator LLM makes the final call, but only from grounded candidates whose
 * real EDS snippets are included in its prompt.
 *
 * Scoring blends:
 *  - keyword overlap between component keywords and the section's layer names + text
 *  - structural heuristics (repeated siblings -> cards/carousel, image+heading+cta -> hero, ...)
 */

const STRUCTURE_HINTS = [
  { test: (s) => s.stats.repeats >= 3 && s.stats.images >= 2, boost: { cards: 6, carousel: 4, 'flip-card': 2 } },
  { test: (s) => s.stats.depth <= 3 && s.stats.buttons >= 1 && s.stats.images >= 1 && s.section.frame?.y === 0, boost: { 'hero-banner': 6, 'content-block': 2 } },
  { test: (s) => /head|nav/i.test(s.section.name) || (s.section.frame?.y ?? 1) === 0 && s.stats.links >= 3, boost: { header: 5, breadcrumb: 1 } },
  { test: (s) => /foot/i.test(s.section.name), boost: { footer: 8 } },
  { test: (s) => s.stats.texts >= 4 && s.stats.images === 0 && s.stats.repeats >= 3, boost: { accordion: 3, references: 2, table: 2 } },
  { test: (s) => s.stats.inputs > 0, boost: { form: 8, search: 3 } },
  { test: (s) => /video|play/i.test(s.allNames), boost: { video: 5, 'video-modal': 3 } },
  { test: (s) => /tab/i.test(s.allNames), boost: { tabs: 5 } },
  { test: (s) => /testimonial|quote/i.test(s.allNames), boost: { testimonial: 6 } },
  { test: (s) => /breadcrumb/i.test(s.allNames), boost: { breadcrumb: 8 } },
  { test: (s) => /accordion|faq|expand/i.test(s.allNames), boost: { accordion: 6, 'accordion-media': 3 } },
];

function collectStats(node, stats = { texts: 0, images: 0, buttons: 0, links: 0, inputs: 0, repeats: 0, depth: 0 }, depth = 0) {
  stats.depth = Math.max(stats.depth, depth);
  if (node.text) stats.texts++;
  if (node.asset || node.bgImage) stats.images++;
  const name = (node.name || '').toLowerCase();
  if (/\b(btn|button|cta)\b/.test(name)) stats.buttons++;
  if (/\b(link|nav item|menu)\b/.test(name)) stats.links++;
  if (/\b(input|field|form|textarea|checkbox|radio|select)\b/.test(name)) stats.inputs++;
  if (node.repeats) stats.repeats = Math.max(stats.repeats, node.repeats.count);
  (node.children || []).forEach((c) => collectStats(c, stats, depth + 1));
  return stats;
}

function collectText(node, out = []) {
  out.push(node.name || '');
  if (node.text?.content) out.push(node.text.content);
  (node.children || []).forEach((c) => collectText(c, out));
  return out;
}

function tokenize(s) {
  return new Set(
    String(s)
      .toLowerCase()
      .split(/[^a-z0-9]+/)
      .filter((w) => w.length > 2)
  );
}

/**
 * Splits the design into top-level sections (direct children of the root frame,
 * or the root itself when it has no container children) and scores each EDS
 * component against each section.
 */
export function matchSections(specRoot, components, topK = 5) {
  if (!specRoot) return [];
  const sections =
    (specRoot.children || []).filter((c) => (c.children || []).length || c.asset || c.bgImage);
  const targets = sections.length ? sections : [specRoot];

  return targets.map((section) => {
    const stats = collectStats(section);
    const words = tokenize(collectText(section).join(' '));
    const allNames = collectText(section).join(' ');
    const ctx = { section, stats, allNames };

    const scored = components.map((comp) => {
      let score = 0;
      for (const kw of comp.keywords || []) {
        if (words.has(String(kw).toLowerCase())) score += 2;
      }
      const nameTokens = tokenize(String(comp.name ?? comp.folder ?? '').replace(/-/g, ' '));
      for (const t of nameTokens) if (words.has(t)) score += 3;
      for (const hint of STRUCTURE_HINTS) {
        if (!hint.test(ctx)) continue;
        const boost = hint.boost[comp.name] ?? hint.boost[comp.folder];
        if (boost) score += boost;
      }
      return { name: comp.name, score };
    });

    scored.sort((a, b) => b.score - a.score);
    return {
      section: section.name,
      stats,
      candidates: scored.slice(0, topK).filter((s) => s.score > 0),
    };
  });
}

/** The set of component names that appear in any section's candidate list. */
export function shortlistedComponents(matches, components, max = 12) {
  const names = new Set();
  for (const m of matches) for (const c of m.candidates) names.add(c.name);
  const shortlist = components.filter((c) => names.has(c.name));
  // Always make the layout primitives available.
  for (const always of ['buttons', 'button-links', 'content-block', 'cards', 'card']) {
    const comp = components.find((c) => c.name === always || c.folder === always);
    if (comp && !shortlist.includes(comp)) shortlist.push(comp);
  }
  return shortlist.slice(0, max);
}
