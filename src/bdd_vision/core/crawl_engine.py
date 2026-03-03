"""
Crawl Engine — autonomous site crawler.
Explores a website breadth-first, building a structured sitemap JSON.

Phase 2 implementation.
"""

import asyncio
import json
from collections import deque
from datetime import datetime
from urllib.parse import urljoin, urlparse

from loguru import logger

from ..browser.capture import ScreenCapture
from ..browser.cdp import CDPClient
from ..config.settings import Settings
from ..models.router import AllProvidersFailed, CostLimitExceeded, ModelRouter


class CrawlEngine:
    def __init__(self, settings: Settings):
        self.settings = settings

    async def crawl(self, project: str, url: str) -> dict:
        project_dir = self.settings.data_dir / project
        screenshots_dir = project_dir / "screenshots" / "crawl"
        sitemaps_dir = project_dir / "sitemaps"

        capture = ScreenCapture(screenshots_dir)
        cdp = CDPClient(port=self.settings.chrome_cdp_port)
        router = ModelRouter(self.settings)

        await cdp.connect()

        base_url = url.rstrip("/")
        base_domain = urlparse(base_url).netloc

        visited: set[str] = set()
        queue: deque[tuple[str, int]] = deque([(url, 0)])
        pages: list[dict] = []

        loop = asyncio.get_event_loop()
        deadline = loop.time() + self.settings.crawl_timeout_seconds

        try:
            while queue and len(pages) < self.settings.max_pages:
                if loop.time() > deadline:
                    logger.warning("Crawl timeout reached")
                    break

                current_url, depth = queue.popleft()

                normalised = current_url.rstrip("/")
                if normalised in visited:
                    continue
                visited.add(normalised)

                if depth > self.settings.max_depth:
                    continue

                logger.info(f"Crawling [{depth}] {current_url}")

                try:
                    await cdp.navigate(current_url)
                    title = await cdp.get_page_title()
                    actual_url = await cdp.get_current_url()

                    img, screenshot_path = capture.capture(f"crawl_{len(pages):03d}")

                    result = await router.analyze_page(img)

                    page_data = {
                        "url": actual_url or current_url,
                        "title": title,
                        "depth": depth,
                        "description": result.page_description,
                        "elements": result.elements,
                        "links_found": result.navigation_links,
                        "notes": result.notes,
                        "screenshot": str(screenshot_path),
                        "tokens_used": result.tokens_used,
                        "cost_usd": result.cost_usd,
                    }
                    pages.append(page_data)

                    if depth < self.settings.max_depth:
                        for link in result.navigation_links:
                            path = link.get("inferred_path", "")
                            next_url = _resolve_url(base_url, path, base_domain)
                            if next_url and next_url.rstrip("/") not in visited:
                                queue.append((next_url, depth + 1))

                except (CostLimitExceeded, AllProvidersFailed):
                    logger.warning("VLM unavailable — stopping crawl early")
                    break
                except Exception as e:
                    logger.warning(f"Failed to crawl {current_url}: {e}")
                    continue

        finally:
            await cdp.disconnect()

        sitemap = {
            "project": project,
            "base_url": url,
            "crawled_at": datetime.now().isoformat(),
            "pages": pages,
            "total_pages": len(pages),
            "total_cost_usd": round(router.session_cost, 6),
            "total_tokens": router.session_tokens,
        }

        sitemaps_dir.mkdir(parents=True, exist_ok=True)
        sitemap_path = (
            sitemaps_dir
            / f"sitemap_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        )
        tmp = sitemap_path.with_suffix(".tmp")
        tmp.write_text(json.dumps(sitemap, indent=2))
        tmp.rename(sitemap_path)

        logger.info(
            f"Crawl complete: {len(pages)} pages, "
            f"${router.session_cost:.4f}, saved to {sitemap_path}"
        )
        return sitemap


def _resolve_url(base_url: str, path: str, base_domain: str) -> str | None:
    """Resolve a link path against base_url. Returns None for external/non-HTTP links."""
    if not path:
        return None

    if path.startswith(("#", "mailto:", "tel:", "javascript:")):
        return None

    if path.startswith("http"):
        parsed = urlparse(path)
        if parsed.netloc != base_domain:
            return None
        return path.rstrip("/")

    resolved = urljoin(base_url + "/", path.lstrip("/")).rstrip("/")
    if urlparse(resolved).netloc != base_domain:
        return None
    return resolved
