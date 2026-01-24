"""Win Probability Calculator.

Converts adjusted SPS scores into win probability percentages
using logistic regression.
"""

import logging
import math
from dataclasses import dataclass
from datetime import date
from typing import Optional

from .contextual_layer import ContextualAdjustmentLayer, AdjustedMatchup

logger = logging.getLogger(__name__)


@dataclass
class WinProbability:
    """Win probability for a matchup."""

    home_team: str
    away_team: str
    game_date: date

    # Probabilities (0.0 to 1.0)
    home_win_prob: float
    away_win_prob: float

    # Confidence metrics
    confidence_level: str  # "high", "medium", "low"
    data_quality: float  # 0-1 based on data availability

    # Underlying metrics
    home_adjusted_sps: float
    away_adjusted_sps: float
    sps_differential: float


class ProbabilityEngine:
    """Calculates win probabilities from adjusted SPS."""

    # Logistic regression coefficient
    # Calibrated so that a 10-point SPS difference = ~60% win probability
    LOGISTIC_K = 0.05

    # Home ice adjustment already in SPS, but we can fine-tune here
    BASE_HOME_ADVANTAGE = 0.0  # Already factored into CAL

    # Confidence thresholds
    HIGH_CONFIDENCE_THRESHOLD = 0.58
    LOW_CONFIDENCE_THRESHOLD = 0.53

    def __init__(self):
        """Initialize probability engine."""
        self.cal = ContextualAdjustmentLayer()

    def calculate_probability(
        self,
        home_team: str,
        away_team: str,
        game_date: Optional[date] = None,
        home_goalie: Optional[str] = None,
        away_goalie: Optional[str] = None,
        home_injuries: Optional[list[str]] = None,
        away_injuries: Optional[list[str]] = None,
    ) -> Optional[WinProbability]:
        """
        Calculate win probability for a matchup.

        Args:
            home_team: Home team code.
            away_team: Away team code.
            game_date: Date of the game.
            home_goalie: Home goalie name.
            away_goalie: Away goalie name.
            home_injuries: Home injured players.
            away_injuries: Away injured players.

        Returns:
            WinProbability for the matchup.
        """
        if game_date is None:
            game_date = date.today()

        # Get adjusted matchup
        matchup = self.cal.calculate_adjusted_matchup(
            home_team, away_team, game_date,
            home_goalie, away_goalie,
            home_injuries, away_injuries,
        )

        if not matchup:
            logger.warning(f"Could not calculate matchup for {away_team} @ {home_team}")
            return None

        # Calculate probability using logistic function
        home_prob = self._logistic(matchup.adjusted_differential)
        away_prob = 1.0 - home_prob

        # Ensure probabilities are valid
        home_prob = max(0.01, min(0.99, home_prob))
        away_prob = 1.0 - home_prob

        # Determine confidence level
        max_prob = max(home_prob, away_prob)
        if max_prob >= self.HIGH_CONFIDENCE_THRESHOLD:
            confidence = "high"
        elif max_prob >= self.LOW_CONFIDENCE_THRESHOLD:
            confidence = "medium"
        else:
            confidence = "low"

        # Assess data quality (placeholder - would check data freshness)
        data_quality = self._assess_data_quality(matchup)

        return WinProbability(
            home_team=home_team,
            away_team=away_team,
            game_date=game_date,
            home_win_prob=home_prob,
            away_win_prob=away_prob,
            confidence_level=confidence,
            data_quality=data_quality,
            home_adjusted_sps=matchup.home.adjusted_sps,
            away_adjusted_sps=matchup.away.adjusted_sps,
            sps_differential=matchup.adjusted_differential,
        )

    def _logistic(self, sps_differential: float) -> float:
        """
        Convert SPS differential to probability using logistic function.

        P(home win) = 1 / (1 + e^(-k * differential))

        Args:
            sps_differential: Home SPS - Away SPS

        Returns:
            Probability of home team winning (0 to 1).
        """
        try:
            exponent = -self.LOGISTIC_K * sps_differential
            return 1.0 / (1.0 + math.exp(exponent))
        except OverflowError:
            # Handle extreme values
            return 0.01 if sps_differential < 0 else 0.99

    def _assess_data_quality(self, matchup: AdjustedMatchup) -> float:
        """
        Assess the quality/completeness of data used.

        Returns:
            Quality score from 0 to 1.
        """
        quality = 1.0

        # Check if we have goalie data
        if matchup.home.original_components.get("goalie") == "Unknown":
            quality -= 0.15
        if matchup.away.original_components.get("goalie") == "Unknown":
            quality -= 0.15

        # Check for reasonable SPS values (not default 50)
        home_xgf = matchup.home.original_components.get("xgf_score", 50)
        away_xgf = matchup.away.original_components.get("xgf_score", 50)

        if home_xgf == 50.0 and away_xgf == 50.0:
            quality -= 0.20

        return max(0.0, quality)

    def calculate_batch(
        self,
        games: list[dict],
    ) -> list[WinProbability]:
        """
        Calculate probabilities for multiple games.

        Args:
            games: List of dicts with 'home_team', 'away_team', 'date' keys.

        Returns:
            List of WinProbability objects.
        """
        results = []

        for game in games:
            prob = self.calculate_probability(
                game["home_team"],
                game["away_team"],
                game.get("date"),
                game.get("home_goalie"),
                game.get("away_goalie"),
            )
            if prob:
                results.append(prob)

        return results

    def get_probability_breakdown(
        self,
        probability: WinProbability,
    ) -> dict:
        """
        Get detailed breakdown of probability calculation.

        Returns:
            Dict with calculation details.
        """
        matchup = self.cal.calculate_adjusted_matchup(
            probability.home_team,
            probability.away_team,
            probability.game_date,
        )

        if not matchup:
            return {"error": "Could not recalculate matchup"}

        return {
            "home_team": probability.home_team,
            "away_team": probability.away_team,
            "home_win_prob": f"{probability.home_win_prob:.1%}",
            "away_win_prob": f"{probability.away_win_prob:.1%}",
            "sps_differential": round(probability.sps_differential, 1),
            "home_raw_sps": round(matchup.home.raw_sps, 1),
            "home_adjusted_sps": round(matchup.home.adjusted_sps, 1),
            "home_adjustment": f"{(matchup.home.adjustments.total_multiplier - 1) * 100:+.1f}%",
            "away_raw_sps": round(matchup.away.raw_sps, 1),
            "away_adjusted_sps": round(matchup.away.adjusted_sps, 1),
            "away_adjustment": f"{(matchup.away.adjustments.total_multiplier - 1) * 100:+.1f}%",
            "key_factors": matchup.key_factors,
            "confidence": probability.confidence_level,
            "data_quality": f"{probability.data_quality:.0%}",
        }


def calculate_win_probability(
    home_team: str,
    away_team: str,
    game_date: Optional[date] = None,
) -> Optional[WinProbability]:
    """Convenience function to calculate win probability."""
    engine = ProbabilityEngine()
    return engine.calculate_probability(home_team, away_team, game_date)
