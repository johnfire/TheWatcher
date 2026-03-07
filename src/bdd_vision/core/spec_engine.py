"""
Spec Engine — BDD specification lifecycle.
  1. CLI interview: collect human brief
  2. VLM clarification: generate targeted questions, collect answers
  3. VLM spec generation: produce Gherkin-style BDD scenarios from brief + sitemap + answers
  4. Save spec JSON to data/<project>/specs/

Phase 3 implementation.
"""

import json
import re
from datetime import datetime
from pathlib import Path

import click
from loguru import logger
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from ..config.settings import Settings
from ..models.router import AllProvidersFailed, CostLimitExceeded, ModelRouter

console = Console()

_CLARIFY_PROMPT = """\
You are a BDD test specification expert.

Testing brief: {brief}

Website structure:
{sitemap_summary}

Generate 3-5 targeted clarifying questions that will help produce better BDD test scenarios.
Focus on: specific user flows, authentication requirements, test data, edge cases, expected outcomes.

Return ONLY a JSON array of strings — no explanation, no markdown fences:
["question 1", "question 2", ...]"""

_SPEC_PROMPT = """\
You are a BDD test specification expert. Generate a comprehensive BDD test specification.

Testing brief: {brief}

Clarifications:
{clarifications}

Website structure:
{sitemap_summary}

Generate Gherkin-style BDD scenarios covering the key user flows. Be specific — use realistic
values for URLs, button text, and form fields based on the site structure described above.

Return ONLY a valid JSON object — no explanation, no markdown fences:
{{
  "features": [
    {{
      "name": "Feature name",
      "description": "What this feature tests",
      "scenarios": [
        {{
          "name": "Scenario name",
          "steps": [
            {{"keyword": "Given", "text": "step text"}},
            {{"keyword": "When", "text": "step text"}},
            {{"keyword": "Then", "text": "step text"}}
          ]
        }}
      ]
    }}
  ]
}}"""


class SpecEngine:
    def __init__(self, settings: Settings):
        self.settings = settings

    # ── Public API ───────────────────────────────────────────────────────────

    async def generate(self, project: str) -> dict:
        """Full spec generation flow: interview → clarify → generate → save."""
        project_dir = self.settings.data_dir / project
        cfg = json.loads((project_dir / "project.json").read_text())

        # Load sitemap (required)
        sitemap = self._load_latest_sitemap(project_dir)
        if sitemap is None:
            raise RuntimeError(
                f"No sitemap found for project '{project}'. "
                "Run `bdd-vision crawl` first."
            )

        sitemap_summary = _sitemap_summary(sitemap)
        router = ModelRouter(self.settings)

        # Step 1 — collect brief
        console.print("\n[bold]Step 1 — Testing brief[/bold]")
        console.print("Describe what you want to test (user flows, features, scenarios).")
        brief = click.prompt("\nBrief")

        # Step 2 — VLM clarifying questions
        console.print("\n[bold]Step 2 — Clarifying questions[/bold]")
        console.print("[dim]Generating questions based on your brief and the crawled site...[/dim]")

        questions = await self._get_clarifying_questions(router, brief, sitemap_summary)
        clarifications: dict[str, str] = {}

        if questions:
            console.print()
            for i, q in enumerate(questions, 1):
                answer = click.prompt(f"Q{i}: {q}")
                clarifications[q] = answer
        else:
            console.print("[dim]No clarifying questions generated — proceeding.[/dim]")

        # Step 3 — generate spec
        console.print("\n[bold]Step 3 — Generating BDD spec...[/bold]")
        spec_data, tokens, cost = await self._generate_spec(
            router, brief, clarifications, sitemap_summary
        )

        # Step 4 — assemble and save
        spec_version = cfg.get("spec_version", 0) + 1
        spec = {
            "project": project,
            "version": spec_version,
            "brief": brief,
            "clarifications": clarifications,
            "base_url": cfg["url"],
            "created_at": datetime.now().isoformat(),
            "features": spec_data.get("features", []),
            "total_scenarios": _count_scenarios(spec_data),
            "total_steps": _count_steps(spec_data),
            "tokens_used": tokens,
            "cost_usd": cost,
        }

        saved_path = self._save_spec(project_dir, spec_version, spec)

        # Update project.json spec_version
        cfg["spec_version"] = spec_version
        tmp = (project_dir / "project.json").with_suffix(".tmp")
        tmp.write_text(json.dumps(cfg, indent=2))
        tmp.rename(project_dir / "project.json")

        logger.info(
            f"Spec v{spec_version} saved: {spec['total_scenarios']} scenarios, "
            f"{spec['total_steps']} steps, ${cost:.4f}"
        )
        return spec

    async def edit(self, project: str) -> dict:
        """Re-generate spec, pre-filling the brief from the existing spec."""
        project_dir = self.settings.data_dir / project
        existing = self._load_latest_spec(project_dir)

        if existing:
            console.print(
                Panel(
                    f"[bold]Current spec v{existing['version']}[/bold]\n"
                    f"Brief: {existing['brief']}\n"
                    f"Scenarios: {existing['total_scenarios']}",
                    title="Existing spec",
                )
            )
            if not click.confirm("\nRe-generate spec? (existing will be kept as previous version)", default=True):
                return existing

        return await self.generate(project)

    # ── Internals ────────────────────────────────────────────────────────────

    def _load_latest_sitemap(self, project_dir: Path) -> dict | None:
        sitemaps_dir = project_dir / "sitemaps"
        if not sitemaps_dir.exists():
            return None
        files = sorted(sitemaps_dir.glob("sitemap_*.json"))
        return json.loads(files[-1].read_text()) if files else None

    def _load_latest_spec(self, project_dir: Path) -> dict | None:
        specs_dir = project_dir / "specs"
        if not specs_dir.exists():
            return None
        files = sorted(specs_dir.glob("spec_v*.json"))
        return json.loads(files[-1].read_text()) if files else None

    def _save_spec(self, project_dir: Path, version: int, spec: dict) -> Path:
        specs_dir = project_dir / "specs"
        specs_dir.mkdir(parents=True, exist_ok=True)
        path = specs_dir / f"spec_v{version:03d}.json"
        tmp = path.with_suffix(".tmp")
        tmp.write_text(json.dumps(spec, indent=2))
        tmp.rename(path)
        return path

    async def _get_clarifying_questions(
        self, router: ModelRouter, brief: str, sitemap_summary: str
    ) -> list[str]:
        prompt = _CLARIFY_PROMPT.format(brief=brief, sitemap_summary=sitemap_summary)
        try:
            resp = await router.generate_text(prompt)
            return _parse_question_list(resp.text)
        except (CostLimitExceeded, AllProvidersFailed) as e:
            logger.warning(f"Could not generate clarifying questions: {e}")
            return []

    async def _generate_spec(
        self,
        router: ModelRouter,
        brief: str,
        clarifications: dict[str, str],
        sitemap_summary: str,
    ) -> tuple[dict, int, float]:
        clarification_text = (
            "\n".join(f"Q: {q}\nA: {a}" for q, a in clarifications.items())
            if clarifications
            else "(none provided)"
        )
        prompt = _SPEC_PROMPT.format(
            brief=brief,
            clarifications=clarification_text,
            sitemap_summary=sitemap_summary,
        )
        resp = await router.generate_text(prompt)
        parsed = _parse_spec_json(resp.text)
        return parsed, resp.tokens_used, resp.cost_usd


# ── Helpers ──────────────────────────────────────────────────────────────────

def _sitemap_summary(sitemap: dict) -> str:
    pages = sitemap.get("pages", [])
    lines = [
        f"Base URL: {sitemap.get('base_url', '')}",
        f"Pages crawled: {len(pages)}",
    ]
    for p in pages[:25]:  # cap to avoid token bloat
        desc = (p.get("description") or "")[:120]
        lines.append(f"  [{p['depth']}] {p['url']}  \"{p.get('title', '')}\"  — {desc}")
    return "\n".join(lines)


def _parse_question_list(text: str) -> list[str]:
    try:
        parsed = json.loads(text)
        if isinstance(parsed, list):
            return [str(q) for q in parsed if q]
    except json.JSONDecodeError:
        pass
    match = re.search(r"\[.*?\]", text, re.DOTALL)
    if match:
        try:
            parsed = json.loads(match.group())
            if isinstance(parsed, list):
                return [str(q) for q in parsed if q]
        except json.JSONDecodeError:
            pass
    return []


def _parse_spec_json(text: str) -> dict:
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass
    match = re.search(r"\{.*\}", text, re.DOTALL)
    if match:
        try:
            return json.loads(match.group())
        except json.JSONDecodeError:
            pass
    logger.warning("Could not parse VLM spec response — returning empty spec")
    return {"features": []}


def _count_scenarios(spec_data: dict) -> int:
    return sum(len(f.get("scenarios", [])) for f in spec_data.get("features", []))


def _count_steps(spec_data: dict) -> int:
    return sum(
        len(s.get("steps", []))
        for f in spec_data.get("features", [])
        for s in f.get("scenarios", [])
    )
