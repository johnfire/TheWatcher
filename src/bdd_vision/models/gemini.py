"""
Gemini Flash 2.0 provider — STUB.
Not yet implemented. health_check() returns False so the router skips it.
Wire this up when a Gemini API key is available.
"""

from PIL import Image
from loguru import logger

from .base import BaseVLMProvider, CrawlPageResult, TextResponse, VLMResponse


class GeminiProvider(BaseVLMProvider):
    def __init__(self, api_key: str = ""):
        self._api_key = api_key

    @property
    def name(self) -> str:
        return "google/gemini-flash-2.0"

    @property
    def cost_per_screenshot_usd(self) -> float:
        return 0.0001

    async def health_check(self) -> bool:
        if not self._api_key:
            return False
        # TODO: implement Gemini provider
        logger.debug("Gemini provider not yet implemented — skipping")
        return False

    async def generate_text(self, prompt: str) -> TextResponse:
        raise NotImplementedError("Gemini provider not yet implemented")


    async def analyze_page(self, screenshot: Image.Image) -> CrawlPageResult:
        raise NotImplementedError("Gemini provider not yet implemented")

    async def analyze_screenshot(
        self,
        screenshot: Image.Image,
        instruction: str,
        context: str = "",
    ) -> VLMResponse:
        raise NotImplementedError("Gemini provider not yet implemented")
