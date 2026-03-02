import pytest

from bdd_vision.config.settings import ModelTier, Settings


@pytest.fixture
def settings(tmp_path):
    """Settings with temp paths and test API keys — no real API calls."""
    return Settings(
        model_tier=ModelTier.STAGING,
        gemini_api_key="",
        deepseek_api_key="test-deepseek-key",
        anthropic_api_key="test-anthropic-key",
        data_dir=tmp_path / "data",
        log_dir=tmp_path / "logs",
        max_cost_per_session_usd=5.0,
    )
