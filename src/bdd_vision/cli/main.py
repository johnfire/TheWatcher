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
