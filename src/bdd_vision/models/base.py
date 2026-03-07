from abc import ABC, abstractmethod
from dataclasses import dataclass

from PIL import Image


@dataclass
class TextResponse:
    """Response from a text-only (no image) VLM call."""
    text: str
    tokens_used: int
    cost_usd: float


@dataclass
class CrawlPageResult:
    """Structured analysis of a page for the crawl engine."""
    page_description: str
    elements: list[dict]        # {type, label, approximate_location, purpose}
    navigation_links: list[dict]  # {label, inferred_path, purpose}
    notes: list[str]
    tokens_used: int
    cost_usd: float


@dataclass
class VLMResponse:
    action: str                          # "click" | "type" | "scroll" | "observe" | "done"
    target_description: str              # natural language description of target element
    coordinates: tuple[int, int] | None  # (x, y) pixel coords if determinable
    text_to_type: str | None             # only populated for "type" action
    observation: str                     # what the model sees / reasoning
    confidence: float                    # 0.0 – 1.0
    tokens_used: int
    cost_usd: float


class BaseVLMProvider(ABC):
    @abstractmethod
    async def analyze_screenshot(
        self,
        screenshot: Image.Image,
        instruction: str,
        context: str = "",
    ) -> VLMResponse:
        """Given a screenshot and an instruction, return an action decision."""

    @abstractmethod
    async def generate_text(self, prompt: str) -> TextResponse:
        """Text-only generation — no screenshot. Used for spec generation and clarification."""

    @abstractmethod
    async def analyze_page(
        self,
        screenshot: Image.Image,
    ) -> CrawlPageResult:
        """Analyze a page screenshot for crawl purposes (structure, links, elements)."""

    @abstractmethod
    async def health_check(self) -> bool:
        """Return True if this provider is configured and usable."""

    @property
    @abstractmethod
    def name(self) -> str:
        """Human-readable provider identifier, e.g. 'deepseek/deepseek-vl2'."""

    @property
    @abstractmethod
    def cost_per_screenshot_usd(self) -> float:
        """Estimated average cost per screenshot analysis call."""
