import { log } from '../utils/log.js';

/**
 * Storybook-backed EDS component source.
 *
 * Replaces the local `eds-components/` folder: instead of reading each
 * component's demo HTML off disk, we fetch the live markup from the EDS
 * redesign Storybook (DEV). The canonical DOM snippet used to ground the
 * generator/reviewer agents is extracted from that rendered HTML.
 *
 * Only components that expose a Storybook page appear in STORYBOOK_URLS.
 * Components without a URL keep whatever snippet the curated eds-manifest.json
 * already carries.
 */

/** Base of the DEV Storybook host. Override with EDS_STORYBOOK_BASE. */
export const DEFAULT_STORYBOOK_BASE =
  process.env.EDS_STORYBOOK_BASE || 'https://affinitycmpd103.gilead.com';

/**
 * Map of manifest component name -> Storybook path (relative to the base host).
 * Paths are stored un-encoded and URL-encoded at fetch time.
 */
export const STORYBOOK_PATHS = {
  accordion: '/edsredesign/Accordion',
  carousel: '/edsredesign/Carousel',
  footer: '/edsredesign/footer',
  'hero-banner': '/edsredesign/Herobanner',
  header: '/edsredesign/header',
  'button-links': '/edsredesign/buttons and links',
  card: '/edsredesign/card',
  'content-block': '/edsredesign/content-block',
  filter: '/edsredesign/a/filter#customsearch_e=0',
  'announcement-banner': '/edsredesign/Announcement Banner',
  breadcrumb: '/edsredesign/Breadcrumb Demo/Breadcrumb',
  dropdown: '/edsredesign/dropdown',
  isi: '/eDSRedesign/isi variant 1',
  modal: '/edsredesign/a/modal',
  video: '/edsredesign/video',
  'professional-profile': '/edsredesign/Professional Profile Card',
  quiz: '/edsredesign/quiz',
  'resources-downloads': '/edsredesign/Resources and Downloads',
  'sticky-cta': '/edsredesign/sticky CTA',
  search: '/edsredesign/a/Search',
  tabs: '/edsredesign/tabdemo',
  testimonial: '/edsredesign/Testimonial Variants',
  'flip-card': '/edsredesign/Flipcards',
  'read-more-read-less': '/edsredesign/a/rd',
};

/** Builds the absolute, properly-encoded Storybook URL for a component name. */
export function storybookUrl(name, base = DEFAULT_STORYBOOK_BASE) {
  const rel = STORYBOOK_PATHS[name];
  if (!rel) return null;
  const [pathPart, hash] = rel.split('#');
  const encodedPath = pathPart
    .split('/')
    .map((seg) => encodeURIComponent(seg))
    .join('/');
  return `${base.replace(/\/$/, '')}${encodedPath}${hash ? `#${hash}` : ''}`;
}

/** Fetches the rendered HTML of a Storybook page. Returns '' on failure. */
export async function fetchStorybookHtml(url, { timeoutMs = 20000 } = {}) {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), timeoutMs);
  try {
    const res = await fetch(url, {
      signal: controller.signal,
      headers: { Accept: 'text/html,application/xhtml+xml' },
    });
    if (!res.ok) {
      log.warn(`Storybook ${url} -> HTTP ${res.status}`);
      return '';
    }
    return await res.text();
  } catch (err) {
    log.warn(`Storybook ${url} unreachable (${err.name === 'AbortError' ? 'timeout' : err.message}).`);
    return '';
  } finally {
    clearTimeout(timer);
  }
}

/** Pulls the first real component block (class="component eds-...") out of a demo page. */
export function extractSnippet(html) {
  if (!html) return '';
  const idx = html.search(/<\w+[^>]*class="[^"]*\bcomponent eds-[a-z0-9-]+/);
  if (idx === -1) return '';
  return html
    .slice(idx, idx + 6000)
    .split('\n')
    .slice(0, 90)
    .join('\n');
}

/** Collects the eds-* class names present in the markup. */
function collectEdsClasses(html) {
  const edsClasses = new Set();
  for (const m of html.matchAll(/\beds-[a-z0-9-]+\b/g)) {
    if (!m[0].startsWith('eds-btn') || m[0] === 'eds-btn') edsClasses.add(m[0]);
  }
  for (const wrapper of ['eds-wrapper', 'eds-header', 'eds-main', 'eds-footer']) {
    edsClasses.delete(wrapper);
  }
  return [...edsClasses];
}

/**
 * Refreshes each component's `snippet` (and eds classes when missing) from its
 * live Storybook page. Components without a Storybook URL, or whose fetch fails,
 * keep their existing curated snippet. Mutates and returns the array.
 */
export async function hydrateStorybookSnippets(components, { base = DEFAULT_STORYBOOK_BASE } = {}) {
  const targets = components.filter((c) => STORYBOOK_PATHS[c.name ?? c.folder]);
  if (!targets.length) return components;
  log.step(`Fetching ${targets.length} EDS component snippet(s) from Storybook…`);
  let ok = 0;
  await Promise.all(
    targets.map(async (c) => {
      const url = storybookUrl(c.name ?? c.folder, base);
      const html = await fetchStorybookHtml(url);
      const snippet = extractSnippet(html);
      if (snippet) {
        c.snippet = snippet.slice(0, 4000);
        if (!c.edsClasses || !c.edsClasses.length) c.edsClasses = collectEdsClasses(html);
        c.source = 'storybook';
        ok++;
      }
    })
  );
  log.info(`Storybook snippets refreshed for ${ok}/${targets.length} component(s).`);
  return components;
}

/**
 * Builds a component manifest purely from Storybook (no local folder).
 * Used by the --manifest-only path as a replacement for scanning the deleted
 * eds-components folder.
 */
export async function scanStorybookComponents({ base = DEFAULT_STORYBOOK_BASE } = {}) {
  const names = Object.keys(STORYBOOK_PATHS);
  log.step(`Building manifest from ${names.length} Storybook page(s)…`);
  const components = [];
  await Promise.all(
    names.map(async (name) => {
      const url = storybookUrl(name, base);
      const html = await fetchStorybookHtml(url);
      const snippet = extractSnippet(html);
      components.push({
        name,
        folder: name,
        edsClasses: collectEdsClasses(html),
        bootstrapFeatures: [...new Set([...html.matchAll(/data-bs-(toggle|ride|target)="([a-z-]+)"?/g)].map((m) => m[2] || m[1]))],
        description: `EDS ${name.replace(/-/g, ' ')} component`,
        whenToUse: '',
        keywords: name.split('-'),
        structureOutline: '',
        snippet: snippet.slice(0, 4000),
        source: 'storybook',
        url,
      });
    })
  );
  components.sort((a, b) => a.name.localeCompare(b.name));
  log.info(`Scanned ${components.length} Storybook components.`);
  return components;
}
