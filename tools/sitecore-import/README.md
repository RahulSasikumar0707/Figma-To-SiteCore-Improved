# SiteCore Import Tools

Reusable tools for importing Figma-generated content into SiteCore.

## Quick Reference

```bash
# 1. Generate structure (creates Output_1/sitecore-structure.json)
node tools/sitecore-import/generate-structure.js --input Output_1
# or Output_2, Output_3, etc.

# 2. Validate structure
node tools/sitecore-import/validate-structure.js Output_1/sitecore-structure.json

# 3. Import to SiteCore (requires MCP server running)
node tools/sitecore-import/import-to-sitecore.js \
  --structure Output_1/sitecore-structure.json \
  --assets Output_1/assets \
  --http http://localhost:3847/mcp

# Using npm scripts (pass args after --)
npm run generate-structure -- --input Output_2
npm run validate-structure -- Output_2/sitecore-structure.json
npm run import-sitecore -- --structure Output_2/sitecore-structure.json --assets Output_2/assets --http http://localhost:3847/mcp
```

## Tools

| File | Description |
|------|-------------|
| `generate-structure.js` | Analyzes Output_N folder and creates sitecore-structure.json |
| `validate-structure.js` | Validates structure JSON before import |
| `import-to-sitecore.js` | Automated import using SiteCore MCP server |
| `IMPORT-GUIDE.md` | Complete documentation |

## Prerequisites

- Node.js installed
- SiteCore Item Service API accessible
- Environment variables configured in `.env`:
  ```env
  ITEM_SERVICE_SERVER_URL=https://your-sitecore.com
  ITEM_SERVICE_USERNAME=admin
  ITEM_SERVICE_PASSWORD=your-password
  ```

## Documentation

See [IMPORT-GUIDE.md](./IMPORT-GUIDE.md) for complete documentation including:
- Step-by-step instructions
- All command options
- Troubleshooting guide
- Production deployment process
