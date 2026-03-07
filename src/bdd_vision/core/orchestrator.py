"""
Orchestrator — top-level session state machine.
Wires all components together and manages the session lifecycle.

States: INIT → CRAWLING → SPEC_GENERATION → RUNNING → REPORTING → DONE
"""

from loguru import logger

from ..config.settings import Settings
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

    async def run_test_session(self, scenario_filter: str | None = None):
        # Phase 4
        raise NotImplementedError

    async def run_report(self, session_id: str, fmt: str):
        # Phase 5
        raise NotImplementedError
