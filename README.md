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
   │  index.html · css/ · js/ · assets/ · component-map.json · reference/ · report.json
   ▼
[OPTIONAL] SiteCore Import (Manual Process)
   │
   │  Using tools from tools/sitecore-import/:
   │
   ├── 1. Generate structure blueprint from Output_N:
   │      node tools/sitecore-import/generate-structure.js --input Output_1
   │      → creates sitecore-structure.json
   │
   ├── 2. Validate before import:
   │      node tools/sitecore-import/validate-structure.js sitecore-structure.json
   │
   ├── 3a. Manual: Use JSON as reference in SiteCore UI
   │
   └── 3b. Automated: Run import via MCP Server
          node tools/sitecore-import/import-to-sitecore.js --structure sitecore-structure.json
          → creates pages, datasources, media, renderings in SiteCore
```

## Setup

```bash
npm install
# optional, enables the browser render + pixel-diff verification:
npm i puppeteer
```

Configure `.env`:

### Figma → HTML Conversion

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

### SiteCore Integration (Optional)

| Variable | Purpose |
|---|---|
| `ITEM_SERVICE_SERVER_URL` | SiteCore base URL (e.g., `https://sitecore.example.com/sitecore`) |
| `ITEM_SERVICE_USERNAME` | SiteCore username for API authentication |
| `ITEM_SERVICE_PASSWORD` | SiteCore password for API authentication |
| `ITEM_SERVICE_DOMAIN` | Optional domain prefix (e.g., `sitecore`) |
| `SITECORE_MCP_PORT` | HTTP server port for MCP server (default `3847`) |

Each review round renders the page in headless Chrome, computes a pixel-diff heatmap
(`reference/pixel-diff.png`), and hands the Figma design, the current render **and** the
heatmap to both agents — the reviewer to find issues, the generator to fix them visually.

> The MCP source needs the Figma **desktop app** running with *Dev Mode MCP server*
> enabled (Figma menu → Preferences). Without it the converter automatically uses the
> REST API, which is fully sufficient.

## Run

### Figma → HTML Conversion

```bash
npm start                       # converts FIGMA_FILE_KEY / FIGMA_NODE_ID from .env
node src/index.js --node 12:34  # override the node per run
node src/index.js --manifest-only   # rebuild eds-manifest.json from the EDS Storybook
```

### SiteCore MCP Server

```bash
npm run sitecore-mcp            # stdio mode (for Claude Desktop / VS Code)
npm run sitecore-mcp:http       # HTTP mode on port 3847 (for testing)
```

Each run creates a fresh folder:

```
Output_1/
├── index.html            # EDS + Bootstrap responsive page
├── css/
│   ├── tokens.css        # design tokens extracted from Figma
│   ├── styles.css        # component styles (overrides eds-native.css)
│   └── eds-native.css    # copied in when found on this machine
├── js/script.js
├── assets/
│   ├── images/
│   ├── icons/
│   └── vectors/
├── component-map.json    # Figma section → EDS component mapping
├── reference/
│   ├── figma-design.png        # ground-truth render from Figma
│   ├── generated-render.png    # headless-Chrome render (when enabled)
│   └── pixel-diff.png          # diff heatmap (when enabled)
└── report.json / REPORT.md     # scores, iterations, mapping, warnings
```

**SiteCore import tools** are separate (in `tools/sitecore-import/`):

```
tools/sitecore-import/
├── generate-structure.js        # Generate sitecore-structure.json from Output_N
├── validate-structure.js        # Validate structure before import
├── import-to-sitecore.js        # Automated MCP-based import
└── IMPORT-GUIDE.md              # Import documentation
```

## SiteCore Import

After generating HTML/CSS/JS, use the **SiteCore MCP server** to push content into SiteCore.

### SiteCore MCP Server

A standalone MCP server that provides programmatic access to SiteCore's Item Service API.

**Configure** `.env` with your SiteCore credentials:

```bash
ITEM_SERVICE_SERVER_URL=https://your-sitecore.com/sitecore
ITEM_SERVICE_USERNAME=your-username
ITEM_SERVICE_PASSWORD=your-password
ITEM_SERVICE_DOMAIN=sitecore  # optional
```

**Start the server:**

```bash
# stdio mode (for Claude Desktop / VS Code Copilot)
npm run sitecore-mcp

# HTTP mode (for testing / custom clients)
npm run sitecore-mcp:http    # runs on http://localhost:3847/mcp
```

**Available tools:**

- `sitecore_get_item` — Get item fields by path or GUID
- `sitecore_search_items` — Search by keyword/template/path
- `sitecore_create_item` — Create item from template
- `sitecore_update_item_fields` — Update field values
- `sitecore_delete_item` — Delete item (requires confirmation)
- `sitecore_download_media` — Download media as base64
- `sitecore_upload_media` — Upload base64 content
- `sitecore_get_layout` — Get JSS layout data
- `sitecore_publish` — Trigger publish job
- `sitecore_push_rendering` — Push generated component as rendering
- `sitecore_request` — Generic API pass-through

### Import Generated Content

Use the tools in `tools/sitecore-import/` to push content to SiteCore:

**1. Generate SiteCore structure** from your Output folder:

```bash
# Using npm script (creates Output_1/sitecore-structure.json)
npm run generate-structure -- --input Output_1

# Or directly (creates Output_2/sitecore-structure.json by default)
node tools/sitecore-import/generate-structure.js --input Output_2

# Custom output location
node tools/sitecore-import/generate-structure.js --input Output_2 --output /path/to/my-structure.json
```

This analyzes `component-map.json` and generates a complete content tree blueprint in the Output folder.

**2. Validate structure** (optional but recommended):

```bash
# Using npm script (validates Output_1/sitecore-structure.json)
npm run validate-structure -- Output_1/sitecore-structure.json

# Or directly
node tools/sitecore-import/validate-structure.js Output_2/sitecore-structure.json --verbose
```

**3. Import to SiteCore**:

```bash
# Ensure MCP server is running (in separate terminal)
npm run sitecore-mcp:http

# Preview import (dry run)
npm run import-sitecore:dry-run -- --structure Output_1/sitecore-structure.json

# Run automated import (structure file is in Output_1/)
npm run import-sitecore -- --structure Output_1/sitecore-structure.json --assets Output_1/assets --http http://localhost:3847/mcp

# Or directly with different output folder
node tools/sitecore-import/import-to-sitecore.js \
  --structure Output_2/sitecore-structure.json \
  --assets Output_2/assets \
  --http http://localhost:3847/mcp
```

This creates:
- Page item at `/sitecore/content/Home/[Page-Name]`
- Datasource items for each component (Header, Hero, Cards, Accordion, Footer, etc.)
- Media library items for all assets
- View Rendering definitions
- Layout assignments

**4. Manual import**: See `tools/sitecore-import/IMPORT-GUIDE.md` for:
- Manual UI import steps
- Content tree structure
- Component mapping details
- Production deployment guidelines

> ⚠️ **Dev Environment**: For dev servers, review and test imports before running automation.
> For production, export as SiteCore packages and follow deployment workflows.
> 
> **Note**: The example files in `Output_1/` (sitecore-structure.json, import-to-sitecore.js, etc.) 
> are demonstrations. The actual tools should be used from `tools/sitecore-import/`.

## Key files

### Figma → HTML Conversion

- `eds-manifest.json` — deep metadata for all 37 EDS components (classes, modifiers,
  variants, keywords, canonical snippets). Regenerate a basic version with
  `--manifest-only`; the curated one checked in was produced by multi-agent analysis.
- `src/eds/storybook.js` — fetches each component's live DOM snippet from the EDS
  redesign Storybook (`EDS_STORYBOOK_BASE`, default `https://affinitycmpd103.gilead.com`).
  Snippets are refreshed from Storybook on every run and used to ground the agents.
- `src/figma/normalize.js` — Figma tree → layout spec + asset detection algorithms.
- `src/eds/matcher.js` — section→component scoring heuristics.
- `src/llm/generator.js` / `src/llm/reviewer.js` — the two-key agent loop.

### SiteCore Integration

**MCP Server** (programmatic SiteCore access):
- `src/sitecore-mcp.js` — entry point for the SiteCore MCP server (stdio or HTTP mode).
- `src/sitecore/mcpServer.js` — MCP server implementation with 11 tools for SiteCore operations.
- `src/sitecore/restClient.js` — HTTP client for SiteCore Item Service API (Basic auth).

**Import Tools** (content migration):
- `tools/sitecore-import/generate-structure.js` — analyzes Output_N and creates sitecore-structure.json blueprint.
- `tools/sitecore-import/validate-structure.js` — validates structure JSON before import.
- `tools/sitecore-import/import-to-sitecore.js` — automated import script using MCP tools.
- `tools/sitecore-import/IMPORT-GUIDE.md` — comprehensive import documentation.

## Security Considerations

### SiteCore Credentials

- Store `ITEM_SERVICE_*` credentials in `.env` file (never commit to version control)
- `.env` is gitignored by default
- Use environment-specific credentials for dev/staging/production
- Rotate credentials regularly

### MCP Server Access

The SiteCore MCP server provides **full access** to your SiteCore instance through the configured credentials:
- **stdio mode**: Only accessible to the local process (Claude Desktop, VS Code)
- **HTTP mode**: Exposed on `localhost:3847` (not network accessible by default)
- For network access, implement authentication middleware
- Do not expose HTTP mode to untrusted networks

### Authorization Header Override (Known Issue)

The `sitecore_request` tool allows passing custom headers, which can potentially override the `Authorization` header. 

**Mitigation**: The MCP server reads credentials per-request from environment variables. Only trusted clients (Claude Desktop, authenticated MCP clients) should have access to the server.

**Production deployment**: Use SiteCore packages (.zip) or deployment tools (TDS, Unicorn) instead of direct MCP automation.

## Troubleshooting

### "Missing required env vars"
Ensure `.env` contains all required variables for your workflow. Check that:
- Figma credentials are set for HTML generation
- SiteCore credentials are set for MCP operations
- No spaces around `=` in `.env` entries

### "Cannot connect to Figma MCP"
The Figma desktop app may not be running or Dev Mode MCP is disabled:
- Open Figma desktop app
- Check: Figma menu → Preferences → Enable Dev Mode MCP server
- Or set `FIGMA_SOURCE=rest` to use REST API instead

### "SiteCore MCP server not responding"
- Verify server is running: `npm run sitecore-mcp:http`
- Check health endpoint: `curl http://localhost:3847/health`
- Ensure `ITEM_SERVICE_*` credentials are correct
- Check network connectivity to SiteCore instance

### "Item already exists" during import
- Delete existing items in SiteCore first
- Or modify `import-to-sitecore.js` to update instead of create
- Check `sitecore-structure.json` for duplicate paths

### Review loop not converging
- Increase `MAX_REVIEW_ITERATIONS` (default 8)
- Adjust `REVIEW_TARGET_ISSUES` to accept more issues (default 0)
- Set `VISUAL_DIFF=false` to disable pixel diff (speeds up but less accurate)
- Simplify the Figma design or split into smaller components

## License & Credits

This project integrates:
- **Bootstrap 5.1.3** — MIT License
- **Anthropic Claude** — requires API key
- **Figma API** — requires personal access token
- **SiteCore** — requires valid instance and credentials
- **Model Context Protocol (MCP)** — Anthropic's standard for AI-application integration

Built for converting Figma designs to SiteCore EDS components with AI-powered generation and review.
