"""Referee bias analyzer and integrator.

Analyzes referee assignments and calculates bias adjustments for predictions.
"""

import logging
from dataclasses import dataclass
from datetime import date
from typing import Optional

from ..models.database import get_db
from ..models.schema import Referee, RefereeAssignment

logger = logging.getLogger(__name__)


@dataclass
class RefereeBiasAnalysis:
    """Referee bias analysis for a game."""

    referees: list[str]
    avg_home_win_pct: float
    avg_penalties_per_game: float

    # Deviations from league average
    home_bias: float  # Positive = favors home
    penalty_deviation: float  # Positive = more penalties

    # Tags
    bias_tag: str  # "neutral", "home_friendly", "away_friendly"
    event_level: str  # "low", "average", "high"

    # Adjustment factors
    home_adjustment: float  # Multiplier for home team (0.97 - 1.03)
    pp_team_boost: Optional[str]  # Team that benefits from high penalties


class RefereeAnalyzer:
    """Analyzes referee assignments and their impact."""

    # League averages
    LEAGUE_AVG_HOME_WIN_PCT = 0.54
    LEAGUE_AVG_PENALTIES = 7.5

    # Thresholds
    HOME_BIAS_THRESHOLD = 0.05  # 5% above average for "home_friendly"
    HIGH_PENALTY_THRESHOLD = 1.5  # penalties above avg for "high_event"
    LOW_PENALTY_THRESHOLD = -1.5  # penalties below avg for "low_event"

    # Adjustment ranges
    MAX_HOME_ADJUSTMENT = 1.03
    MIN_HOME_ADJUSTMENT = 0.97

    def __init__(self):
        self.db = get_db()

    def get_game_referee_analysis(
        self,
        home_team: str,
        away_team: str,
        game_date: date,
    ) -> RefereeBiasAnalysis:
        """
        Get referee bias analysis for a game.

        Args:
            home_team: Home team code.
            away_team: Away team code.
            game_date: Date of the game.

        Returns:
            RefereeBiasAnalysis for the game.
        """
        with self.db.session_scope() as session:
            # Get referee assignments for this game
            assignments = session.query(RefereeAssignment).filter(
                RefereeAssignment.date == game_date,
                RefereeAssignment.home_team == home_team,
                RefereeAssignment.away_team == away_team,
                RefereeAssignment.role == "referee",
            ).all()

            if not assignments:
                # No referee data, return neutral
                return self._create_neutral_analysis()

            # Get referee profiles
            ref_names = [a.referee_name for a in assignments]
            profiles = []

            for name in ref_names:
                ref = session.query(Referee).filter(
                    Referee.name == name
                ).first()
                if ref:
                    profiles.append(ref)

            if not profiles:
                return self._create_neutral_analysis()

            return self._analyze_referees(profiles, home_team, away_team)

    def _create_neutral_analysis(self) -> RefereeBiasAnalysis:
        """Create a neutral analysis when no referee data."""
        return RefereeBiasAnalysis(
            referees=[],
            avg_home_win_pct=self.LEAGUE_AVG_HOME_WIN_PCT,
            avg_penalties_per_game=self.LEAGUE_AVG_PENALTIES,
            home_bias=0.0,
            penalty_deviation=0.0,
            bias_tag="neutral",
            event_level="average",
            home_adjustment=1.0,
            pp_team_boost=None,
        )

    def _analyze_referees(
        self,
        profiles: list,
        home_team: str,
        away_team: str,
    ) -> RefereeBiasAnalysis:
        """Analyze referee profiles and calculate bias."""
        ref_names = [p.name for p in profiles]

        # Calculate averages
        avg_home_pct = sum(
            p.home_win_pct or self.LEAGUE_AVG_HOME_WIN_PCT
            for p in profiles
        ) / len(profiles)

        avg_penalties = sum(
            p.penalties_per_game or self.LEAGUE_AVG_PENALTIES
            for p in profiles
        ) / len(profiles)

        # Calculate deviations
        home_bias = avg_home_pct - self.LEAGUE_AVG_HOME_WIN_PCT
        penalty_deviation = avg_penalties - self.LEAGUE_AVG_PENALTIES

        # Determine bias tag
        if home_bias >= self.HOME_BIAS_THRESHOLD:
            bias_tag = "home_friendly"
        elif home_bias <= -self.HOME_BIAS_THRESHOLD:
            bias_tag = "away_friendly"
        else:
            bias_tag = "neutral"

        # Determine event level
        if penalty_deviation >= self.HIGH_PENALTY_THRESHOLD:
            event_level = "high"
        elif penalty_deviation <= self.LOW_PENALTY_THRESHOLD:
            event_level = "low"
        else:
            event_level = "average"

        # Calculate home adjustment
        # Scale home_bias to adjustment range
        adjustment_range = self.MAX_HOME_ADJUSTMENT - self.MIN_HOME_ADJUSTMENT
        home_adjustment = 1.0 + (home_bias * adjustment_range / self.HOME_BIAS_THRESHOLD)
        home_adjustment = max(
            self.MIN_HOME_ADJUSTMENT,
            min(self.MAX_HOME_ADJUSTMENT, home_adjustment)
        )

        # Determine which team benefits from high penalties
        pp_team_boost = None
        if event_level == "high":
            # Would need PP data to determine - placeholder
            pp_team_boost = None  # To be filled by PP analyzer

        return RefereeBiasAnalysis(
            referees=ref_names,
            avg_home_win_pct=avg_home_pct,
            avg_penalties_per_game=avg_penalties,
            home_bias=home_bias,
            penalty_deviation=penalty_deviation,
            bias_tag=bias_tag,
            event_level=event_level,
            home_adjustment=home_adjustment,
            pp_team_boost=pp_team_boost,
        )

    def get_referee_profile(self, name: str) -> Optional[Referee]:
        """Get a referee's profile from database."""
        with self.db.session_scope() as session:
            return session.query(Referee).filter(
                Referee.name == name
            ).first()

    def update_referee_stats(
        self,
        name: str,
        home_win_pct: float,
        penalties_per_game: float,
        games_officiated: int,
    ) -> None:
        """Update referee statistics."""
        with self.db.session_scope() as session:
            ref = session.query(Referee).filter(
                Referee.name == name
            ).first()

            if ref:
                ref.home_win_pct = home_win_pct
                ref.penalties_per_game = penalties_per_game
                ref.games_officiated = games_officiated
                ref.home_bias = home_win_pct - self.LEAGUE_AVG_HOME_WIN_PCT
                ref.penalty_deviation = penalties_per_game - self.LEAGUE_AVG_PENALTIES

                # Update tags
                if ref.home_bias >= self.HOME_BIAS_THRESHOLD:
                    ref.bias_tag = "home_friendly"
                elif ref.home_bias <= -self.HOME_BIAS_THRESHOLD:
                    ref.bias_tag = "away_friendly"
                else:
                    ref.bias_tag = "neutral"

                if ref.penalty_deviation >= self.HIGH_PENALTY_THRESHOLD:
                    ref.event_level = "high"
                elif ref.penalty_deviation <= self.LOW_PENALTY_THRESHOLD:
                    ref.event_level = "low"
                else:
                    ref.event_level = "average"
            else:
                # Create new referee
                ref = Referee(
                    name=name,
                    games_officiated=games_officiated,
                    home_win_pct=home_win_pct,
                    penalties_per_game=penalties_per_game,
                    home_bias=home_win_pct - self.LEAGUE_AVG_HOME_WIN_PCT,
                    penalty_deviation=penalties_per_game - self.LEAGUE_AVG_PENALTIES,
                )
                session.add(ref)

    def get_high_event_referees(self) -> list:
        """Get referees who call many penalties."""
        with self.db.session_scope() as session:
            return session.query(Referee).filter(
                Referee.event_level == "high"
            ).all()

    def get_home_friendly_referees(self) -> list:
        """Get referees who favor home teams."""
        with self.db.session_scope() as session:
            return session.query(Referee).filter(
                Referee.bias_tag == "home_friendly"
            ).all()


def get_referee_analysis(
    home_team: str,
    away_team: str,
    game_date: date,
) -> RefereeBiasAnalysis:
    """Convenience function to get referee analysis."""
    analyzer = RefereeAnalyzer()
    return analyzer.get_game_referee_analysis(home_team, away_team, game_date)
