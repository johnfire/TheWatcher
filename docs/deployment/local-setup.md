# Local Development Setup

## Requirements

- Python 3.12+
- Chrome or Chromium
- Linux desktop with X11 (macOS secondary)
- DeepSeek API key and/or Anthropic API key

## Bootstrap

```bash
git clone <repo>
cd TheWatcher
bash scripts/setup.sh
```

This will:
1. Check Python version
2. Install `uv` if not present
3. Install system dependencies (`python3-xlib`, `scrot`, `xdotool`)
4. Install Python packages: `uv pip install -e ".[dev]"`
5. Create `.env` from `.env.example`
6. Create `~/logs/` and `data/` directories

## Configure API Keys

Edit `.env`:

```bash
DEEPSEEK_API_KEY=sk-...
ANTHROPIC_API_KEY=sk-ant-...
MODEL_TIER=staging   # staging = DeepSeek first, prod = Claude first
```

## Verify Installation

```bash
bdd-vision --help
```

## Run Smoke Test

```bash
bdd-vision init --url https://example.com --name smoke
# Answer 'y' to the smoke test prompt
```

This will:
1. Auto-launch Chrome with `--remote-debugging-port=9222`
2. Navigate to `https://example.com`
3. Take a screenshot
4. Send to your configured VLM
5. Print the VLM's description of the page

## Chrome Notes

Chrome is launched automatically with:
```
--remote-debugging-port=9222
--no-first-run
--no-default-browser-check
--disable-default-apps
```

If Chrome is already running without these flags, kill it first or use a fresh profile.

## Troubleshooting

**`python3-xlib` missing**: `sudo apt-get install python3-xlib`

**`pyautogui` import error**: Ensure `DISPLAY` is set: `export DISPLAY=:0`

**Chrome not found**: Install `google-chrome-stable` or `chromium-browser`

**DeepSeek VL2 model not available**: Try changing `DEEPSEEK_MODEL_NAME` in `.env` to a model name confirmed in your DeepSeek API dashboard
