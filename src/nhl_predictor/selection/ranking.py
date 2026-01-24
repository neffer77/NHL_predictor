"""Edge-Based Ranking Module.

Ranks games by calculated edge (model probability vs market implied).
"""

import logging
from dataclasses import dataclass
from datetime import date
from typing import Optional

from ..models.database import get_db
from ..models.schema import Game
from ..prediction.probability_engine import ProbabilityEngine
from ..prediction.odds_calculator import EdgeCalculator, EdgeAnalysis
from ..prediction.kelly_criterion import KellyCalculator, KellyResult

logger = logging.getLogger(__name__)


@dataclass
class RankedPick:
    """A ranked pick with all relevant data."""

    # Game info
    game_id: int
    home_team: str
    away_team: str
    game_date: date
    start_time: Optional[str]

    # Pick details
    pick_team: str
    opponent: str
    pick_side: str  # "home" or "away"

    # Model probabilities
    model_probability: float
    market_probability: float

    # Edge metrics
    edge: float  # Percentage edge
    edge_percentage: float  # Same as edge, for display

    # Kelly metrics
    kelly_score: float
    kelly_half: float
    kelly_quarter: float
    confidence_rating: str  # "lock", "strong", "standard", "lean"
    confidence_score: float  # 0-100

    # Expected value
    expected_value: float

    # Ranking
    rank: int

    # Risk flags from filtering
    risk_flags: list


class EdgeRanker:
    """Ranks games by edge and Kelly score."""

    # Minimum edge to consider a pick
    MIN_EDGE_THRESHOLD = 0.02  # 2% edge

    # Weight for combining edge and probability for ranking
    EDGE_WEIGHT = 0.6
    PROBABILITY_WEIGHT = 0.4

    def __init__(self):
        """Initialize ranker with required components."""
        self.db = get_db()
        self.probability_engine = ProbabilityEngine()
        self.edge_calculator = EdgeCalculator()
        self.kelly_calculator = KellyCalculator()

    def rank_games(
        self,
        games: list,
        market_odds: Optional[dict] = None,
    ) -> list[RankedPick]:
        """
        Rank games by edge.

        Args:
            games: List of FilteredGame objects from StayAwayFilter.
            market_odds: Optional dict mapping game_id to odds data.

        Returns:
            List of RankedPick objects sorted by edge.
        """
        ranked = []

        for game in games:
            # Calculate edge for home and away
            home_edge = self._calculate_edge(
                game.home_win_prob,
                market_odds.get(game.game_id, {}).get("home_implied", 0.5)
                if market_odds else 0.5,
            )
            away_edge = self._calculate_edge(
                game.away_win_prob,
                market_odds.get(game.game_id, {}).get("away_implied", 0.5)
                if market_odds else 0.5,
            )

            # Pick the side with more edge
            if home_edge >= away_edge:
                pick_side = "home"
                pick_team = game.home_team
                opponent = game.away_team
                model_prob = game.home_win_prob
                market_prob = (
                    market_odds.get(game.game_id, {}).get("home_implied", 0.5)
                    if market_odds else 0.5
                )
                edge = home_edge
            else:
                pick_side = "away"
                pick_team = game.away_team
                opponent = game.home_team
                model_prob = game.away_win_prob
                market_prob = (
                    market_odds.get(game.game_id, {}).get("away_implied", 0.5)
                    if market_odds else 0.5
                )
                edge = away_edge

            # Skip if no meaningful edge
            if edge < self.MIN_EDGE_THRESHOLD:
                continue

            # Get Kelly calculation
            # Convert market prob to decimal odds for Kelly
            decimal_odds = 1 / market_prob if market_prob > 0 else 2.0
            kelly = self.kelly_calculator.calculate_kelly(
                model_prob, decimal_odds, "decimal"
            )

            ranked.append(RankedPick(
                game_id=game.game_id,
                home_team=game.home_team,
                away_team=game.away_team,
                game_date=game.game_date,
                start_time=str(game.start_time) if game.start_time else None,
                pick_team=pick_team,
                opponent=opponent,
                pick_side=pick_side,
                model_probability=model_prob,
                market_probability=market_prob,
                edge=edge,
                edge_percentage=edge * 100,
                kelly_score=kelly.full_kelly,
                kelly_half=kelly.half_kelly,
                kelly_quarter=kelly.quarter_kelly,
                confidence_rating=kelly.confidence_rating,
                confidence_score=kelly.confidence_score,
                expected_value=kelly.expected_value,
                rank=0,  # Will be set after sorting
                risk_flags=game.risk_flags,
            ))

        # Sort by composite score (edge + probability weighted)
        ranked.sort(
            key=lambda x: self._calculate_ranking_score(x),
            reverse=True,
        )

        # Assign ranks
        for i, pick in enumerate(ranked, 1):
            pick.rank = i

        return ranked

    def _calculate_edge(
        self,
        model_prob: float,
        market_prob: float,
    ) -> float:
        """Calculate edge as difference between model and market."""
        return model_prob - market_prob

    def _calculate_ranking_score(self, pick: RankedPick) -> float:
        """
        Calculate composite ranking score.

        Combines edge with raw probability for ranking.
        Higher edge games should rank higher, but also
        favor higher probability plays.
        """
        # Normalize edge (0-20% edge maps to 0-1)
        edge_score = min(1.0, pick.edge / 0.20)

        # Normalize probability (50-75% maps to 0-1)
        prob_score = (pick.model_probability - 0.50) / 0.25
        prob_score = max(0, min(1.0, prob_score))

        return (
            self.EDGE_WEIGHT * edge_score +
            self.PROBABILITY_WEIGHT * prob_score
        )

    def get_value_picks(
        self,
        games: list,
        market_odds: Optional[dict] = None,
        min_edge: float = 0.03,
        min_confidence: str = "standard",
    ) -> list[RankedPick]:
        """
        Get only value picks meeting thresholds.

        Args:
            games: List of FilteredGame objects.
            market_odds: Market odds data.
            min_edge: Minimum edge required.
            min_confidence: Minimum confidence rating.

        Returns:
            Filtered list of RankedPick objects.
        """
        ranked = self.rank_games(games, market_odds)

        # Filter by edge
        filtered = [p for p in ranked if p.edge >= min_edge]

        # Filter by confidence
        confidence_levels = ["lock", "strong", "standard", "lean", "pass"]
        min_level = confidence_levels.index(min_confidence)
        filtered = [
            p for p in filtered
            if confidence_levels.index(p.confidence_rating) <= min_level
        ]

        return filtered

    def get_contrarian_picks(
        self,
        games: list,
        market_odds: Optional[dict] = None,
    ) -> list[RankedPick]:
        """
        Find contrarian picks where model disagrees with market.

        These are picks where the model sees value on the underdog
        or significant edge against public perception.

        Returns:
            List of contrarian RankedPick objects.
        """
        ranked = self.rank_games(games, market_odds)

        contrarian = []
        for pick in ranked:
            # Contrarian = model favors different side than market
            # Market underdog (prob < 0.5) but model likes them
            if pick.market_probability < 0.48 and pick.model_probability > 0.52:
                contrarian.append(pick)

        return contrarian

    def format_pick_card(self, pick: RankedPick) -> dict:
        """
        Format a pick for display.

        Returns:
            Dict with formatted pick data.
        """
        return {
            "rank": f"#{pick.rank}",
            "matchup": f"{pick.away_team} @ {pick.home_team}",
            "pick": pick.pick_team,
            "vs": pick.opponent,
            "confidence": pick.confidence_rating.upper(),
            "model_prob": f"{pick.model_probability:.1%}",
            "market_prob": f"{pick.market_probability:.1%}",
            "edge": f"+{pick.edge:.1%}",
            "kelly": f"{pick.kelly_score:.1%}",
            "ev": f"{pick.expected_value:+.2%}",
            "score": round(pick.confidence_score, 1),
            "flags": pick.risk_flags if pick.risk_flags else ["CLEAN"],
        }

    def get_ranking_summary(self, picks: list[RankedPick]) -> dict:
        """
        Get summary statistics for ranked picks.

        Returns:
            Dict with summary stats.
        """
        if not picks:
            return {
                "total_picks": 0,
                "avg_edge": 0,
                "avg_probability": 0,
                "confidence_breakdown": {},
            }

        confidence_counts = {}
        for pick in picks:
            rating = pick.confidence_rating
            confidence_counts[rating] = confidence_counts.get(rating, 0) + 1

        return {
            "total_picks": len(picks),
            "avg_edge": sum(p.edge for p in picks) / len(picks),
            "avg_probability": sum(p.model_probability for p in picks) / len(picks),
            "avg_kelly": sum(p.kelly_score for p in picks) / len(picks),
            "confidence_breakdown": confidence_counts,
            "best_pick": self.format_pick_card(picks[0]) if picks else None,
        }


def rank_daily_games(
    games: list,
    market_odds: Optional[dict] = None,
) -> list[RankedPick]:
    """Convenience function to rank games."""
    ranker = EdgeRanker()
    return ranker.rank_games(games, market_odds)
