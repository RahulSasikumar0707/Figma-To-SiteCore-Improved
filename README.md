# Figma → Sitecore EDS (Python + LangChain)

This project converts a Figma node into responsive Sitecore EDS HTML/CSS/JavaScript. It is now a Python application built with LangChain's `ChatAnthropic` integration and a LangGraph generator → reviewer → refinement workflow.

## Project structure

```text
.
├── pyproject.toml                 # package, dependencies, CLI, tooling
├── .env.example                  # configuration template
├── eds-manifest.json             # curated Sitecore EDS component catalog
├── src/figma_to_sitecore/
│   ├── application.py            # end-to-end use-case orchestration
│   ├── cli.py                    # command-line entry point
│   ├── config.py                 # validated environment settings
│   ├── domain/                   # shared application models
│   ├── figma/                    # REST/MCP clients, normalization, assets
│   ├── eds/                      # manifest, Storybook, component matching
│   ├── tokens/                   # Figma-to-CSS token generation
│   ├── generation/               # LangChain generator/reviewer agents
│   ├── workflow/                 # LangGraph review/refinement state machine
│   ├── review/                   # Playwright render and Pillow pixel diff
│   ├── output/                   # safe file and report writers
│   └── utils/                    # small shared utilities
└── tests/                        # unit and workflow tests
```

The deterministic work—Figma extraction, normalization, asset downloads, token creation, and EDS matching—remains regular Python. Only the model-driven generate/review/refine cycle is implemented as an agent graph. This keeps the workflow observable and testable without turning ordinary API calls into agents.

## Processing flow

```text
Figma Desktop MCP (optional) + Figma REST
        ↓
normalized design tree + local assets + CSS tokens + Figma design screenshots
        ↓
Sitecore EDS component matching and Storybook grounding
        ↓
LangChain generator agent (visually grounded on the Figma design renders)
        ↓
mechanical output-contract check (no embedded CSS, EDS classes, breakpoints, assets)
        ↓
deterministic browser renders at every reference viewport
        ↓
per-element DOM-vs-Figma geometry audit + decoded-pixel analysis + responsive audit
        ↓
LangChain reviewer/refiner proposes a candidate
        ↓
promote improvement ── reject regression ── restore best checkpoint
        ↓
strict target met, or best measured result + explicit failure report
```

## Requirements

- Python 3.10–3.14 (Python 3.12 is recommended)
- An Anthropic API key
- A Figma personal access token
- Optional: Figma Desktop with its Dev Mode MCP server enabled
- Optional in standard mode, required in strict mode: Chromium installed by Playwright

## Setup

Create and activate a virtual environment:

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -e ".[visual,dev]"
python -m playwright install chromium
Copy-Item .env.example .env
```

On macOS/Linux, activate with `source .venv/bin/activate` and copy the environment file with `cp .env.example .env`.

Set at least these values in `.env`:

```dotenv
ANTHROPIC_API_KEY_1=your-key
FIGMA_TOKEN=your-figma-token
FIGMA_FILE_KEY=your-file-key
FIGMA_NODE_ID=68569:2790
```

The Figma token must include the `file_content:read` scope and its account must be able to open the target file. Figma personal access tokens expire after at most 90 days; when one expires, generate a replacement under **Figma Settings → Security → Personal access tokens** and update `FIGMA_TOKEN` in `.env`.

Values in this project's `.env` intentionally take precedence over Windows/user environment variables, preventing an older globally configured token from silently overriding the project token.

`ANTHROPIC_API_KEY_2` is optional and allows the reviewer to use a separate key. It falls back to key 1. The model defaults to `claude-sonnet-4-6`; override it with `ANTHROPIC_MODEL` when needed.

### Model settings

`LLM_MAX_TOKENS` defaults to `64000`. Claude 4.6 and later accept up to 128000 output tokens while streaming, and a full page plus its stylesheet regularly exceeds 32000 — every truncation costs a resume round trip and risks dropped markup. Responses are always streamed, and a truncated response is resumed with a *user* turn: re-sending the partial answer as a trailing assistant message (prefill) is rejected with HTTP 400 by every model from Claude 4.6 onward.

`LLM_REASONING_EFFORT` sets `output_config.effort` (`low`, `medium`, `high`, `xhigh`, `max`) and defaults to `xhigh`. On adaptive-thinking models the application also sends `thinking: {"type": "adaptive"}`. Both are omitted automatically for models that predate adaptive thinking, and `xhigh` is downgraded to `high` on models released before it existed, so switching `ANTHROPIC_MODEL` never produces a parameter the target rejects.

A `refusal` stop reason is raised as an explicit error rather than being parsed as empty output.

### Figma MCP choice

This standalone CLI supports Figma Desktop's local MCP endpoint:

```dotenv
FIGMA_SOURCE=auto
FIGMA_MCP_URL=http://127.0.0.1:3845/mcp
```

Figma's hosted endpoint (`https://mcp.figma.com/mcp`) uses its own OAuth flow and only accepts supported MCP hosts; a REST personal access token does not authenticate it. If the hosted URL is configured with `FIGMA_SOURCE=auto`, this application now skips it safely and continues through the Figma REST API. Use `FIGMA_SOURCE=rest` if you do not need Desktop MCP context.

## Run

```powershell
# Values from .env
figma-sitecore

# Per-run overrides
figma-sitecore --file-key FILE_KEY --node 12:34

# Generate once without the reviewer/refinement loop
figma-sitecore --skip-review

# Disable Playwright and pixel comparison
figma-sitecore --no-visual-diff

# Enforce decoded-pixel convergence at the primary Figma frame
figma-sitecore --accuracy strict --pixel-target 0

# Enforce the target at desktop, tablet, and mobile Figma frames
figma-sitecore --accuracy strict --pixel-target 0 `
  --reference 375=12:35 --reference 768=12:36 --reference 1440=12:34

# Rebuild the EDS manifest from Storybook (corporate network only)
figma-sitecore --manifest-only

# Re-fetch Storybook snippets during a run instead of trusting eds-manifest.json
figma-sitecore --refresh-storybook
```

`eds-manifest.json` is the default source of EDS component grounding: when it is present and
valid, a run never touches Storybook. Storybook is crawled only when the manifest is missing or
unreadable, when `--refresh-storybook` / `EDS_STORYBOOK_REFRESH=true` is set, or on
`--manifest-only`. If a crawl reaches the host but comes back empty (HTTP 403 off-network),
`--manifest-only` fails instead of overwriting the curated manifest with empty entries.

You can also run `python -m figma_to_sitecore` with the same options.

## Strict visual convergence

Strict mode is a fail-closed, objective optimization loop. It does not treat a reviewer score or a rounded percentage as proof of pixel equality. At each iteration it:

1. serves only the candidate output, batches all viewports through one Chromium process, uses fresh browser contexts, waits for fonts/images, renders twice, and rejects unstable evidence;
2. compares decoded pixels with channel threshold `0`, including every pixel outside unequal canvas dimensions;
3. measures every supplied Figma viewport and audits intermediate widths for overflow, broken images, and unloaded fonts;
4. identifies the highest-error image regions and sends those numeric diagnostics to the refiner;
5. checkpoints only an objectively better candidate and locks a viewport once it reaches the target;
6. rejects regressions and restores the best candidate, render, and diff before continuing;
7. reports success only when the reviewer gate, every viewport target, stable rendering, and responsive audit all pass.

Configure several ground-truth frames in `.env` when the Figma file contains separate responsive designs:

```dotenv
ACCURACY_MODE=strict
PIXEL_MISMATCH_TARGET=0
FIGMA_REFERENCE_NODES={"375":"12:35","768":"12:36","1440":"12:34"}
RESPONSIVE_VIEWPORTS=375,480,768,1024,1440
```

The JSON keys are CSS viewport widths; values are the matching Figma frame node IDs. The primary `FIGMA_NODE_ID` is automatically included. Exactness is provable only at supplied reference widths. Widths between them are tested for responsive invariants because there is no pixel ground truth for an unsupplied width.

For reproducible zero-pixel testing, use the same Chromium build and make all fonts, Bootstrap files, EDS CSS, images, and icons locally available and version-locked. A failed network resource, unstable capture, missing reference, dimension difference, remaining review issue, or nonzero decoded pixel prevents strict acceptance. The best candidate is still written, but the command exits with code `3` and `REPORT.md` explains why.

Generated HTML is never opened with unrestricted `file://` access. The visual runner serves only the current `Output_N` directory from an ephemeral localhost origin, blocks external navigation, and rejects requests outside `RENDER_ALLOWED_ORIGINS`.

Each conversion creates an incrementing output directory:

```text
Output_1/
├── index.html
├── css/
│   ├── tokens.css
│   ├── styles.css
│   └── eds-native.css            # copied when available
├── js/script.js
├── assets/images|icons|vectors/
├── component-map.json
├── reference/
│   ├── figma-design.png
│   ├── generated-render.png
│   ├── pixel-diff.png
│   ├── iterations/                # every evaluated candidate/viewport
│   └── viewports/                 # selected best render/diff per viewport
├── report.json
└── REPORT.md
```

## Output contract

Three requirements are checked mechanically on every candidate, before the reviewer is consulted, and a candidate carrying any violation cannot be accepted. Violations are also injected into the reviewer's issue list, so the refinement loop repairs them like any other defect, and they are listed in `REPORT.md` under **Output contract**.

1. **No inline or internal CSS.** `index.html` must contain no `style="…"` attribute and no `<style>` element, and `js/script.js` must not write `element.style.*`, `cssText`, `setAttribute('style', …)`, `insertRule`, `adoptedStyleSheets`, or an injected `<style>` tag. Runtime style injection is inline CSS with extra steps, so it is treated the same way. Commented-out markup is ignored, and a commented-out `<link>` does not satisfy a requirement.
2. **EDS component match.** Every component named in `component-map.json` must exist in the EDS catalog and must contribute at least one of its canonical EDS classes to the markup, so a mapping cannot claim a component the page does not actually use.
3. **Responsive.** The viewport meta tag must be present and `css/styles.css` must contain real `@media` rules; the browser audit then confirms no horizontal overflow, broken image, clipped element, or unloaded font at every configured width — including one above the design width, where a layout pinned to the design's pixel offsets would otherwise pass unnoticed. See [Guarding the measurement](#guarding-the-measurement).

The same pass also verifies Bootstrap CSS/JS wiring, that `css/styles.css` is the last stylesheet so component overrides win the cascade, that no asset path was invented and none was left unused, and that `data-figma-id` hooks carry real Figma node ids.

## Geometry audit

A whole-page image diff is close to useless on a long page: one section that is 80px too tall displaces every section below it, so the diff reports that almost everything is wrong without indicating why. After each render the application reads the laid-out box of every `data-figma-id` element straight from the DOM and compares it with that Figma node's absolute box in CSS pixels:

- `heightErrorPx` / `widthErrorPx` — the element's own size defect.
- `offsetErrorPx` — its position error, most of which is inherited from earlier siblings.
- `driftIntroducedPx` — the *new* vertical error that appeared between the previous section and this one, which attributes each displacement to the gap that actually caused it.

The refiner is told to work down `driftIntroducedPx` first, and the report shows the same table plus the total document-height error. Because the hooks make this possible, an emitted `data-figma-id` that is not a real node id (a layer name, for example) is itself a contract violation — otherwise the audit degrades silently to a single page-height number.

### Guarding the measurement

Any metric can be satisfied the wrong way. The cheapest way to match a Figma box is to pin the element to that absolute offset, force it to that height, and clip whatever no longer fits — which reproduces the design width exactly and breaks every other width. Three checks close that off:

- **Pinning.** A viewport above the design width (`WIDE_AUDIT_RATIO`, default 1.4×) is always audited. A centred element keeps a constant distance from the viewport centre as the viewport grows, while an element pinned to a fixed left offset drifts by exactly half the width increase. The ratio between the two is a scale-free score — 0 is centred, 1 is fully pinned — and anything above 0.5 is a responsive violation.
- **Clipping.** Any element whose `overflow` is hidden while its content overflows its box is reported at every audited width. A fixed height never trips an overflow check, because the box itself does not grow.
- **CSS shape.** A rule pairing a fixed pixel `height` with a hidden `overflow`, and class names derived from pixel offsets (`.x279`), are contract violations in their own right.

## Configuration

All options are documented in [.env.example](.env.example). Important review controls are:

- `REVIEW_TARGET_ISSUES=0`: accept only when the reviewer returns no actionable issues.
- `MAX_REVIEW_ITERATIONS=8`: cap the LangGraph refinement loop.
- `MATCH_THRESHOLD=95`: informational score target included in reports.
- `VISUAL_DIFF=true`: enable browser rendering when the optional visual dependencies are installed. While a Figma reference exists and rendering works, standard mode only accepts a candidate that was actually rendered and pixel-compared against the design; if the environment cannot render at all, it warns and falls back to the reviewer gate.
- `ACCURACY_MODE=standard|strict`: retain the normal reviewer gate or enforce objective visual evidence.
- `PIXEL_MISMATCH_TARGET=0`: maximum worst-viewport mismatch accepted by strict mode.
- `PIXEL_DIFF_THRESHOLD=31`: tolerant standard-mode channel threshold; strict mode always overrides it to `0`.
- `FIGMA_REFERENCE_NODES`: JSON width-to-node mapping for responsive ground truth.
- `RESPONSIVE_VIEWPORTS=375,768,1440`: widths audited for responsive failures between exact references.
- `GEOMETRY_TOLERANCE_PX=2`: per-element CSS-pixel tolerance for the DOM-versus-Figma geometry audit.
- `WIDE_AUDIT_RATIO=1.4`: multiple of the design width that is always audited, so a layout pinned to the design's pixel offsets cannot pass unnoticed.
- `LLM_MAX_TOKENS=64000`, `LLM_REVIEWER_MAX_TOKENS=32000`, `LLM_REASONING_EFFORT=xhigh`: model output budgets and reasoning effort.
- `RENDER_ALLOWED_ORIGINS`: comma-separated origins permitted during sandboxed browser capture.
- `PIXEL_DIFF_TILE_SIZE=160`: diagnostic tile size used to rank high-error regions.
- `MIN_PIXEL_IMPROVEMENT=0.01`: meaningful progress threshold used by plateau diagnostics.
- `EDS_NATIVE_CSS_PATH`: path to your Sitecore EDS native stylesheet.
- `EDS_STORYBOOK_REFRESH=false`: re-fetch component snippets from Storybook even when `eds-manifest.json` exists. Storybook is reachable only from the corporate network, so this stays off by default and the curated manifest is used as-is.

Optional [LangSmith tracing](https://docs.langchain.com/langsmith/observability-quickstart) can be enabled with `LANGSMITH_TRACING=true` and `LANGSMITH_API_KEY`.

## Development

```powershell
python -m pytest
python -m ruff check .
python -m mypy
```

The implementation follows the current [LangChain Anthropic integration](https://docs.langchain.com/oss/python/integrations/chat/anthropic) and [LangGraph Graph API](https://docs.langchain.com/oss/python/langgraph/graph-api).
