from __future__ import annotations

import json

from figma_to_sitecore.domain.models import GenerationContext
from figma_to_sitecore.eds.manifest import manifest_catalog

GENERATOR_SYSTEM_PROMPT = """You are an elite Sitecore EDS front-end engineer. You convert Figma design specifications into pixel-accurate, production-quality, responsive HTML/CSS/JS built on Bootstrap 5.1.3 and the Sitecore EDS component library.
 
NON-NEGOTIABLE RULES
1. EXACT VISUAL MATCH. Reproduce the design spec exactly: colors, font families/sizes/weights/line-heights, spacing (gaps/paddings/margins), border radii, shadows, alignment and stacking order. Never invent, "improve" or approximate values that exist in the spec.
2. DESIGN TOKENS. css/tokens.css (provided) defines CSS custom properties for every color, font size, spacing, radius and shadow in the design. In css/styles.css, ALWAYS reference these tokens (var(--fig-...)) instead of hardcoding values. Only hardcode a value if no token exists for it.
3. EDS COMPONENT STRUCTURE. Each design section must be built with the DOM structure of its mapped EDS component (snippets provided). Keep EDS class names intact (component eds-<name>, modifiers, inner class hierarchy). Wrap the page in:
   <div id="eds-wrapper"><header id="eds-header">...</header><main id="eds-main">...</main><footer id="eds-footer">...</footer></div>
   (omit header/footer wrappers only if the design has no such section).
4. BOOTSTRAP 5. Use the Bootstrap grid (container-fluid / row / col-*) for layout and Bootstrap behaviors (data-bs-* for collapse, carousel, modal, dropdown, tabs) instead of writing custom JS where Bootstrap covers it. No jQuery.
5. ASSETS. Use ONLY the image/icon/vector files listed in the asset manifest, via their exact relative paths (assets/...). Every image visible in the design must appear in the HTML (or as a CSS background when the spec marks it bgImage). Set width/height or aspect-ratio to prevent layout shift, alt text from the layer name, img-fluid where appropriate. For large banner/hero images use the EDS <picture> pattern with (min-width:992px) / (min-width:768px) / (min-width:0px) sources.
6. RESPONSIVE. Mobile-first. The spec's frame geometry describes the desktop layout; derive tablet (>=768px) and mobile (<768px) behavior from the auto-layout semantics (row layouts stack into columns on mobile unless they are small inline groups; grids of N cards become 2-up on tablet and 1-up on mobile via col-12 col-md-6 col-lg-*). Nothing may overflow the viewport at 375px, 768px or 1440px.
7. A sticky header implementation is required, as the eds-header is expected to remain fixed during scrolling
8. CSS QUALITY. styles.css loads AFTER eds-native.css, so your rules override EDS defaults when the design differs — override deliberately and minimally, scoped to the component (e.g. .eds-hero-banner .hero-title { ... }). Do not use !important unless a Bootstrap utility must be beaten.
9. The layout semantics in the spec map directly: layout.mode=row -> display:flex;flex-direction:row, mode=column -> flex-direction:column, gap -> gap, padding -> padding, justify/align -> justify-content/align-items, sizing fill -> flex:1/width:100%, hug -> fit-content, fixed -> exact px (desktop only; relax responsively).
 
OUTPUT FORMAT — CRITICAL
Return ONLY the files, each introduced by a delimiter line, no other prose:
===FILE: index.html===
<complete file>
===FILE: css/styles.css===
<complete file>
===FILE: js/script.js===
<complete file>
===FILE: component-map.json===
{"mappings":[{"designSection":"...","edsComponent":"...","modifiers":["..."],"confidence":0-100,"notes":"..."}]}
===END==="""


REVIEWER_SYSTEM_PROMPT = """You are a ruthless design-QA reviewer for Figma-to-code conversions targeting Sitecore EDS + Bootstrap 5. You are a different agent from the developer and must not trust their work.
 
Compare the generated code against the ground truth (design spec + Figma reference screenshot). If a browser render of the generated page is provided, visually diff it against the Figma reference region by region.
 
Check, in priority order:
1. Layout accuracy (40 pts): section order, positions, column structure, alignment, sizes.
2. Typography (20 pts): family, size, weight, line-height, color, alignment of every text node.
3. Color fidelity (15 pts): backgrounds, gradients, borders — exact hex values from the spec/tokens.
4. Spacing (15 pts): paddings, gaps, margins vs the spec's auto-layout values.
5. Assets & responsiveness (10 pts): every design image/icon present with correct path from the manifest, sensible crops, EDS structure preserved, no horizontal overflow at 375/768/1440 px.
 
Also verify: design tokens (var(--fig-*)) are used instead of hardcoded values; EDS component DOM structures are respected; Bootstrap behaviors use data-bs-*.
 
WHAT COUNTS AS AN ISSUE — the goal is an EMPTY issues array once the code genuinely matches:
- Report ONLY defects that are actionable in the HTML/CSS/JS (a concrete change would fix them).
- Do NOT report: sub-pixel/anti-aliasing/font-hinting rendering differences, browser scrollbar artifacts, differences under ~2px that no CSS change can control, image compression noise, or anything the provided asset files make impossible to fix.
- Do NOT restate an issue that the code demonstrably already addresses.
- When every remaining visual difference falls into the unfixable categories above, return "issues": [] and score accordingly (>= 95).
 
Return ONLY a JSON object:
{
  "score": <0-100 overall fidelity>,
  "summary": "<one paragraph>",
  "issues": [
    {"severity": "critical|major|minor", "area": "<section/component>", "description": "<what is wrong, with exact expected vs actual values>", "fix": "<concrete instruction for the developer>"}
  ]
}
Be specific and quantitative in every issue.
 """


def head_template(context: GenerationContext) -> str:
    eds = (
        '  <link href="css/eds-native.css" rel="stylesheet" />'
        if context.eds_native_available
        else ""
    )
    return f"""<head>
  <meta charset="UTF-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1.0" />
  <title>{{page title from design}}</title>
  <link href="{context.bootstrap_css_url}" rel="stylesheet" />
{eds}
  <link rel="preconnect" href="https://fonts.googleapis.com">
  <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin="">
  <link href="https://fonts.googleapis.com/css2?family=Inter:ital,opsz,wght@0,14..32,100..900;1,14..32,100..900&family=Material+Symbols+Outlined&family=Material+Symbols+Rounded&display=swap" rel="stylesheet" />
  {{add Google Fonts links for non-Inter design fonts}}
  <link href="css/tokens.css" rel="stylesheet" />
  <link href="css/styles.css" rel="stylesheet" />
</head>"""


def generator_context(context: GenerationContext) -> str:
    width = context.root_size.get("w") if context.root_size else None
    height = context.root_size.get("h") if context.root_size else None
    assets = [
        {key: asset.get(key) for key in ("id", "name", "kind", "file", "w", "h")}
        for asset in context.asset_manifest
    ]

    def component_snippet(component: dict) -> str:
        modifiers = "; ".join(
            f"{item.get('cls')} ({item.get('purpose', '')})"
            for item in component.get("modifiers") or []
        ) or "none"
        return (
            f"## {component['name']} (classes: {' '.join(component.get('edsClasses') or [])})\n"
            f"Structure:\n{component.get('structureOutline') or 'n/a'}\n"
            f"Modifiers: {modifiers}\n"
            f"Canonical snippet:\n{component.get('snippet') or 'n/a'}"
        )

    snippets = "\n\n".join(component_snippet(component) for component in context.shortlist)
    parts = [
        f'# TASK\nConvert Figma design "{context.design_name}" into EDS + Bootstrap responsive code.\n'
        f"The desktop frame is {width}x{height}px. At a {width}px viewport the rendered document "
        f"height must be {height}px: that single number is the primary acceptance signal, because "
        f"every section below a mis-sized one is displaced by the same error.",
        f"# REQUIRED HEAD\n{head_template(context)}\n\nBefore </body> include:\n"
        f'<script src="{context.bootstrap_js_url}"></script>\n<script src="js/script.js"></script>',
        f"# DESIGN SPEC\nCoordinates: `frame` is relative to the parent, `abs` is relative to the "
        f"frame origin, both in CSS pixels at the {width}px design width.\n{context.spec_json}",
        "# DESIGN COPY DECK\nEvery text run in the design, complete and in document order. This is "
        "the authoritative wording; the spec tree above may omit deep nodes, this never does. "
        f"Reproduce each `content` value verbatim.\n{context.text_inventory_json}",
        f"# DESIGN TOKENS\n{context.tokens_css}",
        f"# ASSET MANIFEST\n{json.dumps(assets, indent=1)}",
        f"# EDS COMPONENT CATALOG\n{manifest_catalog(context.all_components)}",
        f"# SECTION MATCHES\n{json.dumps(context.matches, indent=1)}",
        f"# AUTHORITATIVE EDS SNIPPETS\n{snippets}",
    ]
    if context.responsive_specs:
        parts.append(
            "# VIEWPORT-SPECIFIC FIGMA REFERENCES\n"
            + "\n\n".join(
                f"## {item['width']}px / node {item['nodeId']}\n{item['spec']}"
                for item in context.responsive_specs
            )
        )
    if context.mcp_design_context:
        parts.append(f"# FIGMA DEV MODE CONTEXT\n{context.mcp_design_context[:30_000]}")
    return "\n\n".join(parts)
