"""
Crawl Engine — autonomous site crawler.
Explores a website breadth-first, building a structured sitemap JSON.

Phase 2 stub — to be implemented in Phase 2.
"""

from loguru import logger

from ..config.settings import Settings


class CrawlEngine:
    def __init__(self, settings: Settings):
        self.settings = settings

    async def crawl(self, project: str, url: str) -> dict:
        # Phase 2
        raise NotImplementedError
