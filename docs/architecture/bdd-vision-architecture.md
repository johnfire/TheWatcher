# BDD Vision Agent — Architecture & Build Specification
**For Claude Code — Complete Implementation Guide**  
Version 1.0 | Python 3.12 | CLI-First | Commercial SaaS Foundation

---

## Project Overview

**bdd-vision** is an AI-powered BDD (Behavior Driven Development) testing agent that uses vision-language models to test websites exactly as a human would — by looking at the screen, understanding the UI, and interacting with it using mouse and keyboard. It does **not** use DOM scraping, Selenium, Playwright, or Cypress. It is a true black-box perceptual testing system.

### What Makes This Different
- The AI **sees** the screen as pixels, like a human QA tester
- Works on **any** rendered surface — no instrumentation of the site required
- Generates test specs **collaboratively** — AI crawls the site, human refines the spec
- Anti-fragile by design — partial failures do not kill the test suite
- Model-agnostic — swappable vision model backends

---

## Core Design Principles

1. **Anti-fragility first**: Every component must fail gracefully. A failed test step logs the failure and continues. A failed provider falls back to the next. No single failure cascades into a system crash.
2. **Clean, simple code**: Prefer clarity over cleverness. One responsibility per module.
3. **Model-agnostic**: The rest of the system never cares which VLM is running.
4. **Black-box by default**: VLM does all element identification. CDP is used only for page lifecycle management (load detection, network idle), never for DOM inspection or element finding.
5. **Versioned everything**: Specs, sitemaps, and test sessions are versioned. Reruns always reference a specific spec version.

---

## Technology Stack

| Layer | Technology |
|---|---|
| Language | Python 3.12 |
| CLI Framework | Click |
| Browser Control | pyautogui + Chrome DevTools Protocol (CDP via `pycdp` or `playwright` CDP mode) |
| Screenshot Capture | `mss` (fast, cross-platform) |
| Vision Models | Gemini Flash 2.0, DeepSeek VL2, Claude Computer Use API |
| HTTP Client | `httpx` (async) |
| Config Management | `pydantic-settings` |
| PDF Reports | `reportlab` |
| Data Storage | JSON files (flat file, no database for CLI phase) |
| Dependency Management | `uv` |
| Python Version | 3.12 |

---

## Project Structure

```
bdd-vision/
├── pyproject.toml
├── README.md
├── .env.example
│
├── cli/
│   └── main.py                  # Click CLI entry point
│
├── core/
│   ├── __init__.py
│   ├── orchestrator.py          # Session state machine, top-level coordinator
│   ├── spec_engine.py           # Two-phase spec generation loop
│   ├── crawl_engine.py          # Autonomous site crawler
│   ├── agent_runner.py          # BDD step executor
│   └── reporter.py              # PDF + markdown report generator
│
├── models/
│   ├── __init__.py
│   ├── router.py                # Model selection + fallback chain
│   ├── base.py                  # Abstract provider interface
│   ├── gemini.py                # Gemini Flash 2.0 provider
│   ├── deepseek.py              # DeepSeek VL2 provider
│   └── claude_cu.py             # Claude Computer Use provider
│
├── browser/
│   ├── __init__.py
│   ├── controller.py            # Mouse + keyboard actuation (pyautogui)
│   ├── capture.py               # Screenshot capture (mss)
│   └── cdp.py                   # Chrome DevTools Protocol wrapper
│
├── config/
│   ├── __init__.py
│   └── settings.py              # Pydantic settings, env vars, tier config
│
├── data/
│   ├── specs/                   # Spec documents (markdown, versioned)
│   ├── sitemaps/                # Crawl outputs (JSON)
│   ├── sessions/                # Test run results (JSON)
│   ├── screenshots/             # Screenshot archive per session
│   └── reports/                 # Final PDF + markdown reports
│
└── tests/                       # Tests for the tester
    ├── test_router.py
    ├── test_spec_engine.py
    ├── test_crawl_engine.py
    └── test_agent_runner.py
```

---

## CLI Interface

The CLI is the primary interface. All commands follow this pattern:

```bash
# Initialize a new project for a target site
bdd-vision init --url https://example.com --name "My Project"

# Run the two-phase spec generation (crawl + dialogue + spec output)
bdd-vision spec generate --project my-project

# Review and edit the generated spec (opens in default editor)
bdd-vision spec edit --project my-project

# Run the full test suite against current spec
bdd-vision run --project my-project

# Run a specific scenario only
bdd-vision run --project my-project --scenario "User Login Flow"

# Generate a report from the last session
bdd-vision report --project my-project --format pdf
bdd-vision report --project my-project --format markdown

# List all projects
bdd-vision list

# Show cost estimate for last session
bdd-vision costs --project my-project
```

---

## Component Specifications

---

### 1. Configuration (`config/settings.py`)

Use `pydantic-settings` to manage all configuration from environment variables and a `.env` file.

```python
# Key settings to implement:

class ModelTier(str, Enum):
    DEV = "dev"       # Cheapest — Gemini Flash free tier
    STAGING = "staging"  # Medium — DeepSeek VL2
    PROD = "prod"     # Full quality — Claude Computer Use

class Settings(BaseSettings):
    # Active tier
    model_tier: ModelTier = ModelTier.DEV
    
    # API Keys
    gemini_api_key: str
    deepseek_api_key: str
    anthropic_api_key: str
    
    # Cost controls
    max_cost_per_session_usd: float = 5.00
    max_screenshots_per_run: int = 200
    
    # Browser
    browser_headless: bool = False
    browser_width: int = 1280
    browser_height: int = 900
    chrome_cdp_port: int = 9222
    
    # Paths
    data_dir: Path = Path("./data")
    
    # Retry
    max_step_retries: int = 3
    screenshot_interval_ms: int = 500
```

The `.env.example` file must document every variable with descriptions and safe defaults.

---

### 2. Model Router (`models/router.py`)

The router is the most critical component. It abstracts all model differences behind a single interface and implements the fallback chain.

#### Abstract Base Interface (`models/base.py`)

```python
from abc import ABC, abstractmethod
from dataclasses import dataclass
from PIL import Image

@dataclass
class VLMResponse:
    action: str           # "click", "type", "scroll", "observe", "done"
    target_description: str  # Natural language description of target element
    coordinates: tuple[int, int] | None  # (x, y) if determinable
    text_to_type: str | None
    observation: str      # What the model sees / reasoning
    confidence: float     # 0.0 - 1.0
    tokens_used: int
    cost_usd: float

class BaseVLMProvider(ABC):
    @abstractmethod
    async def analyze_screenshot(
        self,
        screenshot: Image.Image,
        instruction: str,
        context: str = ""
    ) -> VLMResponse:
        """Given a screenshot and an instruction, return an action decision."""
        pass
    
    @abstractmethod
    async def health_check(self) -> bool:
        """Returns True if this provider is available and responding."""
        pass
    
    @property
    @abstractmethod
    def name(self) -> str:
        pass
    
    @property
    @abstractmethod  
    def cost_per_screenshot_usd(self) -> float:
        """Estimated average cost per screenshot analysis."""
        pass
```

#### Router Implementation

```python
class ModelRouter:
    """
    Selects provider based on configured tier.
    Falls back to next tier if primary provider fails.
    Tracks total cost per session.
    All failures are logged, never silently swallowed.
    """
    
    def __init__(self, settings: Settings):
        self.providers: list[BaseVLMProvider] = self._build_chain(settings)
        self.session_cost: float = 0.0
        self.session_tokens: int = 0
        self.max_cost: float = settings.max_cost_per_session_usd
    
    def _build_chain(self, settings: Settings) -> list[BaseVLMProvider]:
        # Always build full chain regardless of tier
        # Tier determines starting point, fallback goes down the chain
        chain = [
            GeminiProvider(settings.gemini_api_key),
            DeepSeekProvider(settings.deepseek_api_key),
            ClaudeComputerUseProvider(settings.anthropic_api_key),
        ]
        # Reorder based on tier
        if settings.model_tier == ModelTier.PROD:
            chain = list(reversed(chain))
        return chain
    
    async def analyze(self, screenshot, instruction, context="") -> VLMResponse:
        if self.session_cost >= self.max_cost:
            raise CostLimitExceeded(f"Session cost limit ${self.max_cost} reached")
        
        last_error = None
        for provider in self.providers:
            try:
                if not await provider.health_check():
                    continue
                response = await provider.analyze_screenshot(screenshot, instruction, context)
                self.session_cost += response.cost_usd
                self.session_tokens += response.tokens_used
                return response
            except Exception as e:
                last_error = e
                logger.warning(f"Provider {provider.name} failed: {e}. Trying next.")
                continue
        
        raise AllProvidersFailed(f"All providers failed. Last error: {last_error}")
```

---

### 3. Browser Controller (`browser/controller.py`, `browser/capture.py`, `browser/cdp.py`)

#### Screenshot Capture (`browser/capture.py`)
- Use `mss` for fast screen capture
- Always capture the full browser window region
- Save screenshot with timestamp + session ID to `data/screenshots/`
- Return both the PIL Image object and the saved file path
- Handle multi-monitor setups gracefully (default to primary monitor)

#### CDP Wrapper (`browser/cdp.py`)
CDP is used **only** for:
1. Detecting when a page has finished loading (Network.loadingFinished)
2. Waiting for network to go idle after an action
3. Navigating to a URL
4. Getting current URL (to track navigation)

CDP is **never** used for:
- Finding elements
- Reading DOM content
- Clicking elements
- Any action that a VLM + mouse could do instead

```python
class CDPClient:
    """
    Minimal CDP wrapper. Only page lifecycle management.
    Connect to Chrome started with --remote-debugging-port=9222
    """
    
    async def connect(self, port: int = 9222): ...
    async def navigate(self, url: str): ...
    async def wait_for_load(self, timeout_ms: int = 10000): ...
    async def wait_for_network_idle(self, idle_time_ms: int = 500, timeout_ms: int = 10000): ...
    async def get_current_url(self) -> str: ...
    async def get_page_title(self) -> str: ...
```

Chrome must be launched with `--remote-debugging-port=9222`. The controller should check if Chrome is running and offer to launch it if not, with the correct flags.

#### Mouse/Keyboard Controller (`browser/controller.py`)
```python
class BrowserController:
    """
    Wraps pyautogui for all mouse and keyboard actions.
    All actions include pre/post screenshot capture.
    All actions are logged with coordinates and timing.
    Failures are caught and logged — never propagate silently.
    """
    
    async def click(self, x: int, y: int, button: str = "left"): ...
    async def double_click(self, x: int, y: int): ...
    async def right_click(self, x: int, y: int): ...
    async def type_text(self, text: str, interval_ms: int = 50): ...
    async def press_key(self, key: str): ...
    async def scroll(self, x: int, y: int, clicks: int): ...
    async def hover(self, x: int, y: int): ...
    async def drag(self, x1: int, y1: int, x2: int, y2: int): ...
    
    # Before every action: capture "before" screenshot
    # After every action: wait for network idle via CDP, then capture "after" screenshot
    # Return both screenshots + action metadata
```

**Important**: Add a human-readable action delay (100-300ms) between actions by default. This makes the agent watchable by humans and avoids race conditions with UI animations.

---

### 4. Crawl Engine (`core/crawl_engine.py`)

The crawl engine autonomously explores a website and builds a structured inventory. This is Phase 2 of the spec generation loop.

#### Crawl Strategy
1. Start at the provided URL
2. Take a screenshot
3. Ask the VLM: "What interactive elements do you see? What pages can you navigate to?"
4. Record all elements found on this page
5. Follow links/navigation to new pages (breadth-first, max depth configurable)
6. Repeat until all reachable pages are mapped or max pages limit reached
7. Return structured sitemap

#### Output Format (`data/sitemaps/{project}-{timestamp}.json`)
```json
{
  "project": "my-project",
  "url": "https://example.com",
  "crawled_at": "2025-01-15T10:30:00Z",
  "pages": [
    {
      "url": "https://example.com/login",
      "title": "Login Page",
      "screenshot_path": "data/screenshots/crawl_001.png",
      "elements": [
        {
          "type": "input",
          "label": "Email address",
          "approximate_location": "center-left",
          "purpose": "email input for login"
        },
        {
          "type": "button",
          "label": "Sign In",
          "approximate_location": "center",
          "purpose": "submit login form"
        }
      ],
      "links_to": ["https://example.com/dashboard", "https://example.com/register"]
    }
  ],
  "notes": [
    "Found admin panel link in footer — may be out of scope",
    "Payment form uses embedded iframe — may require special handling"
  ]
}
```

#### Crawl Limits (configurable in settings)
- `max_pages: int = 30`
- `max_depth: int = 4`
- `crawl_timeout_seconds: int = 300`
- `excluded_patterns: list[str] = []` — URL patterns to skip

---

### 5. Spec Engine (`core/spec_engine.py`)

The spec engine manages the full two-phase specification lifecycle.

#### Phase 1 — Human Brief (CLI Interview)

When `bdd-vision spec generate` is run, the engine interviews the human via CLI prompts:

```
Questions to ask (in order):
1. What does this website do? (brief description)
2. Who are the primary users?
3. What are the 3-5 most important workflows to test?
4. Are there any areas that should be OUT OF SCOPE? (admin panels, payment flows, etc.)
5. Are there any known business rules we should validate? (e.g. "users cannot book more than 2 weeks in advance")
6. Are there test credentials we can use? (username/password for test accounts)
7. Any specific browsers or screen sizes to target?
```

Store the brief as `data/specs/{project}-brief.json`.

#### Phase 2 — AI Crawl

Run the Crawl Engine against the site. Store sitemap.

#### Phase 3 — Clarification Dialogue

After crawling, the engine analyzes the sitemap and brief together, then generates specific clarifying questions based on what it found. Examples:

- "I found a 'Guest Checkout' option — should anonymous checkout be tested?"
- "There are 3 payment methods visible (Stripe, PayPal, invoice) — test all three?"
- "I found an `/admin` path — is this in scope?"
- "The registration form has an optional 'Company Name' field — test with and without it?"

Present these questions to the human via CLI. Record answers.

#### Phase 4 — Spec Document Generation

Generate a structured natural language spec document in markdown. This is the ground truth for all test runs.

**Spec Document Structure:**
```markdown
# [Project Name] — Test Specification
Version: 1.0
Generated: [timestamp]
Site: [url]
Spec ID: [uuid]

## Site Overview
[Brief description from human + AI observations]

## Scope
### In Scope
- [workflow 1]
- [workflow 2]

### Out of Scope  
- [excluded areas]

## Test Scenarios

### Scenario: User Registration
**Priority:** High  
**Preconditions:** User is not logged in, on the homepage

**Steps:**
1. Given the user is on the homepage
2. When they click the "Register" or "Sign Up" button
3. Then they should be taken to a registration form
4. When they fill in all required fields with valid data
5. And they submit the form
6. Then they should see a success confirmation
7. And they should be redirected to the dashboard or confirmation page

**Expected Outcomes:**
- Registration form accepts valid email format
- Password field masks input
- Error messages appear for invalid/missing fields
- Successful registration results in confirmation

**Variations to Test:**
- Empty required fields → should show validation errors
- Invalid email format → should show format error
- Password too short → should show strength error

---
### Scenario: [Next Scenario]
...
```

The spec is saved as `data/specs/{project}-spec-v{N}.md` where N increments on each regeneration.

---

### 6. Agent Runner (`core/agent_runner.py`)

The agent runner executes each scenario from the spec document.

#### Execution Model

For each scenario:
1. Parse the scenario steps from the spec
2. Navigate to the precondition URL
3. For each step:
   a. Capture screenshot
   b. Send screenshot + step instruction to VLM via router
   c. VLM returns action (click/type/observe/scroll/done)
   d. If action requires coordinates: derive pixel coordinates from VLM description
   e. Execute action via browser controller
   f. Wait for network idle via CDP
   g. Capture post-action screenshot
   h. Ask VLM: "Does this match the expected outcome described in the spec?"
   i. Record result (pass/fail/partial + confidence + observations)
   j. If step fails: log, continue to next step (anti-fragile)
4. After all steps: generate scenario result summary

#### Coordinate Resolution

The VLM describes elements in natural language ("the blue Submit button in the center of the form"). To get pixel coordinates:

1. Use **Set-of-Mark prompting**: overlay the screenshot with numbered bounding boxes for detected interactive elements
2. Ask VLM: "Which numbered element matches [description]? Return the number."
3. Map number back to coordinates

Implement a simple element detector using:
- PIL for image processing
- Contour detection to find button-like regions
- Number overlays rendered onto the screenshot before VLM analysis

If coordinate resolution fails after `max_step_retries` attempts, log the failure with full context and move to next step.

#### Step Result Schema
```python
@dataclass
class StepResult:
    step_number: int
    step_text: str
    status: Literal["pass", "fail", "skip", "partial"]
    confidence: float
    action_taken: str
    coordinates_used: tuple[int, int] | None
    before_screenshot: Path
    after_screenshot: Path
    vlm_observation: str          # What the VLM saw
    expected_outcome: str         # From spec
    actual_outcome: str           # VLM's description of what happened
    deviation_description: str | None  # If status != pass
    tokens_used: int
    cost_usd: float
    duration_seconds: float
    error: str | None
```

#### Session Result Schema
```python
@dataclass 
class SessionResult:
    session_id: str
    project: str
    spec_version: str
    started_at: datetime
    completed_at: datetime
    scenarios: list[ScenarioResult]
    total_steps: int
    passed: int
    failed: int
    skipped: int
    total_cost_usd: float
    total_tokens: int
    model_used: str
```

Save session results to `data/sessions/{project}-{session_id}.json`.

---

### 7. Reporter Engine (`core/reporter.py`)

Generates human-readable reports from session results.

#### Markdown Report Structure
```markdown
# BDD Test Report — [Project Name]
**Date:** [timestamp]  
**Spec Version:** [version]  
**Model Used:** [provider name]  
**Session ID:** [id]

## Summary
| Metric | Value |
|---|---|
| Total Scenarios | N |
| Passed | N (X%) |
| Failed | N (X%) |
| Total Steps | N |
| Total Cost | $X.XX |
| Duration | Xm Xs |

## Results by Scenario

### ✅ Scenario: User Registration — PASSED (94% confidence)
**Steps:** 7 | **Passed:** 7 | **Failed:** 0

| Step | Status | Confidence | Notes |
|---|---|---|---|
| Navigate to registration | ✅ Pass | 0.98 | |
| Click Register button | ✅ Pass | 0.95 | |
| ... | | | |

---

### ❌ Scenario: Password Reset — FAILED
**Steps:** 5 | **Passed:** 3 | **Failed:** 2

**Deviations Found:**
- Step 4: Expected "Check your email" confirmation message. Observed: Page refreshed with no message.
- Step 5: Expected redirect to login page. Observed: Remained on password reset page.

**Screenshots:**
- Before: [link]
- After: [link]

---

## Cost Breakdown
[Table by scenario + model tier used]

## Recommendations
[VLM-generated summary of failures and suggested fixes]
```

#### PDF Report
Use `reportlab` to render the markdown report as a well-formatted PDF.
- Include embedded screenshots for failed steps (before + after side by side)
- Use a clean, professional layout
- Include a cover page with project name, date, pass/fail summary
- Table of contents for multi-scenario reports

---

### 8. Orchestrator (`core/orchestrator.py`)

Top-level coordinator. Manages session lifecycle and wires all components together.

```python
class Orchestrator:
    """
    State machine for a test session.
    States: INIT → CRAWLING → SPEC_GENERATION → RUNNING → REPORTING → DONE
    Any state failure logs the error and attempts graceful completion of remaining states.
    """
    
    def __init__(self, project: str, settings: Settings): ...
    
    async def run_spec_generation(self): ...
    async def run_test_session(self, scenario_filter: str | None = None): ...
    async def run_report(self, session_id: str, format: str): ...
```

---

## Anti-Fragility Requirements

These are non-negotiable. Every component must follow these patterns:

### 1. Step-Level Isolation
```python
for step in scenario.steps:
    try:
        result = await execute_step(step)
    except Exception as e:
        # Log full traceback
        # Record step as failed
        # Continue to next step
        results.append(StepResult(status="fail", error=str(e), ...))
        continue
```

### 2. Provider Fallback (already described in router)

### 3. Screenshot Capture Never Blocks
If screenshot capture fails, log it and use the last successful screenshot. Never let a capture failure stop a test run.

### 4. Cost Guard
Check cost limit before every VLM call. If limit is reached, mark remaining steps as "skipped" with reason "cost limit reached" and generate a partial report.

### 5. File Write Safety
All file writes use atomic write pattern (write to temp file, then rename). Never leave corrupt/partial files.

### 6. CDP Timeout Safety
All CDP operations have explicit timeouts. If CDP is unavailable, fall back to a fixed sleep (configurable `fallback_wait_ms = 2000`) and continue.

---

## Environment Setup

### `.env.example`
```bash
# Model tier: dev | staging | prod
MODEL_TIER=dev

# API Keys (only need the ones for your active tier)
GEMINI_API_KEY=
DEEPSEEK_API_KEY=
ANTHROPIC_API_KEY=

# Cost controls
MAX_COST_PER_SESSION_USD=5.00
MAX_SCREENSHOTS_PER_RUN=200

# Browser
BROWSER_HEADLESS=false
BROWSER_WIDTH=1280
BROWSER_HEIGHT=900
CHROME_CDP_PORT=9222

# Retry
MAX_STEP_RETRIES=3
SCREENSHOT_INTERVAL_MS=500

# Paths (defaults are fine)
DATA_DIR=./data
```

### `pyproject.toml` Dependencies
```toml
[project]
name = "bdd-vision"
version = "0.1.0"
requires-python = ">=3.12"

dependencies = [
    "click>=8.1",
    "pydantic>=2.0",
    "pydantic-settings>=2.0",
    "httpx>=0.27",
    "pillow>=10.0",
    "mss>=9.0",
    "pyautogui>=0.9.54",
    "reportlab>=4.0",
    "python-dotenv>=1.0",
    "google-generativeai>=0.8",
    "anthropic>=0.40",
    "websockets>=13.0",
    "rich>=13.0",       # Pretty CLI output
    "loguru>=0.7",      # Structured logging
]

[project.scripts]
bdd-vision = "cli.main:cli"
```

---

## Build Sequence

Build in this exact order. Each phase must be working before starting the next.

### Phase 1 — Foundation (Week 1)
**Goal:** Can take a screenshot and send it to a VLM, get a response back.

1. `config/settings.py` — all settings with defaults
2. `models/base.py` — abstract interface
3. `models/gemini.py` — Gemini Flash provider (cheapest, test with this first)
4. `models/router.py` — router with single provider for now
5. `browser/capture.py` — screenshot capture with mss
6. `browser/cdp.py` — minimal CDP (navigate + wait_for_load only)
7. `browser/controller.py` — click + type_text + scroll
8. `cli/main.py` — `bdd-vision init` command only

**Validation:** Run `bdd-vision init`, navigate Chrome to a test URL manually, run a hardcoded "take screenshot, ask VLM what you see" script. Should return a coherent description.

### Phase 2 — Crawl Engine (Week 2)
**Goal:** Given a URL, produce a sitemap JSON.

1. `core/crawl_engine.py`
2. `cli/main.py` — add `bdd-vision crawl` command
3. Add DeepSeek provider to router

**Validation:** Crawl a simple public site (e.g. example.com or a local test app). Inspect sitemap.json for accuracy.

### Phase 3 — Spec Engine (Week 2-3)
**Goal:** Full spec generation loop — interview → crawl → clarify → spec document.

1. `core/spec_engine.py`
2. `cli/main.py` — add `bdd-vision spec generate` and `bdd-vision spec edit`

**Validation:** Run spec generation on a real site. Review output spec for quality and completeness.

### Phase 4 — Agent Runner (Week 3-4)
**Goal:** Execute a spec and produce session results JSON.

1. `core/agent_runner.py` — step executor with Set-of-Mark coordinate resolution
2. `cli/main.py` — add `bdd-vision run`

**Validation:** Run a 5-step scenario on a known site. Verify step results JSON captures pass/fail correctly with screenshots.

### Phase 5 — Reporter (Week 4)
**Goal:** Produce PDF and markdown reports from session results.

1. `core/reporter.py`
2. `cli/main.py` — add `bdd-vision report`

**Validation:** Generate report from a completed session. Review PDF and markdown outputs for correctness and readability.

### Phase 6 — Hardening (Week 5)
**Goal:** Every failure mode is handled gracefully.

1. Audit every component against anti-fragility requirements
2. Add retry logic to all VLM calls
3. Add cost tracking and cost guard
4. Add atomic file writes everywhere
5. Add comprehensive logging with loguru
6. Write unit tests for router, spec engine, crawl engine, agent runner

### Phase 7 — Full Provider Integration (Week 5-6)
**Goal:** All three providers working with clean fallback.

1. `models/claude_cu.py` — Claude Computer Use provider
2. Full router fallback chain testing
3. Cost comparison across providers for same test scenario
4. `cli/main.py` — add `bdd-vision costs` command

---

## Logging Standards

Use `loguru` throughout. Log levels:
- `DEBUG` — every VLM call input/output, every screenshot, every coordinate
- `INFO` — step start/end, scenario start/end, provider selection
- `WARNING` — provider fallback, step retry, CDP timeout fallback
- `ERROR` — step failure (with full context), provider failure

Every log entry for a VLM call must include:
- provider name
- tokens used
- cost in USD
- action returned
- confidence score

Session logs are saved to `data/sessions/{session_id}.log`.

---

## Testing Strategy

The test suite tests the tester. Focus on:

- **Router tests**: Provider fallback, cost limit enforcement
- **Spec engine tests**: Brief parsing, spec document structure validation
- **Crawl engine tests**: Sitemap schema validation, depth limiting
- **Agent runner tests**: Step isolation (one failure doesn't stop others), result schema correctness
- **Reporter tests**: Markdown and PDF generation from fixture data

Use `pytest` with `pytest-asyncio`. Mock all VLM providers in tests — never make real API calls in the test suite.

---

## Security Considerations

- API keys are **only** read from environment variables or `.env` file. Never hardcoded, never logged.
- Test credentials (usernames/passwords for target sites) are stored in `data/specs/{project}-credentials.json` and must be listed in `.gitignore`
- Screenshot archive may contain sensitive data — document this clearly for users
- The `.gitignore` must exclude: `.env`, `data/screenshots/`, `data/sessions/`, `data/specs/*-credentials.json`

---

## Future Considerations (Post-CLI, Pre-SaaS)

These are not in scope for the CLI phase but the architecture must not prevent them:

1. **Video spec input** — user records a walkthrough video, AI extracts test scenarios from it
2. **Web UI** — wrap the CLI orchestrator in a FastAPI backend + React frontend
3. **Multi-browser support** — Firefox, Safari via similar CDP/automation protocols
4. **Parallel test execution** — run multiple scenarios simultaneously
5. **CI/CD integration** — GitHub Actions / GitLab CI YAML examples
6. **Baseline comparison** — store "last known good" screenshots and diff against them
7. **Natural language spec editing** — chat interface to refine spec with the AI

The flat-file data layer (JSON + markdown) is intentionally chosen for the CLI phase. It maps cleanly to a database schema when SaaS migration happens.

---

## Definition of Done (CLI Phase)

The CLI phase is complete when:

- [ ] `bdd-vision init` creates a project structure
- [ ] `bdd-vision spec generate` runs the full two-phase loop and produces a readable spec document
- [ ] `bdd-vision run` executes all scenarios in the spec and produces a session results JSON
- [ ] `bdd-vision report --format pdf` produces a readable PDF with pass/fail summary and screenshots
- [ ] `bdd-vision report --format markdown` produces a readable markdown report
- [ ] A single step failure does not stop the test suite
- [ ] A provider failure falls back to the next provider automatically
- [ ] Cost limit is enforced and remaining steps are gracefully skipped when reached
- [ ] All API keys are loaded from environment — zero hardcoded secrets
- [ ] The system runs on Linux (primary), macOS (secondary)

---

*End of specification. Build Phase 1 first. Validate before proceeding to Phase 2.*
