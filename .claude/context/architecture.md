# Architecture — bdd-vision

## System Overview

```
CLI (Click)
    └── Orchestrator (state machine)
            ├── SpecEngine (interview → crawl → clarify → spec doc)
            │       └── CrawlEngine (autonomous site exploration)
            ├── AgentRunner (BDD step executor)
            │       ├── ModelRouter (VLM provider + fallback chain)
            │       │       ├── GeminiProvider (stub)
            │       │       ├── DeepSeekProvider (active)
            │       │       └── ClaudeComputerUseProvider (active)
            │       ├── BrowserController (pyautogui mouse/keyboard)
            │       ├── ScreenCapture (mss screenshots)
            │       └── CDPClient (page lifecycle only)
            └── Reporter (PDF + markdown)
```

## Data Flow

1. User runs `bdd-vision run --project foo`
2. Orchestrator loads project config + spec from `data/foo/`
3. AgentRunner parses spec scenarios
4. For each step:
   - ScreenCapture takes before screenshot
   - ModelRouter sends screenshot + instruction to VLM
   - VLM returns action (click/type/scroll/observe/done) + coordinates
   - BrowserController executes action via pyautogui
   - CDPClient waits for network idle
   - ScreenCapture takes after screenshot
   - VLM verifies expected outcome → StepResult
5. SessionResult saved to `data/foo/sessions/`
6. Reporter generates PDF + markdown

## Key Design Decisions

See [decisions.md](decisions.md)

## Anti-Fragility Pattern

Every component follows this pattern:
- Try the operation
- On failure: log full context (ERROR level), record failure, continue
- Never propagate silently
- Cost guard checked before every VLM call
- CDP unavailability falls back to fixed sleep
- Screenshot capture failure falls back to last known screenshot
