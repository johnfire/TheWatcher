"""
Reporter — Markdown and PDF report generator.
Produces human-readable reports from SessionResult data.

Phase 5 implementation.
"""

from datetime import datetime
from pathlib import Path

from loguru import logger

from .agent_runner import ScenarioResult, SessionResult, StepResult

_STATUS_EMOJI = {"pass": "✅", "fail": "❌", "partial": "⚠️", "skip": "⏭️"}
_STATUS_ICON = {"pass": "PASS", "fail": "FAIL", "partial": "PARTIAL", "skip": "SKIP"}


class Reporter:
    def generate_markdown(self, result: SessionResult, output_dir: Path) -> Path:
        output_dir.mkdir(parents=True, exist_ok=True)
        path = output_dir / f"report_{result.session_id}.md"

        lines = _md_report(result)
        tmp = path.with_suffix(".tmp")
        tmp.write_text("\n".join(lines), encoding="utf-8")
        tmp.rename(path)
        logger.info(f"Markdown report saved: {path}")
        return path

    def generate_pdf(self, result: SessionResult, output_dir: Path) -> Path:
        output_dir.mkdir(parents=True, exist_ok=True)
        path = output_dir / f"report_{result.session_id}.pdf"

        from reportlab.lib import colors
        from reportlab.lib.pagesizes import A4
        from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
        from reportlab.lib.units import cm
        from reportlab.platypus import (
            HRFlowable,
            Paragraph,
            SimpleDocTemplate,
            Spacer,
            Table,
            TableStyle,
        )

        styles = getSampleStyleSheet()
        h1 = styles["Heading1"]
        h2 = styles["Heading2"]
        h3 = styles["Heading3"]
        normal = styles["Normal"]
        code = ParagraphStyle(
            "code",
            parent=normal,
            fontName="Courier",
            fontSize=8,
            leftIndent=12,
        )

        doc = SimpleDocTemplate(str(path), pagesize=A4, topMargin=2 * cm, bottomMargin=2 * cm)
        story = []

        # Title
        story.append(Paragraph(f"BDD Test Report — {result.project}", h1))
        story.append(Paragraph(
            f"Session: {result.session_id}  |  Spec v{result.spec_version}  |  "
            f"Model: {result.model_used}",
            normal,
        ))
        story.append(Paragraph(
            f"Started: {result.started_at.strftime('%Y-%m-%d %H:%M:%S')}  |  "
            f"Completed: {result.completed_at.strftime('%Y-%m-%d %H:%M:%S')}",
            normal,
        ))
        story.append(Spacer(1, 0.4 * cm))
        story.append(HRFlowable(width="100%"))
        story.append(Spacer(1, 0.4 * cm))

        # Summary table
        total = result.passed + result.failed + result.skipped
        summary_data = [
            ["Scenarios", "Passed", "Failed", "Skipped", "Steps", "Cost"],
            [
                str(total),
                str(result.passed),
                str(result.failed),
                str(result.skipped),
                str(result.total_steps),
                f"${result.total_cost_usd:.4f}",
            ],
        ]
        summary_table = Table(summary_data, hAlign="LEFT")
        summary_table.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#2c3e50")),
            ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
            ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
            ("GRID", (0, 0), (-1, -1), 0.5, colors.grey),
            ("ALIGN", (0, 0), (-1, -1), "CENTER"),
            ("BACKGROUND", (1, 1), (1, 1), colors.HexColor("#27ae60")),  # passed green
            ("BACKGROUND", (2, 1), (2, 1), colors.HexColor("#e74c3c") if result.failed else colors.HexColor("#27ae60")),
            ("TEXTCOLOR", (1, 1), (2, 1), colors.white),
        ]))
        story.append(summary_table)
        story.append(Spacer(1, 0.6 * cm))

        # Scenarios
        for scenario in result.scenarios:
            icon = _STATUS_ICON[scenario.status]
            story.append(Paragraph(f"[{icon}] {scenario.scenario_name}", h2))
            story.append(Paragraph(
                f"Duration: {scenario.duration_seconds:.1f}s  |  "
                f"Cost: ${scenario.total_cost_usd:.4f}",
                normal,
            ))
            story.append(Spacer(1, 0.2 * cm))

            # Steps table
            step_data = [["#", "Step", "Status", "Confidence", "Action"]]
            for s in scenario.steps:
                step_data.append([
                    str(s.step_number),
                    s.step_text[:70] + ("…" if len(s.step_text) > 70 else ""),
                    _STATUS_ICON[s.status],
                    f"{s.confidence:.2f}",
                    s.action_taken,
                ])

            step_table = Table(step_data, colWidths=[1 * cm, 9 * cm, 2 * cm, 2 * cm, 2.5 * cm])
            step_table.setStyle(TableStyle([
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#34495e")),
                ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                ("FONTSIZE", (0, 0), (-1, -1), 8),
                ("GRID", (0, 0), (-1, -1), 0.3, colors.lightgrey),
                ("ALIGN", (2, 0), (-1, -1), "CENTER"),
                *[
                    ("BACKGROUND", (2, i + 1), (2, i + 1),
                     colors.HexColor("#27ae60") if step_data[i + 1][2] == "PASS"
                     else colors.HexColor("#e74c3c") if step_data[i + 1][2] == "FAIL"
                     else colors.HexColor("#f39c12"))
                    for i in range(len(scenario.steps))
                ],
                *[
                    ("TEXTCOLOR", (2, i + 1), (2, i + 1), colors.white)
                    for i in range(len(scenario.steps))
                ],
            ]))
            story.append(step_table)

            # Deviations
            for s in scenario.steps:
                if s.deviation_description:
                    story.append(Spacer(1, 0.2 * cm))
                    story.append(Paragraph(f"Step {s.step_number} deviation:", h3))
                    story.append(Paragraph(s.deviation_description[:500], code))

            story.append(Spacer(1, 0.5 * cm))

        doc.build(story)
        logger.info(f"PDF report saved: {path}")
        return path


# ── Markdown builder ──────────────────────────────────────────────────────────

def _md_report(result: SessionResult) -> list[str]:
    total = result.passed + result.failed + result.skipped
    lines = [
        f"# BDD Test Report — {result.project}",
        "",
        f"| Field | Value |",
        f"|-------|-------|",
        f"| Session | `{result.session_id}` |",
        f"| Spec version | {result.spec_version} |",
        f"| Model | {result.model_used} |",
        f"| Started | {result.started_at.strftime('%Y-%m-%d %H:%M:%S')} |",
        f"| Completed | {result.completed_at.strftime('%Y-%m-%d %H:%M:%S')} |",
        f"| Duration | {(result.completed_at - result.started_at).seconds}s |",
        f"| Total cost | ${result.total_cost_usd:.4f} |",
        f"| Total tokens | {result.total_tokens} |",
        "",
        "## Summary",
        "",
        f"| Scenarios | Passed | Failed | Skipped | Steps |",
        f"|-----------|--------|--------|---------|-------|",
        f"| {total} | {result.passed} | {result.failed} | {result.skipped} | {result.total_steps} |",
        "",
    ]

    for scenario in result.scenarios:
        icon = _STATUS_EMOJI[scenario.status]
        lines += [
            f"## {icon} {scenario.scenario_name}",
            "",
            f"**Status:** {scenario.status.upper()}  |  "
            f"**Duration:** {scenario.duration_seconds:.1f}s  |  "
            f"**Cost:** ${scenario.total_cost_usd:.4f}",
            "",
            "| # | Step | Status | Confidence | Action |",
            "|---|------|--------|------------|--------|",
        ]
        for s in scenario.steps:
            icon_s = _STATUS_EMOJI[s.status]
            lines.append(
                f"| {s.step_number} | {s.step_text} | {icon_s} {s.status} "
                f"| {s.confidence:.2f} | {s.action_taken} |"
            )

        # Deviations
        deviations = [s for s in scenario.steps if s.deviation_description]
        if deviations:
            lines += ["", "**Deviations:**", ""]
            for s in deviations:
                lines += [
                    f"- **Step {s.step_number}** ({s.step_text})",
                    f"  ```",
                    f"  {s.deviation_description}",
                    f"  ```",
                ]

        lines.append("")

    return lines
