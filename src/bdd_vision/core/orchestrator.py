"""
Orchestrator — top-level session state machine.
Wires all components together and manages the session lifecycle.

States: INIT → CRAWLING → SPEC_GENERATION → RUNNING → REPORTING → DONE
"""

from pathlib import Path

from loguru import logger

from ..config.settings import Settings
from .agent_runner import AgentRunner, SessionResult
from .reporter import Reporter
from .spec_engine import SpecEngine


class Orchestrator:
    def __init__(self, project: str, settings: Settings):
        self.project = project
        self.settings = settings

    async def run_spec_generation(self) -> dict:
        logger.info(f"[{self.project}] state=SPEC_GENERATION")
        engine = SpecEngine(self.settings)
        spec = await engine.generate(self.project)
        logger.info(f"[{self.project}] state=DONE spec_version={spec['version']}")
        return spec

    async def run_test_session(
        self,
        spec_path: Path,
        scenario_filter: str | None = None,
    ) -> SessionResult:
        logger.info(f"[{self.project}] state=RUNNING spec={spec_path.name}")
        runner = AgentRunner(self.settings)
        result = await runner.run(self.project, spec_path, scenario_filter)
        logger.info(
            f"[{self.project}] state=DONE "
            f"pass={result.passed} fail={result.failed} skip={result.skipped}"
        )
        return result

    async def run_report(self, session_id: str, fmt: str) -> Path:
        logger.info(f"[{self.project}] state=REPORTING session={session_id} fmt={fmt}")
        session_path = self.settings.data_dir / self.project / "sessions" / session_id / "session.json"
        if not session_path.exists():
            raise FileNotFoundError(f"Session not found: {session_path}")

        import json
        from datetime import datetime
        data = json.loads(session_path.read_text())

        # Reconstruct SessionResult from JSON
        from .agent_runner import ScenarioResult, StepResult
        scenarios = []
        for s in data["scenarios"]:
            steps = [StepResult(**{
                "step_number": step["step_number"],
                "step_text": step["step_text"],
                "status": step["status"],
                "confidence": step["confidence"],
                "action_taken": step["action_taken"],
                "coordinates_used": tuple(step["coordinates_used"]) if step["coordinates_used"] else None,
                "before_screenshot": Path(step["before_screenshot"]),
                "after_screenshot": Path(step["after_screenshot"]),
                "vlm_observation": step["vlm_observation"],
                "expected_outcome": step["expected_outcome"],
                "actual_outcome": step["actual_outcome"],
                "deviation_description": step["deviation_description"],
                "tokens_used": step["tokens_used"],
                "cost_usd": step["cost_usd"],
                "duration_seconds": step["duration_seconds"],
                "error": step["error"],
            }) for step in s["steps"]]
            scenarios.append(ScenarioResult(
                scenario_name=s["name"],
                status=s["status"],
                steps=steps,
                total_cost_usd=s["total_cost_usd"],
                duration_seconds=s["duration_seconds"],
            ))

        result = SessionResult(
            session_id=data["session_id"],
            project=data["project"],
            spec_version=data["spec_version"],
            started_at=datetime.fromisoformat(data["started_at"]),
            completed_at=datetime.fromisoformat(data["completed_at"]),
            scenarios=scenarios,
            total_steps=data["total_steps"],
            passed=data["passed"],
            failed=data["failed"],
            skipped=data["skipped"],
            total_cost_usd=data["total_cost_usd"],
            total_tokens=data["total_tokens"],
            model_used=data["model_used"],
        )

        output_dir = self.settings.data_dir / self.project / "reports"
        reporter = Reporter()
        if fmt == "pdf":
            path = reporter.generate_pdf(result, output_dir)
        else:
            path = reporter.generate_markdown(result, output_dir)

        logger.info(f"[{self.project}] state=DONE report={path}")
        return path
