"""Schedule analyzer for fatigue and travel impact.

Analyzes rest days, back-to-backs, travel, and circadian factors.
"""

import logging
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from typing import Optional
from zoneinfo import ZoneInfo

from ..models.database import get_db
from ..models.schema import Game
from ..utils.team_mapping import get_team_timezone, TEAM_TIMEZONES

logger = logging.getLogger(__name__)


@dataclass
class TeamScheduleContext:
    """Schedule context for a team entering a game."""

    team: str
    game_date: date

    # Rest
    rest_days: int  # Days since last game
    is_back_to_back: bool  # 0 rest days
    is_three_in_four: bool  # 3 games in 4 nights
    is_four_in_six: bool  # 4 games in 6 nights

    # Travel
    last_game_location: Optional[str]  # Team code of venue
    games_on_road_trip: int  # Consecutive away games
    is_first_home_after_road: bool
    timezone_change: int  # Hours of timezone difference

    # Previous game info
    previous_game_date: Optional[date]
    previous_opponent: Optional[str]
    previous_was_home: Optional[bool]

    # Calculated factors
    fatigue_score: float  # 0-1, higher = more fatigued
    travel_score: float  # 0-1, higher = more travel impact


@dataclass
class ScheduleMatchup:
    """Schedule comparison for a matchup."""

    home_context: TeamScheduleContext
    away_context: TeamScheduleContext

    # Differentials
    rest_advantage: int  # Positive = home has more rest
    is_scheduled_loss: bool  # B2B road team vs rested home
    fatigue_differential: float  # Positive = home more rested

    # Recommendations
    schedule_edge: str  # "home", "away", "neutral"


class ScheduleAnalyzer:
    """Analyzes schedule factors for predictions."""

    # Timezone mappings (hours offset from Eastern)
    TIMEZONE_OFFSETS = {
        "America/New_York": 0,
        "America/Toronto": 0,
        "America/Montreal": 0,
        "America/Detroit": 0,
        "America/Chicago": -1,
        "America/Winnipeg": -1,
        "America/Denver": -2,
        "America/Edmonton": -2,
        "America/Los_Angeles": -3,
        "America/Vancouver": -3,
    }

    def __init__(self):
        self.db = get_db()

    def get_team_schedule_context(
        self,
        team: str,
        game_date: date,
    ) -> TeamScheduleContext:
        """
        Get schedule context for a team entering a game.

        Args:
            team: Team code.
            game_date: Date of the upcoming game.

        Returns:
            TeamScheduleContext with all schedule factors.
        """
        with self.db.session_scope() as session:
            # Get recent games for this team
            recent_games = session.query(Game).filter(
                ((Game.home_team == team) | (Game.away_team == team)),
                Game.date < game_date,
            ).order_by(Game.date.desc()).limit(10).all()

            # Calculate rest days
            if recent_games:
                last_game = recent_games[0]
                rest_days = (game_date - last_game.date).days
                previous_game_date = last_game.date
                previous_opponent = (
                    last_game.away_team if last_game.home_team == team
                    else last_game.home_team
                )
                previous_was_home = last_game.home_team == team
                last_game_location = last_game.home_team
            else:
                rest_days = 7  # Assume well-rested if no data
                previous_game_date = None
                previous_opponent = None
                previous_was_home = None
                last_game_location = None

            # Check for back-to-back
            is_back_to_back = rest_days == 0

            # Check for 3-in-4
            is_three_in_four = self._check_three_in_four(recent_games, game_date)

            # Check for 4-in-6
            is_four_in_six = self._check_four_in_six(recent_games, game_date)

            # Calculate road trip length
            games_on_road_trip = self._count_road_trip_games(recent_games, team)

            # Check if first home after road trip
            is_first_home_after_road = (
                games_on_road_trip >= 3 and
                self._is_home_game(session, team, game_date)
            )

            # Calculate timezone change
            timezone_change = self._calculate_timezone_change(
                team, last_game_location
            )

            # Calculate fatigue score (0-1)
            fatigue_score = self._calculate_fatigue_score(
                rest_days, is_three_in_four, is_four_in_six
            )

            # Calculate travel score (0-1)
            travel_score = self._calculate_travel_score(
                timezone_change, games_on_road_trip
            )

            return TeamScheduleContext(
                team=team,
                game_date=game_date,
                rest_days=rest_days,
                is_back_to_back=is_back_to_back,
                is_three_in_four=is_three_in_four,
                is_four_in_six=is_four_in_six,
                last_game_location=last_game_location,
                games_on_road_trip=games_on_road_trip,
                is_first_home_after_road=is_first_home_after_road,
                timezone_change=timezone_change,
                previous_game_date=previous_game_date,
                previous_opponent=previous_opponent,
                previous_was_home=previous_was_home,
                fatigue_score=fatigue_score,
                travel_score=travel_score,
            )

    def _check_three_in_four(self, recent_games: list, game_date: date) -> bool:
        """Check if this is the 3rd game in 4 nights."""
        four_days_ago = game_date - timedelta(days=3)
        games_in_window = sum(
            1 for g in recent_games
            if four_days_ago <= g.date < game_date
        )
        return games_in_window >= 2  # This would be 3rd

    def _check_four_in_six(self, recent_games: list, game_date: date) -> bool:
        """Check if this is the 4th game in 6 nights."""
        six_days_ago = game_date - timedelta(days=5)
        games_in_window = sum(
            1 for g in recent_games
            if six_days_ago <= g.date < game_date
        )
        return games_in_window >= 3  # This would be 4th

    def _count_road_trip_games(self, recent_games: list, team: str) -> int:
        """Count consecutive away games."""
        count = 0
        for game in recent_games:
            if game.home_team != team:  # Away game
                count += 1
            else:
                break  # Hit a home game, stop counting
        return count

    def _is_home_game(self, session, team: str, game_date: date) -> bool:
        """Check if the upcoming game is a home game."""
        game = session.query(Game).filter(
            Game.home_team == team,
            Game.date == game_date,
        ).first()
        return game is not None

    def _calculate_timezone_change(
        self,
        team: str,
        last_location: Optional[str],
    ) -> int:
        """Calculate timezone change in hours."""
        if not last_location:
            return 0

        try:
            team_tz = get_team_timezone(team)
            last_tz = get_team_timezone(last_location)

            team_offset = self.TIMEZONE_OFFSETS.get(team_tz, 0)
            last_offset = self.TIMEZONE_OFFSETS.get(last_tz, 0)

            return abs(team_offset - last_offset)
        except ValueError:
            return 0

    def _calculate_fatigue_score(
        self,
        rest_days: int,
        is_three_in_four: bool,
        is_four_in_six: bool,
    ) -> float:
        """
        Calculate fatigue score (0-1).

        0 = fully rested, 1 = maximum fatigue
        """
        score = 0.0

        # Rest days component (max 0.4)
        if rest_days == 0:
            score += 0.4  # Back-to-back
        elif rest_days == 1:
            score += 0.2  # One day rest
        elif rest_days == 2:
            score += 0.1  # Two days rest
        # 3+ days = no fatigue from rest

        # Game density component (max 0.4)
        if is_four_in_six:
            score += 0.4
        elif is_three_in_four:
            score += 0.3

        return min(score, 1.0)

    def _calculate_travel_score(
        self,
        timezone_change: int,
        road_trip_games: int,
    ) -> float:
        """
        Calculate travel impact score (0-1).

        0 = no travel impact, 1 = maximum travel impact
        """
        score = 0.0

        # Timezone component (max 0.5)
        if timezone_change >= 3:
            score += 0.5
        elif timezone_change == 2:
            score += 0.3
        elif timezone_change == 1:
            score += 0.1

        # Road trip length component (max 0.3)
        if road_trip_games >= 5:
            score += 0.3
        elif road_trip_games >= 3:
            score += 0.2
        elif road_trip_games >= 2:
            score += 0.1

        return min(score, 1.0)

    def get_matchup_schedule_analysis(
        self,
        home_team: str,
        away_team: str,
        game_date: date,
    ) -> ScheduleMatchup:
        """
        Analyze schedule factors for a matchup.

        Args:
            home_team: Home team code.
            away_team: Away team code.
            game_date: Date of the game.

        Returns:
            ScheduleMatchup analysis.
        """
        home_context = self.get_team_schedule_context(home_team, game_date)
        away_context = self.get_team_schedule_context(away_team, game_date)

        # Calculate rest advantage
        rest_advantage = home_context.rest_days - away_context.rest_days

        # Check for "scheduled loss" scenario
        # Away team on B2B vs rested home team
        is_scheduled_loss = (
            away_context.is_back_to_back and
            home_context.rest_days >= 2
        )

        # Calculate fatigue differential
        fatigue_differential = away_context.fatigue_score - home_context.fatigue_score

        # Determine schedule edge
        if is_scheduled_loss:
            schedule_edge = "home"
        elif fatigue_differential > 0.3:
            schedule_edge = "home"
        elif fatigue_differential < -0.3:
            schedule_edge = "away"
        else:
            schedule_edge = "neutral"

        return ScheduleMatchup(
            home_context=home_context,
            away_context=away_context,
            rest_advantage=rest_advantage,
            is_scheduled_loss=is_scheduled_loss,
            fatigue_differential=fatigue_differential,
            schedule_edge=schedule_edge,
        )

    def calculate_fatigue_adjustment(
        self,
        team: str,
        game_date: date,
    ) -> float:
        """
        Calculate the fatigue adjustment scalar for a team.

        Returns:
            Scalar between 0.88 and 1.0 (lower = more fatigued).
        """
        context = self.get_team_schedule_context(team, game_date)

        # Base adjustment
        adjustment = 1.0

        # Back-to-back penalty
        if context.is_back_to_back:
            adjustment *= 0.88

        # 3-in-4 penalty
        elif context.is_three_in_four:
            adjustment *= 0.92

        # 4-in-6 penalty
        elif context.is_four_in_six:
            adjustment *= 0.94

        # Travel penalty
        if context.timezone_change >= 3:
            adjustment *= 0.94
        elif context.timezone_change == 2:
            adjustment *= 0.97

        return adjustment

    def find_scheduled_losses(
        self,
        game_date: date,
    ) -> list[dict]:
        """
        Find all "scheduled loss" scenarios for a date.

        These are high-probability spots to fade the road team.

        Returns:
            List of games with scheduled loss scenarios.
        """
        scheduled_losses = []

        with self.db.session_scope() as session:
            games = session.query(Game).filter(
                Game.date == game_date,
            ).all()

            for game in games:
                matchup = self.get_matchup_schedule_analysis(
                    game.home_team, game.away_team, game_date
                )

                if matchup.is_scheduled_loss:
                    scheduled_losses.append({
                        "game_id": game.game_id,
                        "home_team": game.home_team,
                        "away_team": game.away_team,
                        "away_rest_days": matchup.away_context.rest_days,
                        "home_rest_days": matchup.home_context.rest_days,
                        "fade_team": game.away_team,
                    })

        return scheduled_losses


def get_schedule_context(team: str, game_date: date) -> TeamScheduleContext:
    """Convenience function to get team schedule context."""
    analyzer = ScheduleAnalyzer()
    return analyzer.get_team_schedule_context(team, game_date)


def get_matchup_schedule(home_team: str, away_team: str, game_date: date) -> ScheduleMatchup:
    """Convenience function to get matchup schedule analysis."""
    analyzer = ScheduleAnalyzer()
    return analyzer.get_matchup_schedule_analysis(home_team, away_team, game_date)


def find_scheduled_losses(game_date: date) -> list[dict]:
    """Convenience function to find scheduled loss scenarios."""
    analyzer = ScheduleAnalyzer()
    return analyzer.find_scheduled_losses(game_date)
