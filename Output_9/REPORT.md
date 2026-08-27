# Figma → EDS Conversion Report

- **Status:** BEST-EFFORT
- **Design:** Desktop - 2 (HOduchunJj9pJt4ruH5r3r / node 0:105)
- **Source:** REST
- **Generated:** 2026-08-27T12:16:10.040260+00:00
- **Final score:** 72.0/100 (threshold 95.0) — pixel mismatch 11.209324%
- **Review iterations:** 1
- **Accuracy mode:** standard
- **Pixel target:** 0.000000% (channel threshold 31)
- **Converged:** no
- **Exact decoded pixels:** no
- **Selected iteration:** 1
- **Stop reason:** refinement_model_error

## Viewport accuracy

| Viewport | Size match | Mismatched pixels | Mismatch | Stable |
|---|---:|---:|---:|---:|
| 1440px | no | 384413 | 11.209324% | yes |

## Accuracy blockers

- **1440px:** canvas size differs: reference `[902, 3800]`, rendered `[902, 3802]`.

## Measured geometry vs Figma

- **Document height:** 6069.0px rendered vs 6069.0px design (+0px).
- **Measured nodes:** 0 of 167 (0.0% hook coverage).

## Output contract

- **Status:** FAILED (1 violation(s))
- ⛔ **[major] geometry/hooks:** No data-figma-id attributes were emitted, so no element can be measured against its Figma box. → Add data-figma-id="<node id>" to every top-level section, card, media block, the header and the footer, using the id field from the design spec.

## Score history

1. score **72.0** — 6 issues (0 critical, 4 major, 2 minor) — mismatch 11.209324% — checkpointed

## EDS component mapping

- **Frame 40 (top navigation bar)** → `header` (navbar, navbar-expand-lg) — confidence 95% — Sticky translucent gray bar with DHS logo, 4 nav links and Log In / Sign Up eds-btn CTAs; Bootstrap collapse handles mobile.
- **image 1 + hero copy (Take your first step…)** → `hero-banner` (eds-hero-banner) — confidence 92% — Left text column, right 675x758 image using the EDS <picture> pattern; fixed 758px height at desktop.
- **We provide you with different type of healthcare jobs (Frames 18/19/20 + bordered rectangles)** → `cards` (card-img-center) — confidence 90% — Three eds-card cards (398x318, 1px #181818 border, 10px radius) in a Bootstrap row with 33px gutters; col-12 col-md-6 col-lg-4.
- **Fast track to your next job intro** → `content-block` (text-center) — confidence 85% — Centered heading + sub-copy block.
- **Create your profile feature (Rectangle 34 + floating profile/verified/experience cards)** → `content-block` (eds-card overlays) — confidence 85% — Image with absolutely-positioned eds-card float cards (radii 15px w/ one square corner) and outline eds-btn CTA.
- **Explore your options feature (Rectangle 49 + HealthisWealth job card)** → `content-block` (eds-card overlays) — confidence 85% — Text left / image right; floating 403x274 job card with Interested/Apply outline buttons.
- **Talk on your terms feature (Rectangle 53 + chat card)** → `content-block` (eds-card overlays) — confidence 85% — Image left / text right; floating white chat card with two circular avatars.
- **Explore top healthcare jobs list (Groups 40/48/49/50 + See details)** → `professional-profile` (cards, col-lg-6 grid) — confidence 80% — 2x2 Bootstrap grid (146px column gap / 100px row gap at desktop) of icon + title + company•location rows with See details outline buttons; stacks to 1-up below lg.
- **Explore jobs / Browse all jobs / Sign up now CTAs** → `buttons` (eds-btn, gs-btn-primary-like solid orange) — confidence 90% — Solid #fc7c05, 10px radius, Sora 800 24px, #d9d9d9 text, 20/50 padding.
- **Already we help 1000+ people (orbit graphic)** → `content-block` (custom orbit visual) — confidence 80% — 720px circle bg with 3 dashed rings, avatar images and dot icons positioned by percentages so the graphic scales responsively.
- **Sign up and get matched band (Rectangle 82)** → `announcement-banner` (eds-announcement-banner) — confidence 88% — 1290x330 #fc7c0552 band with centered heading and Sign up now eds-btn.
- **Footer (DHS brand, Partnership/About/Support columns)** → `footer` (eds-link columns) — confidence 92% — Brand + description and three link columns; Partnership heading uses Poppins, links #00000080 20px; fixed 466px height at desktop.

## Assets (30)

- `assets/images/rectangle-34.png` — image, 632.0×506.0 ('Rectangle 34')
- `assets/images/rectangle-49.png` — image, 632.0×506.0 ('Rectangle 49')
- `assets/images/rectangle-53.png` — image, 632.0×506.0 ('Rectangle 53')
- `assets/images/ellipse-1.jpg` — image, 100.0×100.0 ('Ellipse 1')
- `assets/images/ellipse-2.jpg` — image, 100.0×100.0 ('Ellipse 2')
- `assets/images/ellipse-3.jpg` — image, 100.0×100.0 ('Ellipse 3')
- `assets/images/ellipse-4.jpg` — image, 200.0×200.0 ('Ellipse 4')
- `assets/images/ellipse-6.jpg` — image, 80.0×80.0 ('Ellipse 6')
- `assets/images/ellipse-21.jpg` — image, 80.0×80.0 ('Ellipse 21')
- `assets/images/ellipse-5.jpg` — image, 100.0×100.0 ('Ellipse 5')
- `assets/images/image-1.png` — image, 675.0×758.0 ('image 1')
- `assets/images/rectangle-101.png` — image, 96.0×85.0 ('Rectangle 101')
- `assets/images/ellipse-9.png` — image, 70.0×70.0 ('Ellipse 9')
- `assets/images/ellipse-10.png` — image, 70.0×70.0 ('Ellipse 10')
- `assets/icons/ellipse-7.svg` — icon, 36.0×36.0 ('Ellipse 7')
- `assets/icons/ellipse-22.svg` — icon, 36.0×36.0 ('Ellipse 22')
- `assets/icons/ellipse-23.svg` — icon, 36.0×36.0 ('Ellipse 23')
- `assets/icons/ellipse-24.svg` — icon, 36.0×36.0 ('Ellipse 24')
- `assets/icons/ellipse-7.svg` — icon, 36.0×36.0 ('Ellipse 25')
- `assets/icons/material-symbols-shelf-position-outline.svg` — icon, 50.0×50.0 ('material-symbols:shelf-position-outline')
- `assets/icons/ic-baseline-card-travel.svg` — icon, 50.0×50.0 ('ic:baseline-card-travel')
- `assets/icons/ic-outline-book.svg` — icon, 50.0×50.0 ('ic:outline-book')
- `assets/icons/vector.svg` — icon, 70.0×70.0 ('Vector')
- `assets/icons/uil-comment-alt-verify.svg` — icon, 50.0×50.0 ('uil:comment-alt-verify')
- `assets/icons/ellipse-8.svg` — icon, 72.0×72.0 ('Ellipse 8')
- `assets/icons/group-41.svg` — icon, 80.0×80.0 ('Group 41')
- `assets/icons/group-41.svg` — icon, 80.0×80.0 ('Group 46')
- `assets/icons/group-41.svg` — icon, 80.0×80.0 ('Group 44')
- `assets/icons/group-41.svg` — icon, 80.0×80.0 ('Group 47')
- `assets/icons/star-2.svg` — icon, 20.0×20.0 ('Star 2')

## Warnings

- ⚠ https://mcp.figma.com/mcp requires Figma OAuth through a supported MCP host and cannot use FIGMA_TOKEN directly. Set FIGMA_MCP_URL=http://127.0.0.1:3845/mcp after enabling Figma Desktop MCP, or set FIGMA_SOURCE=rest. Continuing with REST.
- ⚠ eds-native.css was not found; generated styles.css must carry complete component styling.
- ⚠ Refinement model failed; restored the best measured candidate: Error code: 400 - {'type': 'error', 'error': {'type': 'invalid_request_error', 'message': 'You have reached your specified workspace API usage limits. You will regain access on 2026-09-01 at 00:00 UTC.'}, 'request_id': 'req_011CeTEhrsWUamewnQY6EaAi'}
- ⚠ 1 output-contract violation(s) remain in the delivered files: geometry/hooks

## Remaining review issues

- **[major] geometry/hooks:** No data-figma-id attributes were emitted, so no element can be measured against its Figma box.
- **[major] Explore top healthcare jobs — grid position:** The 2x2 job grid renders ~95px lower than the design. Figma places row-1 icons at y=3989 and row-2 at y=4169; the render puts them at ~y=4084 / ~y=4264 and the 'Explore jobs' CTA at ~y=4410 instead of y=4316, so it nearly collides with the orbit circle (top y=4453) of the next section. Root cause: `.jobs-grid { --bs-gutter-y: 100px; margin-top: 100px }` — the explicit margin-top overrides Bootstrap's compensating `margin-top: calc(-1 * var(--bs-gutter-y))` on `.row`, while each `.col-*` still receives `margin-top: 100px` from the gutter, stacking to ~+200px total instead of +100px.
- **[major] Hero — image crop:** The hero photo (assets/images/image-1.png, displayed 675x758 at x=765, y=130) renders a noticeably wider/zoomed-out composition than the Figma fill crop: in Figma the nurse's face and crossed arms fill the frame; in the render she is smaller and shifted up-left with extra background (blinds/furniture) visible bottom-right. This region drives the largest diff clusters (55–75% mismatch across the hero image tiles).
- **[major] Geometry hooks (automated contract check):** Mechanical check flagged: no data-figma-id attributes are emitted anywhere, so none of the 167 measurable nodes can be matched to their Figma boxes (hook coverage 0%). Not re-verified visually here, but it blocks a passing verdict.
- **[minor] Job types — card row position:** Same double-gutter defect as the jobs grid, smaller magnitude: `.jobtype-row { --bs-gutter-y: 33px; margin-top: 70px }` overrides Bootstrap's negative row margin while cols keep +33px, so cards sit at ~y=1281 instead of y=1263 (~18px low). Card bottoms land at ~1599 vs 1581; visible ghosting on card borders and 'Permanent positions'/'Learn more' text in the diff.
- **[minor] Header — nav horizontal alignment:** Nav labels ghost horizontally in the diff: HOME should start at x=294, ABOUT x=409, LOCATION x=533, BROWSE JOBS x=694 (50px gaps after a 90px logo + 131px offset). The rendered logo ('DHS' Sora 700 40px plus anchor padding) is wider than the 90px Figma box, pushing all links ~10–20px right; Log In / Sign Up CTAs also drift slightly from x=1083 / x=1235.
