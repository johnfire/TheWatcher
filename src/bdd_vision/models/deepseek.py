import base64
import io
import json
import re

import httpx
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

# Prompt instructs the VLM to return a structured JSON action decision.
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


class DeepSeekProvider(BaseVLMProvider):
    BASE_URL = "https://api.deepseek.com/v1"

    def __init__(self, api_key: str, model: str = "deepseek-vl2"):
        self._api_key = api_key
        self._model = model

    @property
    def name(self) -> str:
        return f"deepseek/{self._model}"

    @property
    def cost_per_screenshot_usd(self) -> float:
        return 0.002  # rough estimate

    async def health_check(self) -> bool:
        # Fast check: key presence only. API errors during analyze() trigger fallback.
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

        payload = {
            "model": self._model,
            "messages": [
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "image_url",
                            "image_url": {"url": f"data:image/png;base64,{b64}"},
                        },
                        {"type": "text", "text": prompt},
                    ],
                }
            ],
            "max_tokens": 1024,
        }

        async with httpx.AsyncClient(timeout=60.0) as client:
            resp = await client.post(
                f"{self.BASE_URL}/chat/completions",
                headers={
                    "Authorization": f"Bearer {self._api_key}",
                    "Content-Type": "application/json",
                },
                json=payload,
            )
            resp.raise_for_status()

        data = resp.json()
        content = data["choices"][0]["message"]["content"]
        usage = data.get("usage", {})
        tokens = usage.get("total_tokens", 0)
        # DeepSeek pricing is approx $0.14/MTok input, $0.28/MTok output (as of early 2026)
        input_tokens = usage.get("prompt_tokens", tokens // 2)
        output_tokens = usage.get("completion_tokens", tokens // 2)
        cost = input_tokens * 0.14 / 1_000_000 + output_tokens * 0.28 / 1_000_000

        parsed = _parse_json(content)
        logger.debug(f"DeepSeek raw response: {content[:200]}")

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

        payload = {
            "model": self._model,
            "messages": [
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "image_url",
                            "image_url": {"url": f"data:image/png;base64,{b64}"},
                        },
                        {"type": "text", "text": _CRAWL_PROMPT},
                    ],
                }
            ],
            "max_tokens": 2048,
        }

        async with httpx.AsyncClient(timeout=60.0) as client:
            resp = await client.post(
                f"{self.BASE_URL}/chat/completions",
                headers={
                    "Authorization": f"Bearer {self._api_key}",
                    "Content-Type": "application/json",
                },
                json=payload,
            )
            resp.raise_for_status()

        data = resp.json()
        content = data["choices"][0]["message"]["content"]
        usage = data.get("usage", {})
        tokens = usage.get("total_tokens", 0)
        input_tokens = usage.get("prompt_tokens", tokens // 2)
        output_tokens = usage.get("completion_tokens", tokens // 2)
        cost = input_tokens * 0.14 / 1_000_000 + output_tokens * 0.28 / 1_000_000

        parsed = _parse_json(content)
        logger.debug(f"DeepSeek crawl response: {content[:200]}")

        return CrawlPageResult(
            page_description=parsed.get("page_description", ""),
            elements=parsed.get("elements", []),
            navigation_links=parsed.get("navigation_links", []),
            notes=parsed.get("notes", []),
            tokens_used=tokens,
            cost_usd=cost,
        )


def _parse_json(text: str) -> dict:
    """Parse JSON from VLM response, tolerating markdown fences."""
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
