"""PDO regression tracker.

PDO (Shooting % + Save %) is the primary "luck" indicator in hockey.
Teams with extreme PDO values are due for regression to the mean.
"""

import logging
from dataclasses import dataclass
from datetime import date
from typing import Optional

from ..models.database import get_db
from ..models.schema import TeamDailyStats

logger = logging.getLogger(__name__)


@dataclass
class TeamPDOMetrics:
    """PDO metrics for a team."""

    team: str
    games_played: int

    # Current PDO
    pdo: float
    shooting_pct: float
    save_pct: float

    # Rolling PDO
    pdo_rolling_10: Optional[float] = None
    pdo_rolling_20: Optional[float] = None

    # Deviation from mean (1000)
    pdo_deviation: float = 0.0

    # Regression flags
    is_lucky: bool = False  # PDO > 1020
    is_unlucky: bool = False  # PDO < 980

    # Regression prediction
    expected_regression: float = 0.0  # Points expected toward 1000


class PDOTracker:
    """Tracks and analyzes PDO for regression identification."""

    # Constants
    LEAGUE_AVG_PDO = 1000.0
    LUCKY_THRESHOLD = 1020.0  # Teams above this are "lucky"
    UNLUCKY_THRESHOLD = 980.0  # Teams below this are "unlucky"
    EXTREME_LUCKY = 1040.0  # Strong regression candidate
    EXTREME_UNLUCKY = 960.0  # Strong bounce-back candidate

    def __init__(self):
        self.db = get_db()

    def get_team_pdo(
        self,
        team: str,
        as_of_date: Optional[date] = None,
        source: str = "nst_5v5",
    ) -> Optional[TeamPDOMetrics]:
        """
        Get PDO metrics for a team.

        Args:
            team: Team code.
            as_of_date: Date to get stats for.
            source: Data source.

        Returns:
            TeamPDOMetrics or None.
        """
        if as_of_date is None:
            as_of_date = date.today()

        with self.db.session_scope() as session:
            stats = session.query(TeamDailyStats).filter(
                TeamDailyStats.team == team,
                TeamDailyStats.date <= as_of_date,
                TeamDailyStats.source == source,
            ).order_by(TeamDailyStats.date.desc()).first()

            if not stats:
                logger.warning(f"No PDO data found for {team}")
                return None

            pdo = stats.pdo or self.LEAGUE_AVG_PDO
            shooting_pct = stats.shooting_pct or 0.0
            save_pct = stats.save_pct or 0.0
            games = stats.games_played or 1

            # Calculate rolling PDO
            pdo_10 = self._calculate_rolling_pdo(session, team, as_of_date, 10, source)
            pdo_20 = self._calculate_rolling_pdo(session, team, as_of_date, 20, source)

            # Calculate deviation
            deviation = pdo - self.LEAGUE_AVG_PDO

            # Determine luck status
            is_lucky = pdo >= self.LUCKY_THRESHOLD
            is_unlucky = pdo <= self.UNLUCKY_THRESHOLD

            # Calculate expected regression
            # Teams tend to regress ~50% toward the mean over 20 games
            expected_regression = -deviation * 0.5

            return TeamPDOMetrics(
                team=team,
                games_played=games,
                pdo=pdo,
                shooting_pct=shooting_pct,
                save_pct=save_pct,
                pdo_rolling_10=pdo_10,
                pdo_rolling_20=pdo_20,
                pdo_deviation=deviation,
                is_lucky=is_lucky,
                is_unlucky=is_unlucky,
                expected_regression=expected_regression,
            )

    def _calculate_rolling_pdo(
        self,
        session,
        team: str,
        as_of_date: date,
        window: int,
        source: str,
    ) -> Optional[float]:
        """Calculate rolling PDO over a window."""
        stats_list = session.query(TeamDailyStats).filter(
            TeamDailyStats.team == team,
            TeamDailyStats.date <= as_of_date,
            TeamDailyStats.source == source,
        ).order_by(TeamDailyStats.date.desc()).limit(window).all()

        if not stats_list:
            return None

        pdo_values = [s.pdo for s in stats_list if s.pdo is not None]
        if not pdo_values:
            return None

        return sum(pdo_values) / len(pdo_values)

    def find_regression_candidates(
        self,
        as_of_date: Optional[date] = None,
        min_games: int = 10,
    ) -> dict:
        """
        Find teams due for PDO regression.

        Returns:
            Dict with 'sell_high' (lucky teams) and 'buy_low' (unlucky teams).
        """
        from ..utils.team_mapping import get_all_team_codes

        if as_of_date is None:
            as_of_date = date.today()

        sell_high = []  # Lucky teams due for negative regression
        buy_low = []  # Unlucky teams due for positive regression

        for team in get_all_team_codes():
            metrics = self.get_team_pdo(team, as_of_date)
            if not metrics or metrics.games_played < min_games:
                continue

            if metrics.pdo >= self.EXTREME_LUCKY:
                sell_high.append(metrics)
            elif metrics.pdo <= self.EXTREME_UNLUCKY:
                buy_low.append(metrics)

        # Sort by extremity
        sell_high.sort(key=lambda x: x.pdo, reverse=True)
        buy_low.sort(key=lambda x: x.pdo)

        return {
            "sell_high": sell_high,
            "buy_low": buy_low,
        }

    def get_pdo_mismatch(
        self,
        home_team: str,
        away_team: str,
        as_of_date: Optional[date] = None,
    ) -> dict:
        """
        Identify PDO mismatch between teams.

        High-value betting scenario: Low PDO team vs High PDO team.

        Args:
            home_team: Home team code.
            away_team: Away team code.
            as_of_date: Date for analysis.

        Returns:
            Dict with mismatch analysis.
        """
        home_pdo = self.get_team_pdo(home_team, as_of_date)
        away_pdo = self.get_team_pdo(away_team, as_of_date)

        if not home_pdo or not away_pdo:
            return {"available": False}

        pdo_diff = home_pdo.pdo - away_pdo.pdo

        # Identify mismatch scenarios
        is_mismatch = False
        value_side = None

        if home_pdo.is_unlucky and away_pdo.is_lucky:
            is_mismatch = True
            value_side = "home"
        elif home_pdo.is_lucky and away_pdo.is_unlucky:
            is_mismatch = True
            value_side = "away"

        return {
            "available": True,
            "home_pdo": home_pdo.pdo,
            "away_pdo": away_pdo.pdo,
            "pdo_differential": pdo_diff,
            "home_is_lucky": home_pdo.is_lucky,
            "home_is_unlucky": home_pdo.is_unlucky,
            "away_is_lucky": away_pdo.is_lucky,
            "away_is_unlucky": away_pdo.is_unlucky,
            "is_mismatch": is_mismatch,
            "value_side": value_side,
            "home_expected_regression": home_pdo.expected_regression,
            "away_expected_regression": away_pdo.expected_regression,
        }

    def get_pdo_rankings(
        self,
        as_of_date: Optional[date] = None,
    ) -> list[TeamPDOMetrics]:
        """
        Get all teams ranked by PDO.

        Returns:
            List sorted by PDO (highest first = luckiest).
        """
        from ..utils.team_mapping import get_all_team_codes

        metrics = []
        for team in get_all_team_codes():
            team_pdo = self.get_team_pdo(team, as_of_date)
            if team_pdo:
                metrics.append(team_pdo)

        return sorted(metrics, key=lambda x: x.pdo, reverse=True)


def get_team_pdo(team: str, as_of_date: Optional[date] = None) -> Optional[TeamPDOMetrics]:
    """Convenience function to get team PDO metrics."""
    tracker = PDOTracker()
    return tracker.get_team_pdo(team, as_of_date)


def get_pdo_mismatch(home_team: str, away_team: str) -> dict:
    """Convenience function to check PDO mismatch."""
    tracker = PDOTracker()
    return tracker.get_pdo_mismatch(home_team, away_team)


def find_regression_candidates() -> dict:
    """Convenience function to find regression candidates."""
    tracker = PDOTracker()
    return tracker.find_regression_candidates()
