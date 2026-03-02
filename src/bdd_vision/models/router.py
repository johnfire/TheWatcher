from loguru import logger
from PIL import Image

from ..config.settings import ModelTier, Settings
from .base import BaseVLMProvider, VLMResponse
from .claude_cu import ClaudeComputerUseProvider
from .deepseek import DeepSeekProvider
from .gemini import GeminiProvider


class CostLimitExceeded(Exception):
    pass


class AllProvidersFailed(Exception):
    pass


class ModelRouter:
    """
    Selects VLM provider based on configured tier.
    Falls back to the next provider in the chain on failure.
    Tracks total cost and tokens for the session.
    """

    def __init__(self, settings: Settings):
        self.providers: list[BaseVLMProvider] = self._build_chain(settings)
        self.session_cost: float = 0.0
        self.session_tokens: int = 0
        self.max_cost: float = settings.max_cost_per_session_usd

    def _build_chain(self, settings: Settings) -> list[BaseVLMProvider]:
        gemini = GeminiProvider(settings.gemini_api_key)
        deepseek = DeepSeekProvider(settings.deepseek_api_key, settings.deepseek_model_name)
        claude = ClaudeComputerUseProvider(settings.anthropic_api_key)

        if settings.model_tier == ModelTier.PROD:
            return [claude, deepseek, gemini]
        elif settings.model_tier == ModelTier.STAGING:
            return [deepseek, claude, gemini]
        else:  # DEV — Gemini first, falls through to DeepSeek when key absent
            return [gemini, deepseek, claude]

    async def analyze(
        self,
        screenshot: Image.Image,
        instruction: str,
        context: str = "",
    ) -> VLMResponse:
        if self.session_cost >= self.max_cost:
            raise CostLimitExceeded(
                f"Session cost limit ${self.max_cost:.2f} reached "
                f"(used ${self.session_cost:.4f})"
            )

        last_error: Exception | None = None

        for provider in self.providers:
            try:
                if not await provider.health_check():
                    logger.debug(f"Provider {provider.name} unavailable — skipping")
                    continue

                response = await provider.analyze_screenshot(
                    screenshot, instruction, context
                )
                self.session_cost += response.cost_usd
                self.session_tokens += response.tokens_used

                logger.info(
                    f"VLM {provider.name} | action={response.action} | "
                    f"confidence={response.confidence:.2f} | "
                    f"tokens={response.tokens_used} | cost=${response.cost_usd:.4f}"
                )
                return response

            except Exception as e:
                last_error = e
                logger.warning(
                    f"Provider {provider.name} failed: {e}. Trying next provider."
                )
                continue

        raise AllProvidersFailed(
            f"All providers failed. Last error: {last_error}"
        )

    def cost_summary(self) -> dict:
        return {
            "session_cost_usd": round(self.session_cost, 6),
            "session_tokens": self.session_tokens,
            "cost_limit_usd": self.max_cost,
        }
