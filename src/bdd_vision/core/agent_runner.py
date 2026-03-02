"""
Agent Runner — BDD step executor.
Executes each scenario from the spec document using Set-of-Mark coordinate resolution.

Phase 4 stub — to be implemented in Phase 4.
"""

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Literal

from ..config.settings import Settings


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


class AgentRunner:
    def __init__(self, settings: Settings):
        self.settings = settings

    async def run(
        self,
        project: str,
        spec_path: Path,
        scenario_filter: str | None = None,
    ) -> SessionResult:
        # Phase 4
        raise NotImplementedError
