"""Power Play efficiency analyzer.

Analyzes expected vs actual power play performance for prediction adjustments.
"""

import logging
from dataclasses import dataclass
from datetime import date
from typing import Optional

from ..models.database import get_db
from ..models.schema import TeamDailyStats

logger = logging.getLogger(__name__)


@dataclass
class TeamPowerPlayMetrics:
    """Power play and penalty kill metrics for a team."""

    team: str

    # Power Play
    pp_pct: float  # Actual PP conversion rate
    pp_opportunities: int  # Approximate PP chances
    pp_xg_per_60: Optional[float]  # Expected goals per 60 on PP

    # Penalty Kill
    pk_pct: float  # PK success rate (inverse of opponent PP)
    times_shorthanded: int  # Approximate SH situations

    # Efficiency analysis
    pp_luck: float  # Actual PP% - Expected PP%
    is_pp_breakout_candidate: bool  # High xG, low actual
    is_pp_regression_candidate: bool  # Low xG, high actual

    # Penalty differential
    penalty_differential: float  # Drawn - Taken


@dataclass
class SpecialTeamsMatchup:
    """Special teams matchup analysis."""

    home_pp: TeamPowerPlayMetrics
    away_pp: TeamPowerPlayMetrics

    # Advantage analysis
    pp_advantage: str  # "home", "away", "even"
    pk_advantage: str  # "home", "away", "even"

    # High-event game expectations
    benefits_from_penalties: Optional[str]  # Team that benefits from more calls


class PowerPlayAnalyzer:
    """Analyzes power play and penalty kill efficiency."""

    # League averages (approximate for 2025-26)
    LEAGUE_AVG_PP_PCT = 20.0
    LEAGUE_AVG_PK_PCT = 80.0
    EXPECTED_PP_CONVERSION = 0.20  # 20% expected

    # Thresholds
    ELITE_PP_THRESHOLD = 25.0  # Elite PP%
    POOR_PP_THRESHOLD = 15.0  # Poor PP%
    BREAKOUT_XG_THRESHOLD = 8.0  # High xG/60 on PP

    def __init__(self):
        self.db = get_db()

    def get_team_special_teams(
        self,
        team: str,
        as_of_date: Optional[date] = None,
    ) -> Optional[TeamPowerPlayMetrics]:
        """
        Get special teams metrics for a team.

        Args:
            team: Team code.
            as_of_date: Date to get stats for.

        Returns:
            TeamPowerPlayMetrics or None.
        """
        if as_of_date is None:
            as_of_date = date.today()

        with self.db.session_scope() as session:
            # Get team stats - try multiple sources
            stats = session.query(TeamDailyStats).filter(
                TeamDailyStats.team == team,
                TeamDailyStats.date <= as_of_date,
            ).order_by(TeamDailyStats.date.desc()).first()

            if not stats:
                logger.warning(f"No special teams data found for {team}")
                return None

            pp_pct = stats.pp_pct or self.LEAGUE_AVG_PP_PCT
            pk_pct = stats.pk_pct or self.LEAGUE_AVG_PK_PCT
            pp_xg = stats.pp_xg_per_60

            # Estimate opportunities (rough calculation)
            games = stats.games_played or 1
            pp_opportunities = int(games * 3.5)  # ~3.5 PP per game avg
            times_shorthanded = int(games * 3.5)

            # Calculate PP luck
            expected_pp_pct = self._calculate_expected_pp_pct(pp_xg)
            pp_luck = pp_pct - expected_pp_pct

            # Identify breakout/regression candidates
            is_breakout = (
                pp_xg is not None and
                pp_xg >= self.BREAKOUT_XG_THRESHOLD and
                pp_pct < self.LEAGUE_AVG_PP_PCT
            )

            is_regression = (
                pp_xg is not None and
                pp_xg < self.BREAKOUT_XG_THRESHOLD * 0.7 and
                pp_pct > self.ELITE_PP_THRESHOLD
            )

            # Penalty differential (placeholder - would need more data)
            penalty_diff = 0.0

            return TeamPowerPlayMetrics(
                team=team,
                pp_pct=pp_pct,
                pp_opportunities=pp_opportunities,
                pp_xg_per_60=pp_xg,
                pk_pct=pk_pct,
                times_shorthanded=times_shorthanded,
                pp_luck=pp_luck,
                is_pp_breakout_candidate=is_breakout,
                is_pp_regression_candidate=is_regression,
                penalty_differential=penalty_diff,
            )

    def _calculate_expected_pp_pct(
        self,
        pp_xg_per_60: Optional[float],
    ) -> float:
        """Calculate expected PP% from xG per 60."""
        if pp_xg_per_60 is None:
            return self.LEAGUE_AVG_PP_PCT

        # Approximate: xG/60 of 8.0 corresponds to ~20% PP
        # Linear scaling
        return pp_xg_per_60 * 2.5

    def get_matchup_special_teams(
        self,
        home_team: str,
        away_team: str,
        as_of_date: Optional[date] = None,
    ) -> Optional[SpecialTeamsMatchup]:
        """
        Analyze special teams matchup.

        Args:
            home_team: Home team code.
            away_team: Away team code.
            as_of_date: Date for analysis.

        Returns:
            SpecialTeamsMatchup analysis.
        """
        home_pp = self.get_team_special_teams(home_team, as_of_date)
        away_pp = self.get_team_special_teams(away_team, as_of_date)

        if not home_pp or not away_pp:
            return None

        # Determine PP advantage
        pp_diff = home_pp.pp_pct - away_pp.pp_pct
        if pp_diff > 5.0:
            pp_advantage = "home"
        elif pp_diff < -5.0:
            pp_advantage = "away"
        else:
            pp_advantage = "even"

        # Determine PK advantage
        pk_diff = home_pp.pk_pct - away_pp.pk_pct
        if pk_diff > 5.0:
            pk_advantage = "home"
        elif pk_diff < -5.0:
            pk_advantage = "away"
        else:
            pk_advantage = "even"

        # Determine who benefits from high-penalty game
        # Team with better PP and worse PK benefits from more penalties
        home_penalty_benefit = home_pp.pp_pct - (100 - home_pp.pk_pct)
        away_penalty_benefit = away_pp.pp_pct - (100 - away_pp.pk_pct)

        if home_penalty_benefit > away_penalty_benefit + 5:
            benefits_from_penalties = home_team
        elif away_penalty_benefit > home_penalty_benefit + 5:
            benefits_from_penalties = away_team
        else:
            benefits_from_penalties = None

        return SpecialTeamsMatchup(
            home_pp=home_pp,
            away_pp=away_pp,
            pp_advantage=pp_advantage,
            pk_advantage=pk_advantage,
            benefits_from_penalties=benefits_from_penalties,
        )

    def find_breakout_candidates(
        self,
        as_of_date: Optional[date] = None,
    ) -> list[TeamPowerPlayMetrics]:
        """
        Find teams due for PP breakout.

        These teams have high xG on PP but low actual conversion.

        Returns:
            List of breakout candidate teams.
        """
        from ..utils.team_mapping import get_all_team_codes

        candidates = []
        for team in get_all_team_codes():
            metrics = self.get_team_special_teams(team, as_of_date)
            if metrics and metrics.is_pp_breakout_candidate:
                candidates.append(metrics)

        return sorted(candidates, key=lambda x: x.pp_luck)

    def find_regression_candidates(
        self,
        as_of_date: Optional[date] = None,
    ) -> list[TeamPowerPlayMetrics]:
        """
        Find teams due for PP regression.

        These teams have low xG on PP but high actual conversion.

        Returns:
            List of regression candidate teams.
        """
        from ..utils.team_mapping import get_all_team_codes

        candidates = []
        for team in get_all_team_codes():
            metrics = self.get_team_special_teams(team, as_of_date)
            if metrics and metrics.is_pp_regression_candidate:
                candidates.append(metrics)

        return sorted(candidates, key=lambda x: x.pp_luck, reverse=True)

    def get_pp_rankings(
        self,
        as_of_date: Optional[date] = None,
    ) -> list[TeamPowerPlayMetrics]:
        """Get all teams ranked by PP%."""
        from ..utils.team_mapping import get_all_team_codes

        metrics = []
        for team in get_all_team_codes():
            team_pp = self.get_team_special_teams(team, as_of_date)
            if team_pp:
                metrics.append(team_pp)

        return sorted(metrics, key=lambda x: x.pp_pct, reverse=True)


def get_special_teams(team: str) -> Optional[TeamPowerPlayMetrics]:
    """Convenience function to get team special teams metrics."""
    analyzer = PowerPlayAnalyzer()
    return analyzer.get_team_special_teams(team)


def get_matchup_special_teams(
    home_team: str,
    away_team: str,
) -> Optional[SpecialTeamsMatchup]:
    """Convenience function to get matchup special teams analysis."""
    analyzer = PowerPlayAnalyzer()
    return analyzer.get_matchup_special_teams(home_team, away_team)
