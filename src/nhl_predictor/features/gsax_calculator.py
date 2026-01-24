"""Goals Saved Above Expected (GSAx) calculator.

Calculates rolling GSAx for goaltenders and analyzes goalie matchups.
"""

import logging
from dataclasses import dataclass
from datetime import date, timedelta
from typing import Optional

from ..models.database import get_db
from ..models.schema import GoalieStats

logger = logging.getLogger(__name__)


@dataclass
class GoalieGSAxMetrics:
    """GSAx metrics for a goaltender."""

    player_name: str
    team: str

    # Game counts
    games_played: int
    games_started: int

    # Season GSAx
    gsax_season: float
    gsax_per_game: float

    # Rolling GSAx
    gsax_rolling_10: float
    gsax_rolling_20: float

    # Status
    is_hot: bool  # GSAx > 3 in last 10
    is_cold: bool  # GSAx < -3 in last 10

    # Raw stats
    save_pct: Optional[float] = None
    goals_against_avg: Optional[float] = None

    # Confirmation for today
    confirmation_status: Optional[str] = None


@dataclass
class GoalieMatchup:
    """Goalie matchup comparison."""

    home_goalie: Optional[GoalieGSAxMetrics]
    away_goalie: Optional[GoalieGSAxMetrics]
    gsax_differential: float
    advantage: str  # "home", "away", "even"
    is_mismatch: bool  # Significant GSAx difference


class GSAxCalculator:
    """Calculates and tracks GSAx for goaltenders."""

    # Thresholds
    HOT_THRESHOLD = 3.0  # GSAx in 10 games for "hot" status
    COLD_THRESHOLD = -3.0  # GSAx in 10 games for "cold" status
    MISMATCH_THRESHOLD = 5.0  # GSAx difference for "mismatch"

    def __init__(self):
        self.db = get_db()

    def get_goalie_gsax(
        self,
        player_name: str,
        team: Optional[str] = None,
        as_of_date: Optional[date] = None,
    ) -> Optional[GoalieGSAxMetrics]:
        """
        Get GSAx metrics for a goaltender.

        Args:
            player_name: Goaltender name.
            team: Team code (optional, for filtering).
            as_of_date: Date to calculate stats as of.

        Returns:
            GoalieGSAxMetrics or None.
        """
        if as_of_date is None:
            as_of_date = date.today()

        with self.db.session_scope() as session:
            # Build query
            query = session.query(GoalieStats).filter(
                GoalieStats.player_name == player_name,
                GoalieStats.date <= as_of_date,
            )

            if team:
                query = query.filter(GoalieStats.team == team)

            # Get all games for this goalie
            all_games = query.order_by(GoalieStats.date.desc()).all()

            if not all_games:
                logger.debug(f"No stats found for goalie {player_name}")
                return None

            # Calculate season totals
            games_played = len(all_games)
            games_started = sum(1 for g in all_games if g.is_starter)
            gsax_season = sum(g.gsax or 0 for g in all_games)
            gsax_per_game = gsax_season / games_played if games_played > 0 else 0

            # Calculate rolling GSAx
            last_10 = all_games[:10]
            last_20 = all_games[:20]

            gsax_rolling_10 = sum(g.gsax or 0 for g in last_10)
            gsax_rolling_20 = sum(g.gsax or 0 for g in last_20)

            # Determine hot/cold status
            is_hot = gsax_rolling_10 >= self.HOT_THRESHOLD
            is_cold = gsax_rolling_10 <= self.COLD_THRESHOLD

            # Get most recent record for save_pct and team
            latest = all_games[0]

            # Check confirmation status for today
            today_record = session.query(GoalieStats).filter(
                GoalieStats.player_name == player_name,
                GoalieStats.date == as_of_date,
            ).first()

            confirmation = None
            if today_record:
                confirmation = today_record.confirmation_status

            return GoalieGSAxMetrics(
                player_name=player_name,
                team=latest.team,
                games_played=games_played,
                games_started=games_started,
                gsax_season=gsax_season,
                gsax_per_game=gsax_per_game,
                gsax_rolling_10=gsax_rolling_10,
                gsax_rolling_20=gsax_rolling_20,
                is_hot=is_hot,
                is_cold=is_cold,
                save_pct=latest.save_pct,
                confirmation_status=confirmation,
            )

    def get_team_goalies(
        self,
        team: str,
        as_of_date: Optional[date] = None,
    ) -> list[GoalieGSAxMetrics]:
        """
        Get GSAx metrics for all goalies on a team.

        Args:
            team: Team code.
            as_of_date: Date to calculate stats as of.

        Returns:
            List of GoalieGSAxMetrics.
        """
        if as_of_date is None:
            as_of_date = date.today()

        with self.db.session_scope() as session:
            # Get unique goalie names for this team
            goalie_names = session.query(GoalieStats.player_name).filter(
                GoalieStats.team == team,
            ).distinct().all()

            goalies = []
            for (name,) in goalie_names:
                metrics = self.get_goalie_gsax(name, team, as_of_date)
                if metrics:
                    goalies.append(metrics)

            # Sort by games started (starter first)
            return sorted(goalies, key=lambda g: g.games_started, reverse=True)

    def get_confirmed_starter(
        self,
        team: str,
        game_date: Optional[date] = None,
    ) -> Optional[GoalieGSAxMetrics]:
        """
        Get the confirmed starting goalie for a team.

        Args:
            team: Team code.
            game_date: Date of the game.

        Returns:
            Confirmed starter's metrics or None.
        """
        if game_date is None:
            game_date = date.today()

        with self.db.session_scope() as session:
            # Look for confirmed starter
            starter = session.query(GoalieStats).filter(
                GoalieStats.team == team,
                GoalieStats.date == game_date,
                GoalieStats.is_starter == True,
            ).first()

            if starter:
                return self.get_goalie_gsax(starter.player_name, team, game_date)

            # If no confirmed starter, return None
            return None

    def get_expected_starter(
        self,
        team: str,
        as_of_date: Optional[date] = None,
    ) -> Optional[GoalieGSAxMetrics]:
        """
        Get the expected starting goalie based on games started.

        Falls back to this when no confirmed starter.

        Args:
            team: Team code.
            as_of_date: Date to check.

        Returns:
            Expected starter's metrics.
        """
        goalies = self.get_team_goalies(team, as_of_date)
        if goalies:
            return goalies[0]  # Most games started
        return None

    def get_matchup_analysis(
        self,
        home_team: str,
        away_team: str,
        game_date: Optional[date] = None,
    ) -> GoalieMatchup:
        """
        Analyze goalie matchup for a game.

        Args:
            home_team: Home team code.
            away_team: Away team code.
            game_date: Date of the game.

        Returns:
            GoalieMatchup analysis.
        """
        if game_date is None:
            game_date = date.today()

        # Try to get confirmed starters, fall back to expected
        home_goalie = self.get_confirmed_starter(home_team, game_date)
        if not home_goalie:
            home_goalie = self.get_expected_starter(home_team, game_date)

        away_goalie = self.get_confirmed_starter(away_team, game_date)
        if not away_goalie:
            away_goalie = self.get_expected_starter(away_team, game_date)

        # Calculate differential
        home_gsax = home_goalie.gsax_rolling_10 if home_goalie else 0
        away_gsax = away_goalie.gsax_rolling_10 if away_goalie else 0
        differential = home_gsax - away_gsax

        # Determine advantage
        if abs(differential) < 1.0:
            advantage = "even"
        elif differential > 0:
            advantage = "home"
        else:
            advantage = "away"

        # Check for mismatch
        is_mismatch = abs(differential) >= self.MISMATCH_THRESHOLD

        return GoalieMatchup(
            home_goalie=home_goalie,
            away_goalie=away_goalie,
            gsax_differential=differential,
            advantage=advantage,
            is_mismatch=is_mismatch,
        )

    def get_backup_penalty(
        self,
        team: str,
        as_of_date: Optional[date] = None,
    ) -> float:
        """
        Calculate the "backup penalty" - difference between starter and backup.

        Args:
            team: Team code.
            as_of_date: Date to check.

        Returns:
            Difference in GSAx between starter and backup (positive = starter better).
        """
        goalies = self.get_team_goalies(team, as_of_date)

        if len(goalies) < 2:
            return 0.0

        starter = goalies[0]
        backup = goalies[1]

        return starter.gsax_rolling_10 - backup.gsax_rolling_10

    def find_hot_goalies(
        self,
        as_of_date: Optional[date] = None,
    ) -> list[GoalieGSAxMetrics]:
        """Find all goalies currently on a hot streak."""
        from ..utils.team_mapping import get_all_team_codes

        hot_goalies = []
        for team in get_all_team_codes():
            for goalie in self.get_team_goalies(team, as_of_date):
                if goalie.is_hot:
                    hot_goalies.append(goalie)

        return sorted(hot_goalies, key=lambda g: g.gsax_rolling_10, reverse=True)

    def find_cold_goalies(
        self,
        as_of_date: Optional[date] = None,
    ) -> list[GoalieGSAxMetrics]:
        """Find all goalies currently on a cold streak."""
        from ..utils.team_mapping import get_all_team_codes

        cold_goalies = []
        for team in get_all_team_codes():
            for goalie in self.get_team_goalies(team, as_of_date):
                if goalie.is_cold:
                    cold_goalies.append(goalie)

        return sorted(cold_goalies, key=lambda g: g.gsax_rolling_10)


def get_goalie_gsax(player_name: str, team: Optional[str] = None) -> Optional[GoalieGSAxMetrics]:
    """Convenience function to get goalie GSAx."""
    calculator = GSAxCalculator()
    return calculator.get_goalie_gsax(player_name, team)


def get_matchup_goalie_analysis(home_team: str, away_team: str) -> GoalieMatchup:
    """Convenience function to get goalie matchup analysis."""
    calculator = GSAxCalculator()
    return calculator.get_matchup_analysis(home_team, away_team)
