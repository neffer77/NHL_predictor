"""Historical Performance Tracker.

Tracks and displays model performance over time including
win rate, ROI, and breakdown by confidence tier.
"""

import logging
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from typing import Optional

from ..models.database import get_db
from ..models.schema import Prediction, Game
from ..prediction.calibration import ModelCalibrator

logger = logging.getLogger(__name__)


@dataclass
class PerformanceRecord:
    """Single prediction performance record."""

    date: date
    game_id: int
    matchup: str
    pick: str
    tier: str
    model_probability: float
    edge: float
    result: str  # "WIN", "LOSS", "PENDING"
    correct: Optional[bool]


@dataclass
class TierPerformance:
    """Performance breakdown by tier."""

    tier: str
    total_picks: int
    wins: int
    losses: int
    pending: int
    win_rate: float
    avg_edge: float
    avg_confidence: float


@dataclass
class PerformanceSummary:
    """Overall performance summary."""

    period: str
    start_date: date
    end_date: date

    # Overall stats
    total_picks: int
    wins: int
    losses: int
    pending: int
    win_rate: float

    # Financial (if tracked)
    units_wagered: float
    units_won: float
    roi: float

    # Quality metrics
    avg_edge: float
    avg_confidence: float
    brier_score: float

    # Tier breakdown
    tier_breakdown: list[TierPerformance]

    # Streak info
    current_streak: int  # Positive = wins, negative = losses
    best_streak: int
    worst_streak: int


class PerformanceTracker:
    """Tracks historical model performance."""

    # Tier mappings from Kelly score
    TIER_THRESHOLDS = {
        "LOCK": 0.08,
        "STRONG": 0.05,
        "STANDARD": 0.02,
        "LEAN": 0.0,
    }

    def __init__(self):
        """Initialize performance tracker."""
        self.db = get_db()
        self.calibrator = ModelCalibrator()

    def record_pick(
        self,
        game_id: int,
        pick_team: str,
        model_probability: float,
        edge: float,
        tier: str,
        kelly_score: float,
    ) -> None:
        """
        Record a pick for tracking.

        Args:
            game_id: NHL game ID.
            pick_team: Team picked to win.
            model_probability: Model's win probability.
            edge: Edge over market.
            tier: Pick tier (LOCK, STRONG, etc).
            kelly_score: Kelly criterion score.
        """
        with self.db.session_scope() as session:
            # Get game info
            game = session.query(Game).filter(
                Game.game_id == game_id
            ).first()

            if not game:
                logger.warning(f"Game {game_id} not found in database")
                return

            # Create or update prediction record
            existing = session.query(Prediction).filter(
                Prediction.game_id == game_id
            ).first()

            if existing:
                logger.debug(f"Prediction for game {game_id} already exists")
                return

            home_prob = (
                model_probability if pick_team == game.home_team
                else 1 - model_probability
            )

            prediction = Prediction(
                game_id=game_id,
                home_win_prob=home_prob,
                away_win_prob=1 - home_prob,
                home_edge=edge if pick_team == game.home_team else -edge,
                away_edge=edge if pick_team != game.home_team else -edge,
                pick=pick_team,
                pick_confidence=model_probability,
                kelly_score=kelly_score,
            )
            session.add(prediction)

        logger.info(f"Recorded pick: {pick_team} for game {game_id}")

    def update_results(self) -> int:
        """
        Update prediction results from completed games.

        Returns:
            Number of predictions updated.
        """
        return self.calibrator.update_outcomes()

    def get_performance_summary(
        self,
        period: str = "30d",
        as_of_date: Optional[date] = None,
    ) -> PerformanceSummary:
        """
        Get performance summary for a period.

        Args:
            period: Time period ("7d", "30d", "season").
            as_of_date: End date for period.

        Returns:
            PerformanceSummary with all metrics.
        """
        if as_of_date is None:
            as_of_date = date.today()

        # Calculate start date
        if period == "7d":
            start_date = as_of_date - timedelta(days=7)
        elif period == "30d":
            start_date = as_of_date - timedelta(days=30)
        else:  # season
            year = as_of_date.year if as_of_date.month >= 10 else as_of_date.year - 1
            start_date = date(year, 10, 1)

        with self.db.session_scope() as session:
            predictions = session.query(Prediction).join(
                Game, Prediction.game_id == Game.game_id
            ).filter(
                Game.date >= start_date,
                Game.date <= as_of_date,
            ).all()

            if not predictions:
                return self._empty_summary(period, start_date, as_of_date)

            # Calculate overall stats
            total = len(predictions)
            with_results = [p for p in predictions if p.actual_winner is not None]
            pending = total - len(with_results)
            wins = sum(1 for p in with_results if p.pick_correct)
            losses = len(with_results) - wins

            win_rate = wins / len(with_results) if with_results else 0

            # Calculate financial metrics (assuming flat betting)
            units_wagered = len(with_results)  # 1 unit per pick
            # Simplified: assume -110 odds (lose 1.1 to win 1)
            units_won = wins - (losses * 1.1)
            roi = (units_won / units_wagered * 100) if units_wagered > 0 else 0

            # Quality metrics
            avg_edge = (
                sum(max(p.home_edge or 0, p.away_edge or 0) for p in predictions)
                / total if total > 0 else 0
            )
            avg_confidence = (
                sum(p.pick_confidence for p in predictions if p.pick_confidence)
                / total if total > 0 else 0
            )

            # Brier score
            brier = self.calibrator._calculate_brier_score(with_results)

            # Tier breakdown
            tier_breakdown = self._calculate_tier_breakdown(predictions)

            # Streak calculation
            streaks = self._calculate_streaks(with_results)

            return PerformanceSummary(
                period=period,
                start_date=start_date,
                end_date=as_of_date,
                total_picks=total,
                wins=wins,
                losses=losses,
                pending=pending,
                win_rate=win_rate,
                units_wagered=units_wagered,
                units_won=units_won,
                roi=roi,
                avg_edge=avg_edge,
                avg_confidence=avg_confidence,
                brier_score=brier,
                tier_breakdown=tier_breakdown,
                current_streak=streaks["current"],
                best_streak=streaks["best"],
                worst_streak=streaks["worst"],
            )

    def _calculate_tier_breakdown(
        self,
        predictions: list,
    ) -> list[TierPerformance]:
        """Calculate performance breakdown by tier."""
        tiers = {"LOCK": [], "STRONG": [], "STANDARD": [], "LEAN": []}

        for pred in predictions:
            # Determine tier from kelly score
            kelly = pred.kelly_score or 0
            if kelly >= self.TIER_THRESHOLDS["LOCK"]:
                tier = "LOCK"
            elif kelly >= self.TIER_THRESHOLDS["STRONG"]:
                tier = "STRONG"
            elif kelly >= self.TIER_THRESHOLDS["STANDARD"]:
                tier = "STANDARD"
            else:
                tier = "LEAN"

            tiers[tier].append(pred)

        breakdown = []
        for tier_name, tier_preds in tiers.items():
            if not tier_preds:
                continue

            with_results = [p for p in tier_preds if p.actual_winner is not None]
            wins = sum(1 for p in with_results if p.pick_correct)
            losses = len(with_results) - wins
            pending = len(tier_preds) - len(with_results)

            breakdown.append(TierPerformance(
                tier=tier_name,
                total_picks=len(tier_preds),
                wins=wins,
                losses=losses,
                pending=pending,
                win_rate=wins / len(with_results) if with_results else 0,
                avg_edge=sum(
                    max(p.home_edge or 0, p.away_edge or 0) for p in tier_preds
                ) / len(tier_preds),
                avg_confidence=sum(
                    p.pick_confidence for p in tier_preds if p.pick_confidence
                ) / len(tier_preds),
            ))

        return breakdown

    def _calculate_streaks(self, predictions: list) -> dict:
        """Calculate win/loss streaks."""
        if not predictions:
            return {"current": 0, "best": 0, "worst": 0}

        # Sort by date
        sorted_preds = sorted(
            predictions,
            key=lambda p: p.game.date if p.game else date.min
        )

        streaks = []
        current = 0

        for pred in sorted_preds:
            if pred.pick_correct:
                if current >= 0:
                    current += 1
                else:
                    streaks.append(current)
                    current = 1
            else:
                if current <= 0:
                    current -= 1
                else:
                    streaks.append(current)
                    current = -1

        streaks.append(current)

        return {
            "current": current,
            "best": max(streaks) if streaks else 0,
            "worst": min(streaks) if streaks else 0,
        }

    def _empty_summary(
        self,
        period: str,
        start_date: date,
        end_date: date,
    ) -> PerformanceSummary:
        """Return empty summary when no data."""
        return PerformanceSummary(
            period=period,
            start_date=start_date,
            end_date=end_date,
            total_picks=0,
            wins=0,
            losses=0,
            pending=0,
            win_rate=0,
            units_wagered=0,
            units_won=0,
            roi=0,
            avg_edge=0,
            avg_confidence=0,
            brier_score=0,
            tier_breakdown=[],
            current_streak=0,
            best_streak=0,
            worst_streak=0,
        )

    def get_recent_picks(
        self,
        limit: int = 20,
    ) -> list[PerformanceRecord]:
        """
        Get recent pick history.

        Args:
            limit: Maximum number of picks to return.

        Returns:
            List of PerformanceRecord objects.
        """
        records = []

        with self.db.session_scope() as session:
            predictions = session.query(Prediction).join(
                Game, Prediction.game_id == Game.game_id
            ).order_by(Game.date.desc()).limit(limit).all()

            for pred in predictions:
                game = pred.game

                # Determine tier
                kelly = pred.kelly_score or 0
                if kelly >= 0.08:
                    tier = "LOCK"
                elif kelly >= 0.05:
                    tier = "STRONG"
                elif kelly >= 0.02:
                    tier = "STANDARD"
                else:
                    tier = "LEAN"

                # Determine result
                if pred.actual_winner is None:
                    result = "PENDING"
                    correct = None
                elif pred.pick_correct:
                    result = "WIN"
                    correct = True
                else:
                    result = "LOSS"
                    correct = False

                records.append(PerformanceRecord(
                    date=game.date,
                    game_id=game.game_id,
                    matchup=f"{game.away_team} @ {game.home_team}",
                    pick=pred.pick,
                    tier=tier,
                    model_probability=pred.pick_confidence or 0.5,
                    edge=max(pred.home_edge or 0, pred.away_edge or 0),
                    result=result,
                    correct=correct,
                ))

        return records

    def format_summary_report(
        self,
        summary: PerformanceSummary,
    ) -> str:
        """
        Format performance summary as text report.

        Returns:
            Formatted string.
        """
        lines = [
            "",
            "═" * 50,
            f"PERFORMANCE REPORT - {summary.period.upper()}",
            f"{summary.start_date} to {summary.end_date}",
            "═" * 50,
            "",
            "OVERALL",
            f"  Record: {summary.wins}-{summary.losses}"
            f" ({summary.pending} pending)",
            f"  Win Rate: {summary.win_rate:.1%}",
            f"  ROI: {summary.roi:+.1f}%",
            f"  Units: {summary.units_won:+.1f}",
            "",
            "QUALITY METRICS",
            f"  Avg Edge: +{summary.avg_edge:.1%}",
            f"  Avg Confidence: {summary.avg_confidence:.1%}",
            f"  Brier Score: {summary.brier_score:.4f}",
            "",
            "STREAKS",
            f"  Current: {summary.current_streak:+d}",
            f"  Best: +{summary.best_streak}",
            f"  Worst: {summary.worst_streak}",
            "",
        ]

        if summary.tier_breakdown:
            lines.extend([
                "TIER BREAKDOWN",
                "─" * 50,
            ])
            for tier in summary.tier_breakdown:
                lines.append(
                    f"  {tier.tier:8s}: {tier.wins}-{tier.losses} "
                    f"({tier.win_rate:.1%}) | "
                    f"Edge: +{tier.avg_edge:.1%}"
                )

        lines.extend([
            "",
            "═" * 50,
        ])

        return "\n".join(lines)

    def format_weekly_summary(self) -> str:
        """Generate formatted weekly summary."""
        summary_7d = self.get_performance_summary("7d")
        summary_30d = self.get_performance_summary("30d")
        summary_season = self.get_performance_summary("season")

        lines = [
            "",
            "╔" + "═" * 58 + "╗",
            "║" + "WEEKLY PERFORMANCE SUMMARY".center(58) + "║",
            "╚" + "═" * 58 + "╝",
            "",
            "┌─────────┬────────┬──────────┬─────────┬─────────┐",
            "│ Period  │ Record │ Win Rate │   ROI   │  Brier  │",
            "├─────────┼────────┼──────────┼─────────┼─────────┤",
        ]

        for label, summary in [
            ("7 Day", summary_7d),
            ("30 Day", summary_30d),
            ("Season", summary_season),
        ]:
            record = f"{summary.wins}-{summary.losses}"
            lines.append(
                f"│ {label:7s} │ {record:6s} │ "
                f"{summary.win_rate:7.1%} │ {summary.roi:+6.1f}% │ "
                f"{summary.brier_score:7.4f} │"
            )

        lines.extend([
            "└─────────┴────────┴──────────┴─────────┴─────────┘",
            "",
        ])

        # Add recent results
        recent = self.get_recent_picks(10)
        if recent:
            lines.extend([
                "RECENT PICKS:",
                "─" * 60,
            ])
            for pick in recent[:10]:
                result_icon = (
                    "✓" if pick.result == "WIN" else
                    "✗" if pick.result == "LOSS" else
                    "○"
                )
                lines.append(
                    f"  {result_icon} {pick.date} | {pick.matchup} | "
                    f"{pick.pick} ({pick.tier})"
                )

        return "\n".join(lines)


def get_performance_summary(period: str = "30d") -> PerformanceSummary:
    """Convenience function to get performance summary."""
    tracker = PerformanceTracker()
    return tracker.get_performance_summary(period)


def format_performance_report(period: str = "30d") -> str:
    """Convenience function to format performance report."""
    tracker = PerformanceTracker()
    summary = tracker.get_performance_summary(period)
    return tracker.format_summary_report(summary)
