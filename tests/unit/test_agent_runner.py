import json
import pytest
from pathlib import Path
from PIL import Image

import sys
from unittest.mock import MagicMock, AsyncMock, patch

from bdd_vision.core.agent_runner import (
    AgentRunner,
    ScenarioResult,
    SessionResult,
    StepResult,
    _scenario_status,
    _skip_step,
)
from bdd_vision.models.base import VLMResponse


def _ctrl_module(ctrl_instance):
    """Return a fake bdd_vision.browser.controller module with BrowserController mocked."""
    mod = MagicMock()
    mod.BrowserController = MagicMock(return_value=ctrl_instance)
    return mod



def _blank_image() -> Image.Image:
    return Image.new("RGB", (100, 100))


def _vlm_resp(**kwargs) -> VLMResponse:
    defaults = dict(
        action="observe",
        target_description="",
        coordinates=None,
        text_to_type=None,
        observation="page looks good",
        confidence=0.85,
        tokens_used=100,
        cost_usd=0.001,
    )
    defaults.update(kwargs)
    return VLMResponse(**defaults)


def _make_spec(scenarios: list[dict], base_url: str = "https://example.com") -> dict:
    return {
        "version": 1,
        "base_url": base_url,
        "features": [
            {
                "name": "Test Feature",
                "scenarios": scenarios,
            }
        ],
    }


def _simple_scenario(name: str = "Login", steps: int = 2) -> dict:
    return {
        "name": name,
        "steps": [
            {"keyword": "Given", "text": "I am on the login page"},
            {"keyword": "When", "text": "I click Login"},
            {"keyword": "Then", "text": "I see the dashboard"},
        ][:steps],
    }


# ── Helper functions ─────────────────────────────────────────────────────────

def test_skip_step_returns_correct_status():
    result = _skip_step(3, "Then", "I see the dashboard")
    assert result.status == "skip"
    assert result.step_number == 3
    assert result.action_taken == "skip"
    assert result.cost_usd == 0.0


def test_scenario_status_all_pass():
    steps = [_skip_step(1, "G", "x") for _ in range(2)]
    for s in steps:
        object.__setattr__(s, "status", "pass")
    assert _scenario_status(steps) == "pass"


def test_scenario_status_any_fail():
    steps = [_skip_step(i, "G", "x") for i in range(3)]
    object.__setattr__(steps[0], "status", "pass")
    object.__setattr__(steps[1], "status", "fail")
    object.__setattr__(steps[2], "status", "pass")
    assert _scenario_status(steps) == "fail"


def test_scenario_status_partial_no_fail():
    steps = [_skip_step(i, "G", "x") for i in range(2)]
    object.__setattr__(steps[0], "status", "pass")
    object.__setattr__(steps[1], "status", "partial")
    assert _scenario_status(steps) == "partial"


def test_scenario_status_all_skip():
    steps = [_skip_step(i, "G", "x") for i in range(2)]
    assert _scenario_status(steps) == "skip"


def test_scenario_status_empty():
    assert _scenario_status([]) == "skip"


# ── AgentRunner ──────────────────────────────────────────────────────────────

@pytest.fixture
def run_env(tmp_path):
    """Provides spec file + project dir + settings."""
    from bdd_vision.config.settings import ModelTier, Settings

    data_dir = tmp_path / "data"
    project_dir = data_dir / "myproject"
    (project_dir / "sessions").mkdir(parents=True)
    (project_dir / "specs").mkdir(parents=True)

    spec = _make_spec([_simple_scenario()])
    spec_path = project_dir / "specs" / "spec_v001.json"
    spec_path.write_text(json.dumps(spec))

    settings = Settings(
        model_tier=ModelTier.STAGING,
        deepseek_api_key="key",
        anthropic_api_key="key",
        data_dir=data_dir,
        log_dir=tmp_path / "logs",
        max_cost_per_session_usd=5.0,
        fallback_wait_ms=0,
    )
    return spec_path, settings


@pytest.fixture
def mock_cdp():
    cdp = AsyncMock()
    cdp.connect = AsyncMock()
    cdp.disconnect = AsyncMock()
    cdp.navigate = AsyncMock()
    cdp.wait_for_network_idle = AsyncMock()
    return cdp


@pytest.fixture
def mock_capture(tmp_path):
    img = _blank_image()
    path = tmp_path / "shot.png"
    img.save(path)
    capture = MagicMock()
    capture.capture = MagicMock(return_value=(img, path))
    return capture


@pytest.fixture
def mock_controller():
    ctrl = AsyncMock()
    ctrl.click = AsyncMock(return_value={})
    ctrl.type_text = AsyncMock(return_value={})
    ctrl.scroll = AsyncMock(return_value={})
    return ctrl


@pytest.mark.asyncio
async def test_run_passes_all_steps(run_env, mock_cdp, mock_capture, mock_controller):
    spec_path, settings = run_env

    with (
        patch("bdd_vision.core.agent_runner.CDPClient", return_value=mock_cdp),
        patch("bdd_vision.core.agent_runner.ScreenCapture", return_value=mock_capture),
        patch("bdd_vision.core.agent_runner.ModelRouter") as MockRouter,
        patch.dict(sys.modules, {"bdd_vision.browser.controller": _ctrl_module(mock_controller)}),
    ):
        router = MockRouter.return_value
        mock_provider = MagicMock()
        mock_provider.name = "deepseek/vl2"
        router.providers = [mock_provider]
        router.session_cost = 0.01
        router.session_tokens = 500
        router.max_cost = 5.0
        # Each step calls analyze twice (action + verify), all high-confidence
        router.analyze = AsyncMock(return_value=_vlm_resp(confidence=0.9))

        runner = AgentRunner(settings)
        result = await runner.run("myproject", spec_path)

    assert isinstance(result, SessionResult)
    assert len(result.scenarios) == 1
    assert result.scenarios[0].status == "pass"


@pytest.mark.asyncio
async def test_run_fails_low_confidence(run_env, mock_cdp, mock_capture, mock_controller):
    spec_path, settings = run_env

    with (
        patch("bdd_vision.core.agent_runner.CDPClient", return_value=mock_cdp),
        patch("bdd_vision.core.agent_runner.ScreenCapture", return_value=mock_capture),
        patch("bdd_vision.core.agent_runner.ModelRouter") as MockRouter,
        patch.dict(sys.modules, {"bdd_vision.browser.controller": _ctrl_module(mock_controller)}),
    ):
        router = MockRouter.return_value
        mock_provider = MagicMock()
        mock_provider.name = "deepseek/vl2"
        router.providers = [mock_provider]
        router.session_cost = 0.01
        router.session_tokens = 500
        router.max_cost = 5.0
        # Low confidence → fail
        router.analyze = AsyncMock(return_value=_vlm_resp(confidence=0.2))

        runner = AgentRunner(settings)
        result = await runner.run("myproject", spec_path)

    assert result.scenarios[0].status == "fail"
    assert result.failed == 1


@pytest.mark.asyncio
async def test_run_skips_steps_after_failure(run_env, mock_cdp, mock_capture, mock_controller):
    spec_path, settings = run_env

    # Spec with 3 steps: Given / When / Then
    spec = _make_spec([_simple_scenario(steps=3)])
    spec_path.write_text(json.dumps(spec))

    call_count = 0

    async def analyze_side_effect(img, instruction, context=""):
        nonlocal call_count
        call_count += 1
        # First call (Given action): low confidence → step 1 fails
        if call_count == 1:
            return _vlm_resp(confidence=0.1)
        # Second call (Given verify): also low → confirmed fail
        return _vlm_resp(confidence=0.1)

    with (
        patch("bdd_vision.core.agent_runner.CDPClient", return_value=mock_cdp),
        patch("bdd_vision.core.agent_runner.ScreenCapture", return_value=mock_capture),
        patch("bdd_vision.core.agent_runner.ModelRouter") as MockRouter,
        patch.dict(sys.modules, {"bdd_vision.browser.controller": _ctrl_module(mock_controller)}),
    ):
        router = MockRouter.return_value
        mock_provider = MagicMock()
        mock_provider.name = "deepseek/vl2"
        router.providers = [mock_provider]
        router.session_cost = 0.01
        router.session_tokens = 500
        router.max_cost = 5.0
        router.analyze = AsyncMock(side_effect=analyze_side_effect)

        runner = AgentRunner(settings)
        result = await runner.run("myproject", spec_path)

    steps = result.scenarios[0].steps
    # Step 1 (Given) fails, step 2 (When) and 3 (Then) should be skipped
    assert steps[0].status == "fail"
    assert steps[1].status == "skip"
    assert steps[2].status == "skip"


@pytest.mark.asyncio
async def test_run_scenario_filter(run_env, mock_cdp, mock_capture, mock_controller):
    spec = _make_spec([
        _simple_scenario("Login flow"),
        _simple_scenario("Logout flow"),
    ])
    spec_path, settings = run_env
    spec_path.write_text(json.dumps(spec))

    with (
        patch("bdd_vision.core.agent_runner.CDPClient", return_value=mock_cdp),
        patch("bdd_vision.core.agent_runner.ScreenCapture", return_value=mock_capture),
        patch("bdd_vision.core.agent_runner.ModelRouter") as MockRouter,
        patch.dict(sys.modules, {"bdd_vision.browser.controller": _ctrl_module(mock_controller)}),
    ):
        router = MockRouter.return_value
        mock_provider = MagicMock()
        mock_provider.name = "deepseek/vl2"
        router.providers = [mock_provider]
        router.session_cost = 0.0
        router.session_tokens = 0
        router.max_cost = 5.0
        router.analyze = AsyncMock(return_value=_vlm_resp(confidence=0.9))

        runner = AgentRunner(settings)
        result = await runner.run("myproject", spec_path, scenario_filter="login")

    assert len(result.scenarios) == 1
    assert "Login" in result.scenarios[0].scenario_name


@pytest.mark.asyncio
async def test_run_saves_session_json(run_env, mock_cdp, mock_capture, mock_controller, tmp_path):
    spec_path, settings = run_env

    with (
        patch("bdd_vision.core.agent_runner.CDPClient", return_value=mock_cdp),
        patch("bdd_vision.core.agent_runner.ScreenCapture", return_value=mock_capture),
        patch("bdd_vision.core.agent_runner.ModelRouter") as MockRouter,
        patch.dict(sys.modules, {"bdd_vision.browser.controller": _ctrl_module(mock_controller)}),
    ):
        router = MockRouter.return_value
        mock_provider = MagicMock()
        mock_provider.name = "deepseek/vl2"
        router.providers = [mock_provider]
        router.session_cost = 0.005
        router.session_tokens = 300
        router.max_cost = 5.0
        router.analyze = AsyncMock(return_value=_vlm_resp(confidence=0.9))

        runner = AgentRunner(settings)
        result = await runner.run("myproject", spec_path)

    sessions_dir = settings.data_dir / "myproject" / "sessions"
    session_files = list(sessions_dir.glob("*/session.json"))
    assert len(session_files) == 1
    data = json.loads(session_files[0].read_text())
    assert data["session_id"] == result.session_id
    assert "scenarios" in data


@pytest.mark.asyncio
async def test_run_click_action_dispatched(run_env, mock_cdp, mock_capture, mock_controller):
    spec_path, settings = run_env

    with (
        patch("bdd_vision.core.agent_runner.CDPClient", return_value=mock_cdp),
        patch("bdd_vision.core.agent_runner.ScreenCapture", return_value=mock_capture),
        patch("bdd_vision.core.agent_runner.ModelRouter") as MockRouter,
        patch.dict(sys.modules, {"bdd_vision.browser.controller": _ctrl_module(mock_controller)}),
    ):
        router = MockRouter.return_value
        mock_provider = MagicMock()
        mock_provider.name = "deepseek/vl2"
        router.providers = [mock_provider]
        router.session_cost = 0.0
        router.session_tokens = 0
        router.max_cost = 5.0
        # First call: click action with coords; second: verify observe
        router.analyze = AsyncMock(side_effect=[
            _vlm_resp(action="click", coordinates=(640, 400), confidence=0.9),
            _vlm_resp(action="observe", confidence=0.9),
            _vlm_resp(action="observe", confidence=0.9),
            _vlm_resp(action="observe", confidence=0.9),
        ])

        runner = AgentRunner(settings)
        await runner.run("myproject", spec_path)

    mock_controller.click.assert_called_once_with(640, 400)
