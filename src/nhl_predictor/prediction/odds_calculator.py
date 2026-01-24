"""Market Odds Integrator and Edge Calculator.

Handles conversion of betting odds to implied probabilities
and calculates edges between model and market.
"""

import logging
from dataclasses import dataclass
from datetime import date
from typing import Optional, Union

from .probability_engine import ProbabilityEngine, WinProbability

logger = logging.getLogger(__name__)


@dataclass
class MarketOdds:
    """Market odds for a game."""

    home_team: str
    away_team: str

    # Original odds format
    home_odds: float  # American odds (e.g., -150, +130)
    away_odds: float

    # Implied probabilities
    home_implied_prob: float
    away_implied_prob: float

    # Juice/vig
    total_implied: float  # Should be > 1.0 due to vig
    vig_percentage: float


@dataclass
class EdgeAnalysis:
    """Edge analysis comparing model to market."""

    home_team: str
    away_team: str
    game_date: date

    # Model probabilities
    model_home_prob: float
    model_away_prob: float

    # Market probabilities
    market_home_prob: float
    market_away_prob: float

    # Edge calculations
    home_edge: float  # Model - Market (positive = value on home)
    away_edge: float  # Model - Market (positive = value on away)

    # Value assessment
    has_value: bool
    value_side: Optional[str]  # "home", "away", or None
    edge_magnitude: float  # Absolute edge on value side

    # Edge categories
    edge_category: str  # "strong", "moderate", "weak", "none"


class OddsConverter:
    """Converts between different odds formats."""

    @staticmethod
    def american_to_probability(odds: float) -> float:
        """
        Convert American odds to implied probability.

        Args:
            odds: American odds (e.g., -150, +130)

        Returns:
            Implied probability (0 to 1)
        """
        if odds == 0:
            return 0.5

        if odds > 0:
            # Underdog: +130 means risk 100 to win 130
            return 100.0 / (odds + 100.0)
        else:
            # Favorite: -150 means risk 150 to win 100
            return abs(odds) / (abs(odds) + 100.0)

    @staticmethod
    def probability_to_american(prob: float) -> float:
        """
        Convert probability to American odds.

        Args:
            prob: Probability (0 to 1)

        Returns:
            American odds
        """
        if prob <= 0 or prob >= 1:
            return 0.0

        if prob >= 0.5:
            # Favorite
            return -100 * prob / (1 - prob)
        else:
            # Underdog
            return 100 * (1 - prob) / prob

    @staticmethod
    def decimal_to_probability(odds: float) -> float:
        """
        Convert decimal odds to implied probability.

        Args:
            odds: Decimal odds (e.g., 1.67, 2.30)

        Returns:
            Implied probability
        """
        if odds <= 1:
            return 1.0
        return 1.0 / odds

    @staticmethod
    def decimal_to_american(odds: float) -> float:
        """
        Convert decimal odds to American odds.

        Args:
            odds: Decimal odds

        Returns:
            American odds
        """
        if odds >= 2.0:
            return (odds - 1) * 100
        else:
            return -100 / (odds - 1)

    @staticmethod
    def remove_vig(home_implied: float, away_implied: float) -> tuple[float, float]:
        """
        Remove vig from implied probabilities to get "true" probabilities.

        Args:
            home_implied: Home implied probability
            away_implied: Away implied probability

        Returns:
            Tuple of (home_true_prob, away_true_prob)
        """
        total = home_implied + away_implied

        if total <= 0:
            return 0.5, 0.5

        return home_implied / total, away_implied / total


class EdgeCalculator:
    """Calculates betting edges between model and market."""

    # Edge thresholds
    STRONG_EDGE = 0.05  # 5%+ edge
    MODERATE_EDGE = 0.02  # 2-5% edge
    WEAK_EDGE = 0.00  # 0-2% edge

    def __init__(self):
        """Initialize edge calculator."""
        self.probability_engine = ProbabilityEngine()
        self.converter = OddsConverter()

    def parse_market_odds(
        self,
        home_team: str,
        away_team: str,
        home_odds: float,
        away_odds: float,
        odds_format: str = "american",
    ) -> MarketOdds:
        """
        Parse market odds into MarketOdds object.

        Args:
            home_team: Home team code.
            away_team: Away team code.
            home_odds: Home team odds.
            away_odds: Away team odds.
            odds_format: "american" or "decimal"

        Returns:
            MarketOdds object.
        """
        if odds_format == "decimal":
            home_implied = self.converter.decimal_to_probability(home_odds)
            away_implied = self.converter.decimal_to_probability(away_odds)
        else:
            home_implied = self.converter.american_to_probability(home_odds)
            away_implied = self.converter.american_to_probability(away_odds)

        total_implied = home_implied + away_implied
        vig = (total_implied - 1.0) * 100 if total_implied > 1 else 0.0

        return MarketOdds(
            home_team=home_team,
            away_team=away_team,
            home_odds=home_odds,
            away_odds=away_odds,
            home_implied_prob=home_implied,
            away_implied_prob=away_implied,
            total_implied=total_implied,
            vig_percentage=vig,
        )

    def calculate_edge(
        self,
        home_team: str,
        away_team: str,
        home_odds: float,
        away_odds: float,
        game_date: Optional[date] = None,
        odds_format: str = "american",
        remove_vig: bool = True,
    ) -> Optional[EdgeAnalysis]:
        """
        Calculate edge between model and market.

        Args:
            home_team: Home team code.
            away_team: Away team code.
            home_odds: Home team odds.
            away_odds: Away team odds.
            game_date: Date of the game.
            odds_format: "american" or "decimal"
            remove_vig: Whether to remove vig from market odds.

        Returns:
            EdgeAnalysis object.
        """
        if game_date is None:
            game_date = date.today()

        # Get model probability
        model_prob = self.probability_engine.calculate_probability(
            home_team, away_team, game_date
        )

        if not model_prob:
            logger.warning(f"Could not calculate model probability for {away_team} @ {home_team}")
            return None

        # Parse market odds
        market = self.parse_market_odds(
            home_team, away_team, home_odds, away_odds, odds_format
        )

        # Get market probabilities (optionally remove vig)
        if remove_vig:
            market_home, market_away = self.converter.remove_vig(
                market.home_implied_prob, market.away_implied_prob
            )
        else:
            market_home = market.home_implied_prob
            market_away = market.away_implied_prob

        # Calculate edges
        home_edge = model_prob.home_win_prob - market_home
        away_edge = model_prob.away_win_prob - market_away

        # Determine value side
        has_value = False
        value_side = None
        edge_magnitude = 0.0

        if home_edge > self.WEAK_EDGE:
            has_value = True
            value_side = "home"
            edge_magnitude = home_edge
        elif away_edge > self.WEAK_EDGE:
            has_value = True
            value_side = "away"
            edge_magnitude = away_edge

        # Categorize edge
        if edge_magnitude >= self.STRONG_EDGE:
            edge_category = "strong"
        elif edge_magnitude >= self.MODERATE_EDGE:
            edge_category = "moderate"
        elif edge_magnitude > 0:
            edge_category = "weak"
        else:
            edge_category = "none"

        return EdgeAnalysis(
            home_team=home_team,
            away_team=away_team,
            game_date=game_date,
            model_home_prob=model_prob.home_win_prob,
            model_away_prob=model_prob.away_win_prob,
            market_home_prob=market_home,
            market_away_prob=market_away,
            home_edge=home_edge,
            away_edge=away_edge,
            has_value=has_value,
            value_side=value_side,
            edge_magnitude=edge_magnitude,
            edge_category=edge_category,
        )

    def get_edge_summary(self, edge: EdgeAnalysis) -> dict:
        """Get human-readable edge summary."""
        pick = edge.value_side if edge.has_value else "pass"

        return {
            "matchup": f"{edge.away_team} @ {edge.home_team}",
            "pick": pick.upper() if pick != "pass" else "PASS",
            "pick_team": (
                edge.home_team if pick == "home"
                else edge.away_team if pick == "away"
                else None
            ),
            "model_prob": (
                f"{edge.model_home_prob:.1%}" if pick == "home"
                else f"{edge.model_away_prob:.1%}" if pick == "away"
                else "N/A"
            ),
            "market_prob": (
                f"{edge.market_home_prob:.1%}" if pick == "home"
                else f"{edge.market_away_prob:.1%}" if pick == "away"
                else "N/A"
            ),
            "edge": f"+{edge.edge_magnitude:.1%}" if edge.has_value else "0.0%",
            "edge_category": edge.edge_category,
        }

    def find_value_games(
        self,
        games_with_odds: list[dict],
        min_edge: float = 0.02,
    ) -> list[EdgeAnalysis]:
        """
        Find games with positive edge.

        Args:
            games_with_odds: List of dicts with game info and odds.
            min_edge: Minimum edge to consider valuable.

        Returns:
            List of EdgeAnalysis objects with positive edge.
        """
        value_games = []

        for game in games_with_odds:
            edge = self.calculate_edge(
                game["home_team"],
                game["away_team"],
                game["home_odds"],
                game["away_odds"],
                game.get("date"),
            )

            if edge and edge.edge_magnitude >= min_edge:
                value_games.append(edge)

        # Sort by edge magnitude (descending)
        return sorted(value_games, key=lambda x: x.edge_magnitude, reverse=True)


def calculate_edge(
    home_team: str,
    away_team: str,
    home_odds: float,
    away_odds: float,
    game_date: Optional[date] = None,
) -> Optional[EdgeAnalysis]:
    """Convenience function to calculate edge."""
    calculator = EdgeCalculator()
    return calculator.calculate_edge(
        home_team, away_team, home_odds, away_odds, game_date
    )


def american_to_probability(odds: float) -> float:
    """Convenience function for odds conversion."""
    return OddsConverter.american_to_probability(odds)


def probability_to_american(prob: float) -> float:
    """Convenience function for odds conversion."""
    return OddsConverter.probability_to_american(prob)
