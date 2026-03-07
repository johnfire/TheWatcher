"""
Agent Runner — BDD step executor.
Executes each scenario from the spec document using VLM coordinate resolution.

For each step the runner:
  1. Captures a before-screenshot
  2. Asks the VLM what action to take (click/type/scroll/observe/done) + coordinates
  3. Executes the action via BrowserController
  4. Captures an after-screenshot
  5. Asks the VLM to verify the outcome against the expected step text
  6. Records StepResult (pass/fail/partial)

Phase 4 implementation.
"""

import json
import uuid
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from time import monotonic
from typing import TYPE_CHECKING, Literal

if TYPE_CHECKING:
    from ..browser.controller import BrowserController

from loguru import logger

from ..browser.capture import ScreenCapture
from ..browser.cdp import CDPClient
from ..config.settings import Settings
from ..models.router import AllProvidersFailed, CostLimitExceeded, ModelRouter


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
    vlm_observation: str
    expected_outcome: str
    actual_outcome: str
    deviation_description: str | None
    tokens_used: int
    cost_usd: float
    duration_seconds: float
    error: str | None


@dataclass
class ScenarioResult:
    scenario_name: str
    status: Literal["pass", "fail", "partial", "skip"]
    steps: list[StepResult]
    total_cost_usd: float
    duration_seconds: float


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


_STEP_INSTRUCTION = """\
BDD step to execute: {step_keyword} {step_text}

You are executing a BDD test step on the current page.
Decide what single action to take to progress this step.

If the step is a "Given" or navigation step, use "observe" if already on the right page, \
or "click" a navigation link.
If the step is a "When" action step, perform the appropriate interaction.
If the step is a "Then" assertion step, use "observe" to verify the expected state.
If the step is already complete or not applicable, use "done"."""

_VERIFY_INSTRUCTION = """\
BDD step just executed: {step_keyword} {step_text}

Examine the current state of the page and determine if this step PASSED or FAILED.
- PASSED: The page shows what the step expected
- FAILED: The page does not show the expected outcome
- PARTIAL: The step partially succeeded

Respond with "observe" action and set confidence to reflect pass likelihood (>=0.7 = pass)."""


class AgentRunner:
    def __init__(self, settings: Settings):
        self.settings = settings

    async def run(
        self,
        project: str,
        spec_path: Path,
        scenario_filter: str | None = None,
    ) -> SessionResult:
        session_id = str(uuid.uuid4())[:8]
        started_at = datetime.now()

        project_dir = self.settings.data_dir / project
        session_dir = project_dir / "sessions" / session_id
        screenshots_dir = session_dir / "screenshots"
        screenshots_dir.mkdir(parents=True, exist_ok=True)

        spec = json.loads(spec_path.read_text())
        spec_version = str(spec.get("version", "?"))
        base_url = spec.get("base_url", "")

        capture = ScreenCapture(screenshots_dir)
        cdp = CDPClient(port=self.settings.chrome_cdp_port)
        router = ModelRouter(self.settings)

        from ..browser.controller import BrowserController  # lazy: needs display
        await cdp.connect()
        controller = BrowserController(
            capture=capture,
            cdp=cdp,
            action_delay_ms=200,
            fallback_wait_ms=self.settings.fallback_wait_ms,
        )

        scenario_results: list[ScenarioResult] = []
        model_name = router.providers[0].name if router.providers else "unknown"

        try:
            for feature in spec.get("features", []):
                for scenario in feature.get("scenarios", []):
                    name = scenario["name"]
                    if scenario_filter and scenario_filter.lower() not in name.lower():
                        continue

                    logger.info(f"[{session_id}] Running scenario: {name}")
                    result = await self._run_scenario(
                        scenario, base_url, router, controller, cdp, capture
                    )
                    scenario_results.append(result)

                    if router.session_cost >= self.settings.max_cost_per_session_usd:
                        logger.warning("Cost limit reached — stopping session")
                        break

        finally:
            await cdp.disconnect()

        passed = sum(1 for r in scenario_results if r.status == "pass")
        failed = sum(1 for r in scenario_results if r.status == "fail")
        skipped = sum(1 for r in scenario_results if r.status == "skip")
        total_steps = sum(len(r.steps) for r in scenario_results)

        session = SessionResult(
            session_id=session_id,
            project=project,
            spec_version=spec_version,
            started_at=started_at,
            completed_at=datetime.now(),
            scenarios=scenario_results,
            total_steps=total_steps,
            passed=passed,
            failed=failed,
            skipped=skipped,
            total_cost_usd=router.session_cost,
            total_tokens=router.session_tokens,
            model_used=model_name,
        )

        self._save_session(session_dir, session)
        return session

    # ── Internals ────────────────────────────────────────────────────────────

    async def _run_scenario(
        self,
        scenario: dict,
        base_url: str,
        router: ModelRouter,
        controller: "BrowserController",
        cdp: CDPClient,
        capture: ScreenCapture,
    ) -> ScenarioResult:
        scenario_start = monotonic()
        step_results: list[StepResult] = []
        prior_failed = False

        try:
            await cdp.navigate(base_url)
        except Exception as e:
            logger.warning(f"Pre-scenario navigation failed: {e}")

        for i, step in enumerate(scenario.get("steps", []), 1):
            keyword = step.get("keyword", "")
            text = step.get("text", "")

            if prior_failed and keyword in ("When", "Then"):
                step_results.append(_skip_step(i, keyword, text))
                continue

            step_result = await self._run_step(
                step_number=i,
                keyword=keyword,
                text=text,
                router=router,
                controller=controller,
                capture=capture,
            )
            step_results.append(step_result)

            if step_result.status == "fail":
                prior_failed = True

        duration = monotonic() - scenario_start
        status = _scenario_status(step_results)
        cost = sum(s.cost_usd for s in step_results)

        return ScenarioResult(
            scenario_name=scenario["name"],
            status=status,
            steps=step_results,
            total_cost_usd=cost,
            duration_seconds=round(duration, 2),
        )

    async def _run_step(
        self,
        step_number: int,
        keyword: str,
        text: str,
        router: ModelRouter,
        controller: "BrowserController",
        capture: ScreenCapture,
    ) -> StepResult:
        step_start = monotonic()
        tokens_used = 0
        cost_usd = 0.0
        error: str | None = None

        before_img, before_path = capture.capture(f"step{step_number:02d}_before")

        try:
            instruction = _STEP_INSTRUCTION.format(step_keyword=keyword, step_text=text)
            vlm_resp = await router.analyze(before_img, instruction)
            tokens_used += vlm_resp.tokens_used
            cost_usd += vlm_resp.cost_usd

            action = vlm_resp.action
            coords = vlm_resp.coordinates
            observation = vlm_resp.observation

            if action == "click" and coords:
                await controller.click(*coords)
            elif action == "type" and vlm_resp.text_to_type:
                if coords:
                    await controller.click(*coords)
                await controller.type_text(vlm_resp.text_to_type)
            elif action == "scroll" and coords:
                await controller.scroll(coords[0], coords[1], clicks=3)
            elif action in ("observe", "done"):
                pass
            else:
                logger.debug(f"Step {step_number}: unhandled action '{action}' — treating as observe")

            after_img, after_path = capture.capture(f"step{step_number:02d}_after")

            verify_instruction = _VERIFY_INSTRUCTION.format(step_keyword=keyword, step_text=text)
            verify_resp = await router.analyze(after_img, verify_instruction)
            tokens_used += verify_resp.tokens_used
            cost_usd += verify_resp.cost_usd

            confidence = verify_resp.confidence
            actual_outcome = verify_resp.observation

            if confidence >= 0.7:
                status: Literal["pass", "fail", "skip", "partial"] = "pass"
                deviation = None
            elif confidence >= 0.4:
                status = "partial"
                deviation = f"Low confidence ({confidence:.2f}): {actual_outcome[:200]}"
            else:
                status = "fail"
                deviation = f"Expected: {text}\nActual: {actual_outcome[:200]}"

        except (CostLimitExceeded, AllProvidersFailed) as e:
            error = str(e)
            logger.warning(f"Step {step_number} VLM unavailable: {e}")
            _, after_path = capture.capture(f"step{step_number:02d}_after")
            action, coords, observation, actual_outcome = "skip", None, "", ""
            confidence, status, deviation = 0.0, "fail", error

        except Exception as e:
            error = str(e)
            logger.error(f"Step {step_number} error: {e}")
            _, after_path = capture.capture(f"step{step_number:02d}_after")
            action, coords, observation, actual_outcome = "error", None, "", str(e)
            confidence, status, deviation = 0.0, "fail", error

        duration = monotonic() - step_start
        return StepResult(
            step_number=step_number,
            step_text=f"{keyword} {text}",
            status=status,
            confidence=confidence,
            action_taken=action,
            coordinates_used=coords,
            before_screenshot=before_path,
            after_screenshot=after_path,
            vlm_observation=observation,
            expected_outcome=text,
            actual_outcome=actual_outcome,
            deviation_description=deviation,
            tokens_used=tokens_used,
            cost_usd=cost_usd,
            duration_seconds=round(duration, 2),
            error=error,
        )

    def _save_session(self, session_dir: Path, session: SessionResult):
        session_dir.mkdir(parents=True, exist_ok=True)
        data = {
            "session_id": session.session_id,
            "project": session.project,
            "spec_version": session.spec_version,
            "started_at": session.started_at.isoformat(),
            "completed_at": session.completed_at.isoformat(),
            "total_steps": session.total_steps,
            "passed": session.passed,
            "failed": session.failed,
            "skipped": session.skipped,
            "total_cost_usd": round(session.total_cost_usd, 6),
            "total_tokens": session.total_tokens,
            "model_used": session.model_used,
            "scenarios": [
                {
                    "name": r.scenario_name,
                    "status": r.status,
                    "duration_seconds": r.duration_seconds,
                    "total_cost_usd": round(r.total_cost_usd, 6),
                    "steps": [
                        {
                            "step_number": s.step_number,
                            "step_text": s.step_text,
                            "status": s.status,
                            "confidence": round(s.confidence, 3),
                            "action_taken": s.action_taken,
                            "coordinates_used": list(s.coordinates_used) if s.coordinates_used else None,
                            "before_screenshot": str(s.before_screenshot),
                            "after_screenshot": str(s.after_screenshot),
                            "vlm_observation": s.vlm_observation,
                            "expected_outcome": s.expected_outcome,
                            "actual_outcome": s.actual_outcome,
                            "deviation_description": s.deviation_description,
                            "tokens_used": s.tokens_used,
                            "cost_usd": round(s.cost_usd, 6),
                            "duration_seconds": s.duration_seconds,
                            "error": s.error,
                        }
                        for s in r.steps
                    ],
                }
                for r in session.scenarios
            ],
        }
        path = session_dir / "session.json"
        tmp = path.with_suffix(".tmp")
        tmp.write_text(json.dumps(data, indent=2))
        tmp.rename(path)
        logger.info(f"Session saved: {path}")


# ── Helpers ──────────────────────────────────────────────────────────────────

def _skip_step(step_number: int, keyword: str, text: str) -> StepResult:
    return StepResult(
        step_number=step_number,
        step_text=f"{keyword} {text}",
        status="skip",
        confidence=0.0,
        action_taken="skip",
        coordinates_used=None,
        before_screenshot=Path("/dev/null"),
        after_screenshot=Path("/dev/null"),
        vlm_observation="",
        expected_outcome=text,
        actual_outcome="",
        deviation_description="Skipped — prior step failed",
        tokens_used=0,
        cost_usd=0.0,
        duration_seconds=0.0,
        error=None,
    )


def _scenario_status(steps: list[StepResult]) -> Literal["pass", "fail", "partial", "skip"]:
    statuses = {s.status for s in steps}
    if not steps:
        return "skip"
    if statuses == {"skip"}:
        return "skip"
    if "fail" in statuses:
        return "fail"
    if "partial" in statuses:
        return "partial"
    return "pass"
