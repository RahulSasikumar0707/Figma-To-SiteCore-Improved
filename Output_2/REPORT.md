# Figma → EDS Conversion Report

- **Status:** ACCEPTED
- **Design:** v1 (UUbf1MaoqHcRVdNephQ8Hs / node 34:2)
- **Source:** REST
- **Generated:** 2026-08-26T15:13:05.148799+00:00
- **Final score:** 96.0/100 (threshold 95.0)
- **Review iterations:** 1
- **Accuracy mode:** standard
- **Pixel target:** 0.000000% (channel threshold 31)
- **Converged:** yes
- **Exact decoded pixels:** no
- **Selected iteration:** 1
- **Stop reason:** target_met

## Output contract

- **Status:** PASSED

## Score history

1. score **96.0** — 0 issues (0 critical, 0 major, 0 minor) — accepted

## EDS component mapping

- **Frame 481622 (top bar, 34:3)** → `header` (site-header) — confidence 0.9% — Brand text, inline nav with dropdown caret, Join link and Contact Us pill CTA mapped to eds-header with eds-link/eds-btn children.
- **Frame 481618 (hero left, 34:18)** → `hero-banner` (hero-left, hero-top, hero-heading) — confidence 0.8% — Large display heading with overlay pill image and floating 'How do we work' button, CTA row, and partner-logo strip; heights reached via space-between and min-heights at >=1600px only.
- **Frame 481612 (hero right cards, 34:68)** → `cards` (card-journey, card-sm, card-collaborate, card-solutions) — confidence 0.85% — Three eds-card/card blocks with background images, rounded 38px corners, card-body flex column space-between. Third card's top row reproduced with opacity 0 as in Figma (34:84).
- **CTAs (34:15, 34:23, 34:27, 34:77)** → `buttons` (btn-pill, btn-header-contact, btn-work, btn-contact, btn-connect) — confidence 0.9% — All pill CTAs use canonical eds-btn + link-text structure with gs-btn-* variants; outline variant for 'How do we work'.
- **Partner logos strip (34:33)** → `content-block` (partners-logos) — confidence 0.6% — Simple media row inside the hero-banner left column; space-between at design width, wraps fluidly below.

## Assets (14)

- `assets/images/rectangle-20.png` — image, 140.5×58.6 ('Rectangle 20')
- `assets/images/frame-481607.png` — image, 679.7×403.1 ('Frame 481607')
- `assets/images/frame-481608.png` — image, 330.5×365.6 ('Frame 481608')
- `assets/images/frame-481609.png` — image, 330.5×365.6 ('Frame 481609')
- `assets/icons/frame-481626.svg` — icon, 11.2×10.3 ('Frame 481626')
- `assets/icons/polygon-8.svg` — icon, 19.7×19.7 ('Polygon 8')
- `assets/icons/arrow-3.svg` — icon, 11.0×11.0 ('Arrow 3')
- `assets/icons/logo-34.svg` — icon, 115.7×30.4 ('logo-34')
- `assets/icons/frame-481614.svg` — icon, 75.1×30.4 ('Frame 481614')
- `assets/icons/logo-50.svg` — icon, 117.2×30.5 ('logo-50')
- `assets/icons/logo-11.svg` — icon, 127.9×30.4 ('logo-11')
- `assets/icons/frame-481609.svg` — icon, 70.3×70.3 ('Frame 481609')
- `assets/icons/arrow-4.svg` — icon, 12.0×12.0 ('Arrow 4')
- `assets/images/frame-481609-2.png` — icon, 46.9×46.9 ('Frame 481609')

## Warnings

- ⚠ https://mcp.figma.com/mcp requires Figma OAuth through a supported MCP host and cannot use FIGMA_TOKEN directly. Set FIGMA_MCP_URL=http://127.0.0.1:3845/mcp after enabling Figma Desktop MCP, or set FIGMA_SOURCE=rest. Continuing with REST.
- ⚠ Reference screenshot unavailable for 1612px: Figma REST /v1/images/UUbf1MaoqHcRVdNephQ8Hs returned 429: Rate limit exceeded
- ⚠ eds-native.css was not found; generated styles.css must carry complete component styling.
