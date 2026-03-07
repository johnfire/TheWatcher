# bdd-vision — How to Use

End-to-end walkthrough from installation to a PDF test report.

---

## 1. Install

```bash
git clone https://github.com/johnfire/TheWatcher.git
cd TheWatcher
uv venv
uv pip install -e ".[dev]"
```

Verify:

```bash
bdd-vision --help
```

---

## 2. Configure API keys

Copy the example env file and add your keys:

```bash
cp .env.example .env
```

Edit `.env`:

```env
# At least one VLM key is required.
# DeepSeek is cheaper; Claude is higher quality.
DEEPSEEK_API_KEY=sk-...
ANTHROPIC_API_KEY=sk-ant-...

# Optional — not yet implemented
GEMINI_API_KEY=

# Which provider runs first (staging = DeepSeek → Claude, prod = Claude → DeepSeek)
MODEL_TIER=staging

# Cost guard — session stops if total spend exceeds this
MAX_COST_PER_SESSION_USD=5.00
```

---

## 3. Chrome setup

bdd-vision auto-launches Chrome with remote debugging enabled. You don't need to do anything — but Chrome or Chromium must be installed:

```bash
# Ubuntu / Debian
sudo apt install chromium-browser

# Or install google-chrome-stable manually
```

If Chrome is already running on port 9222 when you invoke a command, bdd-vision attaches to it instead of launching a new instance.

---

## 4. Workflow overview

```
init → crawl → spec generate → run → report
```

Each step produces files in `./data/<project-name>/`.

---

## 5. Step by step

### 5.1 Initialize a project

```bash
bdd-vision init --url https://example.com --name example
```

Creates `./data/example/` with subdirectories for specs, sitemaps, sessions, screenshots, and reports.

Optionally runs a smoke test (Chrome + VLM) to confirm everything is wired up.

---

### 5.2 Crawl the site

```bash
bdd-vision crawl example
```

bdd-vision launches Chrome, navigates to the project URL, and explores the site breadth-first. For each page it:

1. Takes a screenshot
2. Sends it to the VLM with a crawl prompt
3. Extracts page description, interactive elements, and navigation links
4. Follows same-domain links up to `max_pages` / `max_depth`

Output: `./data/example/sitemaps/sitemap_<timestamp>.json`

Options:

```bash
bdd-vision crawl example --max-pages 10 --max-depth 2
```

Settings defaults (`MAX_PAGES=30`, `MAX_DEPTH=4`) can be overridden in `.env` or via these flags.

---

### 5.3 Generate a BDD spec

```bash
bdd-vision spec generate example
```

Three-step interactive flow:

**Step 1 — Brief**
You describe what you want to test in plain English:
```
Brief: Test the user login and registration flows, including error states
```

**Step 2 — Clarifying questions**
The VLM reads your brief and the crawl sitemap, then asks targeted questions:
```
Q1: What credentials should be used for the happy-path login test?
> admin / password123

Q2: Should we test "Forgot password" flow?
> Yes

Q3: Are there any rate-limit or CAPTCHA considerations?
> No
```

**Step 3 — Spec generation**
The VLM generates a structured Gherkin-style spec and saves it:

```
✓ Spec v1 generated
  Scenarios : 6
  Steps     : 24
  Cost      : $0.0082

Feature: User Authentication
  Scenario                        Steps
  ──────────────────────────────────────
  Successful login                    4
  Login with invalid password         4
  ...
```

Output: `./data/example/specs/spec_v001.json`

To view the current spec later:

```bash
bdd-vision spec show example
```

To re-generate (previous version is kept):

```bash
bdd-vision spec edit example
```

---

### 5.4 Run the tests

```bash
bdd-vision run example
```

bdd-vision opens Chrome, navigates to the base URL, and executes each scenario. For every step:

1. Takes a before-screenshot
2. Asks the VLM: *what action should I take for this step?*
3. Executes the action (click, type, scroll, or observe)
4. Takes an after-screenshot
5. Asks the VLM: *did this step pass?*
6. Records pass / partial / fail based on VLM confidence

```
Results  session=a3f1b2c4
  Passed : 5/6
  Failed : 1
  Skipped: 0
  Steps  : 24
  Cost   : $0.1240

Scenario                          Status   Steps   Cost
──────────────────────────────────────────────────────────
Successful login                  pass       4   $0.0180
Login with invalid password       pass       4   $0.0210
Forgot password flow              fail       4   $0.0220
...
```

Output: `./data/example/sessions/<session-id>/session.json`

**Options:**

Run only scenarios whose name contains a string:
```bash
bdd-vision run example --scenario "login"
```

Use a specific spec file instead of the latest:
```bash
bdd-vision run example --spec ./data/example/specs/spec_v001.json
```

---

### 5.5 Generate a report

```bash
# Markdown (default)
bdd-vision report example a3f1b2c4

# PDF
bdd-vision report example a3f1b2c4 --format pdf
```

The session ID is shown in the `run` output. Both formats include:

- Session metadata (model, spec version, duration, total cost)
- Summary table (pass/fail/skip counts)
- Per-scenario step tables with status, confidence, action taken
- Deviation details for any failed or partial steps

Output: `./data/example/reports/report_<session-id>.md` (or `.pdf`)

---

## 6. Project data layout

```
data/
└── example/
    ├── project.json          # name, URL, spec_version
    ├── sitemaps/
    │   └── sitemap_20260307_120000.json
    ├── specs/
    │   ├── spec_v001.json
    │   └── spec_v002.json    # each edit creates a new version
    ├── sessions/
    │   └── a3f1b2c4/
    │       ├── session.json
    │       └── screenshots/
    │           ├── step01_before.png
    │           ├── step01_after.png
    │           └── ...
    ├── screenshots/
    │   └── crawl/            # screenshots taken during crawl
    └── reports/
        ├── report_a3f1b2c4.md
        └── report_a3f1b2c4.pdf
```

---

## 7. List all projects

```bash
bdd-vision list
```

---

## 8. Settings reference

All settings can be set in `.env` or as environment variables.

| Variable | Default | Description |
|----------|---------|-------------|
| `MODEL_TIER` | `staging` | `staging` (DeepSeek first), `prod` (Claude first), `dev` (Gemini first) |
| `DEEPSEEK_API_KEY` | — | DeepSeek API key |
| `ANTHROPIC_API_KEY` | — | Anthropic API key |
| `GEMINI_API_KEY` | — | Gemini API key (stub — not yet active) |
| `MAX_COST_PER_SESSION_USD` | `5.00` | Hard stop if a single session exceeds this |
| `MAX_SCREENSHOTS_PER_RUN` | `200` | Screenshot cap per run |
| `MAX_PAGES` | `30` | Max pages to crawl |
| `MAX_DEPTH` | `4` | Max crawl depth from the root URL |
| `CRAWL_TIMEOUT_SECONDS` | `300` | Crawl wall-clock timeout |
| `CHROME_CDP_PORT` | `9222` | Chrome remote debugging port |
| `BROWSER_HEADLESS` | `false` | Run Chrome headless (no visible window) |
| `BROWSER_WIDTH` | `1280` | Browser window width |
| `BROWSER_HEIGHT` | `900` | Browser window height |
| `DATA_DIR` | `./data` | Where project data is stored |

Logs go to `~/logs/bdd-vision.log` (rotated at 10 MB, kept 30 days).

---

## 9. Cost estimates

Costs depend on your provider tier and how many pages/steps you have.

| Operation | Per call | Typical session |
|-----------|----------|----------------|
| Crawl page (DeepSeek) | ~$0.002 | $0.02–$0.10 for 10–50 pages |
| Spec generation (DeepSeek) | ~$0.005 | $0.01–$0.02 total |
| Test step (DeepSeek, 2 VLM calls) | ~$0.004 | $0.05–$0.20 for 20–50 steps |
| Crawl page (Claude) | ~$0.05 | $0.50–$2.50 for 10–50 pages |
| Test step (Claude, 2 VLM calls) | ~$0.10 | $1.00–$5.00 for 20–50 steps |

Use `MODEL_TIER=staging` (DeepSeek first) for development and exploration. Switch to `prod` (Claude first) for CI or high-stakes runs.

---

## 10. Troubleshooting

**Chrome won't connect**
```
✗ Chrome connection failed: ...
```
Make sure no other process is using port 9222, or change `CHROME_CDP_PORT` in `.env`.

**All providers failed**
```
✗ VLM analysis failed: All providers failed.
```
Check your API keys in `.env`. At least one of `DEEPSEEK_API_KEY` or `ANTHROPIC_API_KEY` must be set and valid.

**No sitemap found**
```
✗ No sitemap found for project 'example'. Run `bdd-vision crawl` first.
```
Run `bdd-vision crawl example` before `bdd-vision spec generate`.

**pyautogui / X11 error in headless environments**
bdd-vision requires a real display for mouse/keyboard control (the `run` command). SSH with X forwarding or a VNC session works. The `crawl` and `spec` commands don't require a display.
