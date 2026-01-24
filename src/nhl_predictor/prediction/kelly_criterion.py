"""Kelly Criterion calculator for bet sizing and confidence.

Implements the Kelly Criterion formula to determine optimal bet sizing
and translates this into pick confidence levels.
"""

import logging
from dataclasses import dataclass
from typing import Optional

from .odds_calculator import EdgeAnalysis, OddsConverter

logger = logging.getLogger(__name__)


@dataclass
class KellyResult:
    """Kelly Criterion calculation result."""

    # Inputs
    probability: float  # Model probability of winning
    decimal_odds: float  # Decimal odds offered

    # Kelly calculation
    full_kelly: float  # Optimal fraction of bankroll
    half_kelly: float  # Conservative (50% Kelly)
    quarter_kelly: float  # Very conservative (25% Kelly)

    # Confidence translation
    confidence_rating: str  # "lock", "strong", "standard", "lean", "pass"
    confidence_score: float  # 0-100 scale

    # Expected value
    expected_value: float  # EV per unit wagered


class KellyCalculator:
    """Calculates Kelly Criterion for bet sizing."""

    # Kelly score thresholds for confidence ratings
    LOCK_THRESHOLD = 0.08  # 8%+ Kelly = Lock
    STRONG_THRESHOLD = 0.05  # 5-8% Kelly = Strong
    STANDARD_THRESHOLD = 0.02  # 2-5% Kelly = Standard
    LEAN_THRESHOLD = 0.01  # 1-2% Kelly = Lean
    # Below 1% = Pass

    def __init__(self):
        """Initialize Kelly calculator."""
        self.converter = OddsConverter()

    def calculate_kelly(
        self,
        probability: float,
        odds: float,
        odds_format: str = "american",
    ) -> KellyResult:
        """
        Calculate Kelly Criterion.

        Kelly formula: f* = (bp - q) / b
        Where:
            f* = fraction of bankroll to wager
            b = decimal odds - 1 (net profit per unit)
            p = probability of winning
            q = probability of losing (1 - p)

        Args:
            probability: Model's probability of winning (0 to 1).
            odds: Betting odds.
            odds_format: "american" or "decimal".

        Returns:
            KellyResult with all calculations.
        """
        # Convert to decimal odds if needed
        if odds_format == "american":
            if odds > 0:
                decimal_odds = (odds / 100) + 1
            else:
                decimal_odds = (100 / abs(odds)) + 1
        else:
            decimal_odds = odds

        # Kelly formula
        b = decimal_odds - 1  # Net profit per unit
        p = probability
        q = 1 - probability

        if b <= 0:
            full_kelly = 0.0
        else:
            full_kelly = (b * p - q) / b

        # Clamp to valid range
        full_kelly = max(0.0, min(1.0, full_kelly))

        # Conservative variations
        half_kelly = full_kelly * 0.5
        quarter_kelly = full_kelly * 0.25

        # Determine confidence rating
        confidence_rating = self._get_confidence_rating(full_kelly)

        # Calculate confidence score (0-100)
        confidence_score = self._calculate_confidence_score(full_kelly, probability)

        # Calculate expected value
        ev = (probability * b) - q

        return KellyResult(
            probability=probability,
            decimal_odds=decimal_odds,
            full_kelly=full_kelly,
            half_kelly=half_kelly,
            quarter_kelly=quarter_kelly,
            confidence_rating=confidence_rating,
            confidence_score=confidence_score,
            expected_value=ev,
        )

    def _get_confidence_rating(self, kelly_score: float) -> str:
        """Convert Kelly score to confidence rating."""
        if kelly_score >= self.LOCK_THRESHOLD:
            return "lock"
        elif kelly_score >= self.STRONG_THRESHOLD:
            return "strong"
        elif kelly_score >= self.STANDARD_THRESHOLD:
            return "standard"
        elif kelly_score >= self.LEAN_THRESHOLD:
            return "lean"
        else:
            return "pass"

    def _calculate_confidence_score(
        self,
        kelly_score: float,
        probability: float,
    ) -> float:
        """
        Calculate confidence score (0-100).

        Combines Kelly score with raw probability.
        """
        # Kelly contribution (0-50 points)
        # 10% Kelly = 50 points
        kelly_points = min(50, (kelly_score / 0.10) * 50)

        # Probability contribution (0-50 points)
        # 60% prob = 30 points, 70% = 40 points, 80% = 50 points
        prob_points = max(0, (probability - 0.50) * 100)
        prob_points = min(50, prob_points)

        return kelly_points + prob_points

    def analyze_edge(
        self,
        edge: EdgeAnalysis,
        odds: Optional[float] = None,
    ) -> Optional[KellyResult]:
        """
        Calculate Kelly for an edge analysis.

        Args:
            edge: EdgeAnalysis object.
            odds: Override odds (uses implied if not provided).

        Returns:
            KellyResult for the value side.
        """
        if not edge.has_value:
            return KellyResult(
                probability=0.5,
                decimal_odds=2.0,
                full_kelly=0.0,
                half_kelly=0.0,
                quarter_kelly=0.0,
                confidence_rating="pass",
                confidence_score=0.0,
                expected_value=0.0,
            )

        # Get probability for value side
        if edge.value_side == "home":
            prob = edge.model_home_prob
            market_prob = edge.market_home_prob
        else:
            prob = edge.model_away_prob
            market_prob = edge.market_away_prob

        # Convert market probability to odds if not provided
        if odds is None:
            # Use market implied odds (approximate)
            decimal_odds = 1 / market_prob if market_prob > 0 else 2.0
        else:
            if odds > 0:
                decimal_odds = (odds / 100) + 1
            else:
                decimal_odds = (100 / abs(odds)) + 1

        return self.calculate_kelly(prob, decimal_odds, "decimal")

    def get_pick_strength(self, kelly_result: KellyResult) -> dict:
        """
        Get human-readable pick strength analysis.

        Returns:
            Dict with strength analysis.
        """
        rating_descriptions = {
            "lock": "Top-tier pick with exceptional value",
            "strong": "High-confidence pick with solid edge",
            "standard": "Good pick with positive expected value",
            "lean": "Marginal value, small position only",
            "pass": "No actionable edge",
        }

        return {
            "rating": kelly_result.confidence_rating.upper(),
            "description": rating_descriptions[kelly_result.confidence_rating],
            "confidence_score": round(kelly_result.confidence_score, 1),
            "full_kelly": f"{kelly_result.full_kelly:.1%}",
            "recommended_size": f"{kelly_result.quarter_kelly:.1%}",
            "expected_value": f"{kelly_result.expected_value:+.2%}",
            "is_actionable": kelly_result.confidence_rating != "pass",
        }

    def rank_picks(
        self,
        picks: list[tuple[EdgeAnalysis, float]],
    ) -> list[dict]:
        """
        Rank picks by Kelly score.

        Args:
            picks: List of (EdgeAnalysis, odds) tuples.

        Returns:
            Sorted list of pick analysis dicts.
        """
        analyzed = []

        for edge, odds in picks:
            kelly = self.analyze_edge(edge, odds)
            if kelly and kelly.confidence_rating != "pass":
                analyzed.append({
                    "edge": edge,
                    "kelly": kelly,
                    "pick_team": (
                        edge.home_team if edge.value_side == "home"
                        else edge.away_team
                    ),
                    "opponent": (
                        edge.away_team if edge.value_side == "home"
                        else edge.home_team
                    ),
                })

        # Sort by Kelly score (descending)
        return sorted(
            analyzed,
            key=lambda x: x["kelly"].full_kelly,
            reverse=True,
        )


def calculate_kelly(
    probability: float,
    odds: float,
    odds_format: str = "american",
) -> KellyResult:
    """Convenience function to calculate Kelly."""
    calculator = KellyCalculator()
    return calculator.calculate_kelly(probability, odds, odds_format)


def get_pick_confidence(
    edge: EdgeAnalysis,
    odds: Optional[float] = None,
) -> Optional[KellyResult]:
    """Convenience function to get pick confidence from edge."""
    calculator = KellyCalculator()
    return calculator.analyze_edge(edge, odds)
