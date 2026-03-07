import asyncio
import json
from datetime import datetime
from pathlib import Path

import click
from loguru import logger
from rich.console import Console
from rich.table import Table

from ..browser.capture import ScreenCapture
from ..browser.cdp import CDPClient
from ..config.settings import Settings
from ..core.crawl_engine import CrawlEngine
from ..core.spec_engine import SpecEngine
from ..models.router import AllProvidersFailed, CostLimitExceeded, ModelRouter

console = Console()


def _setup_logging(settings: Settings):
    log_dir = settings.log_dir
    log_dir.mkdir(parents=True, exist_ok=True)
    logger.add(
        log_dir / "bdd-vision.log",
        rotation="10 MB",
        retention="30 days",
        level="DEBUG",
        format="{time:YYYY-MM-DD HH:mm:ss} | {level:<8} | {name}:{line} | {message}",
    )


@click.group()
def cli():
    """bdd-vision — AI-powered BDD testing via vision-language models."""


# ── init ─────────────────────────────────────────────────────────────────────

@cli.command()
@click.option("--url", required=True, help="Target website URL")
@click.option("--name", required=True, help="Project slug (used as directory name)")
def init(url: str, name: str):
    """Initialize a new bdd-vision project."""
    settings = Settings()
    _setup_logging(settings)

    project_dir = settings.data_dir / name
    if project_dir.exists():
        console.print(
            f"[yellow]Project '{name}' already exists at {project_dir}[/yellow]"
        )
        return

    # Create project directory structure
    for subdir in ("specs", "sitemaps", "sessions", "screenshots", "reports"):
        (project_dir / subdir).mkdir(parents=True, exist_ok=True)

    # Save project config
    config = {
        "name": name,
        "url": url,
        "created_at": datetime.now().isoformat(),
        "spec_version": 0,
    }
    config_path = project_dir / "project.json"
    # Atomic write: temp file then rename
    tmp = config_path.with_suffix(".tmp")
    tmp.write_text(json.dumps(config, indent=2))
    tmp.rename(config_path)

    console.print(f"[green]Project '{name}' initialized[/green]")
    console.print(f"  URL:    {url}")
    console.print(f"  Data:   {project_dir}")
    console.print(f"  Config: {config_path}")

    if click.confirm(
        "\nRun a VLM smoke test? (Chrome + API keys required)", default=False
    ):
        asyncio.run(_smoke_test(settings, project_dir, url))


# ── list ─────────────────────────────────────────────────────────────────────

@cli.command(name="list")
def list_projects():
    """List all bdd-vision projects."""
    settings = Settings()
    data_dir = settings.data_dir

    if not data_dir.exists():
        console.print("No projects found.")
        return

    projects = sorted(
        d for d in data_dir.iterdir()
        if d.is_dir() and (d / "project.json").exists()
    )

    if not projects:
        console.print("No projects found.")
        return

    table = Table(title="bdd-vision Projects")
    table.add_column("Name", style="cyan")
    table.add_column("URL")
    table.add_column("Created")

    for p in projects:
        cfg = json.loads((p / "project.json").read_text())
        table.add_row(cfg["name"], cfg["url"], cfg["created_at"][:10])

    console.print(table)


# ── crawl ─────────────────────────────────────────────────────────────────────

@cli.command()
@click.argument("name")
@click.option("--max-pages", default=None, type=int, help="Override max pages setting")
@click.option("--max-depth", default=None, type=int, help="Override max depth setting")
def crawl(name: str, max_pages: int | None, max_depth: int | None):
    """Crawl a project's URL and build a sitemap."""
    settings = Settings()
    _setup_logging(settings)

    project_dir = settings.data_dir / name
    if not project_dir.exists() or not (project_dir / "project.json").exists():
        console.print(f"[red]Project '{name}' not found. Run `bdd-vision init` first.[/red]")
        return

    cfg = json.loads((project_dir / "project.json").read_text())
    url = cfg["url"]

    if max_pages is not None:
        settings.max_pages = max_pages
    if max_depth is not None:
        settings.max_depth = max_depth

    console.print(
        f"[bold]Crawling[/bold] {url} "
        f"(max_pages={settings.max_pages}, max_depth={settings.max_depth})"
    )

    engine = CrawlEngine(settings)
    try:
        sitemap = asyncio.run(engine.crawl(name, url))
    except Exception as e:
        console.print(f"[red]✗ Crawl failed: {e}[/red]")
        logger.exception("Crawl error")
        return

    console.print(f"\n[green]✓ Crawled {sitemap['total_pages']} page(s)[/green]")
    console.print(f"  Cost   : ${sitemap['total_cost_usd']:.4f}")
    console.print(f"  Tokens : {sitemap['total_tokens']}")

    # Print page summary table
    table = Table(title="Crawl Summary")
    table.add_column("Depth", style="dim", width=5)
    table.add_column("URL")
    table.add_column("Title")
    table.add_column("Links", width=6)

    for page in sitemap["pages"]:
        table.add_row(
            str(page["depth"]),
            page["url"],
            page.get("title") or "",
            str(len(page.get("links_found", []))),
        )

    console.print(table)




# ── Smoke test (Phase 1 validation) ─────────────────────────────────────────

async def _smoke_test(settings: Settings, project_dir: Path, url: str):
    """
    Phase 1 validation:
      1. Connect to Chrome (auto-launch if needed)
      2. Navigate to the project URL
      3. Capture a screenshot
      4. Send to VLM and get a description
    """
    console.print("\n[bold]Running smoke test...[/bold]")

    cdp = CDPClient(port=settings.chrome_cdp_port)

    # Step 1 — Chrome
    try:
        await cdp.connect()
        console.print("[green]✓ Chrome connected[/green]")
    except Exception as e:
        console.print(f"[red]✗ Chrome connection failed: {e}[/red]")
        return

    # Step 2 — Navigate
    try:
        await cdp.navigate(url)
        current_url = await cdp.get_current_url()
        console.print(f"[green]✓ Navigated to {current_url or url}[/green]")
    except Exception as e:
        console.print(f"[yellow]  Navigation warning: {e}[/yellow]")

    # Step 3 — Screenshot
    capture = ScreenCapture(project_dir / "screenshots")
    img, path = capture.capture("smoke_test")
    if str(path) == "/dev/null":
        console.print("[red]✗ Screenshot capture failed[/red]")
        await cdp.disconnect()
        return
    console.print(f"[green]✓ Screenshot captured[/green]  {path}")

    # Step 4 — VLM
    router = ModelRouter(settings)
    try:
        response = await router.analyze(
            img, "Describe what you see on this page in one sentence."
        )
        console.print("\n[bold]VLM response:[/bold]")
        console.print(f"  Observation : {response.observation}")
        console.print(f"  Confidence  : {response.confidence:.2f}")
        console.print(f"  Session cost: ${router.session_cost:.4f}")
        console.print("\n[green]✓ Smoke test passed — Phase 1 ready[/green]")
    except (CostLimitExceeded, AllProvidersFailed) as e:
        console.print(f"[red]✗ VLM analysis failed: {e}[/red]")
    except Exception as e:
        console.print(f"[red]✗ Unexpected error: {e}[/red]")
        logger.exception("Smoke test error")

    await cdp.disconnect()


# ── spec ──────────────────────────────────────────────────────────────────────

@cli.group()
def spec():
    """Manage BDD specifications for a project."""


@spec.command(name="generate")
@click.argument("name")
def spec_generate(name: str):
    """Interview + VLM to generate a BDD spec from a crawled sitemap."""
    settings = Settings()
    _setup_logging(settings)

    project_dir = settings.data_dir / name
    if not project_dir.exists() or not (project_dir / "project.json").exists():
        console.print(f"[red]Project '{name}' not found. Run `bdd-vision init` first.[/red]")
        return

    engine = SpecEngine(settings)
    try:
        spec_doc = asyncio.run(engine.generate(name))
    except RuntimeError as e:
        console.print(f"[red]✗ {e}[/red]")
        return
    except Exception as e:
        console.print(f"[red]✗ Spec generation failed: {e}[/red]")
        logger.exception("Spec generation error")
        return

    console.print(f"\n[green]✓ Spec v{spec_doc['version']} generated[/green]")
    console.print(f"  Scenarios : {spec_doc['total_scenarios']}")
    console.print(f"  Steps     : {spec_doc['total_steps']}")
    console.print(f"  Cost      : ${spec_doc['cost_usd']:.4f}")
    _print_spec_summary(spec_doc)


@spec.command(name="edit")
@click.argument("name")
def spec_edit(name: str):
    """Re-generate spec for a project (preserves previous versions)."""
    settings = Settings()
    _setup_logging(settings)

    project_dir = settings.data_dir / name
    if not project_dir.exists() or not (project_dir / "project.json").exists():
        console.print(f"[red]Project '{name}' not found.[/red]")
        return

    engine = SpecEngine(settings)
    try:
        spec_doc = asyncio.run(engine.edit(name))
    except Exception as e:
        console.print(f"[red]✗ {e}[/red]")
        logger.exception("Spec edit error")
        return

    console.print(f"\n[green]✓ Spec v{spec_doc['version']} ready[/green]")


@spec.command(name="show")
@click.argument("name")
def spec_show(name: str):
    """Display the current spec for a project."""
    settings = Settings()
    project_dir = settings.data_dir / name
    specs_dir = project_dir / "specs"

    if not specs_dir.exists():
        console.print(f"[yellow]No specs for '{name}'. Run `bdd-vision spec generate`.[/yellow]")
        return

    files = sorted(specs_dir.glob("spec_v*.json"))
    if not files:
        console.print(f"[yellow]No specs for '{name}'.[/yellow]")
        return

    spec_doc = json.loads(files[-1].read_text())
    console.print(
        f"\n[bold]Spec v{spec_doc['version']}[/bold]  —  "
        f"{spec_doc['project']}  ({spec_doc['created_at'][:10]})"
    )
    console.print(f"Brief: {spec_doc['brief']}\n")
    _print_spec_summary(spec_doc)


def _print_spec_summary(spec_doc: dict):
    for feature in spec_doc.get("features", []):
        console.print(f"[bold cyan]Feature: {feature['name']}[/bold cyan]")
        if feature.get("description"):
            console.print(f"  {feature['description']}")
        table = Table(show_header=True, header_style="bold")
        table.add_column("Scenario")
        table.add_column("Steps", width=6)
        for scenario in feature.get("scenarios", []):
            table.add_row(scenario["name"], str(len(scenario.get("steps", []))))
        console.print(table)
        console.print()


# ── run ───────────────────────────────────────────────────────────────────────

@cli.command(name="run")
@click.argument("name")
@click.option("--scenario", default=None, help="Filter: run only scenarios whose name contains this string")
@click.option("--spec", "spec_file", default=None, help="Specific spec file (default: latest)")
def run_tests(name: str, scenario: str | None, spec_file: str | None):
    """Run BDD scenarios against a project using the VLM agent."""
    settings = Settings()
    _setup_logging(settings)

    project_dir = settings.data_dir / name
    if not project_dir.exists() or not (project_dir / "project.json").exists():
        console.print(f"[red]Project '{name}' not found.[/red]")
        return

    specs_dir = project_dir / "specs"
    if spec_file:
        spec_path = Path(spec_file)
    else:
        files = sorted(specs_dir.glob("spec_v*.json")) if specs_dir.exists() else []
        if not files:
            console.print(f"[red]No specs for '{name}'. Run `bdd-vision spec generate` first.[/red]")
            return
        spec_path = files[-1]

    console.print(f"[bold]Running spec:[/bold] {spec_path.name}")
    if scenario:
        console.print(f"  Filter: '{scenario}'")

    from ..core.agent_runner import AgentRunner
    runner = AgentRunner(settings)
    try:
        result = asyncio.run(runner.run(name, spec_path, scenario))
    except Exception as e:
        console.print(f"[red]✗ Test run failed: {e}[/red]")
        logger.exception("Run error")
        return

    # Summary
    total = result.passed + result.failed + result.skipped
    pass_color = "green" if result.failed == 0 else "red"
    console.print(f"\n[bold]Results[/bold]  session={result.session_id}")
    console.print(f"  [{pass_color}]Passed : {result.passed}/{total}[/{pass_color}]")
    console.print(f"  Failed : {result.failed}")
    console.print(f"  Skipped: {result.skipped}")
    console.print(f"  Steps  : {result.total_steps}")
    console.print(f"  Cost   : ${result.total_cost_usd:.4f}")

    table = Table(title="Scenario Results")
    table.add_column("Scenario")
    table.add_column("Status", width=8)
    table.add_column("Steps", width=6)
    table.add_column("Cost", width=8)

    status_colors = {"pass": "green", "fail": "red", "partial": "yellow", "skip": "dim"}
    for r in result.scenarios:
        color = status_colors.get(r.status, "white")
        table.add_row(
            r.scenario_name,
            f"[{color}]{r.status}[/{color}]",
            str(len(r.steps)),
            f"${r.total_cost_usd:.4f}",
        )

    console.print(table)
