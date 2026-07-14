# HTML Compare

Fetches a live Gilead page and compares it against a generated output folder's
`index.html`, then uses the Anthropic LLM to list the content/structure
differences between them.

## Usage

```powershell
node tools/html-compare/compare-html.js --url "https://dxcmpt6.gilead.com/about-vanddmyo" --output Output_2
```

Or via the npm script:

```powershell
npm run compare-html -- --url "https://dxcmpt6.gilead.com/about-vanddmyo" --output Output_2
```

## Options

| Flag         | Description                                                              |
| ------------ | ------------------------------------------------------------------------ |
| `--url`      | **Required.** Live Gilead page URL (the source of truth).                |
| `--output`   | **Required.** Output folder (e.g. `Output_2`) or a full path. Reads `<folder>/index.html`. |
| `--file`     | HTML file name inside the output folder (default: `index.html`).         |
| `--out`      | Directory for the report (default: `tools/html-compare/results/<timestamp>`). |
| `--model`    | Anthropic model id (default: `ANTHROPIC_MODEL` or `claude-fable-5`).     |
| `--help`     | Show help.                                                               |

## Environment

Reads the repo-root `.env`:

- `ANTHROPIC_API_KEY_1` (or `ANTHROPIC_API_KEY`) — required.
- `ANTHROPIC_MODEL` — optional default model id.

## Output

Two files are written to the results directory:

- `comparison.md` — human-readable report (also printed to the console).
- `comparison.json` — structured verdict: `summary`, `matchPercent`, and a
  `differences[]` array (`severity`, `area`, `type`, `live`, `generated`,
  `recommendation`).
