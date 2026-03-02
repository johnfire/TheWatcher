"""
Spec Engine — two-phase specification lifecycle.
Phase 1: CLI interview (human brief)
Phase 2: AI crawl → sitemap
Phase 3: clarification dialogue
Phase 4: spec document generation

Phase 3 stub — to be implemented in Phase 3.
"""

from ..config.settings import Settings


class SpecEngine:
    def __init__(self, settings: Settings):
        self.settings = settings

    async def generate(self, project: str):
        # Phase 3
        raise NotImplementedError

    async def edit(self, project: str):
        # Phase 3
        raise NotImplementedError
