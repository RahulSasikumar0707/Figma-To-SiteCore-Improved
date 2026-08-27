# Figma → EDS Conversion Report

- **Status:** BEST-EFFORT
- **Design:** HOMEPAGE (VIBFKV6rZiXNVG3nC3yHRC / node 8:39)
- **Source:** REST
- **Generated:** 2026-08-27T12:14:07.472802+00:00
- **Final score:** 86.0/100 (threshold 95.0)
- **Review iterations:** 5
- **Accuracy mode:** standard
- **Pixel target:** 0.000000% (channel threshold 31)
- **Converged:** no
- **Exact decoded pixels:** no
- **Selected iteration:** 4
- **Stop reason:** refinement_model_error

## Output contract

- **Status:** FAILED (1 violation(s))
- ⛔ **[major] eds/unknown-component:** component-map.json names components that are not in the EDS catalog: none → Map each section to a component from the supplied EDS catalog, or drop the mapping.

## Score history

1. score **78.0** — 8 issues (0 critical, 4 major, 4 minor) — checkpointed
2. score **85.0** — 7 issues (0 critical, 1 major, 6 minor) — checkpointed
3. score **86.0** — 5 issues (0 critical, 2 major, 3 minor) — rejected-regression
4. score **86.0** — 5 issues (0 critical, 1 major, 4 minor) — checkpointed
5. score **88.0** — 4 issues (0 critical, 2 major, 2 minor) — rejected-regression

## EDS component mapping

- **topbar (8:119)** → `none` — confidence 0% — Mapping dropped: the supplied EDS catalog contains no matching header component. Built as a custom sticky header inside the mandated <header id="eds-header"> wrapper using Bootstrap layout; logo asset a2, All/BD triggers, search input with orange submit, utility icons via Material Symbols (icon vectors absent from the asset manifest).
- **Hero — Rectangle 69 + Group 10 (17:21/17:27)** → `none` — confidence 0% — Mapping dropped: no hero/banner component in the supplied EDS catalog. Custom section with the responsive <picture> pattern for asset a11, left #d0d0d0→transparent gradient overlay, Inter title/subtitle and 'Learn More' button; 500px design height reproduced with 160px paddings so content can grow.
- **Category pills (8:52..8:65 + 18:xx texts)** → `none` — confidence 0% — Mapping dropped: no pill/tag component in the supplied EDS catalog. Custom centered pill rows with the exact Figma widths (row1 180/261/160/160, row2 261/189/160/258, row3 180/229/185/175) applied as min-widths at desktop, radius 16, shadow --fig-shadow-3; active pill #ff9a00. Icons via Material Symbols (icon assets absent from manifest).
- **Peace of mind with every international order (22:69..27:361)** → `none` — confidence 0% — Mapping dropped: no matching card/split component in the supplied EDS catalog. Custom text column (32/38.9 heading, 16/19.4 copy, orange CTA) plus 285x229 image tiles with bottom gradient labels and one #353535ba 'Discover more' overlay; third tile clipped at the right edge as in the design.
- **Top Sellers in Books (29:13, 8:77..8:88, 30:xx, 34:xx)** → `none` — confidence 0% — Mapping dropped: no product-card component in the supplied EDS catalog. Custom 4x2 grid of 235px bordered cards (0.7px #c8c8c8, radius 18), 101x157 covers with --fig-shadow-1, title/writer/'Know more' row, elevated 'active' card with --fig-shadow-4, CSS ribbon badges (badge assets not in manifest) and 'Load More' button.
- **Rectangle 29 promo strip (8:68)** → `none` — confidence 0% — Mapping dropped: no image/banner component in the supplied EDS catalog. Full-bleed 1440x357 image (asset a1) via the responsive <picture> pattern with aspect-ratio to prevent layout shift.
- **Explore our Amazing Deals (38:161, 8:76..8:89, 47:xx)** → `none` — confidence 0% — Mapping dropped: no carousel component in the supplied EDS catalog; Bootstrap 5 carousel (.carousel > .carousel-inner > .carousel-item) used per rule 4 with data-bs prev/next controls. Cards at Figma x=88/402/742/1073 via explicit 29/31/46px inter-card gaps; per-card image metrics (camera top 67, goggle 76, bottle 46, Nike 29 with 320px width bleeding 22px left of the card); strike-through applied only to the trailing RPR dollar value per line 47:62.
- **Category collage Group 44 (53:27)** → `none` — confidence 0% — Mapping dropped: no collage/mosaic component in the supplied EDS catalog. Custom 3-column grid (360 / fluid / 360) of image tiles with #57575700→#1b1b1b bottom gradients, white 16px labels and a #282828b5 'Discover more' overlay tile; min-heights reproduce the design boxes while allowing content growth.
- **Footer (53:35..53:92, 8:96..8:112, 53:26)** → `none` — confidence 0% — Mapping dropped: no footer component in the supplied EDS catalog. Built inside the mandated <footer id="eds-footer"> wrapper: 224x69 inverted logo (footer vectors a73-a75 absent, header asset a2 reused with CSS invert), two centered uppercase country rows, three orange headings, 611x157 message textarea + 392px email/SEND form, © line in #c4d6d2.

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
- ⚠ Refinement model failed; restored the best measured candidate: Error code: 400 - {'type': 'error', 'error': {'type': 'invalid_request_error', 'message': 'You have reached your specified workspace API usage limits. You will regain access on 2026-09-01 at 00:00 UTC.'}, 'request_id': 'req_011CeTEYz94g2tZih65LWiXW'}
- ⚠ 1 output-contract violation(s) remain in the delivered files: eds/unknown-component

## Remaining review issues

- **[major] eds/unknown-component:** component-map.json names components that are not in the EDS catalog: none
- **[minor] Amazing Deals — water bottle card (8:84):** The bottle image (image-18, 186×186) is horizontally centered in the 285px card (left ≈ 49.5px), but in Figma the image sits at x=780 within the card at x=742, i.e. 38px from the card's left edge — an 11.5px horizontal offset.
- **[minor] Category pills — rows 2 and 3:** Rows are centered with a uniform 16px gap, but Figma row 2 uses a 27px gap between 'pC & video games' and 'electronics' (x: 497→524) and starts at x=236 (generated ≈ x=262, 26px off); row 3 uses a 23px gap between 'Home & garden' and 'best sellers' (x: 740→763). Row 1 matches exactly.
- **[minor] Explore collage — bottom gradients (51:12, 51:13):** All `.explore-grad` overlays use `#57575700 0% → #1b1b1b 80%`, but Figma specifies the mid ('Gaming Accesories', 51:12) and right ('Outdoor Tools', 51:13) bottom tiles with the #1b1b1b stop at 60%, producing a stronger scrim than currently rendered on those two tiles.
- **[minor] Amazing Deals — product ground shadows (46:24):** The elliptical ground shadow under the featured gaming-goggle image is omitted. Unlike the other shadow ellipses (raster assets missing from the manifest), 46:24 is fully specified in CSS-reproducible terms: 177.4×18.5 ellipse at y≈3069 (below the image), gradient #1d1d1dd6 0% → #6161617a 90% → #1d1d1d00 100%, blur 12.8px.
