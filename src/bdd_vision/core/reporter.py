"""
Reporter — PDF and markdown report generator.
Produces human-readable reports from SessionResult data.

Phase 5 stub — to be implemented in Phase 5.
"""

from pathlib import Path

from .agent_runner import SessionResult


class Reporter:
    def generate_markdown(self, result: SessionResult, output_dir: Path) -> Path:
        # Phase 5
        raise NotImplementedError

    def generate_pdf(self, result: SessionResult, output_dir: Path) -> Path:
        # Phase 5
        raise NotImplementedError
