import json
import pytest
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

from PIL import Image

from bdd_vision.core.crawl_engine import CrawlEngine, _resolve_url
from bdd_vision.models.base import CrawlPageResult


def _blank_image() -> Image.Image:
    return Image.new("RGB", (100, 100), color=(200, 200, 200))


def _mock_crawl_result(**kwargs) -> CrawlPageResult:
    defaults = dict(
        page_description="A test page",
        elements=[{"type": "button", "label": "Submit", "approximate_location": "mid-center", "purpose": "submit form"}],
        navigation_links=[],
        notes=[],
        tokens_used=200,
        cost_usd=0.002,
    )
    defaults.update(kwargs)
    return CrawlPageResult(**defaults)


# ── _resolve_url ────────────────────────────────────────────────────────────

def test_resolve_relative_path():
    result = _resolve_url("https://example.com", "/about", "example.com")
    assert result == "https://example.com/about"


def test_resolve_absolute_same_domain():
    result = _resolve_url("https://example.com", "https://example.com/contact", "example.com")
    assert result == "https://example.com/contact"


def test_resolve_external_link_returns_none():
    result = _resolve_url("https://example.com", "https://other.com/page", "example.com")
    assert result is None


def test_resolve_anchor_returns_none():
    result = _resolve_url("https://example.com", "#section", "example.com")
    assert result is None


def test_resolve_mailto_returns_none():
    result = _resolve_url("https://example.com", "mailto:test@example.com", "example.com")
    assert result is None


def test_resolve_empty_path_returns_none():
    result = _resolve_url("https://example.com", "", "example.com")
    assert result is None


def test_resolve_strips_trailing_slash():
    result = _resolve_url("https://example.com", "/about/", "example.com")
    assert result == "https://example.com/about"


# ── CrawlEngine ──────────────────────────────────────────────────────────────

@pytest.fixture
def mock_cdp():
    cdp = AsyncMock()
    cdp.connect = AsyncMock()
    cdp.disconnect = AsyncMock()
    cdp.navigate = AsyncMock()
    cdp.get_page_title = AsyncMock(return_value="Test Page")
    cdp.get_current_url = AsyncMock(return_value="https://example.com")
    return cdp


@pytest.fixture
def mock_capture(tmp_path):
    capture = MagicMock()
    img = _blank_image()
    screenshot_path = tmp_path / "shot.png"
    img.save(screenshot_path)
    capture.capture = MagicMock(return_value=(img, screenshot_path))
    return capture


@pytest.mark.asyncio
async def test_crawl_single_page(settings, tmp_path, mock_cdp, mock_capture):
    settings.data_dir = tmp_path / "data"
    project_dir = settings.data_dir / "myproject"
    (project_dir / "sitemaps").mkdir(parents=True, exist_ok=True)
    (project_dir / "screenshots" / "crawl").mkdir(parents=True, exist_ok=True)

    mock_result = _mock_crawl_result(navigation_links=[])

    with (
        patch("bdd_vision.core.crawl_engine.CDPClient", return_value=mock_cdp),
        patch("bdd_vision.core.crawl_engine.ScreenCapture", return_value=mock_capture),
        patch("bdd_vision.core.crawl_engine.ModelRouter") as MockRouter,
    ):
        router_instance = MockRouter.return_value
        router_instance.analyze_page = AsyncMock(return_value=mock_result)
        router_instance.session_cost = 0.002
        router_instance.session_tokens = 200

        engine = CrawlEngine(settings)
        sitemap = await engine.crawl("myproject", "https://example.com")

    assert sitemap["total_pages"] == 1
    assert sitemap["pages"][0]["url"] == "https://example.com"
    assert sitemap["pages"][0]["description"] == "A test page"
    mock_cdp.navigate.assert_called_once_with("https://example.com")


@pytest.mark.asyncio
async def test_crawl_follows_links(settings, tmp_path, mock_cdp, mock_capture):
    settings.data_dir = tmp_path / "data"
    settings.max_pages = 5
    settings.max_depth = 2
    project_dir = settings.data_dir / "myproject"
    (project_dir / "sitemaps").mkdir(parents=True, exist_ok=True)
    (project_dir / "screenshots" / "crawl").mkdir(parents=True, exist_ok=True)

    # First call returns a link to /about, subsequent calls return no links
    home_result = _mock_crawl_result(
        navigation_links=[{"label": "About", "inferred_path": "/about", "purpose": "about page"}]
    )
    about_result = _mock_crawl_result(navigation_links=[])

    mock_cdp.get_current_url = AsyncMock(side_effect=[
        "https://example.com",
        "https://example.com/about",
    ])
    mock_cdp.get_page_title = AsyncMock(side_effect=["Home", "About"])

    with (
        patch("bdd_vision.core.crawl_engine.CDPClient", return_value=mock_cdp),
        patch("bdd_vision.core.crawl_engine.ScreenCapture", return_value=mock_capture),
        patch("bdd_vision.core.crawl_engine.ModelRouter") as MockRouter,
    ):
        router_instance = MockRouter.return_value
        router_instance.analyze_page = AsyncMock(side_effect=[home_result, about_result])
        router_instance.session_cost = 0.004
        router_instance.session_tokens = 400

        engine = CrawlEngine(settings)
        sitemap = await engine.crawl("myproject", "https://example.com")

    assert sitemap["total_pages"] == 2
    urls = [p["url"] for p in sitemap["pages"]]
    assert "https://example.com" in urls
    assert "https://example.com/about" in urls


@pytest.mark.asyncio
async def test_crawl_deduplicates_urls(settings, tmp_path, mock_cdp, mock_capture):
    settings.data_dir = tmp_path / "data"
    settings.max_pages = 10
    project_dir = settings.data_dir / "myproject"
    (project_dir / "sitemaps").mkdir(parents=True, exist_ok=True)
    (project_dir / "screenshots" / "crawl").mkdir(parents=True, exist_ok=True)

    # Two links pointing to the same URL
    home_result = _mock_crawl_result(
        navigation_links=[
            {"label": "About", "inferred_path": "/about", "purpose": ""},
            {"label": "About again", "inferred_path": "/about", "purpose": ""},
        ]
    )
    about_result = _mock_crawl_result(navigation_links=[])

    mock_cdp.get_current_url = AsyncMock(side_effect=[
        "https://example.com",
        "https://example.com/about",
    ])

    with (
        patch("bdd_vision.core.crawl_engine.CDPClient", return_value=mock_cdp),
        patch("bdd_vision.core.crawl_engine.ScreenCapture", return_value=mock_capture),
        patch("bdd_vision.core.crawl_engine.ModelRouter") as MockRouter,
    ):
        router_instance = MockRouter.return_value
        router_instance.analyze_page = AsyncMock(side_effect=[home_result, about_result])
        router_instance.session_cost = 0.004
        router_instance.session_tokens = 400

        engine = CrawlEngine(settings)
        sitemap = await engine.crawl("myproject", "https://example.com")

    # /about should only be visited once
    assert sitemap["total_pages"] == 2


@pytest.mark.asyncio
async def test_crawl_respects_max_pages(settings, tmp_path, mock_cdp, mock_capture):
    settings.data_dir = tmp_path / "data"
    settings.max_pages = 1
    project_dir = settings.data_dir / "myproject"
    (project_dir / "sitemaps").mkdir(parents=True, exist_ok=True)
    (project_dir / "screenshots" / "crawl").mkdir(parents=True, exist_ok=True)

    home_result = _mock_crawl_result(
        navigation_links=[{"label": "About", "inferred_path": "/about", "purpose": ""}]
    )

    with (
        patch("bdd_vision.core.crawl_engine.CDPClient", return_value=mock_cdp),
        patch("bdd_vision.core.crawl_engine.ScreenCapture", return_value=mock_capture),
        patch("bdd_vision.core.crawl_engine.ModelRouter") as MockRouter,
    ):
        router_instance = MockRouter.return_value
        router_instance.analyze_page = AsyncMock(return_value=home_result)
        router_instance.session_cost = 0.002
        router_instance.session_tokens = 200

        engine = CrawlEngine(settings)
        sitemap = await engine.crawl("myproject", "https://example.com")

    assert sitemap["total_pages"] == 1


@pytest.mark.asyncio
async def test_crawl_saves_sitemap_json(settings, tmp_path, mock_cdp, mock_capture):
    settings.data_dir = tmp_path / "data"
    project_dir = settings.data_dir / "myproject"
    (project_dir / "sitemaps").mkdir(parents=True, exist_ok=True)
    (project_dir / "screenshots" / "crawl").mkdir(parents=True, exist_ok=True)

    mock_result = _mock_crawl_result()

    with (
        patch("bdd_vision.core.crawl_engine.CDPClient", return_value=mock_cdp),
        patch("bdd_vision.core.crawl_engine.ScreenCapture", return_value=mock_capture),
        patch("bdd_vision.core.crawl_engine.ModelRouter") as MockRouter,
    ):
        router_instance = MockRouter.return_value
        router_instance.analyze_page = AsyncMock(return_value=mock_result)
        router_instance.session_cost = 0.002
        router_instance.session_tokens = 200

        engine = CrawlEngine(settings)
        await engine.crawl("myproject", "https://example.com")

    sitemaps = list((project_dir / "sitemaps").glob("sitemap_*.json"))
    assert len(sitemaps) == 1
    data = json.loads(sitemaps[0].read_text())
    assert data["project"] == "myproject"
    assert data["base_url"] == "https://example.com"
    assert "crawled_at" in data


@pytest.mark.asyncio
async def test_crawl_page_failure_is_skipped(settings, tmp_path, mock_cdp, mock_capture):
    settings.data_dir = tmp_path / "data"
    settings.max_pages = 5
    project_dir = settings.data_dir / "myproject"
    (project_dir / "sitemaps").mkdir(parents=True, exist_ok=True)
    (project_dir / "screenshots" / "crawl").mkdir(parents=True, exist_ok=True)

    # First page raises, second succeeds
    good_result = _mock_crawl_result(navigation_links=[])
    mock_cdp.get_current_url = AsyncMock(side_effect=[
        "https://example.com",
        "https://example.com/about",
    ])

    with (
        patch("bdd_vision.core.crawl_engine.CDPClient", return_value=mock_cdp),
        patch("bdd_vision.core.crawl_engine.ScreenCapture", return_value=mock_capture),
        patch("bdd_vision.core.crawl_engine.ModelRouter") as MockRouter,
    ):
        router_instance = MockRouter.return_value
        router_instance.analyze_page = AsyncMock(
            side_effect=[RuntimeError("VLM exploded"), good_result]
        )
        router_instance.session_cost = 0.002
        router_instance.session_tokens = 200

        # Pre-populate queue with two URLs
        engine = CrawlEngine(settings)
        # Patch queue to start with two URLs
        with patch("bdd_vision.core.crawl_engine.deque") as mock_deque:
            from collections import deque as real_deque
            mock_deque.return_value = real_deque([
                ("https://example.com", 0),
                ("https://example.com/about", 0),
            ])
            sitemap = await engine.crawl("myproject", "https://example.com")

    # First page failed (skipped), second succeeded
    assert sitemap["total_pages"] == 1
