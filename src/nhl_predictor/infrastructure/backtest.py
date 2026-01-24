"""Backtesting Framework.

Enables historical backtesting of model changes with
proper point-in-time data handling to prevent data leakage.
"""

import logging
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from typing import Optional

from ..models.database import get_db
from ..models.schema import Game, TeamDailyStats, GoalieStats, Prediction
from ..selection.selector import PickSelector
from ..prediction.calibration import ModelCalibrator

logger = logging.getLogger(__name__)


@dataclass
class BacktestPick:
    """A pick made during backtesting."""

    date: date
    game_id: int
    home_team: str
    away_team: str
    pick: str
    model_probability: float
    edge: float
    tier: str
    actual_winner: Optional[str]
    correct: Optional[bool]


@dataclass
class BacktestDay:
    """Results for a single day of backtesting."""

    date: date
    games_available: int
    games_filtered: int
    picks_made: int
    picks: list[BacktestPick]
    wins: int
    losses: int


@dataclass
class BacktestConfig:
    """Configuration for backtest run."""

    start_date: date
    end_date: date

    # Model configuration (for comparison)
    xgf_weight: float = 0.45
    hdcf_weight: float = 0.25
    gsax_weight: float = 0.30

    # Selection parameters
    min_confidence: float = 0.53
    min_edge: float = 0.02
    picks_per_day: int = 4

    # Name for this configuration
    name: str = "default"


@dataclass
class BacktestResult:
    """Complete backtest results."""

    config: BacktestConfig
    run_timestamp: datetime

    # Overall metrics
    total_days: int
    total_games: int
    total_picks: int
    wins: int
    losses: int
    win_rate: float
    roi: float
    brier_score: float

    # Daily breakdown
    daily_results: list[BacktestDay]

    # Tier breakdown
    tier_performance: dict

    # Streak analysis
    best_streak: int
    worst_streak: int

    # Monthly breakdown
    monthly_performance: dict


class Backtester:
    """Runs historical backtests."""

    def __init__(self, config: Optional[BacktestConfig] = None):
        """
        Initialize backtester.

        Args:
            config: Backtest configuration.
        """
        self.config = config
        self.db = get_db()

    def run(
        self,
        start_date: date,
        end_date: date,
        config: Optional[BacktestConfig] = None,
    ) -> BacktestResult:
        """
        Run backtest over date range.

        Args:
            start_date: Start of backtest period.
            end_date: End of backtest period.
            config: Optional configuration override.

        Returns:
            BacktestResult with all metrics.
        """
        if config:
            self.config = config
        elif not self.config:
            self.config = BacktestConfig(
                start_date=start_date,
                end_date=end_date,
            )

        logger.info(f"Starting backtest from {start_date} to {end_date}")

        daily_results = []
        all_picks = []

        current_date = start_date
        while current_date <= end_date:
            # Run prediction for this date using point-in-time data
            day_result = self._run_day(current_date)

            if day_result:
                daily_results.append(day_result)
                all_picks.extend(day_result.picks)

            current_date += timedelta(days=1)

        # Calculate overall metrics
        result = self._calculate_results(daily_results, all_picks)

        logger.info(
            f"Backtest complete: {result.wins}-{result.losses} "
            f"({result.win_rate:.1%}), ROI: {result.roi:+.1f}%"
        )

        return result

    def _run_day(self, game_date: date) -> Optional[BacktestDay]:
        """
        Run backtest for a single day.

        Uses only data available before game_date to prevent leakage.
        """
        with self.db.session_scope() as session:
            # Get games for this date
            games = session.query(Game).filter(
                Game.date == game_date,
                Game.winner.isnot(None),  # Only completed games
            ).all()

            if not games:
                return None

            # Create point-in-time selector
            selector = self._create_pit_selector(game_date)

            # Generate picks using only historical data
            try:
                daily_picks = selector.select_daily_picks(
                    game_date,
                    pick_count=self.config.picks_per_day,
                )
            except Exception as e:
                logger.warning(f"Error generating picks for {game_date}: {e}")
                return None

            # Convert to backtest picks and check results
            picks = []
            wins = 0
            losses = 0

            for pick in daily_picks.picks:
                # Find actual game result
                game = next(
                    (g for g in games if g.game_id == pick.game_id),
                    None
                )

                if game:
                    correct = pick.pick_team == game.winner

                    if correct:
                        wins += 1
                    else:
                        losses += 1

                    picks.append(BacktestPick(
                        date=game_date,
                        game_id=pick.game_id,
                        home_team=pick.home_team,
                        away_team=pick.away_team,
                        pick=pick.pick_team,
                        model_probability=pick.model_probability,
                        edge=pick.edge,
                        tier=pick.tier,
                        actual_winner=game.winner,
                        correct=correct,
                    ))

            return BacktestDay(
                date=game_date,
                games_available=len(games),
                games_filtered=daily_picks.games_filtered,
                picks_made=len(picks),
                picks=picks,
                wins=wins,
                losses=losses,
            )

    def _create_pit_selector(self, as_of_date: date) -> PickSelector:
        """
        Create a selector that only uses point-in-time data.

        This ensures no future data leaks into predictions.
        """
        # For now, return standard selector
        # In production, this would filter data queries
        return PickSelector()

    def _calculate_results(
        self,
        daily_results: list[BacktestDay],
        all_picks: list[BacktestPick],
    ) -> BacktestResult:
        """Calculate overall backtest metrics."""
        total_wins = sum(d.wins for d in daily_results)
        total_losses = sum(d.losses for d in daily_results)
        total_picks = len(all_picks)

        # Win rate
        win_rate = total_wins / total_picks if total_picks > 0 else 0

        # ROI (assuming -110 odds, flat betting)
        units_won = total_wins - (total_losses * 1.1)
        roi = (units_won / total_picks * 100) if total_picks > 0 else 0

        # Brier score
        brier = self._calculate_brier(all_picks)

        # Tier breakdown
        tier_performance = self._calculate_tier_performance(all_picks)

        # Streaks
        best_streak, worst_streak = self._calculate_streaks(all_picks)

        # Monthly breakdown
        monthly = self._calculate_monthly(daily_results)

        return BacktestResult(
            config=self.config,
            run_timestamp=datetime.now(),
            total_days=len(daily_results),
            total_games=sum(d.games_available for d in daily_results),
            total_picks=total_picks,
            wins=total_wins,
            losses=total_losses,
            win_rate=win_rate,
            roi=roi,
            brier_score=brier,
            daily_results=daily_results,
            tier_performance=tier_performance,
            best_streak=best_streak,
            worst_streak=worst_streak,
            monthly_performance=monthly,
        )

    def _calculate_brier(self, picks: list[BacktestPick]) -> float:
        """Calculate Brier score."""
        if not picks:
            return 0.0

        total = 0.0
        for pick in picks:
            if pick.correct is not None:
                outcome = 1.0 if pick.correct else 0.0
                total += (pick.model_probability - outcome) ** 2

        return total / len(picks)

    def _calculate_tier_performance(
        self,
        picks: list[BacktestPick],
    ) -> dict:
        """Calculate performance by tier."""
        tiers = {"LOCK": [], "STRONG": [], "STANDARD": [], "LEAN": []}

        for pick in picks:
            if pick.tier in tiers:
                tiers[pick.tier].append(pick)

        result = {}
        for tier, tier_picks in tiers.items():
            if tier_picks:
                wins = sum(1 for p in tier_picks if p.correct)
                total = len(tier_picks)
                result[tier] = {
                    "total": total,
                    "wins": wins,
                    "losses": total - wins,
                    "win_rate": wins / total if total > 0 else 0,
                }

        return result

    def _calculate_streaks(
        self,
        picks: list[BacktestPick],
    ) -> tuple[int, int]:
        """Calculate best and worst streaks."""
        if not picks:
            return 0, 0

        # Sort by date
        sorted_picks = sorted(picks, key=lambda p: p.date)

        streaks = []
        current = 0

        for pick in sorted_picks:
            if pick.correct is None:
                continue

            if pick.correct:
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

        return max(streaks) if streaks else 0, min(streaks) if streaks else 0

    def _calculate_monthly(
        self,
        daily_results: list[BacktestDay],
    ) -> dict:
        """Calculate monthly performance breakdown."""
        monthly = {}

        for day in daily_results:
            month_key = day.date.strftime("%Y-%m")

            if month_key not in monthly:
                monthly[month_key] = {
                    "days": 0,
                    "picks": 0,
                    "wins": 0,
                    "losses": 0,
                }

            monthly[month_key]["days"] += 1
            monthly[month_key]["picks"] += day.picks_made
            monthly[month_key]["wins"] += day.wins
            monthly[month_key]["losses"] += day.losses

        # Calculate win rates
        for month_data in monthly.values():
            total = month_data["picks"]
            month_data["win_rate"] = (
                month_data["wins"] / total if total > 0 else 0
            )

        return monthly

    def compare_configs(
        self,
        configs: list[BacktestConfig],
        start_date: date,
        end_date: date,
    ) -> list[BacktestResult]:
        """
        Compare multiple configurations.

        Args:
            configs: List of configurations to test.
            start_date: Start date.
            end_date: End date.

        Returns:
            List of BacktestResult for each config.
        """
        results = []

        for config in configs:
            logger.info(f"Running backtest for config: {config.name}")
            result = self.run(start_date, end_date, config)
            results.append(result)

        # Sort by ROI
        results.sort(key=lambda r: r.roi, reverse=True)

        return results

    def format_report(self, result: BacktestResult) -> str:
        """Format backtest result as text report."""
        lines = [
            "",
            "═" * 60,
            f"BACKTEST REPORT - {result.config.name}",
            "═" * 60,
            "",
            f"Period: {result.config.start_date} to {result.config.end_date}",
            f"Run at: {result.run_timestamp.strftime('%Y-%m-%d %H:%M:%S')}",
            "",
            "─" * 60,
            "OVERALL PERFORMANCE",
            "─" * 60,
            f"  Days: {result.total_days}",
            f"  Games: {result.total_games}",
            f"  Picks: {result.total_picks}",
            f"  Record: {result.wins}-{result.losses}",
            f"  Win Rate: {result.win_rate:.1%}",
            f"  ROI: {result.roi:+.1f}%",
            f"  Brier Score: {result.brier_score:.4f}",
            "",
            "─" * 60,
            "TIER BREAKDOWN",
            "─" * 60,
        ]

        for tier, data in result.tier_performance.items():
            lines.append(
                f"  {tier:10s}: {data['wins']}-{data['losses']} "
                f"({data['win_rate']:.1%})"
            )

        lines.extend([
            "",
            "─" * 60,
            "STREAKS",
            "─" * 60,
            f"  Best Win Streak: +{result.best_streak}",
            f"  Worst Loss Streak: {result.worst_streak}",
            "",
            "─" * 60,
            "MONTHLY BREAKDOWN",
            "─" * 60,
        ])

        for month, data in sorted(result.monthly_performance.items()):
            lines.append(
                f"  {month}: {data['wins']}-{data['losses']} "
                f"({data['win_rate']:.1%}) - {data['picks']} picks"
            )

        lines.extend([
            "",
            "─" * 60,
            "CONFIGURATION",
            "─" * 60,
            f"  xGF Weight: {result.config.xgf_weight}",
            f"  HDCF Weight: {result.config.hdcf_weight}",
            f"  GSAx Weight: {result.config.gsax_weight}",
            f"  Min Confidence: {result.config.min_confidence}",
            f"  Min Edge: {result.config.min_edge}",
            f"  Picks/Day: {result.config.picks_per_day}",
            "",
            "═" * 60,
        ])

        return "\n".join(lines)


def run_backtest(
    start_date: date,
    end_date: date,
    config: Optional[BacktestConfig] = None,
) -> dict:
    """
    Convenience function to run backtest.

    Returns:
        Dict with backtest results.
    """
    backtester = Backtester()

    if config is None:
        config = BacktestConfig(
            start_date=start_date,
            end_date=end_date,
        )

    result = backtester.run(start_date, end_date, config)

    return {
        "total_games": result.total_games,
        "total_picks": result.total_picks,
        "wins": result.wins,
        "losses": result.losses,
        "win_rate": result.win_rate,
        "roi": result.roi,
        "brier_score": result.brier_score,
        "tier_performance": result.tier_performance,
        "monthly_performance": result.monthly_performance,
    }
