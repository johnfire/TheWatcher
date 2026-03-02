# Architecture Decision Records

## ADR-001: No DOM scraping — vision only
**Date:** 2026-03-02
**Status:** Accepted
**Reason:** Black-box testing. Works on any site without instrumentation. CDP used only for page lifecycle (navigate, wait for idle), never for finding or interacting with elements.
**Consequences:** Coordinate resolution relies on VLM; Set-of-Mark prompting needed for reliable clicks.

## ADR-002: Flat file storage for CLI phase
**Date:** 2026-03-02
**Status:** Accepted
**Reason:** No database dependency for CLI tool. JSON + markdown maps cleanly to a DB schema when SaaS migration happens.
**Consequences:** No queries across sessions. Acceptable for CLI phase.

## ADR-003: src/ layout with bdd_vision package
**Date:** 2026-03-02
**Status:** Accepted
**Reason:** Standard Python packaging convention. Clean import paths. Avoids src/ being importable directly.
**Consequences:** Entry point is `bdd_vision.cli.main:cli` not `cli.main:cli`.

## ADR-004: DeepSeek as primary dev/staging tier
**Date:** 2026-03-02
**Status:** Accepted
**Reason:** Gemini API key not available. DeepSeek VL2 is the cheapest available vision model with a hosted API.
**Consequences:** Gemini provider is a stub. Will be wired up later if needed.

## ADR-005: Health check = API key presence only
**Date:** 2026-03-02
**Status:** Accepted
**Reason:** Making real API calls on every health check is expensive. Actual failures during analyze() trigger fallback anyway.
**Consequences:** Invalid keys aren't caught until first use. Acceptable trade-off.

## ADR-006: Logs to ~/logs/ not project-relative
**Date:** 2026-03-02
**Status:** Accepted
**Reason:** Per global engineering standards. Keeps project directory clean. Consistent across all projects.
**Consequences:** Session logs at ~/logs/bdd-vision.log + ~/logs/bdd-vision-{session}.log
