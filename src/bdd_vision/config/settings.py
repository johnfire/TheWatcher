from enum import Enum
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class ModelTier(str, Enum):
    DEV = "dev"         # Gemini first → DeepSeek → Claude
    STAGING = "staging" # DeepSeek first → Claude
    PROD = "prod"       # Claude first → DeepSeek


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # Active tier
    model_tier: ModelTier = ModelTier.STAGING

    # API Keys
    gemini_api_key: str = ""
    deepseek_api_key: str = ""
    anthropic_api_key: str = ""

    # DeepSeek model name (their VL2 via OpenAI-compatible endpoint)
    deepseek_model_name: str = "deepseek-vl2"

    # Cost controls
    max_cost_per_session_usd: float = 5.00
    max_screenshots_per_run: int = 200

    # Browser
    browser_headless: bool = False
    browser_width: int = 1280
    browser_height: int = 900
    chrome_cdp_port: int = 9222

    # Crawl limits
    max_pages: int = 30
    max_depth: int = 4
    crawl_timeout_seconds: int = 300

    # Retry / timing
    max_step_retries: int = 3
    screenshot_interval_ms: int = 500
    fallback_wait_ms: int = 2000  # Used when CDP is unavailable

    # Paths
    data_dir: Path = Path("./data")
    log_dir: Path = Field(default_factory=lambda: Path.home() / "logs")
