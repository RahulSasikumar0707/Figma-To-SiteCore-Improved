# Figma → EDS Conversion Report

- **Status:** BEST-EFFORT
- **Design:** HOMEPAGE (VIBFKV6rZiXNVG3nC3yHRC / node 8:39)
- **Source:** REST
- **Generated:** 2026-08-27T11:25:00.753118+00:00
- **Final score:** 93.0/100 (threshold 95.0)
- **Review iterations:** 3
- **Accuracy mode:** standard
- **Pixel target:** 0.000000% (channel threshold 31)
- **Converged:** no
- **Exact decoded pixels:** no
- **Selected iteration:** 2
- **Stop reason:** review_model_error

## Output contract

- **Status:** PASSED

## Score history

1. score **73.0** — 8 issues (0 critical, 3 major, 5 minor) — checkpointed
2. score **93.0** — 2 issues (0 critical, 0 major, 2 minor) — checkpointed
3. score **92.0** — 4 issues (0 critical, 0 major, 4 minor) — rejected-regression

## EDS component mapping

- **topbar (8:119)** → `header` (site-header, topbar) — confidence 0.9% — Header band with brand logo, All menu, locale, search and action icons; uses component eds-header wrapper.
- **search bar (8:26)** → `search` (search-box, topbar-search) — confidence 0.95% — Canonical search-box structure: component-content > search-box-input + search-box-button; min-height so longer content can grow.
- **hero Rectangle 69 + Group 10 (17:21, 17:27)** → `hero-banner` (eds-hero-banner, hero) — confidence 0.9% — Full-bleed 500px hero with left gradient scrim, title, subtitle and eds-btn CTA.
- **category pill rows (8:52…8:65)** → `buttons` (eds-btn, cat-pill, cat-pill--accent) — confidence 0.8% — Three centered rows of pill buttons; missing Figma icon exports replaced with Material Symbols.
- **international order block (22:69, 22:73, 22:74)** → `content-block` (intl, intl-text) — confidence 0.85% — Text + CTA column beside a peeking media-card row; verbatim multi-line copy via white-space:pre-line.
- **international media cards (22:82, 22:83, 22:86)** → `cards` (eds-card, card, media-card) — confidence 0.85% — 285x229 image cards; card 22:83 reproduces the full Figma layer stack (under image 22:79 + front image 22:88 + dark overlay); min-height so content can grow.
- **Top Sellers in Books grid (29:13, 8:77…8:88)** → `cards` (eds-card, card, book-card, book-card--pop) — confidence 0.9% — 4x2 grid of bordered book cards; featured card uses shadow modifier; ribbon rendered in CSS (asset not exported).
- **Load More (34:153)** → `buttons` (eds-btn, gs-btn-md, gs-btn-primary, btn-amz) — confidence 0.9% — Centered orange CTA, padding 10/26 per spec.
- **promo banner Rectangle 29 (8:68)** → `content-block` (promo-banner) — confidence 0.8% — Full-width image band fixed at 357px height at desktop.
- **Explore our Amazing Deals (38:161, 8:76, 8:80, 8:84, 8:89)** → `carousel` (eds-carousel, deal-card, deal-card--feature) — confidence 0.85% — Scroll-track carousel: track keeps overflow-x auto at every breakpoint so prev/next arrows scroll it everywhere; desktop gaps 29/31/46 and 88/82 insets match Figma.
- **category gallery Group 44 (53:27)** → `cards` (eds-card, card, g-card) — confidence 0.85% — Three-column mosaic (360/537/360, left edge 59px at 1440) with per-column gaps 42/54; full Figma layer stacks incl. under images 47:79 and 47:76; gradient/dark overlays with labels.
- **footer (53:35)** → `footer` (eds-footer, site-footer) — confidence 0.9% — Black footer: inverted logo, two country rows, three orange headings, feedback + subscribe form, copyright line.
- **footer feedback/subscribe (8:96, 8:111, 8:112)** → `form` (eds-sc-form, footer-form) — confidence 0.8% — Textarea placeholder 'Write Here....', email input and SEND button matching 611x157 / 392x45 spec boxes.

## Assets (27)

- `assets/images/rectangle-29.jpg` — image, 1440.0×357.0 ('Rectangle 29')
- `assets/images/vector.png` — image, 147.0×47.0 ('Vector')
- `assets/images/rectangle-69.jpg` — image, 1440.0×500.0 ('Rectangle 69')
- `assets/images/unsplash-2zdw14ycyqk.jpg` — image, 296.0×444.0 ('unsplash:2zDw14yCYqk')
- `assets/images/unsplash-iwd-99qv7uk.jpg` — image, 323.0×323.0 ('unsplash:iwd_99qV7Uk')
- `assets/images/unsplash-zb4eqcnqvus.jpg` — image, 360.0×239.0 ('unsplash:ZB4eQcNqVUs')
- `assets/images/unsplash-gip0e750dr8.jpg` — image, 301.0×451.0 ('unsplash:giP0e750Dr8')
- `assets/images/image-9.png` — image, 101.0×157.0 ('image 9')
- `assets/images/image-9-2.png` — image, 101.0×157.0 ('image 9')
- `assets/images/image-13.png` — image, 101.0×157.0 ('image 13')
- `assets/images/image-12.png` — image, 101.0×157.0 ('image 12')
- `assets/images/image-4.png` — image, 101.0×157.0 ('image 4')
- `assets/images/image-11.png` — image, 101.0×157.0 ('image 11')
- `assets/images/image-5.png` — image, 101.0×157.0 ('image 5')
- `assets/images/image-10.png` — image, 101.0×157.0 ('image 10')
- `assets/images/image-14.png` — image, 320.0×180.0 ('image 14')
- `assets/images/image-18.png` — image, 186.0×186.0 ('image 18')
- `assets/images/image-19.png` — image, 226.0×119.0 ('image 19')
- `assets/images/image-20.png` — image, 158.2×160.0 ('image 20')
- `assets/images/image-1.png` — image, 380.0×402.0 ('image 1')
- `assets/images/unsplash-ecktzgjc-iu.jpg` — image, 711.0×511.4 ('unsplash:eCktzGjC-iU')
- `assets/images/unsplash-x6qffklwyoq.jpg` — image, 540.0×360.0 ('unsplash:X6QffKLwyoQ')
- `assets/images/unsplash-isg37ai2a-s.jpg` — image, 451.0×301.0 ('unsplash:ISg37AI2A-s')
- `assets/images/unsplash-f2bi-vbs71m.jpg` — image, 429.0×286.0 ('unsplash:f2Bi-VBs71M')
- `assets/images/unsplash-d4jrahauaic.jpg` — image, 555.0×694.0 ('unsplash:D4jRahaUaIc')
- `assets/images/unsplash-eruc4fttcuo.jpg` — image, 525.0×350.0 ('unsplash:erUC4fTtCuo')
- `assets/images/unsplash-rhmyydmzq2a.jpg` — image, 524.0×349.0 ('unsplash:rHMyYDmZq2A')

## Warnings

- ⚠ https://mcp.figma.com/mcp requires Figma OAuth through a supported MCP host and cannot use FIGMA_TOKEN directly. Set FIGMA_MCP_URL=http://127.0.0.1:3845/mcp after enabling Figma Desktop MCP, or set FIGMA_SOURCE=rest. Continuing with REST.
- ⚠ Reference screenshot unavailable for 1440px: Figma REST /v1/images/VIBFKV6rZiXNVG3nC3yHRC returned 429: Rate limit exceeded
- ⚠ eds-native.css was not found; generated styles.css must carry complete component styling.
- ⚠ Reviewer model failed after a usable page was generated: No JSON object found in model response

## Remaining review issues

- **[minor] colour fidelity:** .footer-logo img uses filter: invert(1) on assets/images/vector.png. Inversion hue-shifts any non-grayscale pixels — if the logo asset contains the orange (#ff9a00) arc it will render blue (#0065ff) in the footer, diverging from the white-on-black footer logo in the design (group 53:26).
- **[minor] spacing:** .deal-badge uses padding: 0 15px, producing a ~73px-wide badge versus the 83px badge in the design (47:30/47:40/47:44/47:48 are 83×27 with the '% OFF' text inset 20px from the badge's left edge, e.g. 417−397). The badge is ~10px narrow and the text inset is 5px short.
