import json
import pytest
from datetime import datetime
from pathlib import Path
from unittest.mock import patch

from bdd_vision.core.agent_runner import ScenarioResult, SessionResult, StepResult
from bdd_vision.core.reporter import Reporter, _md_report


def _step(n: int, status="pass", confidence=0.9, deviation=None) -> StepResult:
    return StepResult(
        step_number=n,
        step_text=f"Given step {n}",
        status=status,
        confidence=confidence,
        action_taken="observe",
        coordinates_used=None,
        before_screenshot=Path("/dev/null"),
        after_screenshot=Path("/dev/null"),
        vlm_observation="looks good",
        expected_outcome=f"step {n}",
        actual_outcome="ok",
        deviation_description=deviation,
        tokens_used=100,
        cost_usd=0.001,
        duration_seconds=0.5,
        error=None,
    )


def _scenario(name="Login", status="pass", steps=None) -> ScenarioResult:
    if steps is None:
        steps = [_step(1), _step(2)]
    return ScenarioResult(
        scenario_name=name,
        status=status,
        steps=steps,
        total_cost_usd=0.002,
        duration_seconds=1.2,
    )


def _session(scenarios=None) -> SessionResult:
    if scenarios is None:
        scenarios = [_scenario()]
    return SessionResult(
        session_id="abc12345",
        project="myproject",
        spec_version="1",
        started_at=datetime(2026, 3, 7, 10, 0, 0),
        completed_at=datetime(2026, 3, 7, 10, 1, 0),
        scenarios=scenarios,
        total_steps=sum(len(s.steps) for s in scenarios),
        passed=sum(1 for s in scenarios if s.status == "pass"),
        failed=sum(1 for s in scenarios if s.status == "fail"),
        skipped=sum(1 for s in scenarios if s.status == "skip"),
        total_cost_usd=0.01,
        total_tokens=500,
        model_used="deepseek/deepseek-vl2",
    )


# ── Markdown ─────────────────────────────────────────────────────────────────

def test_markdown_contains_project_name():
    result = _session()
    lines = _md_report(result)
    text = "\n".join(lines)
    assert "myproject" in text


def test_markdown_contains_session_id():
    result = _session()
    lines = _md_report(result)
    text = "\n".join(lines)
    assert "abc12345" in text


def test_markdown_contains_scenario_name():
    result = _session([_scenario("User Login")])
    lines = _md_report(result)
    text = "\n".join(lines)
    assert "User Login" in text


def test_markdown_summary_counts():
    result = _session([_scenario(status="pass"), _scenario(name="B", status="fail")])
    result = SessionResult(
        **{**result.__dict__, "passed": 1, "failed": 1, "skipped": 0}
    )
    lines = _md_report(result)
    text = "\n".join(lines)
    assert "| 2 |" in text  # total scenarios


def test_markdown_includes_deviation():
    step_with_dev = _step(1, status="fail", deviation="Button not found on page")
    result = _session([_scenario(steps=[step_with_dev])])
    lines = _md_report(result)
    text = "\n".join(lines)
    assert "Button not found on page" in text


def test_markdown_saved_to_file(tmp_path):
    result = _session()
    reporter = Reporter()
    path = reporter.generate_markdown(result, tmp_path / "reports")
    assert path.exists()
    assert path.suffix == ".md"
    content = path.read_text()
    assert "myproject" in content


def test_markdown_atomic_write(tmp_path):
    """No .tmp file should linger after generation."""
    result = _session()
    reporter = Reporter()
    reporter.generate_markdown(result, tmp_path / "reports")
    tmp_files = list((tmp_path / "reports").glob("*.tmp"))
    assert tmp_files == []


def test_markdown_filename_contains_session_id(tmp_path):
    result = _session()
    reporter = Reporter()
    path = reporter.generate_markdown(result, tmp_path / "reports")
    assert "abc12345" in path.name


# ── PDF ───────────────────────────────────────────────────────────────────────

def test_pdf_saved_to_file(tmp_path):
    result = _session()
    reporter = Reporter()
    path = reporter.generate_pdf(result, tmp_path / "reports")
    assert path.exists()
    assert path.suffix == ".pdf"
    # PDF starts with %PDF
    assert path.read_bytes()[:4] == b"%PDF"


def test_pdf_filename_contains_session_id(tmp_path):
    result = _session()
    reporter = Reporter()
    path = reporter.generate_pdf(result, tmp_path / "reports")
    assert "abc12345" in path.name


def test_pdf_with_failed_steps(tmp_path):
    result = _session([
        _scenario("Login", status="fail", steps=[
            _step(1, status="pass"),
            _step(2, status="fail", deviation="Expected modal, got nothing"),
        ])
    ])
    reporter = Reporter()
    path = reporter.generate_pdf(result, tmp_path / "reports")
    assert path.exists()
    assert path.stat().st_size > 0


def test_pdf_creates_output_dir(tmp_path):
    result = _session()
    reporter = Reporter()
    output = tmp_path / "deep" / "nested" / "reports"
    path = reporter.generate_pdf(result, output)
    assert output.exists()
    assert path.exists()
