# TheWatcher — bdd-vision

AI-powered BDD testing agent. Vision-language models test websites by seeing the screen as pixels — no DOM scraping, no selectors.

## Current Phase

**Phase 1 — Foundation**: screenshot capture + VLM analysis + Chrome CDP + CLI `init` command

## Primary Entry Points

- [src/bdd_vision/cli/main.py](../src/bdd_vision/cli/main.py) — CLI entry point
- [src/bdd_vision/config/settings.py](../src/bdd_vision/config/settings.py) — all configuration
- [src/bdd_vision/models/router.py](../src/bdd_vision/models/router.py) — VLM provider management
- [src/bdd_vision/browser/cdp.py](../src/bdd_vision/browser/cdp.py) — Chrome DevTools Protocol
- [src/bdd_vision/browser/capture.py](../src/bdd_vision/browser/capture.py) — screenshot capture

## Run

```bash
uv pip install -e ".[dev]"
bdd-vision --help
bdd-vision init --url https://example.com --name test-project
```

## Test

```bash
pytest tests/
```

## Do Not Touch

- `data/` — runtime data, gitignored
- `.env` — secrets, gitignored

## Key Constraints

- **CDP is ONLY for page lifecycle**: navigate, wait for network idle, get URL/title. Never for DOM inspection.
- **VLM keys never hardcoded** — always from environment / .env
- **Anti-fragile**: every component catches and logs failures, never propagates silently
- **Logs go to ~/logs/**, not project-relative paths
- **Model-agnostic**: rest of system never cares which VLM is running — all interactions via ModelRouter

## Active Providers

- DeepSeek VL2 (staging tier, cheaper)
- Claude claude-opus-4-6 (prod tier, higher quality)
- Gemini Flash 2.0 (stub, not yet configured)
