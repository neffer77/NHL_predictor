"""Stability and Variance Check Module.

Evaluates pick stability based on GSAx variance and PDO variance.
Used as a tie-breaker for picks with similar edge.
"""

import logging
import math
from dataclasses import dataclass
from datetime import date, timedelta
from typing import Optional

from ..models.database import get_db
from ..models.schema import TeamDailyStats, GoalieStats
from ..features.pdo_tracker import PDOTracker
from ..features.gsax_calculator import GSAxCalculator

logger = logging.getLogger(__name__)


@dataclass
class StabilityMetrics:
    """Stability metrics for a team."""

    team: str

    # PDO stability
    pdo_current: float
    pdo_mean: float
    pdo_variance: float
    pdo_trend: str  # "hot", "cold", "stable"
    pdo_regression_expected: float  # Expected regression amount

    # GSAx stability
    goalie_gsax: float
    goalie_gsax_variance: float
    goalie_games: int
    goalie_stable: bool

    # Performance consistency
    xgf_variance: float
    scoring_variance: float

    # Overall stability score (0-100, higher = more stable)
    stability_score: float


@dataclass
class MatchupStability:
    """Stability comparison for a matchup."""

    home_team: str
    away_team: str

    home_stability: StabilityMetrics
    away_stability: StabilityMetrics

    # Comparative analysis
    more_stable_team: str
    stability_differential: float

    # Regression risk
    home_regression_risk: str  # "high", "medium", "low"
    away_regression_risk: str

    # Pick adjustment
    stability_confidence_modifier: float  # -0.1 to +0.1


class StabilityChecker:
    """Checks pick stability based on variance metrics."""

    # PDO bounds for stability
    PDO_STABLE_LOW = 990
    PDO_STABLE_HIGH = 1010
    PDO_EXTREME_LOW = 980
    PDO_EXTREME_HIGH = 1020

    # Variance thresholds
    HIGH_VARIANCE_THRESHOLD = 0.15
    LOW_VARIANCE_THRESHOLD = 0.05

    # Minimum games for reliable variance calculation
    MIN_GAMES_FOR_VARIANCE = 15

    def __init__(self):
        """Initialize stability checker."""
        self.db = get_db()
        self.pdo_tracker = PDOTracker()
        self.gsax_calculator = GSAxCalculator()

    def calculate_stability(
        self,
        team: str,
        as_of_date: Optional[date] = None,
    ) -> StabilityMetrics:
        """
        Calculate stability metrics for a team.

        Args:
            team: Team code.
            as_of_date: Date for calculation.

        Returns:
            StabilityMetrics for the team.
        """
        if as_of_date is None:
            as_of_date = date.today()

        # Get recent team stats for variance calculation
        with self.db.session_scope() as session:
            lookback = as_of_date - timedelta(days=30)

            stats = session.query(TeamDailyStats).filter(
                TeamDailyStats.team == team,
                TeamDailyStats.date >= lookback,
                TeamDailyStats.date <= as_of_date,
            ).order_by(TeamDailyStats.date.desc()).all()

            if not stats:
                return self._empty_stability(team)

            # Calculate PDO metrics
            pdo_values = [s.pdo for s in stats if s.pdo]
            if pdo_values:
                pdo_current = pdo_values[0]
                pdo_mean = sum(pdo_values) / len(pdo_values)
                pdo_variance = self._calculate_variance(pdo_values)
                pdo_trend = self._get_pdo_trend(pdo_values)
                pdo_regression = self._calculate_regression_expected(pdo_current)
            else:
                pdo_current = 1000
                pdo_mean = 1000
                pdo_variance = 0
                pdo_trend = "stable"
                pdo_regression = 0

            # Calculate xGF variance
            xgf_values = [s.xgf_pct for s in stats if s.xgf_pct]
            xgf_variance = self._calculate_variance(xgf_values) if xgf_values else 0

            # Calculate scoring variance (using xGF as proxy since actual goals not stored)
            scoring_values = [s.xgf for s in stats if s.xgf]
            scoring_variance = (
                self._calculate_variance(scoring_values) if scoring_values
                else 0
            )

            # Get goalie stability
            goalie_stats = self._get_goalie_stability(team, as_of_date)

            # Calculate overall stability score
            stability_score = self._calculate_stability_score(
                pdo_variance,
                xgf_variance,
                goalie_stats["gsax_variance"],
                len(stats),
            )

            return StabilityMetrics(
                team=team,
                pdo_current=pdo_current,
                pdo_mean=pdo_mean,
                pdo_variance=pdo_variance,
                pdo_trend=pdo_trend,
                pdo_regression_expected=pdo_regression,
                goalie_gsax=goalie_stats["gsax"],
                goalie_gsax_variance=goalie_stats["gsax_variance"],
                goalie_games=goalie_stats["games"],
                goalie_stable=goalie_stats["stable"],
                xgf_variance=xgf_variance,
                scoring_variance=scoring_variance,
                stability_score=stability_score,
            )

    def _calculate_variance(self, values: list) -> float:
        """Calculate variance of a list of values."""
        if len(values) < 2:
            return 0.0

        mean = sum(values) / len(values)
        squared_diffs = [(x - mean) ** 2 for x in values]
        return math.sqrt(sum(squared_diffs) / len(values))

    def _get_pdo_trend(self, pdo_values: list) -> str:
        """Determine PDO trend from recent values."""
        if len(pdo_values) < 5:
            return "stable"

        recent = sum(pdo_values[:5]) / 5
        older = sum(pdo_values[5:10]) / min(5, len(pdo_values) - 5) if len(pdo_values) > 5 else recent

        diff = recent - older

        if diff > 5:
            return "hot"
        elif diff < -5:
            return "cold"
        else:
            return "stable"

    def _calculate_regression_expected(self, current_pdo: float) -> float:
        """Calculate expected regression toward 1000."""
        return (1000 - current_pdo) * 0.3  # Expect 30% regression

    def _get_goalie_stability(
        self,
        team: str,
        as_of_date: date,
    ) -> dict:
        """Get goalie stability metrics."""
        with self.db.session_scope() as session:
            lookback = as_of_date - timedelta(days=30)

            goalies = session.query(GoalieStats).filter(
                GoalieStats.team == team,
                GoalieStats.date >= lookback,
                GoalieStats.date <= as_of_date,
            ).all()

            if not goalies:
                return {
                    "gsax": 0,
                    "gsax_variance": 0,
                    "games": 0,
                    "stable": False,
                }

            gsax_values = [g.gsax for g in goalies if g.gsax is not None]
            games = len(goalies)

            return {
                "gsax": sum(gsax_values) / len(gsax_values) if gsax_values else 0,
                "gsax_variance": self._calculate_variance(gsax_values) if gsax_values else 0,
                "games": games,
                "stable": games >= 10 and (self._calculate_variance(gsax_values) < 0.5 if gsax_values else False),
            }

    def _calculate_stability_score(
        self,
        pdo_variance: float,
        xgf_variance: float,
        gsax_variance: float,
        games: int,
    ) -> float:
        """
        Calculate overall stability score (0-100).

        Lower variance = higher stability score.
        """
        # Base score starts at 100
        score = 100.0

        # Deduct for PDO variance (max -30 points)
        pdo_penalty = min(30, pdo_variance * 3)
        score -= pdo_penalty

        # Deduct for xGF variance (max -25 points)
        xgf_penalty = min(25, xgf_variance * 5)
        score -= xgf_penalty

        # Deduct for GSAx variance (max -25 points)
        gsax_penalty = min(25, gsax_variance * 25)
        score -= gsax_penalty

        # Deduct for small sample (max -20 points)
        if games < self.MIN_GAMES_FOR_VARIANCE:
            sample_penalty = 20 * (1 - games / self.MIN_GAMES_FOR_VARIANCE)
            score -= sample_penalty

        return max(0, score)

    def _empty_stability(self, team: str) -> StabilityMetrics:
        """Return empty stability metrics."""
        return StabilityMetrics(
            team=team,
            pdo_current=1000,
            pdo_mean=1000,
            pdo_variance=0,
            pdo_trend="stable",
            pdo_regression_expected=0,
            goalie_gsax=0,
            goalie_gsax_variance=0,
            goalie_games=0,
            goalie_stable=False,
            xgf_variance=0,
            scoring_variance=0,
            stability_score=50,  # Uncertain
        )

    def compare_stability(
        self,
        home_team: str,
        away_team: str,
        as_of_date: Optional[date] = None,
    ) -> MatchupStability:
        """
        Compare stability between two teams.

        Args:
            home_team: Home team code.
            away_team: Away team code.
            as_of_date: Date for comparison.

        Returns:
            MatchupStability with comparative analysis.
        """
        home_stability = self.calculate_stability(home_team, as_of_date)
        away_stability = self.calculate_stability(away_team, as_of_date)

        # Determine more stable team
        if home_stability.stability_score > away_stability.stability_score:
            more_stable = home_team
            differential = (
                home_stability.stability_score - away_stability.stability_score
            )
        else:
            more_stable = away_team
            differential = (
                away_stability.stability_score - home_stability.stability_score
            )

        # Assess regression risk
        home_regression = self._assess_regression_risk(home_stability)
        away_regression = self._assess_regression_risk(away_stability)

        # Calculate confidence modifier
        # More stability = slight confidence boost
        modifier = self._calculate_confidence_modifier(
            home_stability, away_stability
        )

        return MatchupStability(
            home_team=home_team,
            away_team=away_team,
            home_stability=home_stability,
            away_stability=away_stability,
            more_stable_team=more_stable,
            stability_differential=differential,
            home_regression_risk=home_regression,
            away_regression_risk=away_regression,
            stability_confidence_modifier=modifier,
        )

    def _assess_regression_risk(self, stability: StabilityMetrics) -> str:
        """Assess regression risk based on PDO and trend."""
        pdo = stability.pdo_current

        if pdo > self.PDO_EXTREME_HIGH or pdo < self.PDO_EXTREME_LOW:
            return "high"
        elif pdo > self.PDO_STABLE_HIGH or pdo < self.PDO_STABLE_LOW:
            return "medium"
        else:
            return "low"

    def _calculate_confidence_modifier(
        self,
        home_stability: StabilityMetrics,
        away_stability: StabilityMetrics,
    ) -> float:
        """
        Calculate confidence modifier based on stability comparison.

        Returns modifier between -0.05 and +0.05.
        """
        # Compare stability scores
        diff = abs(home_stability.stability_score - away_stability.stability_score)

        # Large stability difference = potential adjustment
        if diff > 30:
            return 0.05  # Boost confidence on more stable side
        elif diff > 15:
            return 0.02
        else:
            return 0.0

    def apply_stability_adjustment(
        self,
        pick_team: str,
        matchup_stability: MatchupStability,
        base_probability: float,
    ) -> tuple[float, list[str]]:
        """
        Apply stability adjustment to pick probability.

        Returns:
            Tuple of (adjusted_probability, adjustment_reasons).
        """
        adjustments = []
        adjusted_prob = base_probability

        # Get stability for picked team
        if pick_team == matchup_stability.home_team:
            pick_stability = matchup_stability.home_stability
            opp_stability = matchup_stability.away_stability
            pick_regression = matchup_stability.home_regression_risk
            opp_regression = matchup_stability.away_regression_risk
        else:
            pick_stability = matchup_stability.away_stability
            opp_stability = matchup_stability.home_stability
            pick_regression = matchup_stability.away_regression_risk
            opp_regression = matchup_stability.home_regression_risk

        # Boost if picking more stable team
        if pick_stability.stability_score > opp_stability.stability_score + 15:
            adjusted_prob += 0.02
            adjustments.append("Stability advantage (+2%)")

        # Penalize if picking team with high regression risk
        if pick_regression == "high":
            adjusted_prob -= 0.03
            adjustments.append("High PDO regression risk (-3%)")
        elif pick_regression == "medium":
            adjusted_prob -= 0.01
            adjustments.append("PDO regression possible (-1%)")

        # Boost if opponent has high regression risk
        if opp_regression == "high":
            adjusted_prob += 0.02
            adjustments.append("Opponent regression likely (+2%)")

        # Clamp probability
        adjusted_prob = max(0.30, min(0.80, adjusted_prob))

        return adjusted_prob, adjustments

    def rank_by_stability(
        self,
        picks: list,
    ) -> list:
        """
        Re-rank picks using stability as tie-breaker.

        For picks with similar edge (within 1%), use stability to break ties.

        Args:
            picks: List of RankedPick objects.

        Returns:
            Re-ranked list with stability considered.
        """
        if len(picks) <= 1:
            return picks

        # Group picks by similar edge (within 1%)
        groups = []
        current_group = [picks[0]]

        for pick in picks[1:]:
            if abs(pick.edge - current_group[0].edge) <= 0.01:
                current_group.append(pick)
            else:
                groups.append(current_group)
                current_group = [pick]

        groups.append(current_group)

        # Within each group, sort by stability
        result = []
        for group in groups:
            if len(group) == 1:
                result.extend(group)
            else:
                # Get stability for each pick in group
                with_stability = []
                for pick in group:
                    stability = self.calculate_stability(pick.pick_team)
                    with_stability.append((pick, stability.stability_score))

                # Sort by stability descending
                with_stability.sort(key=lambda x: x[1], reverse=True)
                result.extend([ws[0] for ws in with_stability])

        # Re-assign ranks
        for i, pick in enumerate(result, 1):
            pick.rank = i

        return result


def check_matchup_stability(
    home_team: str,
    away_team: str,
    as_of_date: Optional[date] = None,
) -> MatchupStability:
    """Convenience function to check matchup stability."""
    checker = StabilityChecker()
    return checker.compare_stability(home_team, away_team, as_of_date)
