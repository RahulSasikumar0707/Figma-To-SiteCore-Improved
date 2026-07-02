# Figma → Sitecore EDS Converter

Converts a Figma design node into **pixel-accurate, responsive HTML/CSS/JS** built on
**Bootstrap 5.1.3** and the **Sitecore EDS component library** (37 components), using a
two-agent Claude pipeline (generator + independent reviewer) that iterates until the
output matches the design.

## How it works

```
Figma (MCP local server ▸ REST fallback)
   │  node tree · variables · dev-mode context · reference screenshot
   ▼
Normalizer  ── auto-layout → flexbox semantics, colors → hex, typography, asset plan
   ▼
Asset pipeline ── images (original fills) · icons/vectors (SVG) → Output_N/assets/
   ▼
Design tokens ── css/tokens.css (every color/size/space/radius/shadow as --fig-* vars)
   ▼
EDS matcher ── scores design sections against eds-manifest.json (37 components)
   ▼
Generator agent (ANTHROPIC_API_KEY_1) ── EDS DOM structures + Bootstrap grid/behaviors
   ▼
Reviewer agent (ANTHROPIC_API_KEY_2) ── vision compare vs Figma screenshot
   │            (+ optional headless-Chrome render & pixel diff)
   └── fix list → generator → re-review … until score ≥ MATCH_THRESHOLD
   ▼
Output_1/ · Output_2/ · …  (auto-incremented per run)
```

## Setup

```bash
npm install
# optional, enables the browser render + pixel-diff verification:
npm i puppeteer
```

Configure `.env`:

| Variable | Purpose |
|---|---|
| `ANTHROPIC_API_KEY_1` | Generator agent key (required) |
| `ANTHROPIC_API_KEY_2` | Reviewer agent key (falls back to key 1) |
| `ANTHROPIC_MODEL` | Claude model (default `claude-fable-5`) |
| `FIGMA_TOKEN` | Figma personal access token (REST tree + asset export) |
| `FIGMA_FILE_KEY` | Target file key |
| `FIGMA_NODE_ID` | Target node id (`68569:2790` or `68569-2790`) |
| `FIGMA_MCP_URL` | Local Dev Mode MCP server (default `http://127.0.0.1:3845/mcp`) |
| `FIGMA_SOURCE` | `auto` (default) / `mcp` / `rest` |
| `EDS_NATIVE_CSS_PATH` | Path to `eds-native.css` — copied into the output when found |
| `REVIEW_TARGET_ISSUES` | The loop accepts only when the reviewer reports ≤ this many issues (default `0` — iterate until the issue list is empty) |
| `MAX_REVIEW_ITERATIONS` | Generate→review→fix rounds cap (default `8`) |
| `MATCH_THRESHOLD` | Informational score target recorded in the report (default `95`) |
| `VISUAL_DIFF` | `true`/`false` — browser render + pixel diff (default `true`, needs puppeteer) |

Each review round renders the page in headless Chrome, computes a pixel-diff heatmap
(`reference/pixel-diff.png`), and hands the Figma design, the current render **and** the
heatmap to both agents — the reviewer to find issues, the generator to fix them visually.

> The MCP source needs the Figma **desktop app** running with *Dev Mode MCP server*
> enabled (Figma menu → Preferences). Without it the converter automatically uses the
> REST API, which is fully sufficient.

## Run

```bash
npm start                       # converts FIGMA_FILE_KEY / FIGMA_NODE_ID from .env
node src/index.js --node 12:34  # override the node per run
node src/index.js --manifest-only   # rebuild eds-manifest.json by scanning eds-components/
```

Each run creates a fresh folder:

```
Output_1/
├── index.html            # EDS + Bootstrap responsive page
├── css/tokens.css        # design tokens extracted from Figma
├── css/styles.css        # component styles (overrides eds-native.css)
├── css/eds-native.css    # copied in when found on this machine
├── js/script.js
├── assets/images|icons|vectors/
├── component-map.json    # Figma section → EDS component mapping
├── reference/figma-design.png       # ground-truth render from Figma
├── reference/generated-render.png   # headless-Chrome render (when enabled)
├── report.json / REPORT.md          # scores, iterations, mapping, warnings
```

## Key files

- `eds-manifest.json` — deep metadata for all 37 EDS components (classes, modifiers,
  variants, keywords, canonical snippets). Regenerate a basic version with
  `--manifest-only`; the curated one checked in was produced by multi-agent analysis.
- `src/figma/normalize.js` — Figma tree → layout spec + asset detection algorithms.
- `src/eds/matcher.js` — section→component scoring heuristics.
- `src/llm/generator.js` / `src/llm/reviewer.js` — the two-key agent loop.
