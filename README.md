# TheWatcher — bdd-vision

AI-powered BDD testing agent. Tests websites the way a human QA tester does — by looking at the screen, not scraping the DOM.

**No Selenium. No Playwright selectors. No DOM instrumentation.**
A vision-language model sees the screen as pixels, understands the UI, and interacts using mouse and keyboard.

---

## How It Works

1. **Spec generation**: Interview + autonomous site crawl → generates a BDD spec in natural language
2. **Test execution**: VLM analyzes screenshots step by step, executes actions via mouse/keyboard
3. **Reporting**: PDF and markdown reports with pass/fail, screenshots, deviations, cost breakdown

---

## Quickstart

```bash
# Install
git clone <repo>
cd TheWatcher
cp .env.example .env
# Add your API keys to .env

bash scripts/setup.sh
uv pip install -e ".[dev]"

# Initialize a project
bdd-vision init --url https://example.com --name my-project

# Generate a test spec
bdd-vision spec generate --project my-project

# Run tests
bdd-vision run --project my-project

# Generate report
bdd-vision report --project my-project --format pdf
```

---

## Requirements

- Python 3.12+
- Chrome or Chromium (auto-launched by the tool)
- Linux desktop (X11) — macOS secondary
- API keys: DeepSeek and/or Anthropic (see `.env.example`)

---

## Tech Stack

| Layer | Technology |
|---|---|
| Language | Python 3.12 |
| CLI | Click + Rich |
| Browser control | pyautogui + Chrome DevTools Protocol |
| Screenshot capture | mss |
| Vision models | DeepSeek VL2, Claude (Anthropic), Gemini Flash |
| Config | pydantic-settings |
| Reports | reportlab (PDF) |

---

## Project Structure

```
src/bdd_vision/
├── cli/          # Click CLI entry point
├── config/       # Settings (pydantic-settings)
├── models/       # VLM providers + router
├── browser/      # Screenshot capture, CDP, mouse/keyboard
└── core/         # Orchestrator, spec engine, crawl, agent runner, reporter
```

---

## Support

If you find this useful, a small donation helps keep projects like this going:
[Donate via PayPal](https://paypal.me/christopherrehm001)
