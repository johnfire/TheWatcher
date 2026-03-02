# Tech Stack

| Layer | Technology | Version | Notes |
|---|---|---|---|
| Language | Python | 3.12+ | Required for `X | Y` union syntax |
| CLI | Click | >=8.1 | |
| CLI output | Rich | >=13.0 | Tables, colors |
| Config | pydantic-settings | >=2.0 | .env + env vars |
| HTTP client | httpx | >=0.27 | Async |
| VLM: DeepSeek | httpx (direct) | — | OpenAI-compatible API |
| VLM: Anthropic | anthropic SDK | >=0.40 | Async client |
| VLM: Gemini | google-generativeai | >=0.8 | Stub only |
| Screenshots | mss | >=9.0 | Fast, X11 |
| Mouse/keyboard | pyautogui | >=0.9.54 | Requires python-xlib on Linux |
| Browser lifecycle | websockets | >=13.0 | Raw CDP over WebSocket |
| Image processing | Pillow | >=10.0 | |
| Reports (PDF) | reportlab | >=4.0 | |
| Logging | loguru | >=0.7 | |
| Dep management | uv | latest | |
| Testing | pytest + pytest-asyncio | >=8.0, >=0.23 | asyncio_mode=auto |

## System Dependencies (Linux)

```bash
sudo apt-get install python3-xlib scrot xdotool
```

## API Endpoints

| Provider | Base URL |
|---|---|
| DeepSeek | https://api.deepseek.com/v1 |
| Anthropic | https://api.anthropic.com (via SDK) |
