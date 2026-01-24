"""High-Danger Chances (HDCF) calculator.

Processes and aggregates High-Danger Chance metrics for team evaluation.
"""

import logging
from dataclasses import dataclass
from datetime import date
from typing import Optional

from ..models.database import get_db
from ..models.schema import TeamDailyStats

logger = logging.getLogger(__name__)


@dataclass
class TeamHDCFMetrics:
    """High-Danger Chances metrics for a team."""

    team: str
    games_played: int

    # Raw HDCF
    hdcf: float  # High Danger Chances For
    hdca: float  # High Danger Chances Against
    hdcf_pct: float  # High Danger Chances For %

    # Per-game rates
    hdcf_per_game: float
    hdca_per_game: float

    # Rolling windows
    hdcf_pct_10: Optional[float] = None
    hdcf_pct_20: Optional[float] = None

    # Scoring Chances (if available)
    scf_pct: Optional[float] = None

    # Corsi comparison (for counter-attack profile detection)
    cf_pct: Optional[float] = None

    # Profile detection
    is_counter_attack: bool = False  # Low CF, High HDCF


class HDCFCalculator:
    """Calculates and analyzes High-Danger Chance metrics."""

    # Thresholds for counter-attack profile
    COUNTER_ATTACK_CF_THRESHOLD = 48.0  # Below 48% Corsi
    COUNTER_ATTACK_HDCF_THRESHOLD = 52.0  # Above 52% HDCF

    def __init__(self):
        self.db = get_db()

    def get_team_hdcf(
        self,
        team: str,
        as_of_date: Optional[date] = None,
        source: str = "nst_5v5",
    ) -> Optional[TeamHDCFMetrics]:
        """
        Get HDCF metrics for a team.

        Args:
            team: Team code.
            as_of_date: Date to get stats for.
            source: Data source.

        Returns:
            TeamHDCFMetrics or None.
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
                logger.warning(f"No HDCF data found for {team}")
                return None

            games = stats.games_played or 1
            hdcf = stats.hdcf or 0.0
            hdca = stats.hdca or 0.0
            cf_pct = stats.cf_pct

            # Calculate HDCF%
            total_hdc = hdcf + hdca
            hdcf_pct = (hdcf / total_hdc * 100) if total_hdc > 0 else 50.0

            # Calculate rolling windows
            hdcf_pct_10 = self._calculate_rolling_hdcf_pct(session, team, as_of_date, 10, source)
            hdcf_pct_20 = self._calculate_rolling_hdcf_pct(session, team, as_of_date, 20, source)

            # Detect counter-attack profile
            is_counter_attack = self._detect_counter_attack_profile(cf_pct, hdcf_pct)

            return TeamHDCFMetrics(
                team=team,
                games_played=games,
                hdcf=hdcf,
                hdca=hdca,
                hdcf_pct=hdcf_pct,
                hdcf_per_game=hdcf / games if games > 0 else 0,
                hdca_per_game=hdca / games if games > 0 else 0,
                hdcf_pct_10=hdcf_pct_10,
                hdcf_pct_20=hdcf_pct_20,
                scf_pct=stats.scf_pct,
                cf_pct=cf_pct,
                is_counter_attack=is_counter_attack,
            )

    def _calculate_rolling_hdcf_pct(
        self,
        session,
        team: str,
        as_of_date: date,
        window: int,
        source: str,
    ) -> Optional[float]:
        """Calculate rolling HDCF% over a window."""
        stats_list = session.query(TeamDailyStats).filter(
            TeamDailyStats.team == team,
            TeamDailyStats.date <= as_of_date,
            TeamDailyStats.source == source,
        ).order_by(TeamDailyStats.date.desc()).limit(window).all()

        if not stats_list:
            return None

        total_hdcf = sum(s.hdcf or 0 for s in stats_list)
        total_hdca = sum(s.hdca or 0 for s in stats_list)
        total = total_hdcf + total_hdca

        if total == 0:
            return 50.0

        return (total_hdcf / total) * 100

    def _detect_counter_attack_profile(
        self,
        cf_pct: Optional[float],
        hdcf_pct: float,
    ) -> bool:
        """
        Detect if team has counter-attack profile.

        Counter-attack teams have low possession (CF%) but generate
        high-quality chances (HDCF%). They are often undervalued.
        """
        if cf_pct is None:
            return False

        return (
            cf_pct < self.COUNTER_ATTACK_CF_THRESHOLD and
            hdcf_pct > self.COUNTER_ATTACK_HDCF_THRESHOLD
        )

    def get_matchup_hdcf_differential(
        self,
        home_team: str,
        away_team: str,
        as_of_date: Optional[date] = None,
    ) -> dict:
        """
        Calculate HDCF differential for a matchup.

        Args:
            home_team: Home team code.
            away_team: Away team code.
            as_of_date: Date for the matchup.

        Returns:
            Dict with differential metrics.
        """
        home_hdcf = self.get_team_hdcf(home_team, as_of_date)
        away_hdcf = self.get_team_hdcf(away_team, as_of_date)

        if not home_hdcf or not away_hdcf:
            return {"available": False}

        return {
            "available": True,
            "home_hdcf_pct": home_hdcf.hdcf_pct,
            "away_hdcf_pct": away_hdcf.hdcf_pct,
            "hdcf_pct_diff": home_hdcf.hdcf_pct - away_hdcf.hdcf_pct,
            "home_is_counter_attack": home_hdcf.is_counter_attack,
            "away_is_counter_attack": away_hdcf.is_counter_attack,
            # Expected high-danger chances in matchup
            "expected_home_hdc": (home_hdcf.hdcf_per_game + away_hdcf.hdca_per_game) / 2,
            "expected_away_hdc": (away_hdcf.hdcf_per_game + home_hdcf.hdca_per_game) / 2,
        }

    def find_counter_attack_teams(
        self,
        as_of_date: Optional[date] = None,
    ) -> list[TeamHDCFMetrics]:
        """
        Find all teams with counter-attack profile.

        These teams are often undervalued by traditional metrics.

        Returns:
            List of teams with counter-attack profile.
        """
        from ..utils.team_mapping import get_all_team_codes

        teams = get_all_team_codes()
        counter_attack_teams = []

        for team in teams:
            metrics = self.get_team_hdcf(team, as_of_date)
            if metrics and metrics.is_counter_attack:
                counter_attack_teams.append(metrics)

        return counter_attack_teams

    def get_hdcf_rankings(
        self,
        as_of_date: Optional[date] = None,
    ) -> list[TeamHDCFMetrics]:
        """
        Get all teams ranked by HDCF%.

        Returns:
            List of all teams sorted by HDCF%.
        """
        from ..utils.team_mapping import get_all_team_codes

        teams = get_all_team_codes()
        metrics = []

        for team in teams:
            team_hdcf = self.get_team_hdcf(team, as_of_date)
            if team_hdcf:
                metrics.append(team_hdcf)

        return sorted(metrics, key=lambda x: x.hdcf_pct, reverse=True)


def get_team_hdcf(team: str, as_of_date: Optional[date] = None) -> Optional[TeamHDCFMetrics]:
    """Convenience function to get team HDCF metrics."""
    calculator = HDCFCalculator()
    return calculator.get_team_hdcf(team, as_of_date)


def get_matchup_hdcf(home_team: str, away_team: str) -> dict:
    """Convenience function to get matchup HDCF differential."""
    calculator = HDCFCalculator()
    return calculator.get_matchup_hdcf_differential(home_team, away_team)
