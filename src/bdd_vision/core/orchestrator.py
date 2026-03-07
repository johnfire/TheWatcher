"""
Orchestrator — top-level session state machine.
Wires all components together and manages the session lifecycle.

States: INIT → CRAWLING → SPEC_GENERATION → RUNNING → REPORTING → DONE
"""

from pathlib import Path

from loguru import logger

from ..config.settings import Settings
from .agent_runner import AgentRunner, SessionResult
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

    async def run_report(self, session_id: str, fmt: str):
        # Phase 5
        raise NotImplementedError
