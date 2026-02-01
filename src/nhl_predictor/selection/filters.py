"""Stay Away Filter and game filtering logic.

Filters out high-risk/low-value games from consideration.
"""

import logging
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from typing import Optional

from ..models.database import get_db
from ..models.schema import Game, GoalieStats
from ..features.schedule_analyzer import ScheduleAnalyzer
from ..features.gsax_calculator import GSAxCalculator
from ..prediction.probability_engine import ProbabilityEngine

logger = logging.getLogger(__name__)


@dataclass
class FilterResult:
    """Result of filtering a game."""

    game_id: int
    home_team: str
    away_team: str
    passed: bool
    filtered_reason: Optional[str] = None
    risk_flags: list = field(default_factory=list)


@dataclass
class FilteredGame:
    """A game that passed all filters."""

    game_id: int
    home_team: str
    away_team: str
    game_date: date
    start_time: Optional[datetime]

    # Goalie info
    home_goalie: Optional[str]
    away_goalie: Optional[str]
    home_goalie_confirmed: bool
    away_goalie_confirmed: bool

    # Model outputs
    home_win_prob: float
    away_win_prob: float

    # Risk assessment
    risk_level: str  # "low", "medium", "high"
    risk_flags: list


class StayAwayFilter:
    """Filters games based on risk and data quality criteria."""

    # Minimum probability threshold (avoid coin flips)
    MIN_MODEL_PROBABILITY = 0.53

    # Minimum games for reliable data
    MIN_GAMES_PLAYED = 10

    # Time threshold for late injury news (hours before game)
    LATE_INJURY_THRESHOLD = 2

    def __init__(self):
        """Initialize filter with required analyzers."""
        self.db = get_db()
        self.schedule_analyzer = ScheduleAnalyzer()
        self.gsax_calculator = GSAxCalculator()
        self.probability_engine = ProbabilityEngine()

    def filter_game(
        self,
        home_team: str,
        away_team: str,
        game_date: date,
        game_id: Optional[int] = None,
    ) -> FilterResult:
        """
        Apply all filters to a single game.

        Args:
            home_team: Home team code.
            away_team: Away team code.
            game_date: Date of the game.
            game_id: NHL game ID.

        Returns:
            FilterResult indicating if game passed filters.
        """
        risk_flags = []
        filtered_reason = None

        # 1. Check goalie confirmation status
        goalie_result = self._check_goalie_status(home_team, away_team, game_date)
        if goalie_result["filter"]:
            return FilterResult(
                game_id=game_id or 0,
                home_team=home_team,
                away_team=away_team,
                passed=False,
                filtered_reason=goalie_result["reason"],
                risk_flags=goalie_result.get("flags", []),
            )
        risk_flags.extend(goalie_result.get("flags", []))

        # 2. Check for extreme schedule disadvantage with no value
        schedule_result = self._check_schedule_value(home_team, away_team, game_date)
        if schedule_result["filter"]:
            return FilterResult(
                game_id=game_id or 0,
                home_team=home_team,
                away_team=away_team,
                passed=False,
                filtered_reason=schedule_result["reason"],
                risk_flags=risk_flags + schedule_result.get("flags", []),
            )
        risk_flags.extend(schedule_result.get("flags", []))

        # 3. Check model probability threshold
        prob_result = self._check_probability_threshold(home_team, away_team, game_date)
        if prob_result["filter"]:
            return FilterResult(
                game_id=game_id or 0,
                home_team=home_team,
                away_team=away_team,
                passed=False,
                filtered_reason=prob_result["reason"],
                risk_flags=risk_flags,
            )

        # 4. Check for early season data quality
        data_result = self._check_data_quality(home_team, away_team, game_date)
        risk_flags.extend(data_result.get("flags", []))

        return FilterResult(
            game_id=game_id or 0,
            home_team=home_team,
            away_team=away_team,
            passed=True,
            filtered_reason=None,
            risk_flags=risk_flags,
        )

    def _check_goalie_status(
        self,
        home_team: str,
        away_team: str,
        game_date: date,
    ) -> dict:
        """Check if goalies are confirmed."""
        flags = []

        with self.db.session_scope() as session:
            # Check home goalie
            home_goalie = session.query(GoalieStats).filter(
                GoalieStats.team == home_team,
                GoalieStats.date == game_date,
                GoalieStats.is_starter == True,
            ).first()

            away_goalie = session.query(GoalieStats).filter(
                GoalieStats.team == away_team,
                GoalieStats.date == game_date,
                GoalieStats.is_starter == True,
            ).first()

            # Check if goalies are confirmed or at least expected
            home_confirmed = (
                home_goalie and
                home_goalie.confirmation_status == "confirmed"
            )
            away_confirmed = (
                away_goalie and
                away_goalie.confirmation_status == "confirmed"
            )
            # Also accept "expected" as valid (just not as confident)
            home_has_goalie = (
                home_goalie and
                home_goalie.confirmation_status in ("confirmed", "expected")
            )
            away_has_goalie = (
                away_goalie and
                away_goalie.confirmation_status in ("confirmed", "expected")
            )

            # Never hard-filter on goalie data — just flag the risk.
            # This allows predictions to run even on a fresh DB or when
            # goalie data hasn't been scraped yet.
            if not home_has_goalie and not away_has_goalie:
                flags.append("NO_GOALIE_INFO")
            elif not home_has_goalie:
                flags.append("HOME_GOALIE_MISSING")
            elif not home_confirmed:
                flags.append("HOME_GOALIE_EXPECTED")

            if not away_has_goalie and home_has_goalie:
                # Only add if we didn't already add NO_GOALIE_INFO
                flags.append("AWAY_GOALIE_MISSING")
            elif away_has_goalie and not away_confirmed:
                flags.append("AWAY_GOALIE_EXPECTED")

            return {"filter": False, "flags": flags}

    def _check_schedule_value(
        self,
        home_team: str,
        away_team: str,
        game_date: date,
    ) -> dict:
        """Check for extreme schedule spots with no betting value."""
        flags = []

        matchup = self.schedule_analyzer.get_matchup_schedule_analysis(
            home_team, away_team, game_date
        )

        # Scheduled loss scenario
        if matchup.is_scheduled_loss:
            flags.append("SCHEDULED_LOSS")

            # Check if this is a heavy favorite situation (no value)
            prob = self.probability_engine.calculate_probability(
                home_team, away_team, game_date
            )

            if prob:
                # If home is already huge favorite, odds are likely bad
                if prob.home_win_prob > 0.70:
                    return {
                        "filter": True,
                        "reason": "Scheduled loss but home already heavy favorite (no value)",
                        "flags": flags,
                    }

        # Extreme fatigue differential
        if matchup.fatigue_differential > 0.5:
            flags.append("EXTREME_FATIGUE_DIFF")

        return {"filter": False, "flags": flags}

    def _check_probability_threshold(
        self,
        home_team: str,
        away_team: str,
        game_date: date,
    ) -> dict:
        """Check if either side meets minimum probability threshold."""
        prob = self.probability_engine.calculate_probability(
            home_team, away_team, game_date
        )

        if not prob:
            return {
                "filter": True,
                "reason": "Could not calculate probability",
            }

        max_prob = max(prob.home_win_prob, prob.away_win_prob)

        if max_prob < self.MIN_MODEL_PROBABILITY:
            return {
                "filter": True,
                "reason": f"Max probability {max_prob:.1%} below threshold {self.MIN_MODEL_PROBABILITY:.1%}",
            }

        return {"filter": False}

    def _check_data_quality(
        self,
        home_team: str,
        away_team: str,
        game_date: date,
    ) -> dict:
        """Check data quality and flag early season games."""
        flags = []

        with self.db.session_scope() as session:
            from ..models.schema import TeamDailyStats

            # Check games played for each team
            home_stats = session.query(TeamDailyStats).filter(
                TeamDailyStats.team == home_team,
                TeamDailyStats.date <= game_date,
            ).order_by(TeamDailyStats.date.desc()).first()

            away_stats = session.query(TeamDailyStats).filter(
                TeamDailyStats.team == away_team,
                TeamDailyStats.date <= game_date,
            ).order_by(TeamDailyStats.date.desc()).first()

            home_games = home_stats.games_played if home_stats else 0
            away_games = away_stats.games_played if away_stats else 0

            if home_games < self.MIN_GAMES_PLAYED:
                flags.append(f"HOME_SMALL_SAMPLE ({home_games} games)")

            if away_games < self.MIN_GAMES_PLAYED:
                flags.append(f"AWAY_SMALL_SAMPLE ({away_games} games)")

            return {"flags": flags}

    def filter_daily_games(
        self,
        game_date: Optional[date] = None,
    ) -> tuple[list[FilteredGame], list[FilterResult]]:
        """
        Filter all games for a given date.

        Args:
            game_date: Date to filter games for.

        Returns:
            Tuple of (passed_games, filtered_games).
        """
        if game_date is None:
            game_date = date.today()

        passed = []
        filtered = []

        with self.db.session_scope() as session:
            games = session.query(Game).filter(
                Game.date == game_date
            ).all()

            for game in games:
                result = self.filter_game(
                    game.home_team,
                    game.away_team,
                    game_date,
                    game.game_id,
                )

                if result.passed:
                    # Get additional info for passed games
                    prob = self.probability_engine.calculate_probability(
                        game.home_team, game.away_team, game_date
                    )

                    # Get goalie info
                    home_goalie_info = self._get_goalie_info(game.home_team, game_date)
                    away_goalie_info = self._get_goalie_info(game.away_team, game_date)

                    # Assess risk level
                    risk_level = self._assess_risk_level(result.risk_flags)

                    passed.append(FilteredGame(
                        game_id=game.game_id,
                        home_team=game.home_team,
                        away_team=game.away_team,
                        game_date=game_date,
                        start_time=game.start_time,
                        home_goalie=home_goalie_info["name"],
                        away_goalie=away_goalie_info["name"],
                        home_goalie_confirmed=home_goalie_info["confirmed"],
                        away_goalie_confirmed=away_goalie_info["confirmed"],
                        home_win_prob=prob.home_win_prob if prob else 0.5,
                        away_win_prob=prob.away_win_prob if prob else 0.5,
                        risk_level=risk_level,
                        risk_flags=result.risk_flags,
                    ))
                else:
                    filtered.append(result)

        logger.info(
            f"Filtered {len(filtered)} games, {len(passed)} passed for {game_date}"
        )

        return passed, filtered

    def _get_goalie_info(self, team: str, game_date: date) -> dict:
        """Get goalie info for a team."""
        with self.db.session_scope() as session:
            goalie = session.query(GoalieStats).filter(
                GoalieStats.team == team,
                GoalieStats.date == game_date,
                GoalieStats.is_starter == True,
            ).first()

            if goalie:
                return {
                    "name": goalie.player_name,
                    "confirmed": goalie.confirmation_status == "confirmed",
                }

            return {"name": None, "confirmed": False}

    def _assess_risk_level(self, flags: list) -> str:
        """Assess overall risk level from flags."""
        high_risk_flags = [
            "NO_GOALIE_INFO",
            "EXTREME_FATIGUE_DIFF",
            "HOME_GOALIE_MISSING",
            "AWAY_GOALIE_MISSING",
        ]

        medium_risk_flags = [
            "SCHEDULED_LOSS",
            "HOME_GOALIE_EXPECTED",
            "AWAY_GOALIE_EXPECTED",
        ]

        for flag in flags:
            if any(hf in flag for hf in high_risk_flags):
                return "high"

        for flag in flags:
            if any(mf in flag for mf in medium_risk_flags):
                return "medium"

        if any("SMALL_SAMPLE" in f for f in flags):
            return "medium"

        return "low"


def filter_games(game_date: Optional[date] = None) -> tuple[list, list]:
    """Convenience function to filter daily games."""
    filter_obj = StayAwayFilter()
    return filter_obj.filter_daily_games(game_date)
