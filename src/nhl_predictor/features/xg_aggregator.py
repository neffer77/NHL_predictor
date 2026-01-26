"""Expected Goals (xG) aggregator and calculator.

Aggregates and processes Expected Goals data at team level with rolling windows.
"""

import logging
from dataclasses import dataclass
from datetime import date, timedelta
from typing import Optional

from sqlalchemy import func, and_

from ..models.database import get_db
from ..models.schema import TeamDailyStats, Game

logger = logging.getLogger(__name__)


@dataclass
class TeamXGMetrics:
    """Expected Goals metrics for a team."""

    team: str
    games_played: int

    # Raw xG
    xgf: float  # Expected Goals For
    xga: float  # Expected Goals Against
    xgf_pct: float  # Expected Goals For %

    # Per-game rates
    xgf_per_game: float
    xga_per_game: float

    # Rolling windows
    xgf_pct_10: Optional[float] = None  # 10-game rolling
    xgf_pct_20: Optional[float] = None  # 20-game rolling

    # Score-adjusted (if available)
    xgf_score_adj: Optional[float] = None
    xga_score_adj: Optional[float] = None

    # Trend (positive = improving)
    xgf_trend: Optional[float] = None


class XGAggregator:
    """Aggregates and calculates Expected Goals metrics."""

    def __init__(self):
        self.db = get_db()

    def get_team_xg(
        self,
        team: str,
        as_of_date: Optional[date] = None,
        source: str = "nst_5v5",
    ) -> Optional[TeamXGMetrics]:
        """
        Get xG metrics for a team.

        Args:
            team: Team code (e.g., 'MTL').
            as_of_date: Date to get stats for (defaults to today).
            source: Data source to use.

        Returns:
            TeamXGMetrics or None if not found.
        """
        if as_of_date is None:
            as_of_date = date.today()

        with self.db.session_scope() as session:
            # Get most recent stats for the team
            stats = session.query(TeamDailyStats).filter(
                TeamDailyStats.team == team,
                TeamDailyStats.date <= as_of_date,
                TeamDailyStats.source == source,
            ).order_by(TeamDailyStats.date.desc()).first()

            # Fallback to NHL API standings data if NST data not available
            if not stats and source == "nst_5v5":
                stats = session.query(TeamDailyStats).filter(
                    TeamDailyStats.team == team,
                    TeamDailyStats.date <= as_of_date,
                    TeamDailyStats.source == "nhl_api",
                ).order_by(TeamDailyStats.date.desc()).first()
                if stats:
                    source = "nhl_api"  # Update source for rolling calculations

            if not stats:
                logger.warning(f"No xG data found for {team}")
                return None

            games = stats.games_played or 1

            xgf = stats.xgf or 0.0
            xga = stats.xga or 0.0

            # Calculate xGF%
            total_xg = xgf + xga
            xgf_pct = (xgf / total_xg * 100) if total_xg > 0 else 50.0

            # Calculate rolling averages
            xgf_pct_10 = self._calculate_rolling_xgf_pct(session, team, as_of_date, 10, source)
            xgf_pct_20 = self._calculate_rolling_xgf_pct(session, team, as_of_date, 20, source)

            # Calculate trend (recent 5 vs previous 5)
            trend = self._calculate_trend(session, team, as_of_date, source)

            return TeamXGMetrics(
                team=team,
                games_played=games,
                xgf=xgf,
                xga=xga,
                xgf_pct=xgf_pct,
                xgf_per_game=xgf / games if games > 0 else 0,
                xga_per_game=xga / games if games > 0 else 0,
                xgf_pct_10=xgf_pct_10,
                xgf_pct_20=xgf_pct_20,
                xgf_trend=trend,
            )

    def get_matchup_xg_differential(
        self,
        home_team: str,
        away_team: str,
        as_of_date: Optional[date] = None,
    ) -> dict:
        """
        Calculate xG differential for a matchup.

        Args:
            home_team: Home team code.
            away_team: Away team code.
            as_of_date: Date for the matchup.

        Returns:
            Dict with differential metrics.
        """
        home_xg = self.get_team_xg(home_team, as_of_date)
        away_xg = self.get_team_xg(away_team, as_of_date)

        if not home_xg or not away_xg:
            return {"available": False}

        return {
            "available": True,
            "home_xgf_pct": home_xg.xgf_pct,
            "away_xgf_pct": away_xg.xgf_pct,
            "xgf_pct_diff": home_xg.xgf_pct - away_xg.xgf_pct,
            "home_xgf_per_game": home_xg.xgf_per_game,
            "away_xgf_per_game": away_xg.xgf_per_game,
            "home_xga_per_game": home_xg.xga_per_game,
            "away_xga_per_game": away_xg.xga_per_game,
            # Expected goals in matchup
            "expected_home_goals": (home_xg.xgf_per_game + away_xg.xga_per_game) / 2,
            "expected_away_goals": (away_xg.xgf_per_game + home_xg.xga_per_game) / 2,
        }

    def _calculate_rolling_xgf_pct(
        self,
        session,
        team: str,
        as_of_date: date,
        window: int,
        source: str,
    ) -> Optional[float]:
        """Calculate rolling xGF% over a window of games."""
        # Get recent stats entries
        stats_list = session.query(TeamDailyStats).filter(
            TeamDailyStats.team == team,
            TeamDailyStats.date <= as_of_date,
            TeamDailyStats.source == source,
        ).order_by(TeamDailyStats.date.desc()).limit(window).all()

        if not stats_list:
            return None

        total_xgf = sum(s.xgf or 0 for s in stats_list)
        total_xga = sum(s.xga or 0 for s in stats_list)
        total = total_xgf + total_xga

        if total == 0:
            return 50.0

        return (total_xgf / total) * 100

    def _calculate_trend(
        self,
        session,
        team: str,
        as_of_date: date,
        source: str,
    ) -> Optional[float]:
        """Calculate xGF% trend (recent 5 vs previous 5 games)."""
        stats_list = session.query(TeamDailyStats).filter(
            TeamDailyStats.team == team,
            TeamDailyStats.date <= as_of_date,
            TeamDailyStats.source == source,
        ).order_by(TeamDailyStats.date.desc()).limit(10).all()

        if len(stats_list) < 10:
            return None

        recent_5 = stats_list[:5]
        previous_5 = stats_list[5:10]

        def calc_xgf_pct(entries):
            xgf = sum(s.xgf or 0 for s in entries)
            xga = sum(s.xga or 0 for s in entries)
            total = xgf + xga
            return (xgf / total * 100) if total > 0 else 50.0

        recent_pct = calc_xgf_pct(recent_5)
        previous_pct = calc_xgf_pct(previous_5)

        return recent_pct - previous_pct

    def get_all_teams_xg(
        self,
        as_of_date: Optional[date] = None,
        source: str = "nst_5v5",
    ) -> list[TeamXGMetrics]:
        """
        Get xG metrics for all teams.

        Args:
            as_of_date: Date to get stats for.
            source: Data source.

        Returns:
            List of TeamXGMetrics for all teams.
        """
        from ..utils.team_mapping import get_all_team_codes

        teams = get_all_team_codes()
        metrics = []

        for team in teams:
            team_xg = self.get_team_xg(team, as_of_date, source)
            if team_xg:
                metrics.append(team_xg)

        return sorted(metrics, key=lambda x: x.xgf_pct, reverse=True)

    def identify_regression_candidates(
        self,
        as_of_date: Optional[date] = None,
        min_games: int = 10,
    ) -> dict:
        """
        Identify teams due for xG regression.

        Teams whose actual goal differential significantly differs
        from their xG differential are candidates for regression.

        Returns:
            Dict with 'positive_regression' and 'negative_regression' lists.
        """
        if as_of_date is None:
            as_of_date = date.today()

        all_xg = self.get_all_teams_xg(as_of_date)

        positive_regression = []  # Teams underperforming xG (should improve)
        negative_regression = []  # Teams overperforming xG (should decline)

        for team_xg in all_xg:
            if team_xg.games_played < min_games:
                continue

            # Would need actual goals data to calculate regression
            # For now, use trend as a proxy
            if team_xg.xgf_trend is not None:
                if team_xg.xgf_trend > 3:  # Improving significantly
                    positive_regression.append(team_xg)
                elif team_xg.xgf_trend < -3:  # Declining significantly
                    negative_regression.append(team_xg)

        return {
            "positive_regression": positive_regression,
            "negative_regression": negative_regression,
        }


def get_team_xg(team: str, as_of_date: Optional[date] = None) -> Optional[TeamXGMetrics]:
    """Convenience function to get team xG metrics."""
    aggregator = XGAggregator()
    return aggregator.get_team_xg(team, as_of_date)


def get_matchup_xg(home_team: str, away_team: str) -> dict:
    """Convenience function to get matchup xG differential."""
    aggregator = XGAggregator()
    return aggregator.get_matchup_xg_differential(home_team, away_team)
