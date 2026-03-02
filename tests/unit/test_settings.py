from pathlib import Path

from bdd_vision.config.settings import ModelTier, Settings


def test_defaults():
    s = Settings(
        gemini_api_key="",
        deepseek_api_key="",
        anthropic_api_key="",
    )
    assert s.model_tier == ModelTier.STAGING
    assert s.max_cost_per_session_usd == 5.0
    assert s.chrome_cdp_port == 9222
    assert s.max_step_retries == 3


def test_log_dir_defaults_to_home():
    s = Settings(gemini_api_key="", deepseek_api_key="", anthropic_api_key="")
    assert s.log_dir == Path.home() / "logs"


def test_model_tier_enum():
    s = Settings(
        model_tier="prod",
        gemini_api_key="",
        deepseek_api_key="",
        anthropic_api_key="",
    )
    assert s.model_tier == ModelTier.PROD
