"""Top 4 Selection Algorithm.

Main selection engine that combines filtering, ranking, and stability
to produce the final top 4 picks for the day.
"""

import logging
from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Optional

from .filters import StayAwayFilter, FilteredGame
from .ranking import EdgeRanker, RankedPick
from .stability import StabilityChecker, MatchupStability
from ..prediction.calibration import ModelCalibrator

logger = logging.getLogger(__name__)


@dataclass
class FinalPick:
    """A final selected pick with all metadata."""

    # Ranking
    rank: int
    tier: str  # "LOCK", "STRONG", "STANDARD", "LEAN"

    # Game info
    game_id: int
    home_team: str
    away_team: str
    game_date: date
    start_time: Optional[str]

    # Pick details
    pick_team: str
    opponent: str
    pick_side: str

    # Probabilities
    model_probability: float
    market_probability: float
    adjusted_probability: float

    # Edge and value
    edge: float
    expected_value: float

    # Kelly
    kelly_score: float
    recommended_stake: float  # Quarter Kelly

    # Stability
    stability_score: float
    regression_risk: str

    # Goalie info
    goalie_confirmed: bool
    goalie_name: Optional[str]

    # Risk assessment
    risk_level: str
    risk_flags: list

    # Adjustments applied
    adjustments: list[str] = field(default_factory=list)


@dataclass
class DailyPicks:
    """Complete daily pick package."""

    date: date
    generated_at: datetime

    # Picks
    picks: list[FinalPick]

    # Summary
    total_games: int
    games_filtered: int
    games_with_value: int

    # Model health
    model_accuracy_7d: float
    model_accuracy_30d: float

    # Notes
    notes: list[str]


class PickSelector:
    """Main selection engine for daily picks."""

    # Default pick count
    DEFAULT_PICK_COUNT = 4

    # Tier thresholds (by Kelly score)
    LOCK_THRESHOLD = 0.08
    STRONG_THRESHOLD = 0.05
    STANDARD_THRESHOLD = 0.02

    # Minimum requirements
    MIN_EDGE = 0.02
    MIN_PROBABILITY = 0.53

    def __init__(self):
        """Initialize selector with all components."""
        self.filter = StayAwayFilter()
        self.ranker = EdgeRanker()
        self.stability_checker = StabilityChecker()
        self.calibrator = ModelCalibrator()

    def select_daily_picks(
        self,
        game_date: Optional[date] = None,
        market_odds: Optional[dict] = None,
        pick_count: int = DEFAULT_PICK_COUNT,
        include_leans: bool = True,
    ) -> DailyPicks:
        """
        Select top picks for a day.

        Args:
            game_date: Date to select picks for.
            market_odds: Dict of market odds by game_id.
            pick_count: Number of picks to return.
            include_leans: Include "lean" tier picks.

        Returns:
            DailyPicks with selected picks.
        """
        if game_date is None:
            game_date = date.today()

        notes = []

        # Step 1: Filter games
        passed_games, filtered_games = self.filter.filter_daily_games(game_date)
        total_games = len(passed_games) + len(filtered_games)

        logger.info(
            f"Filtered {len(filtered_games)}/{total_games} games for {game_date}"
        )

        if not passed_games:
            notes.append("No games passed initial filters")
            return self._empty_picks(game_date, total_games, len(filtered_games))

        # Step 2: Rank by edge
        ranked = self.ranker.rank_games(passed_games, market_odds)

        if not ranked:
            notes.append("No games with positive edge found")
            return self._empty_picks(game_date, total_games, len(filtered_games))

        # Step 3: Apply stability adjustments
        adjusted_picks = self._apply_stability_adjustments(ranked)

        # Step 4: Re-rank with stability as tie-breaker
        final_ranked = self.stability_checker.rank_by_stability(adjusted_picks)

        # Step 5: Filter by minimum requirements
        qualified = [
            p for p in final_ranked
            if p.edge >= self.MIN_EDGE and p.model_probability >= self.MIN_PROBABILITY
        ]

        if not include_leans:
            qualified = [p for p in qualified if p.confidence_rating != "lean"]

        # Step 6: Select top picks
        selected = qualified[:pick_count]

        # Step 7: Convert to FinalPick objects
        final_picks = self._create_final_picks(selected, passed_games, game_date)

        # Step 8: Get model health metrics
        metrics_7d = self.calibrator.calculate_metrics("7d")
        metrics_30d = self.calibrator.calculate_metrics("30d")

        # Add notes
        if len(selected) < pick_count:
            notes.append(
                f"Only {len(selected)} picks met minimum thresholds "
                f"(target: {pick_count})"
            )

        if any(p.risk_level == "medium" for p in final_picks):
            notes.append("Some picks have elevated risk flags")

        return DailyPicks(
            date=game_date,
            generated_at=datetime.now(),
            picks=final_picks,
            total_games=total_games,
            games_filtered=len(filtered_games),
            games_with_value=len(qualified),
            model_accuracy_7d=metrics_7d.accuracy,
            model_accuracy_30d=metrics_30d.accuracy,
            notes=notes,
        )

    def _apply_stability_adjustments(
        self,
        ranked_picks: list[RankedPick],
    ) -> list[RankedPick]:
        """Apply stability-based adjustments to picks."""
        for pick in ranked_picks:
            matchup = self.stability_checker.compare_stability(
                pick.home_team, pick.away_team
            )

            adjusted_prob, adjustments = self.stability_checker.apply_stability_adjustment(
                pick.pick_team, matchup, pick.model_probability
            )

            # Store adjustments (we'll use these when creating FinalPick)
            # Note: RankedPick doesn't have adjustments field, so we track separately

        return ranked_picks

    def _create_final_picks(
        self,
        selected: list[RankedPick],
        filtered_games: list[FilteredGame],
        game_date: date,
    ) -> list[FinalPick]:
        """Convert RankedPick to FinalPick with full metadata."""
        final_picks = []

        # Build lookup for filtered games
        game_lookup = {g.game_id: g for g in filtered_games}

        for i, pick in enumerate(selected, 1):
            game = game_lookup.get(pick.game_id)

            # Get stability info
            matchup = self.stability_checker.compare_stability(
                pick.home_team, pick.away_team
            )

            if pick.pick_side == "home":
                stability = matchup.home_stability
                regression_risk = matchup.home_regression_risk
                goalie_confirmed = game.home_goalie_confirmed if game else False
                goalie_name = game.home_goalie if game else None
            else:
                stability = matchup.away_stability
                regression_risk = matchup.away_regression_risk
                goalie_confirmed = game.away_goalie_confirmed if game else False
                goalie_name = game.away_goalie if game else None

            # Apply stability adjustment
            adjusted_prob, adjustments = self.stability_checker.apply_stability_adjustment(
                pick.pick_team, matchup, pick.model_probability
            )

            # Determine tier
            tier = self._get_tier(pick.kelly_score)

            final_picks.append(FinalPick(
                rank=i,
                tier=tier,
                game_id=pick.game_id,
                home_team=pick.home_team,
                away_team=pick.away_team,
                game_date=game_date,
                start_time=pick.start_time,
                pick_team=pick.pick_team,
                opponent=pick.opponent,
                pick_side=pick.pick_side,
                model_probability=pick.model_probability,
                market_probability=pick.market_probability,
                adjusted_probability=adjusted_prob,
                edge=pick.edge,
                expected_value=pick.expected_value,
                kelly_score=pick.kelly_score,
                recommended_stake=pick.kelly_quarter,
                stability_score=stability.stability_score,
                regression_risk=regression_risk,
                goalie_confirmed=goalie_confirmed,
                goalie_name=goalie_name,
                risk_level=game.risk_level if game else "unknown",
                risk_flags=pick.risk_flags,
                adjustments=adjustments,
            ))

        return final_picks

    def _get_tier(self, kelly_score: float) -> str:
        """Convert Kelly score to tier label."""
        if kelly_score >= self.LOCK_THRESHOLD:
            return "LOCK"
        elif kelly_score >= self.STRONG_THRESHOLD:
            return "STRONG"
        elif kelly_score >= self.STANDARD_THRESHOLD:
            return "STANDARD"
        else:
            return "LEAN"

    def _empty_picks(
        self,
        game_date: date,
        total_games: int,
        filtered_count: int,
    ) -> DailyPicks:
        """Return empty picks when no games qualify."""
        return DailyPicks(
            date=game_date,
            generated_at=datetime.now(),
            picks=[],
            total_games=total_games,
            games_filtered=filtered_count,
            games_with_value=0,
            model_accuracy_7d=0.0,
            model_accuracy_30d=0.0,
            notes=["No qualifying picks for today"],
        )

    def get_pick_explanation(self, pick: FinalPick) -> dict:
        """
        Get detailed explanation for a pick.

        Returns:
            Dict with explanation components.
        """
        explanation = {
            "summary": f"{pick.tier} play on {pick.pick_team} vs {pick.opponent}",
            "confidence": f"{pick.model_probability:.1%} model confidence",
            "edge": f"+{pick.edge:.1%} edge over market",
            "value": f"{pick.expected_value:+.1%} expected value",
        }

        reasons = []

        # Add probability reasoning
        if pick.model_probability >= 0.60:
            reasons.append("Strong model probability (60%+)")
        elif pick.model_probability >= 0.55:
            reasons.append("Solid model probability (55%+)")

        # Add edge reasoning
        if pick.edge >= 0.05:
            reasons.append("Significant edge over market (5%+)")
        elif pick.edge >= 0.03:
            reasons.append("Good edge over market (3%+)")

        # Add stability reasoning
        if pick.stability_score >= 70:
            reasons.append("Stable team performance metrics")
        elif pick.stability_score < 50:
            reasons.append("Note: Some performance variance")

        # Add regression reasoning
        if pick.regression_risk == "low":
            reasons.append("No significant regression risk")
        elif pick.regression_risk == "medium":
            reasons.append("Watch: PDO slightly above normal")
        elif pick.regression_risk == "high":
            reasons.append("Caution: PDO regression likely")

        # Add goalie reasoning
        if pick.goalie_confirmed:
            reasons.append(f"Confirmed starter: {pick.goalie_name}")
        else:
            reasons.append("Goalie not yet confirmed")

        explanation["reasons"] = reasons
        explanation["risk_flags"] = pick.risk_flags
        explanation["adjustments"] = pick.adjustments

        return explanation

    def format_daily_report(self, daily_picks: DailyPicks) -> str:
        """
        Format picks as a text report.

        Returns:
            Formatted string report.
        """
        lines = [
            f"NHL PICKS - {daily_picks.date.strftime('%A, %B %d, %Y')}",
            "=" * 50,
            "",
            f"Games Today: {daily_picks.total_games}",
            f"Filtered Out: {daily_picks.games_filtered}",
            f"With Value: {daily_picks.games_with_value}",
            f"Model Accuracy (7d): {daily_picks.model_accuracy_7d:.1%}",
            f"Model Accuracy (30d): {daily_picks.model_accuracy_30d:.1%}",
            "",
        ]

        if not daily_picks.picks:
            lines.append("No picks meet minimum requirements today.")
        else:
            for pick in daily_picks.picks:
                lines.extend([
                    "-" * 50,
                    f"#{pick.rank} [{pick.tier}] {pick.pick_team}",
                    f"vs {pick.opponent} ({'Home' if pick.pick_side == 'home' else 'Away'})",
                    "",
                    f"  Model: {pick.model_probability:.1%}  |  Market: {pick.market_probability:.1%}",
                    f"  Edge: +{pick.edge:.1%}  |  EV: {pick.expected_value:+.1%}",
                    f"  Kelly: {pick.kelly_score:.1%}  |  Stake: {pick.recommended_stake:.1%}",
                    f"  Stability: {pick.stability_score:.0f}/100  |  Regression: {pick.regression_risk}",
                    "",
                    f"  Goalie: {pick.goalie_name or 'TBD'} ({'Confirmed' if pick.goalie_confirmed else 'Unconfirmed'})",
                    "",
                ])

                if pick.risk_flags:
                    lines.append(f"  Flags: {', '.join(pick.risk_flags)}")
                if pick.adjustments:
                    lines.append(f"  Adjustments: {', '.join(pick.adjustments)}")

                lines.append("")

        if daily_picks.notes:
            lines.extend(["", "Notes:"])
            for note in daily_picks.notes:
                lines.append(f"  - {note}")

        lines.extend([
            "",
            "-" * 50,
            f"Generated: {daily_picks.generated_at.strftime('%Y-%m-%d %H:%M:%S')}",
        ])

        return "\n".join(lines)


def select_picks(
    game_date: Optional[date] = None,
    pick_count: int = 4,
) -> DailyPicks:
    """Convenience function to select daily picks."""
    selector = PickSelector()
    return selector.select_daily_picks(game_date, pick_count=pick_count)


def get_top_pick(game_date: Optional[date] = None) -> Optional[FinalPick]:
    """Convenience function to get the top pick for a day."""
    picks = select_picks(game_date, pick_count=1)
    return picks.picks[0] if picks.picks else None
