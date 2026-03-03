import base64
import io
import json
import re

import anthropic
from loguru import logger
from PIL import Image

from .base import BaseVLMProvider, CrawlPageResult, VLMResponse

_CRAWL_PROMPT = """\
Analyze this webpage screenshot and provide a structured page analysis.

Respond with ONLY a valid JSON object — no explanation, no markdown fences:
{
  "page_description": "<1-2 sentence description of the page purpose and content>",
  "elements": [
    {"type": "<button|link|form|input|nav|image|other>", "label": "<visible text>", "approximate_location": "<top-left|top-center|top-right|mid-left|mid-center|mid-right|bottom-left|bottom-center|bottom-right>", "purpose": "<what this element does>"}
  ],
  "navigation_links": [
    {"label": "<link text>", "inferred_path": "<relative or absolute URL>", "purpose": "<where it leads>"}
  ],
  "notes": ["<notable features, warnings, or observations>"]
}"""

_ACTION_PROMPT = """\
Analyze this screenshot and decide the next action.

Instruction: {instruction}
{context_block}

Respond with ONLY a valid JSON object — no explanation, no markdown fences:
{{
  "action": "<click|type|scroll|observe|done>",
  "target_description": "<natural language description of the UI element to interact with, or empty string>",
  "coordinates": [x, y] or null,
  "text_to_type": "<string or null>",
  "observation": "<what you see on screen>",
  "confidence": <0.0-1.0>
}}"""

# Anthropic pricing (claude-opus-4-6, as of early 2026)
_INPUT_COST_PER_TOKEN = 15.0 / 1_000_000
_OUTPUT_COST_PER_TOKEN = 75.0 / 1_000_000


class ClaudeComputerUseProvider(BaseVLMProvider):
    MODEL = "claude-opus-4-6"

    def __init__(self, api_key: str):
        self._api_key = api_key
        # Client is created lazily so missing key doesn't crash at import time
        self._client: anthropic.AsyncAnthropic | None = None

    def _get_client(self) -> anthropic.AsyncAnthropic:
        if self._client is None:
            self._client = anthropic.AsyncAnthropic(api_key=self._api_key)
        return self._client

    @property
    def name(self) -> str:
        return f"anthropic/{self.MODEL}"

    @property
    def cost_per_screenshot_usd(self) -> float:
        return 0.05  # rough estimate for vision analysis

    async def health_check(self) -> bool:
        return bool(self._api_key)

    def _encode(self, image: Image.Image) -> str:
        buf = io.BytesIO()
        image.save(buf, format="PNG")
        return base64.b64encode(buf.getvalue()).decode()

    async def analyze_screenshot(
        self,
        screenshot: Image.Image,
        instruction: str,
        context: str = "",
    ) -> VLMResponse:
        b64 = self._encode(screenshot)
        context_block = f"Context: {context}" if context else ""
        prompt = _ACTION_PROMPT.format(
            instruction=instruction,
            context_block=context_block,
        )

        response = await self._get_client().messages.create(
            model=self.MODEL,
            max_tokens=1024,
            messages=[
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "image",
                            "source": {
                                "type": "base64",
                                "media_type": "image/png",
                                "data": b64,
                            },
                        },
                        {"type": "text", "text": prompt},
                    ],
                }
            ],
        )

        content = response.content[0].text
        input_tokens = response.usage.input_tokens
        output_tokens = response.usage.output_tokens
        tokens = input_tokens + output_tokens
        cost = (
            input_tokens * _INPUT_COST_PER_TOKEN
            + output_tokens * _OUTPUT_COST_PER_TOKEN
        )

        logger.debug(f"Claude raw response: {content[:200]}")
        parsed = _parse_json(content)
        coords = _extract_coords(parsed.get("coordinates"))

        return VLMResponse(
            action=parsed.get("action", "observe"),
            target_description=parsed.get("target_description", ""),
            coordinates=coords,
            text_to_type=parsed.get("text_to_type"),
            observation=parsed.get("observation", content),
            confidence=float(parsed.get("confidence", 0.5)),
            tokens_used=tokens,
            cost_usd=cost,
        )


    async def analyze_page(self, screenshot: Image.Image) -> CrawlPageResult:
        b64 = self._encode(screenshot)

        response = await self._get_client().messages.create(
            model=self.MODEL,
            max_tokens=2048,
            messages=[
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "image",
                            "source": {
                                "type": "base64",
                                "media_type": "image/png",
                                "data": b64,
                            },
                        },
                        {"type": "text", "text": _CRAWL_PROMPT},
                    ],
                }
            ],
        )

        content = response.content[0].text
        input_tokens = response.usage.input_tokens
        output_tokens = response.usage.output_tokens
        tokens = input_tokens + output_tokens
        cost = (
            input_tokens * _INPUT_COST_PER_TOKEN
            + output_tokens * _OUTPUT_COST_PER_TOKEN
        )

        logger.debug(f"Claude crawl response: {content[:200]}")
        parsed = _parse_json(content)

        return CrawlPageResult(
            page_description=parsed.get("page_description", ""),
            elements=parsed.get("elements", []),
            navigation_links=parsed.get("navigation_links", []),
            notes=parsed.get("notes", []),
            tokens_used=tokens,
            cost_usd=cost,
        )


def _parse_json(text: str) -> dict:
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        match = re.search(r"\{.*\}", text, re.DOTALL)
        if match:
            try:
                return json.loads(match.group())
            except json.JSONDecodeError:
                pass
    return {
        "action": "observe",
        "target_description": "",
        "coordinates": None,
        "text_to_type": None,
        "observation": text,
        "confidence": 0.3,
    }


def _extract_coords(raw) -> tuple[int, int] | None:
    if raw and isinstance(raw, (list, tuple)) and len(raw) == 2:
        try:
            return (int(raw[0]), int(raw[1]))
        except (TypeError, ValueError):
            pass
    return None
