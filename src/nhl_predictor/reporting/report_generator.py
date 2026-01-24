"""Daily Report Generator.

Creates formatted output for daily picks in multiple formats.
"""

import json
import logging
from dataclasses import dataclass, asdict
from datetime import date, datetime
from pathlib import Path
from typing import Optional

from ..selection.selector import DailyPicks, FinalPick

logger = logging.getLogger(__name__)


@dataclass
class PickReport:
    """Formatted pick report for output."""

    rank: int
    tier: str
    matchup: str
    pick: str
    confidence: str
    edge: str
    rationale: str
    risk: str
    game_time: str
    goalie_status: str


@dataclass
class DailyReport:
    """Complete daily report."""

    date: str
    generated_at: str
    picks: list[PickReport]
    summary: dict
    model_health: dict
    notes: list[str]


class ReportGenerator:
    """Generates formatted daily reports."""

    # Risk level mappings
    RISK_LABELS = {
        "low": "LOW",
        "medium": "MEDIUM",
        "high": "HIGH",
        "unknown": "UNKNOWN",
    }

    def __init__(self, output_dir: Optional[str] = None):
        """
        Initialize report generator.

        Args:
            output_dir: Directory for saving report files.
        """
        self.output_dir = Path(output_dir) if output_dir else Path("./reports")
        self.output_dir.mkdir(parents=True, exist_ok=True)

    def generate_report(
        self,
        daily_picks: DailyPicks,
        rationales: Optional[dict] = None,
    ) -> DailyReport:
        """
        Generate formatted report from daily picks.

        Args:
            daily_picks: DailyPicks from selector.
            rationales: Optional dict mapping game_id to rationale text.

        Returns:
            DailyReport object.
        """
        pick_reports = []

        for pick in daily_picks.picks:
            rationale = ""
            if rationales and pick.game_id in rationales:
                rationale = rationales[pick.game_id]

            pick_reports.append(PickReport(
                rank=pick.rank,
                tier=pick.tier,
                matchup=f"{pick.away_team} @ {pick.home_team}",
                pick=pick.pick_team,
                confidence=f"{pick.model_probability:.1%}",
                edge=f"+{pick.edge:.1%}",
                rationale=rationale,
                risk=self.RISK_LABELS.get(pick.risk_level, "UNKNOWN"),
                game_time=pick.start_time or "TBD",
                goalie_status=self._format_goalie_status(pick),
            ))

        summary = self._generate_summary(daily_picks)
        model_health = {
            "accuracy_7d": f"{daily_picks.model_accuracy_7d:.1%}",
            "accuracy_30d": f"{daily_picks.model_accuracy_30d:.1%}",
        }

        return DailyReport(
            date=daily_picks.date.strftime("%A, %B %d, %Y"),
            generated_at=daily_picks.generated_at.strftime("%Y-%m-%d %H:%M:%S"),
            picks=pick_reports,
            summary=summary,
            model_health=model_health,
            notes=daily_picks.notes,
        )

    def _format_goalie_status(self, pick: FinalPick) -> str:
        """Format goalie status string."""
        if pick.goalie_name:
            status = "Confirmed" if pick.goalie_confirmed else "Expected"
            return f"{pick.goalie_name} ({status})"
        return "TBD"

    def _generate_summary(self, daily_picks: DailyPicks) -> dict:
        """Generate summary statistics."""
        if not daily_picks.picks:
            return {
                "total_picks": 0,
                "avg_confidence": "N/A",
                "avg_edge": "N/A",
                "confidence_level": "No picks available",
            }

        picks = daily_picks.picks
        avg_conf = sum(p.model_probability for p in picks) / len(picks)
        avg_edge = sum(p.edge for p in picks) / len(picks)

        # Determine overall confidence level
        lock_count = sum(1 for p in picks if p.tier == "LOCK")
        strong_count = sum(1 for p in picks if p.tier == "STRONG")

        if lock_count >= 2:
            confidence_level = "Very High - Multiple lock plays"
        elif lock_count >= 1 or strong_count >= 2:
            confidence_level = "High - Strong edge opportunities"
        elif strong_count >= 1:
            confidence_level = "Moderate - Good value present"
        else:
            confidence_level = "Standard - Proceed with caution"

        return {
            "total_picks": len(picks),
            "avg_confidence": f"{avg_conf:.1%}",
            "avg_edge": f"+{avg_edge:.1%}",
            "confidence_level": confidence_level,
            "tier_breakdown": {
                "locks": lock_count,
                "strong": strong_count,
                "standard": sum(1 for p in picks if p.tier == "STANDARD"),
                "lean": sum(1 for p in picks if p.tier == "LEAN"),
            },
        }

    def format_console(self, report: DailyReport) -> str:
        """
        Format report for console output.

        Returns:
            Formatted string for terminal display.
        """
        lines = [
            "",
            "═" * 60,
            f"NHL DAILY PICKS - {report.date}",
            "═" * 60,
            "",
            f"Model Accuracy: {report.model_health['accuracy_7d']} (7d) | "
            f"{report.model_health['accuracy_30d']} (30d)",
            f"Overall: {report.summary['confidence_level']}",
            "",
        ]

        for pick in report.picks:
            tier_emoji = self._get_tier_indicator(pick.tier)

            lines.extend([
                "─" * 60,
                f"PICK #{pick.rank} - {tier_emoji} {pick.tier}",
                f"{pick.matchup}",
                f"► PICK: {pick.pick}",
                f"► Confidence: {pick.confidence}",
                f"► Edge: {pick.edge} vs Market",
                f"► Goalie: {pick.goalie_status}",
                f"► Game Time: {pick.game_time}",
                f"► Risk: {pick.risk}",
            ])

            if pick.rationale:
                lines.append(f"► Rationale: {pick.rationale}")

            lines.append("")

        lines.extend([
            "─" * 60,
            "SUMMARY",
            f"  Total Picks: {report.summary['total_picks']}",
            f"  Average Confidence: {report.summary['avg_confidence']}",
            f"  Average Edge: {report.summary['avg_edge']}",
        ])

        if report.notes:
            lines.extend(["", "NOTES:"])
            for note in report.notes:
                lines.append(f"  • {note}")

        lines.extend([
            "",
            "─" * 60,
            f"Generated: {report.generated_at}",
            "═" * 60,
            "",
        ])

        return "\n".join(lines)

    def _get_tier_indicator(self, tier: str) -> str:
        """Get visual indicator for tier."""
        indicators = {
            "LOCK": "★★★",
            "STRONG": "★★",
            "STANDARD": "★",
            "LEAN": "○",
        }
        return indicators.get(tier, "")

    def format_json(self, report: DailyReport) -> str:
        """
        Format report as JSON.

        Returns:
            JSON string.
        """
        data = {
            "date": report.date,
            "generated_at": report.generated_at,
            "picks": [asdict(p) for p in report.picks],
            "summary": report.summary,
            "model_health": report.model_health,
            "notes": report.notes,
        }
        return json.dumps(data, indent=2)

    def format_markdown(self, report: DailyReport) -> str:
        """
        Format report as Markdown.

        Returns:
            Markdown string.
        """
        lines = [
            f"# NHL Daily Picks - {report.date}",
            "",
            f"**Generated:** {report.generated_at}",
            "",
            "## Model Health",
            f"- 7-Day Accuracy: {report.model_health['accuracy_7d']}",
            f"- 30-Day Accuracy: {report.model_health['accuracy_30d']}",
            "",
            f"**{report.summary['confidence_level']}**",
            "",
            "---",
            "",
        ]

        for pick in report.picks:
            lines.extend([
                f"## Pick #{pick.rank} - {pick.tier}",
                "",
                f"**{pick.matchup}**",
                "",
                f"| Metric | Value |",
                f"|--------|-------|",
                f"| Pick | **{pick.pick}** |",
                f"| Confidence | {pick.confidence} |",
                f"| Edge | {pick.edge} |",
                f"| Goalie | {pick.goalie_status} |",
                f"| Game Time | {pick.game_time} |",
                f"| Risk | {pick.risk} |",
                "",
            ])

            if pick.rationale:
                lines.extend([
                    f"> {pick.rationale}",
                    "",
                ])

            lines.append("---")
            lines.append("")

        lines.extend([
            "## Summary",
            "",
            f"- Total Picks: {report.summary['total_picks']}",
            f"- Average Confidence: {report.summary['avg_confidence']}",
            f"- Average Edge: {report.summary['avg_edge']}",
            "",
        ])

        if report.notes:
            lines.extend(["## Notes", ""])
            for note in report.notes:
                lines.append(f"- {note}")

        return "\n".join(lines)

    def save_report(
        self,
        report: DailyReport,
        formats: list[str] = None,
    ) -> dict[str, Path]:
        """
        Save report to files.

        Args:
            report: DailyReport to save.
            formats: List of formats ("json", "txt", "md").

        Returns:
            Dict mapping format to saved file path.
        """
        if formats is None:
            formats = ["json", "txt"]

        saved = {}
        date_str = report.date.replace(", ", "_").replace(" ", "_")

        for fmt in formats:
            if fmt == "json":
                content = self.format_json(report)
                filename = f"picks_{date_str}.json"
            elif fmt == "txt":
                content = self.format_console(report)
                filename = f"picks_{date_str}.txt"
            elif fmt == "md":
                content = self.format_markdown(report)
                filename = f"picks_{date_str}.md"
            else:
                logger.warning(f"Unknown format: {fmt}")
                continue

            path = self.output_dir / filename
            path.write_text(content)
            saved[fmt] = path
            logger.info(f"Saved report to {path}")

        return saved

    def format_email(self, report: DailyReport) -> dict:
        """
        Format report for email.

        Returns:
            Dict with subject and body.
        """
        subject = f"NHL Picks - {report.date}"

        # Simple text body
        body = self.format_console(report)

        return {
            "subject": subject,
            "body": body,
            "html": self._format_html_email(report),
        }

    def _format_html_email(self, report: DailyReport) -> str:
        """Generate HTML email body."""
        html = f"""
        <html>
        <body style="font-family: Arial, sans-serif; max-width: 600px; margin: 0 auto;">
            <h1 style="color: #1a365d; border-bottom: 2px solid #1a365d;">
                NHL Daily Picks
            </h1>
            <p style="color: #666;">{report.date}</p>

            <div style="background: #f0f4f8; padding: 15px; border-radius: 8px; margin-bottom: 20px;">
                <strong>{report.summary['confidence_level']}</strong><br>
                Model Accuracy: {report.model_health['accuracy_7d']} (7d)
            </div>
        """

        for pick in report.picks:
            tier_color = {
                "LOCK": "#22543d",
                "STRONG": "#2c5282",
                "STANDARD": "#553c9a",
                "LEAN": "#744210",
            }.get(pick.tier, "#333")

            html += f"""
            <div style="border: 1px solid #e2e8f0; border-radius: 8px; padding: 15px; margin-bottom: 15px;">
                <div style="background: {tier_color}; color: white; padding: 5px 10px; border-radius: 4px; display: inline-block;">
                    #{pick.rank} {pick.tier}
                </div>
                <h3 style="margin: 10px 0 5px 0;">{pick.matchup}</h3>
                <p style="font-size: 18px; margin: 5px 0;">
                    <strong>Pick: {pick.pick}</strong>
                </p>
                <table style="width: 100%; border-collapse: collapse;">
                    <tr><td>Confidence:</td><td><strong>{pick.confidence}</strong></td></tr>
                    <tr><td>Edge:</td><td><strong>{pick.edge}</strong></td></tr>
                    <tr><td>Goalie:</td><td>{pick.goalie_status}</td></tr>
                    <tr><td>Risk:</td><td>{pick.risk}</td></tr>
                </table>
            """
            if pick.rationale:
                html += f"""
                <p style="font-style: italic; color: #555; margin-top: 10px;">
                    {pick.rationale}
                </p>
                """
            html += "</div>"

        if report.notes:
            html += "<h3>Notes</h3><ul>"
            for note in report.notes:
                html += f"<li>{note}</li>"
            html += "</ul>"

        html += f"""
            <p style="color: #999; font-size: 12px; margin-top: 20px;">
                Generated: {report.generated_at}
            </p>
        </body>
        </html>
        """

        return html


def generate_daily_report(
    daily_picks: DailyPicks,
    output_dir: Optional[str] = None,
) -> DailyReport:
    """Convenience function to generate daily report."""
    generator = ReportGenerator(output_dir)
    return generator.generate_report(daily_picks)
