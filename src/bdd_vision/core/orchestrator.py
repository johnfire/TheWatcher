"""
Orchestrator — top-level session state machine.
Wires all components together and manages the session lifecycle.

States: INIT → CRAWLING → SPEC_GENERATION → RUNNING → REPORTING → DONE

Phase 1 stub — to be implemented in Phase 3+.
"""

from loguru import logger

from ..config.settings import Settings


class Orchestrator:
    def __init__(self, project: str, settings: Settings):
        self.project = project
        self.settings = settings

    async def run_spec_generation(self):
        # Phase 3
        raise NotImplementedError

    async def run_test_session(self, scenario_filter: str | None = None):
        # Phase 4
        raise NotImplementedError

    async def run_report(self, session_id: str, fmt: str):
        # Phase 5
        raise NotImplementedError
