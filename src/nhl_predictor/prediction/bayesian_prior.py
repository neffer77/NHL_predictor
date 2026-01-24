"""Bayesian Prior for Early Season.

Handles small sample size issues at the start of the season
by incorporating prior data and regressing to the mean.
"""

import logging
from dataclasses import dataclass
from datetime import date
from typing import Optional

logger = logging.getLogger(__name__)


@dataclass
class BayesianAdjustedMetrics:
    """Metrics adjusted with Bayesian prior."""

    team: str
    games_played: int

    # Current season metrics
    current_xgf_pct: float
    current_hdcf_pct: float
    current_pdo: float

    # Prior (last season or league average)
    prior_xgf_pct: float
    prior_hdcf_pct: float
    prior_pdo: float

    # Weight applied to current season
    current_weight: float
    prior_weight: float

    # Final adjusted metrics
    adjusted_xgf_pct: float
    adjusted_hdcf_pct: float
    adjusted_pdo: float


class BayesianPriorAdjuster:
    """Adjusts early-season metrics using Bayesian priors."""

    # Games thresholds for prior weighting
    FULL_SEASON_GAMES = 82
    PRIOR_PHASE_OUT_START = 20  # Start reducing prior weight
    PRIOR_PHASE_OUT_END = 40  # Prior fully phased out

    # League averages (regression targets)
    LEAGUE_AVG_XGF_PCT = 50.0
    LEAGUE_AVG_HDCF_PCT = 50.0
    LEAGUE_AVG_PDO = 1000.0

    # Prior season data (would be loaded from database in production)
    # This is placeholder data - in practice, load from previous season
    PRIOR_SEASON_DATA = {
        # Top teams
        "BOS": {"xgf_pct": 54.0, "hdcf_pct": 53.5, "pdo": 1005},
        "CAR": {"xgf_pct": 53.5, "hdcf_pct": 54.0, "pdo": 1002},
        "COL": {"xgf_pct": 53.0, "hdcf_pct": 52.5, "pdo": 1008},
        "DAL": {"xgf_pct": 52.5, "hdcf_pct": 53.0, "pdo": 1003},
        "EDM": {"xgf_pct": 52.0, "hdcf_pct": 51.5, "pdo": 1010},
        "FLA": {"xgf_pct": 53.5, "hdcf_pct": 54.5, "pdo": 1001},
        "NJD": {"xgf_pct": 52.5, "hdcf_pct": 52.0, "pdo": 1004},
        "NYR": {"xgf_pct": 51.5, "hdcf_pct": 51.0, "pdo": 1006},
        "TBL": {"xgf_pct": 52.0, "hdcf_pct": 52.5, "pdo": 1002},
        "TOR": {"xgf_pct": 52.5, "hdcf_pct": 51.5, "pdo": 1005},
        "VGK": {"xgf_pct": 53.0, "hdcf_pct": 53.5, "pdo": 1001},
        "WPG": {"xgf_pct": 51.5, "hdcf_pct": 52.0, "pdo": 1003},

        # Middle teams
        "BUF": {"xgf_pct": 50.0, "hdcf_pct": 50.5, "pdo": 998},
        "CGY": {"xgf_pct": 50.5, "hdcf_pct": 51.0, "pdo": 999},
        "DET": {"xgf_pct": 49.5, "hdcf_pct": 49.0, "pdo": 1001},
        "LAK": {"xgf_pct": 51.0, "hdcf_pct": 51.5, "pdo": 1000},
        "MIN": {"xgf_pct": 50.5, "hdcf_pct": 50.0, "pdo": 1002},
        "MTL": {"xgf_pct": 48.0, "hdcf_pct": 47.5, "pdo": 997},
        "NSH": {"xgf_pct": 49.0, "hdcf_pct": 48.5, "pdo": 999},
        "NYI": {"xgf_pct": 49.5, "hdcf_pct": 50.0, "pdo": 998},
        "OTT": {"xgf_pct": 49.0, "hdcf_pct": 49.5, "pdo": 996},
        "PHI": {"xgf_pct": 48.5, "hdcf_pct": 48.0, "pdo": 998},
        "PIT": {"xgf_pct": 50.0, "hdcf_pct": 49.5, "pdo": 1001},
        "SEA": {"xgf_pct": 50.5, "hdcf_pct": 51.0, "pdo": 997},
        "STL": {"xgf_pct": 49.5, "hdcf_pct": 50.0, "pdo": 999},
        "VAN": {"xgf_pct": 51.0, "hdcf_pct": 50.5, "pdo": 1004},
        "WSH": {"xgf_pct": 50.0, "hdcf_pct": 49.5, "pdo": 1000},

        # Bottom teams
        "ANA": {"xgf_pct": 46.5, "hdcf_pct": 46.0, "pdo": 995},
        "CBJ": {"xgf_pct": 47.0, "hdcf_pct": 47.5, "pdo": 994},
        "CHI": {"xgf_pct": 45.5, "hdcf_pct": 45.0, "pdo": 993},
        "SJS": {"xgf_pct": 45.0, "hdcf_pct": 44.5, "pdo": 992},
        "UTA": {"xgf_pct": 47.5, "hdcf_pct": 47.0, "pdo": 996},
    }

    def __init__(self):
        """Initialize Bayesian prior adjuster."""
        pass

    def get_prior_weight(self, games_played: int) -> float:
        """
        Calculate the weight to give to prior data.

        Weight decreases from 0.5 to 0 as games increase from 0 to 40.

        Args:
            games_played: Number of games played this season.

        Returns:
            Prior weight (0 to 0.5).
        """
        if games_played >= self.PRIOR_PHASE_OUT_END:
            return 0.0

        if games_played <= 0:
            return 0.5

        # Linear decrease from 0.5 to 0 between games 0 and 40
        progress = games_played / self.PRIOR_PHASE_OUT_END
        return 0.5 * (1 - progress)

    def get_prior_data(self, team: str) -> dict:
        """
        Get prior season data for a team.

        If no prior data available, uses league average.

        Args:
            team: Team code.

        Returns:
            Dict with prior metrics.
        """
        if team in self.PRIOR_SEASON_DATA:
            return self.PRIOR_SEASON_DATA[team]

        # Return league average if no prior data
        return {
            "xgf_pct": self.LEAGUE_AVG_XGF_PCT,
            "hdcf_pct": self.LEAGUE_AVG_HDCF_PCT,
            "pdo": self.LEAGUE_AVG_PDO,
        }

    def regress_to_mean(
        self,
        current_value: float,
        prior_value: float,
        prior_weight: float,
    ) -> float:
        """
        Regress current value toward prior using weighted average.

        Args:
            current_value: Current season value.
            prior_value: Prior/expected value.
            prior_weight: Weight for prior (0 to 1).

        Returns:
            Weighted average of current and prior.
        """
        current_weight = 1.0 - prior_weight
        return (current_weight * current_value) + (prior_weight * prior_value)

    def adjust_metrics(
        self,
        team: str,
        games_played: int,
        current_xgf_pct: Optional[float] = None,
        current_hdcf_pct: Optional[float] = None,
        current_pdo: Optional[float] = None,
    ) -> BayesianAdjustedMetrics:
        """
        Adjust current season metrics with Bayesian prior.

        Args:
            team: Team code.
            games_played: Games played this season.
            current_xgf_pct: Current season xGF%.
            current_hdcf_pct: Current season HDCF%.
            current_pdo: Current season PDO.

        Returns:
            BayesianAdjustedMetrics with prior-adjusted values.
        """
        prior = self.get_prior_data(team)
        prior_weight = self.get_prior_weight(games_played)
        current_weight = 1.0 - prior_weight

        # Use league average for missing current values
        if current_xgf_pct is None:
            current_xgf_pct = self.LEAGUE_AVG_XGF_PCT
        if current_hdcf_pct is None:
            current_hdcf_pct = self.LEAGUE_AVG_HDCF_PCT
        if current_pdo is None:
            current_pdo = self.LEAGUE_AVG_PDO

        # Apply regression
        adjusted_xgf = self.regress_to_mean(
            current_xgf_pct, prior["xgf_pct"], prior_weight
        )
        adjusted_hdcf = self.regress_to_mean(
            current_hdcf_pct, prior["hdcf_pct"], prior_weight
        )
        adjusted_pdo = self.regress_to_mean(
            current_pdo, prior["pdo"], prior_weight
        )

        return BayesianAdjustedMetrics(
            team=team,
            games_played=games_played,
            current_xgf_pct=current_xgf_pct,
            current_hdcf_pct=current_hdcf_pct,
            current_pdo=current_pdo,
            prior_xgf_pct=prior["xgf_pct"],
            prior_hdcf_pct=prior["hdcf_pct"],
            prior_pdo=prior["pdo"],
            current_weight=current_weight,
            prior_weight=prior_weight,
            adjusted_xgf_pct=adjusted_xgf,
            adjusted_hdcf_pct=adjusted_hdcf,
            adjusted_pdo=adjusted_pdo,
        )

    def should_apply_prior(self, games_played: int) -> bool:
        """
        Check if Bayesian prior should be applied.

        Args:
            games_played: Games played this season.

        Returns:
            True if prior should be used.
        """
        return games_played < self.PRIOR_PHASE_OUT_END

    def get_data_reliability(self, games_played: int) -> dict:
        """
        Get data reliability assessment.

        Args:
            games_played: Games played.

        Returns:
            Dict with reliability info.
        """
        if games_played >= self.PRIOR_PHASE_OUT_END:
            reliability = "full"
            description = "Sufficient sample size, using current season data"
        elif games_played >= self.PRIOR_PHASE_OUT_START:
            reliability = "moderate"
            description = "Transitioning from prior to current season data"
        elif games_played >= 10:
            reliability = "limited"
            description = "Heavy reliance on prior season data"
        else:
            reliability = "minimal"
            description = "Very small sample, primarily using prior data"

        return {
            "games_played": games_played,
            "reliability": reliability,
            "description": description,
            "prior_weight": f"{self.get_prior_weight(games_played):.0%}",
            "current_weight": f"{1 - self.get_prior_weight(games_played):.0%}",
        }


def adjust_for_sample_size(
    team: str,
    games_played: int,
    current_xgf_pct: Optional[float] = None,
    current_hdcf_pct: Optional[float] = None,
    current_pdo: Optional[float] = None,
) -> BayesianAdjustedMetrics:
    """Convenience function to apply Bayesian adjustment."""
    adjuster = BayesianPriorAdjuster()
    return adjuster.adjust_metrics(
        team, games_played, current_xgf_pct, current_hdcf_pct, current_pdo
    )


def get_prior_weight(games_played: int) -> float:
    """Convenience function to get prior weight."""
    adjuster = BayesianPriorAdjuster()
    return adjuster.get_prior_weight(games_played)
