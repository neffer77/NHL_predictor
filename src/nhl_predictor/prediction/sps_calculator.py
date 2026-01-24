"""Statistical Power Score (SPS) Calculator.

Calculates raw team strength scores based on fundamental metrics.
SPS = weighted combination of xGF%, HDCF%, and GSAx.
"""

import logging
from dataclasses import dataclass
from datetime import date
from typing import Optional

from ..config import get_config
from ..features.xg_aggregator import XGAggregator
from ..features.hdcf_calculator import HDCFCalculator
from ..features.gsax_calculator import GSAxCalculator

logger = logging.getLogger(__name__)


@dataclass
class TeamSPS:
    """Statistical Power Score for a team."""

    team: str
    date: date

    # Component scores (normalized 0-100)
    xgf_score: float
    hdcf_score: float
    gsax_score: float

    # Weights used
    xgf_weight: float
    hdcf_weight: float
    gsax_weight: float

    # Final SPS (0-100)
    sps: float

    # Component details
    xgf_pct: Optional[float] = None
    hdcf_pct: Optional[float] = None
    goalie_gsax: Optional[float] = None
    goalie_name: Optional[str] = None


@dataclass
class MatchupSPS:
    """SPS comparison for a matchup."""

    home_sps: TeamSPS
    away_sps: TeamSPS

    # Differential (positive = home advantage)
    sps_differential: float

    # Raw advantage
    advantage: str  # "home", "away", "even"


class SPSCalculator:
    """Calculates Statistical Power Scores for teams."""

    # Normalization ranges (for converting raw stats to 0-100 scale)
    XGF_MIN = 45.0  # Worst xGF%
    XGF_MAX = 55.0  # Best xGF%
    HDCF_MIN = 45.0  # Worst HDCF%
    HDCF_MAX = 55.0  # Best HDCF%
    GSAX_MIN = -10.0  # Worst rolling GSAx
    GSAX_MAX = 10.0  # Best rolling GSAx

    def __init__(
        self,
        xgf_weight: Optional[float] = None,
        hdcf_weight: Optional[float] = None,
        gsax_weight: Optional[float] = None,
    ):
        """
        Initialize SPS calculator.

        Args:
            xgf_weight: Weight for xGF% (default from config: 0.45)
            hdcf_weight: Weight for HDCF% (default from config: 0.25)
            gsax_weight: Weight for GSAx (default from config: 0.30)
        """
        config = get_config().model

        self.xgf_weight = xgf_weight or config.xgf_weight
        self.hdcf_weight = hdcf_weight or config.hdcf_weight
        self.gsax_weight = gsax_weight or config.gsax_weight

        # Ensure weights sum to 1.0
        total = self.xgf_weight + self.hdcf_weight + self.gsax_weight
        if abs(total - 1.0) > 0.01:
            logger.warning(f"SPS weights sum to {total}, normalizing to 1.0")
            self.xgf_weight /= total
            self.hdcf_weight /= total
            self.gsax_weight /= total

        # Initialize feature calculators
        self.xg_calc = XGAggregator()
        self.hdcf_calc = HDCFCalculator()
        self.gsax_calc = GSAxCalculator()

    def calculate_team_sps(
        self,
        team: str,
        game_date: Optional[date] = None,
        goalie_name: Optional[str] = None,
    ) -> Optional[TeamSPS]:
        """
        Calculate Statistical Power Score for a team.

        Args:
            team: Team code.
            game_date: Date for calculation (defaults to today).
            goalie_name: Specific goalie to use (defaults to expected starter).

        Returns:
            TeamSPS or None if insufficient data.
        """
        if game_date is None:
            game_date = date.today()

        # Get xG metrics
        xg_metrics = self.xg_calc.get_team_xg(team, game_date)
        xgf_pct = xg_metrics.xgf_pct if xg_metrics else 50.0

        # Get HDCF metrics
        hdcf_metrics = self.hdcf_calc.get_team_hdcf(team, game_date)
        hdcf_pct = hdcf_metrics.hdcf_pct if hdcf_metrics else 50.0

        # Get goalie GSAx
        if goalie_name:
            goalie = self.gsax_calc.get_goalie_gsax(goalie_name, team, game_date)
        else:
            goalie = self.gsax_calc.get_confirmed_starter(team, game_date)
            if not goalie:
                goalie = self.gsax_calc.get_expected_starter(team, game_date)

        goalie_gsax = goalie.gsax_rolling_10 if goalie else 0.0
        goalie_name_final = goalie.player_name if goalie else "Unknown"

        # Normalize to 0-100 scale
        xgf_score = self._normalize(xgf_pct, self.XGF_MIN, self.XGF_MAX)
        hdcf_score = self._normalize(hdcf_pct, self.HDCF_MIN, self.HDCF_MAX)
        gsax_score = self._normalize(goalie_gsax, self.GSAX_MIN, self.GSAX_MAX)

        # Calculate weighted SPS
        sps = (
            self.xgf_weight * xgf_score +
            self.hdcf_weight * hdcf_score +
            self.gsax_weight * gsax_score
        )

        return TeamSPS(
            team=team,
            date=game_date,
            xgf_score=xgf_score,
            hdcf_score=hdcf_score,
            gsax_score=gsax_score,
            xgf_weight=self.xgf_weight,
            hdcf_weight=self.hdcf_weight,
            gsax_weight=self.gsax_weight,
            sps=sps,
            xgf_pct=xgf_pct,
            hdcf_pct=hdcf_pct,
            goalie_gsax=goalie_gsax,
            goalie_name=goalie_name_final,
        )

    def _normalize(self, value: float, min_val: float, max_val: float) -> float:
        """
        Normalize a value to 0-100 scale.

        Values outside range are clamped.
        """
        if value <= min_val:
            return 0.0
        if value >= max_val:
            return 100.0

        return ((value - min_val) / (max_val - min_val)) * 100.0

    def calculate_matchup_sps(
        self,
        home_team: str,
        away_team: str,
        game_date: Optional[date] = None,
        home_goalie: Optional[str] = None,
        away_goalie: Optional[str] = None,
    ) -> Optional[MatchupSPS]:
        """
        Calculate SPS comparison for a matchup.

        Args:
            home_team: Home team code.
            away_team: Away team code.
            game_date: Date of the game.
            home_goalie: Home team goalie name.
            away_goalie: Away team goalie name.

        Returns:
            MatchupSPS comparison.
        """
        home_sps = self.calculate_team_sps(home_team, game_date, home_goalie)
        away_sps = self.calculate_team_sps(away_team, game_date, away_goalie)

        if not home_sps or not away_sps:
            return None

        differential = home_sps.sps - away_sps.sps

        # Determine advantage
        if differential > 5.0:
            advantage = "home"
        elif differential < -5.0:
            advantage = "away"
        else:
            advantage = "even"

        return MatchupSPS(
            home_sps=home_sps,
            away_sps=away_sps,
            sps_differential=differential,
            advantage=advantage,
        )

    def get_league_rankings(
        self,
        game_date: Optional[date] = None,
    ) -> list[TeamSPS]:
        """
        Get all teams ranked by SPS.

        Returns:
            List of TeamSPS sorted by SPS (descending).
        """
        from ..utils.team_mapping import get_all_team_codes

        rankings = []
        for team in get_all_team_codes():
            sps = self.calculate_team_sps(team, game_date)
            if sps:
                rankings.append(sps)

        return sorted(rankings, key=lambda x: x.sps, reverse=True)

    def get_component_breakdown(self, team_sps: TeamSPS) -> dict:
        """
        Get detailed component breakdown for a team's SPS.

        Returns:
            Dict with component contributions and analysis.
        """
        # Calculate contribution of each component
        xgf_contribution = team_sps.xgf_weight * team_sps.xgf_score
        hdcf_contribution = team_sps.hdcf_weight * team_sps.hdcf_score
        gsax_contribution = team_sps.gsax_weight * team_sps.gsax_score

        # Identify strongest/weakest components
        contributions = {
            "xgf": xgf_contribution,
            "hdcf": hdcf_contribution,
            "gsax": gsax_contribution,
        }

        strongest = max(contributions, key=contributions.get)
        weakest = min(contributions, key=contributions.get)

        return {
            "sps": team_sps.sps,
            "contributions": contributions,
            "strongest_component": strongest,
            "weakest_component": weakest,
            "xgf_pct": team_sps.xgf_pct,
            "hdcf_pct": team_sps.hdcf_pct,
            "goalie_gsax": team_sps.goalie_gsax,
            "goalie": team_sps.goalie_name,
        }


def calculate_sps(
    team: str,
    game_date: Optional[date] = None,
) -> Optional[TeamSPS]:
    """Convenience function to calculate team SPS."""
    calculator = SPSCalculator()
    return calculator.calculate_team_sps(team, game_date)


def calculate_matchup_sps(
    home_team: str,
    away_team: str,
    game_date: Optional[date] = None,
) -> Optional[MatchupSPS]:
    """Convenience function to calculate matchup SPS."""
    calculator = SPSCalculator()
    return calculator.calculate_matchup_sps(home_team, away_team, game_date)
