# SiteCore Import Guide

This guide explains how to import Figma-generated HTML/CSS/JS into SiteCore.

## 📋 Overview

The import process has 3 main steps:

1. **Generate** structure JSON from an Output folder
2. **Validate** the structure before import
3. **Import** content to SiteCore via MCP server

## 🛠️ Available Tools

All tools are in `tools/sitecore-import/`:

| Tool | Purpose |
|------|---------|
| **generate-structure.js** | Creates sitecore-structure.json from Output_N folder |
| **validate-structure.js** | Validates structure JSON before import |
| **import-to-sitecore.js** | Automated import via MCP server |
| **IMPORT-GUIDE.md** | This documentation |

---

## 🚀 Quick Start

```bash
# 1. Generate structure (creates Output_1/sitecore-structure.json)
node tools/sitecore-import/generate-structure.js --input Output_1

# 2. Validate (optional but recommended)
node tools/sitecore-import/validate-structure.js Output_1/sitecore-structure.json

# 3. Start MCP server (separate terminal)
npm run sitecore-mcp:http

# 4. Import to SiteCore
node tools/sitecore-import/import-to-sitecore.js \
  --structure Output_1/sitecore-structure.json \
  --assets Output_1/assets \
  --http http://localhost:3847/mcp

# Or using npm scripts (pass arguments after --)
npm run generate-structure -- --input Output_2
npm run validate-structure -- Output_2/sitecore-structure.json
npm run import-sitecore -- --structure Output_2/sitecore-structure.json --assets Output_2/assets --http http://localhost:3847/mcp
```

---

## 📖 Detailed Steps

### Step 1: Generate Structure JSON

After running the Figma converter (`npm start`), you'll have an `Output_N` folder with HTML/CSS/JS. Generate the SiteCore structure blueprint:

```bash
# Creates Output_1/sitecore-structure.json
node tools/sitecore-import/generate-structure.js --input Output_1

# Or using npm script
npm run generate-structure -- --input Output_1
```

**Options:**
- `--input <dir>` - (Required) Path to Output folder (Output_1, Output_2, etc.)
- `--output <file>` - Output file name (default: saves in input directory as `sitecore-structure.json`)
- `--page-name <name>` - Custom page name (default: extracted from HTML)

**Output Location:**
- By default, the structure file is saved **inside the input directory** (e.g., `Output_1/sitecore-structure.json`)
- Use `--output` with an absolute path to save elsewhere

**Examples:**
```bash
# Creates Output_2/sitecore-structure.json
node tools/sitecore-import/generate-structure.js --input Output_2

# Custom output file in same directory: Output_2/about-page.json
node tools/sitecore-import/generate-structure.js \
  --input Output_2 \
  --output about-page.json \
  --page-name "About Us"

# Save to different location (absolute path)
node tools/sitecore-import/generate-structure.js \
  --input Output_3 \
  --output C:/Projects/structures/contact-page.json \
  --page-name "Contact"
```

**Output:**
Creates `sitecore-structure.json` with:
- Page item definition
- Datasource items (one per component from component-map.json)
- Media library items
- Layout/rendering assignments

---

### Step 2: Validate Structure (Optional)

Validate the generated structure before importing:

```bash
node tools/sitecore-import/validate-structure.js sitecore-structure.json
```

**Checks:**
- ✅ Valid JSON format
- ✅ Required fields present
- ✅ SiteCore paths well-formed
- ✅ GUIDs in correct format
- ✅ No duplicate items
- ✅ Referenced asset files exist

**Options:**
- `--verbose` or `-v` - Show detailed info messages

**Exit codes:**
- `0` - Validation passed (safe to import)
- `1` - Validation failed (fix errors before import)

---

### Step 3: Import to SiteCore

#### Prerequisites

1. **SiteCore Item Service API** accessible at configured URL
2. **Environment variables** set in `.env`:
   ```env
   ITEM_SERVICE_SERVER_URL=https://your-sitecore.com
   ITEM_SERVICE_USERNAME=admin
   ITEM_SERVICE_PASSWORD=your-password
   ITEM_SERVICE_DOMAIN=sitecore  # optional
   ```
3. **MCP server running** (see below)

#### Start MCP Server

In a **separate terminal**:

```bash
# HTTP mode (recommended)
npm run sitecore-mcp:http

# Or stdio mode (automatic spawning)
npm run sitecore-mcp
```

The HTTP server runs on port `3847` by default. Change with:
```env
SITECORE_MCP_PORT=8080
```

#### Run Import

```bash
# Works with any Output folder's assets
node tools/sitecore-import/import-to-sitecore.js \
  --structure sitecore-structure.json \
  --assets Output_1/assets \
  --http http://localhost:3847/mcp

# Or using npm script (pass args after --)
npm run import-sitecore -- \
  --structure sitecore-structure.json \
  --assets Output_2/assets \
  --http http://localhost:3847/mcp
```

**Options:**
- `--structure <file>` - (Required) Path to structure JSON
- `--assets <dir>` - Path to assets directory (e.g., Output_1/assets, Output_2/assets)
- `--http <url>` - Use HTTP MCP server (default: stdio mode)
- `--dry-run` - Validate and preview without making changes

**Import steps:**
1. ✅ Create page item at `/sitecore/content/Home/[Page-Name]`
2. ✅ Create `Data` folder under page
3. ✅ Create datasource items (Header, Hero, Cards, Footer, etc.)
4. ✅ Upload media assets to `/sitecore/media library/Project/VANDDMYO`
5. ✅ Assign layout renderings
6. ✅ Publish to web database

**Dry run examples:**
```bash
# Preview what would be imported without making changes
node tools/sitecore-import/import-to-sitecore.js \
  --structure sitecore-structure.json \
  --dry-run

# Using npm script with dry run
npm run import-sitecore:dry-run -- --structure sitecore-structure.json

# Preview import from Output_3
node tools/sitecore-import/import-to-sitecore.js \
  --structure sitecore-structure.json \
  --assets Output_3/assets \
  --dry-run
```

---

## 📝 Manual Import (Alternative)

If you prefer manual import via SiteCore UI, use the structure JSON as a reference:

### Content Tree Structure

```
/sitecore/content/Home/
└── [Page-Name]/              ← structure.page
    ├── Data/                 ← Folder
    │   ├── header            ← structure.datasources[0]
    │   ├── hero-banner       ← structure.datasources[1]
    │   ├── content-block-1   ← structure.datasources[2]
    │   ├── card-1            ← structure.datasources[3]
    │   ├── accordion         ← structure.datasources[4]
    │   ├── flip-card-1       ← structure.datasources[5]
    │   ├── content-block-2   ← structure.datasources[6]
    │   ├── content-block-3   ← structure.datasources[7]
    │   ├── isi               ← structure.datasources[8]
    │   └── footer            ← structure.datasources[9]
```

### Manual Steps

1. **Create Page:**
   - Navigate to `/sitecore/content/Home`
   - Insert → Standard Page
   - Name from `structure.page.name`
   - Set fields from `structure.page.fields`

2. **Create Data Folder:**
   - Under page, insert → Folder
   - Name: `Data`

3. **Create Datasources:**
   - For each `structure.datasources[]` item:
     - Insert under `Data/`
     - Use `name` property as item name
     - Set fields from `fields` object

4. **Upload Media:**
   - Navigate to `/sitecore/media library/Project`
   - Create folder: `VANDDMYO` (or your project name)
   - Upload files from `assets/` directory

5. **Assign Layout:**
   - Open page in Experience Editor
   - Add renderings from `structure.layout.renderings[]`
   - Link each rendering to its datasource in `Data/`

6. **Publish:**
   - Right-click page → Publishing → Publish
   - Mode: Smart
   - Target: `web`

---

## 🔧 Troubleshooting

### "Cannot connect to MCP server"

**Solution:**
- Ensure MCP server is running: `npm run sitecore-mcp:http`
- Check port is correct: `http://localhost:3847/mcp`
- Verify no firewall blocking port 3847

### "Unauthorized" or "403 Forbidden"

**Solution:**
- Check `.env` credentials are correct
- Verify `ITEM_SERVICE_SERVER_URL` is accessible
- Test credentials manually in SiteCore UI
- Check domain is specified if using Windows auth

### "Item already exists"

**Solution:**
- Delete existing items in SiteCore or rename
- Use unique page names with `--page-name` flag
- Clear out previous test imports

### "Asset file not found"

**Solution:**
- Ensure `--assets` path is correct
- Verify assets exist in Output folder
- Check asset paths in structure JSON are relative

### Validation fails

**Solution:**
- Run validator with `--verbose` to see details
- Check GUID format (must be `{XXXXXXXX-XXXX-XXXX-XXXX-XXXXXXXXXXXX}`)
- Verify paths start with `/sitecore/`
- Fix any special characters in item names

---

## 🎯 Production Deployment

For **production** environments:

1. ✅ Always run `--dry-run` first
2. ✅ Validate structure with `validate-structure.js`
3. ✅ Test import on dev/staging environment
4. ✅ Export as SiteCore package instead of direct import
5. ✅ Follow your organization's deployment process
6. ✅ Document any manual template/rendering setup needed

### Export as Package

After successful dev import:

1. Content Editor → `/sitecore/content/Home/[Page]`
2. Right-click → Export → Package Designer
3. Add page + Data folder items
4. Add media library items
5. Save package
6. Deploy package to production via standard process

---

## 📚 Additional Resources

- **SiteCore MCP Tools:** See `src/sitecore/mcpServer.js` for all 11 available tools
- **Item Service API:** https://doc.sitecore.com/xp/en/developers/hd/21/sitecore-headless-development/sitecore-services-client-item-web-api.html
- **MCP Documentation:** https://modelcontextprotocol.io
- **Project README:** See root `README.md` for complete workflow

---

## 💡 Tips

- **Multiple runs:** Each Figma conversion creates a new Output_N folder - you can work with any of them
- **Incremental imports:** Generate structure for each Output folder independently (Output_1, Output_2, etc.)
- **Folder selection:** Always specify which Output folder with `--input Output_N` and `--assets Output_N/assets`
- **Reusable templates:** Update template GUIDs in structure JSON to match your SiteCore instance
- **Asset optimization:** Compress images before import for better performance
- **Component mapping:** Review `component-map.json` in each Output folder to verify EDS component selection
- **Versioning:** Add page version notes in SiteCore after each import
- **Testing workflow:** Use Output_1 for testing, then regenerate with fixes → Output_2, Output_3, etc.
