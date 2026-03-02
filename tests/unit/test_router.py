import pytest
from PIL import Image
from unittest.mock import AsyncMock, patch

from bdd_vision.models.router import AllProvidersFailed, CostLimitExceeded, ModelRouter
from bdd_vision.models.base import VLMResponse
from bdd_vision.config.settings import ModelTier


def _mock_response(**kwargs) -> VLMResponse:
    defaults = dict(
        action="observe",
        target_description="",
        coordinates=None,
        text_to_type=None,
        observation="I see a webpage",
        confidence=0.9,
        tokens_used=100,
        cost_usd=0.001,
    )
    defaults.update(kwargs)
    return VLMResponse(**defaults)


def _blank_image() -> Image.Image:
    return Image.new("RGB", (100, 100), color=(200, 200, 200))


@pytest.mark.asyncio
async def test_uses_first_available_provider(settings):
    router = ModelRouter(settings)
    # STAGING tier: [deepseek, claude, gemini]
    # Make deepseek available, mock its analyze
    with (
        patch.object(router.providers[0], "health_check", new=AsyncMock(return_value=True)),
        patch.object(
            router.providers[0],
            "analyze_screenshot",
            new=AsyncMock(return_value=_mock_response()),
        ),
    ):
        response = await router.analyze(_blank_image(), "test instruction")

    assert response.observation == "I see a webpage"
    assert router.session_cost == pytest.approx(0.001)


@pytest.mark.asyncio
async def test_falls_back_to_second_provider(settings):
    router = ModelRouter(settings)
    with (
        patch.object(router.providers[0], "health_check", new=AsyncMock(return_value=False)),
        patch.object(router.providers[1], "health_check", new=AsyncMock(return_value=True)),
        patch.object(
            router.providers[1],
            "analyze_screenshot",
            new=AsyncMock(return_value=_mock_response(observation="fallback response")),
        ),
    ):
        response = await router.analyze(_blank_image(), "test")

    assert response.observation == "fallback response"


@pytest.mark.asyncio
async def test_cost_limit_raises(settings):
    settings.max_cost_per_session_usd = 0.0
    router = ModelRouter(settings)
    router.session_cost = 1.0  # already over limit

    with pytest.raises(CostLimitExceeded):
        await router.analyze(_blank_image(), "test")


@pytest.mark.asyncio
async def test_all_providers_fail_raises(settings):
    router = ModelRouter(settings)
    for p in router.providers:
        p.health_check = AsyncMock(return_value=False)

    with pytest.raises(AllProvidersFailed):
        await router.analyze(_blank_image(), "test")


@pytest.mark.asyncio
async def test_provider_exception_triggers_fallback(settings):
    router = ModelRouter(settings)
    with (
        patch.object(router.providers[0], "health_check", new=AsyncMock(return_value=True)),
        patch.object(
            router.providers[0],
            "analyze_screenshot",
            new=AsyncMock(side_effect=RuntimeError("API error")),
        ),
        patch.object(router.providers[1], "health_check", new=AsyncMock(return_value=True)),
        patch.object(
            router.providers[1],
            "analyze_screenshot",
            new=AsyncMock(return_value=_mock_response(observation="second provider")),
        ),
    ):
        response = await router.analyze(_blank_image(), "test")

    assert response.observation == "second provider"


def test_staging_tier_chain_order(settings):
    settings.model_tier = ModelTier.STAGING
    router = ModelRouter(settings)
    assert router.providers[0].name.startswith("deepseek/")


def test_prod_tier_chain_order(settings):
    settings.model_tier = ModelTier.PROD
    router = ModelRouter(settings)
    assert router.providers[0].name.startswith("anthropic/")


def test_cost_summary(settings):
    router = ModelRouter(settings)
    router.session_cost = 0.123
    router.session_tokens = 500
    summary = router.cost_summary()
    assert summary["session_cost_usd"] == pytest.approx(0.123)
    assert summary["session_tokens"] == 500
