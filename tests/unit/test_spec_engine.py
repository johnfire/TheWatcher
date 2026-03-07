import json
import pytest
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

from bdd_vision.core.spec_engine import (
    SpecEngine,
    _count_scenarios,
    _count_steps,
    _parse_question_list,
    _parse_spec_json,
    _sitemap_summary,
)
from bdd_vision.models.base import TextResponse


def _mock_text_response(text: str) -> TextResponse:
    return TextResponse(text=text, tokens_used=500, cost_usd=0.005)


def _fake_sitemap(base_url: str = "https://example.com") -> dict:
    return {
        "base_url": base_url,
        "pages": [
            {
                "url": base_url,
                "title": "Home",
                "depth": 0,
                "description": "The home page",
                "links_found": [],
            },
            {
                "url": f"{base_url}/login",
                "title": "Login",
                "depth": 1,
                "description": "Login form page",
                "links_found": [],
            },
        ],
    }


def _fake_spec_json() -> str:
    return json.dumps({
        "features": [
            {
                "name": "User Login",
                "description": "Tests for the login flow",
                "scenarios": [
                    {
                        "name": "Successful login",
                        "steps": [
                            {"keyword": "Given", "text": "I am on the login page"},
                            {"keyword": "When", "text": "I enter valid credentials"},
                            {"keyword": "Then", "text": "I am redirected to the dashboard"},
                        ],
                    },
                    {
                        "name": "Failed login",
                        "steps": [
                            {"keyword": "Given", "text": "I am on the login page"},
                            {"keyword": "When", "text": "I enter invalid credentials"},
                            {"keyword": "Then", "text": "I see an error message"},
                        ],
                    },
                ],
            }
        ]
    })


# ── Helper functions ─────────────────────────────────────────────────────────

def test_sitemap_summary_includes_base_url():
    sitemap = _fake_sitemap("https://example.com")
    summary = _sitemap_summary(sitemap)
    assert "https://example.com" in summary
    assert "Pages crawled: 2" in summary


def test_sitemap_summary_includes_page_urls():
    sitemap = _fake_sitemap("https://example.com")
    summary = _sitemap_summary(sitemap)
    assert "/login" in summary


def test_parse_question_list_valid_json():
    text = '["What user roles exist?", "Is login required?", "Any rate limits?"]'
    result = _parse_question_list(text)
    assert len(result) == 3
    assert "What user roles exist?" in result


def test_parse_question_list_embedded_in_text():
    text = 'Here are questions: ["Q1?", "Q2?"]'
    result = _parse_question_list(text)
    assert len(result) == 2


def test_parse_question_list_invalid_returns_empty():
    result = _parse_question_list("not valid json at all")
    assert result == []


def test_parse_spec_json_valid():
    text = _fake_spec_json()
    result = _parse_spec_json(text)
    assert "features" in result
    assert len(result["features"]) == 1


def test_parse_spec_json_with_preamble():
    text = "Sure! Here's your spec:\n" + _fake_spec_json() + "\nThat's it!"
    result = _parse_spec_json(text)
    assert "features" in result


def test_parse_spec_json_invalid_returns_empty_features():
    result = _parse_spec_json("completely unparseable")
    assert result == {"features": []}


def test_count_scenarios():
    spec_data = json.loads(_fake_spec_json())
    assert _count_scenarios(spec_data) == 2


def test_count_steps():
    spec_data = json.loads(_fake_spec_json())
    assert _count_steps(spec_data) == 6


# ── SpecEngine ───────────────────────────────────────────────────────────────

@pytest.fixture
def project_dir(tmp_path):
    settings_data_dir = tmp_path / "data"
    project = settings_data_dir / "myproject"
    (project / "specs").mkdir(parents=True)
    (project / "sitemaps").mkdir(parents=True)
    # Write project.json
    (project / "project.json").write_text(json.dumps({
        "name": "myproject",
        "url": "https://example.com",
        "created_at": "2026-03-07T00:00:00",
        "spec_version": 0,
    }))
    # Write a sitemap
    sitemap = _fake_sitemap()
    sitemap_path = project / "sitemaps" / "sitemap_20260307_120000.json"
    sitemap_path.write_text(json.dumps(sitemap))
    return project


@pytest.fixture
def spec_settings(tmp_path, project_dir):
    from bdd_vision.config.settings import ModelTier, Settings
    return Settings(
        model_tier=ModelTier.STAGING,
        deepseek_api_key="test-key",
        anthropic_api_key="test-anthropic-key",
        data_dir=project_dir.parent,
        log_dir=tmp_path / "logs",
        max_cost_per_session_usd=5.0,
    )


@pytest.mark.asyncio
async def test_generate_saves_spec_file(spec_settings, project_dir):
    questions_resp = _mock_text_response('["What browsers?", "Auth required?"]')
    spec_resp = _mock_text_response(_fake_spec_json())

    with (
        patch("bdd_vision.core.spec_engine.ModelRouter") as MockRouter,
        patch("bdd_vision.core.spec_engine.click.prompt", side_effect=["test the login flow", "Chrome", "Yes"]),
    ):
        router_instance = MockRouter.return_value
        router_instance.generate_text = AsyncMock(side_effect=[questions_resp, spec_resp])
        router_instance.session_cost = 0.01
        router_instance.session_tokens = 1000

        engine = SpecEngine(spec_settings)
        spec = await engine.generate("myproject")

    assert spec["version"] == 1
    assert spec["brief"] == "test the login flow"
    assert spec["total_scenarios"] == 2
    assert spec["total_steps"] == 6

    saved = sorted((project_dir / "specs").glob("spec_v*.json"))
    assert len(saved) == 1
    data = json.loads(saved[0].read_text())
    assert data["version"] == 1


@pytest.mark.asyncio
async def test_generate_increments_version(spec_settings, project_dir):
    # Pre-existing spec v1
    (project_dir / "specs" / "spec_v001.json").write_text(json.dumps({
        "version": 1, "brief": "old brief",
    }))
    # Update project.json to reflect v1
    cfg = json.loads((project_dir / "project.json").read_text())
    cfg["spec_version"] = 1
    (project_dir / "project.json").write_text(json.dumps(cfg))

    questions_resp = _mock_text_response("[]")
    spec_resp = _mock_text_response(_fake_spec_json())

    with (
        patch("bdd_vision.core.spec_engine.ModelRouter") as MockRouter,
        patch("bdd_vision.core.spec_engine.click.prompt", return_value="new brief"),
    ):
        router_instance = MockRouter.return_value
        router_instance.generate_text = AsyncMock(side_effect=[questions_resp, spec_resp])
        router_instance.session_cost = 0.01
        router_instance.session_tokens = 1000

        engine = SpecEngine(spec_settings)
        spec = await engine.generate("myproject")

    assert spec["version"] == 2


@pytest.mark.asyncio
async def test_generate_raises_without_sitemap(spec_settings, project_dir):
    # Remove the sitemap
    for f in (project_dir / "sitemaps").glob("*.json"):
        f.unlink()

    engine = SpecEngine(spec_settings)
    with pytest.raises(RuntimeError, match="No sitemap found"):
        await engine.generate("myproject")


@pytest.mark.asyncio
async def test_generate_handles_no_clarifying_questions(spec_settings, project_dir):
    questions_resp = _mock_text_response("[]")
    spec_resp = _mock_text_response(_fake_spec_json())

    with (
        patch("bdd_vision.core.spec_engine.ModelRouter") as MockRouter,
        patch("bdd_vision.core.spec_engine.click.prompt", return_value="test everything"),
    ):
        router_instance = MockRouter.return_value
        router_instance.generate_text = AsyncMock(side_effect=[questions_resp, spec_resp])
        router_instance.session_cost = 0.01
        router_instance.session_tokens = 1000

        engine = SpecEngine(spec_settings)
        spec = await engine.generate("myproject")

    assert spec["clarifications"] == {}


@pytest.mark.asyncio
async def test_generate_stores_clarifications(spec_settings, project_dir):
    questions_resp = _mock_text_response('["Which browsers?"]')
    spec_resp = _mock_text_response(_fake_spec_json())

    with (
        patch("bdd_vision.core.spec_engine.ModelRouter") as MockRouter,
        patch("bdd_vision.core.spec_engine.click.prompt", side_effect=["my brief", "Chrome only"]),
    ):
        router_instance = MockRouter.return_value
        router_instance.generate_text = AsyncMock(side_effect=[questions_resp, spec_resp])
        router_instance.session_cost = 0.01
        router_instance.session_tokens = 1000

        engine = SpecEngine(spec_settings)
        spec = await engine.generate("myproject")

    assert "Which browsers?" in spec["clarifications"]
    assert spec["clarifications"]["Which browsers?"] == "Chrome only"


@pytest.mark.asyncio
async def test_generate_updates_project_json_version(spec_settings, project_dir):
    questions_resp = _mock_text_response("[]")
    spec_resp = _mock_text_response(_fake_spec_json())

    with (
        patch("bdd_vision.core.spec_engine.ModelRouter") as MockRouter,
        patch("bdd_vision.core.spec_engine.click.prompt", return_value="brief"),
    ):
        router_instance = MockRouter.return_value
        router_instance.generate_text = AsyncMock(side_effect=[questions_resp, spec_resp])
        router_instance.session_cost = 0.01
        router_instance.session_tokens = 1000

        engine = SpecEngine(spec_settings)
        await engine.generate("myproject")

    cfg = json.loads((project_dir / "project.json").read_text())
    assert cfg["spec_version"] == 1
