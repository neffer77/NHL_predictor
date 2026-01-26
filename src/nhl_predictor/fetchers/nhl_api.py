"""NHL Edge API fetcher for schedule and standings data.

Uses the official NHL API at api-web.nhle.com.
"""

import logging
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from typing import Any, Optional

from .base import BaseFetcher
from ..utils.team_mapping import normalize_team_name, normalize_team_name_safe

logger = logging.getLogger(__name__)


@dataclass
class GameInfo:
    """Structured game information."""

    game_id: int
    date: date
    start_time: Optional[datetime]
    home_team: str
    away_team: str
    home_score: Optional[int]
    away_score: Optional[int]
    game_state: str  # FUT (future), LIVE, OFF (final), FINAL
    venue: Optional[str]
    season: str
    game_type: int  # 2 = regular season, 3 = playoffs


@dataclass
class TeamStanding:
    """Team standings information."""

    team_code: str
    team_name: str
    conference: str
    division: str
    games_played: int
    wins: int
    losses: int
    ot_losses: int
    points: int
    points_pct: float
    regulation_wins: int
    goals_for: int
    goals_against: int
    goal_diff: int
    home_record: str
    away_record: str
    l10_record: str
    streak: str
    wildcard_sequence: Optional[int]


class NHLAPIFetcher(BaseFetcher):
    """Fetcher for NHL Edge API data."""

    BASE_URL = "https://api-web.nhle.com/v1"

    def __init__(self):
        super().__init__(source_name="nhl_api")

    @property
    def base_url(self) -> str:
        """Return the base URL (for compatibility)."""
        return self.BASE_URL

    def fetch(self, fetch_type: str = "schedule", **kwargs) -> Any:
        """
        Fetch data from NHL API.

        Args:
            fetch_type: Type of data to fetch ('schedule', 'standings').
            **kwargs: Additional arguments passed to specific fetch method.

        Returns:
            Fetched data.
        """
        if fetch_type == "schedule":
            return self.fetch_schedule(**kwargs)
        elif fetch_type == "standings":
            return self.fetch_standings(**kwargs)
        else:
            raise ValueError(f"Unknown fetch type: {fetch_type}")

    def fetch_schedule(
        self,
        game_date: Optional[date] = None,
        save_to_db: bool = True,
    ) -> list[GameInfo]:
        """
        Fetch the NHL schedule for a specific date.

        Args:
            game_date: Date to fetch schedule for (defaults to today).
            save_to_db: Whether to save games to database.

        Returns:
            List of GameInfo objects for the specified date only.
        """
        if game_date is None:
            game_date = date.today()

        date_str = game_date.strftime("%Y-%m-%d")
        url = f"{self.BASE_URL}/schedule/{date_str}"

        start_time = datetime.now()
        games = []

        try:
            logger.info(f"Fetching NHL schedule for {date_str}")
            response = self.fetch_url(url)
            data = response.json()

            # Parse game weeks structure (API returns full week)
            game_weeks = data.get("gameWeek", [])

            for week in game_weeks:
                if not isinstance(week, dict):
                    continue

                # Get the actual game date from the week structure
                week_date_str = week.get("date", "")
                week_date = None
                if week_date_str:
                    try:
                        week_date = datetime.strptime(week_date_str, "%Y-%m-%d").date()
                    except ValueError:
                        pass

                # Only process games from the requested date
                if week_date != game_date:
                    continue

                for game_data in week.get("games", []):
                    # Pass the week date to avoid UTC timezone issues
                    game = self._parse_game(game_data, override_date=week_date)
                    if game:
                        games.append(game)

            # Also check direct games array (different API response format)
            if not games and "games" in data:
                for game_data in data["games"]:
                    game = self._parse_game(game_data)
                    # Only include games for the requested date
                    if game and game.date == game_date:
                        games.append(game)

            duration = (datetime.now() - start_time).total_seconds()

            if save_to_db and games:
                self._save_games_to_db(games)

            self.log_fetch(
                fetch_type="schedule",
                status="success",
                records_fetched=len(games),
                duration_seconds=duration,
            )

            logger.info(f"Fetched {len(games)} games for {date_str}")
            return games

        except Exception as e:
            duration = (datetime.now() - start_time).total_seconds()
            self.log_fetch(
                fetch_type="schedule",
                status="failed",
                error_message=str(e),
                duration_seconds=duration,
            )
            logger.error(f"Failed to fetch schedule: {e}")
            raise

    def fetch_schedule_range(
        self,
        start_date: date,
        end_date: date,
        save_to_db: bool = True,
    ) -> list[GameInfo]:
        """
        Fetch schedule for a date range.

        Args:
            start_date: Start date.
            end_date: End date.
            save_to_db: Whether to save games to database.

        Returns:
            List of all games in range.
        """
        all_games = []
        current_date = start_date

        while current_date <= end_date:
            try:
                games = self.fetch_schedule(current_date, save_to_db=save_to_db)
                all_games.extend(games)
            except Exception as e:
                logger.warning(f"Failed to fetch schedule for {current_date}: {e}")

            current_date += timedelta(days=1)

        return all_games

    def fetch_standings(
        self,
        standings_date: Optional[date] = None,
        save_to_db: bool = True,
    ) -> list[TeamStanding]:
        """
        Fetch NHL standings for a specific date.

        Args:
            standings_date: Date for standings (defaults to today).
            save_to_db: Whether to save to database.

        Returns:
            List of TeamStanding objects.
        """
        if standings_date is None:
            standings_date = date.today()

        # Use date-specific endpoint for historical data
        date_str = standings_date.strftime("%Y-%m-%d")
        url = f"{self.BASE_URL}/standings/{date_str}"

        start_time = datetime.now()
        standings = []

        try:
            logger.info(f"Fetching NHL standings for {date_str}")
            response = self.fetch_url(url)
            data = response.json()

            # Parse standings by division
            standings_data = data.get("standings", [])

            for team_data in standings_data:
                standing = self._parse_standing(team_data)
                if standing:
                    standings.append(standing)

            duration = (datetime.now() - start_time).total_seconds()

            if save_to_db and standings:
                self._save_standings_to_db(standings, standings_date)

            self.log_fetch(
                fetch_type="standings",
                status="success",
                records_fetched=len(standings),
                duration_seconds=duration,
            )

            logger.info(f"Fetched standings for {len(standings)} teams as of {date_str}")
            return standings

        except Exception as e:
            duration = (datetime.now() - start_time).total_seconds()
            self.log_fetch(
                fetch_type="standings",
                status="failed",
                error_message=str(e),
                duration_seconds=duration,
            )
            logger.error(f"Failed to fetch standings: {e}")
            raise

    def fetch_standings_range(
        self,
        start_date: date,
        end_date: date,
        save_to_db: bool = True,
    ) -> dict[date, list[TeamStanding]]:
        """
        Fetch standings for a date range (for backtesting).

        Args:
            start_date: Start date.
            end_date: End date.
            save_to_db: Whether to save to database.

        Returns:
            Dict mapping dates to standings.
        """
        all_standings = {}
        current_date = start_date

        while current_date <= end_date:
            try:
                standings = self.fetch_standings(current_date, save_to_db=save_to_db)
                if standings:
                    all_standings[current_date] = standings
                    logger.debug(f"Fetched standings for {current_date}: {len(standings)} teams")
            except Exception as e:
                logger.warning(f"Failed to fetch standings for {current_date}: {e}")

            current_date += timedelta(days=1)

        return all_standings

    def _parse_game(self, game_data: dict, override_date: Optional[date] = None) -> Optional[GameInfo]:
        """Parse a game from API response.

        Args:
            game_data: The game data dict from API.
            override_date: If provided, use this date instead of parsing from API
                          (handles UTC timezone issues).
        """
        try:
            # Extract team info
            home_team_data = game_data.get("homeTeam", {})
            away_team_data = game_data.get("awayTeam", {})

            home_abbrev = home_team_data.get("abbrev", "")
            away_abbrev = away_team_data.get("abbrev", "")

            # Normalize team names
            home_team = normalize_team_name_safe(home_abbrev)
            away_team = normalize_team_name_safe(away_abbrev)

            if not home_team or not away_team:
                logger.warning(f"Could not normalize teams: {home_abbrev} vs {away_abbrev}")
                return None

            # Parse date and time
            game_date_str = game_data.get("gameDate", "")
            start_time_str = game_data.get("startTimeUTC", "")

            game_date = override_date  # Use override if provided
            start_time = None

            # Try to parse start time
            if start_time_str:
                try:
                    start_time = datetime.fromisoformat(start_time_str.replace("Z", "+00:00"))
                    # Only extract date from start time if no override and no gameDate
                    if not game_date and not game_date_str:
                        game_date = start_time.date()
                except ValueError:
                    pass

            # Parse gameDate if available and no override
            if game_date_str and not game_date:
                try:
                    game_date = datetime.strptime(game_date_str, "%Y-%m-%d").date()
                except ValueError:
                    pass

            # If still no date, skip this game
            if game_date is None:
                logger.warning(f"Could not parse date for game {game_data.get('id')}")
                return None

            # Get scores
            home_score = home_team_data.get("score")
            away_score = away_team_data.get("score")

            # Get game state
            game_state = game_data.get("gameState", "FUT")

            # Get venue
            venue = game_data.get("venue", {}).get("default", "")

            # Get season and game type
            season = str(game_data.get("season", ""))
            game_type = game_data.get("gameType", 2)

            return GameInfo(
                game_id=game_data.get("id", 0),
                date=game_date,
                start_time=start_time,
                home_team=home_team,
                away_team=away_team,
                home_score=home_score,
                away_score=away_score,
                game_state=game_state,
                venue=venue,
                season=season,
                game_type=game_type,
            )

        except Exception as e:
            logger.warning(f"Failed to parse game: {e}")
            return None

    def _parse_standing(self, team_data: dict) -> Optional[TeamStanding]:
        """Parse a team standing from API response."""
        try:
            team_abbrev = team_data.get("teamAbbrev", {}).get("default", "")
            team_name = team_data.get("teamName", {}).get("default", "")

            # Normalize team code
            team_code = normalize_team_name_safe(team_abbrev)
            if not team_code:
                logger.warning(f"Could not normalize team: {team_abbrev}")
                return None

            # Extract records
            home_wins = team_data.get("homeWins", 0)
            home_losses = team_data.get("homeLosses", 0)
            home_ot = team_data.get("homeOtLosses", 0)

            away_wins = team_data.get("roadWins", 0)
            away_losses = team_data.get("roadLosses", 0)
            away_ot = team_data.get("roadOtLosses", 0)

            l10_wins = team_data.get("l10Wins", 0)
            l10_losses = team_data.get("l10Losses", 0)
            l10_ot = team_data.get("l10OtLosses", 0)

            # Streak
            streak_count = team_data.get("streakCount", 0)
            streak_code = team_data.get("streakCode", "")
            streak = f"{streak_code}{streak_count}"

            return TeamStanding(
                team_code=team_code,
                team_name=team_name,
                conference=team_data.get("conferenceName", ""),
                division=team_data.get("divisionName", ""),
                games_played=team_data.get("gamesPlayed", 0),
                wins=team_data.get("wins", 0),
                losses=team_data.get("losses", 0),
                ot_losses=team_data.get("otLosses", 0),
                points=team_data.get("points", 0),
                points_pct=team_data.get("pointPctg", 0.0),
                regulation_wins=team_data.get("regulationWins", 0),
                goals_for=team_data.get("goalFor", 0),
                goals_against=team_data.get("goalAgainst", 0),
                goal_diff=team_data.get("goalDifferential", 0),
                home_record=f"{home_wins}-{home_losses}-{home_ot}",
                away_record=f"{away_wins}-{away_losses}-{away_ot}",
                l10_record=f"{l10_wins}-{l10_losses}-{l10_ot}",
                streak=streak,
                wildcard_sequence=team_data.get("wildcardSequence"),
            )

        except Exception as e:
            logger.warning(f"Failed to parse standing: {e}")
            return None

    def _save_games_to_db(self, games: list[GameInfo]) -> None:
        """Save games to database."""
        from ..models.database import get_db
        from ..models.schema import Game

        db = get_db()
        with db.session_scope() as session:
            for game_info in games:
                # Check if game exists
                existing = session.query(Game).filter(
                    Game.game_id == game_info.game_id
                ).first()

                if existing:
                    # Update existing game
                    existing.home_score = game_info.home_score
                    existing.away_score = game_info.away_score
                    existing.game_state = game_info.game_state
                    if game_info.home_score is not None and game_info.away_score is not None:
                        existing.winner = (
                            game_info.home_team
                            if game_info.home_score > game_info.away_score
                            else game_info.away_team
                        )
                else:
                    # Create new game
                    winner = None
                    if game_info.home_score is not None and game_info.away_score is not None:
                        winner = (
                            game_info.home_team
                            if game_info.home_score > game_info.away_score
                            else game_info.away_team
                        )

                    game = Game(
                        game_id=game_info.game_id,
                        date=game_info.date,
                        season=game_info.season,
                        game_type=game_info.game_type,
                        home_team=game_info.home_team,
                        away_team=game_info.away_team,
                        home_score=game_info.home_score,
                        away_score=game_info.away_score,
                        winner=winner,
                        venue=game_info.venue,
                        start_time=game_info.start_time,
                        game_state=game_info.game_state,
                    )
                    session.add(game)

        logger.debug(f"Saved {len(games)} games to database")

    def _save_standings_to_db(self, standings: list[TeamStanding], standings_date: date) -> None:
        """Save standings as team daily stats to database."""
        from ..models.database import get_db
        from ..models.schema import TeamDailyStats

        db = get_db()
        with db.session_scope() as session:
            for standing in standings:
                # Calculate xGF% proxy from goals for/against
                # This gives us a reasonable approximation for backtesting
                total_goals = standing.goals_for + standing.goals_against
                if total_goals > 0:
                    gf_pct = (standing.goals_for / total_goals) * 100
                    # Scale to typical xGF% range (45-55)
                    # NHL average is 50%, good teams ~52-54%, bad teams ~46-48%
                    xgf_pct_approx = 45 + (gf_pct - 45) * 1.0  # Keep in similar range
                    xgf_pct_approx = max(45.0, min(55.0, xgf_pct_approx))
                else:
                    xgf_pct_approx = 50.0

                # Calculate points percentage as another strength indicator
                max_points = standing.games_played * 2 if standing.games_played > 0 else 1
                points_pct = standing.points / max_points if max_points > 0 else 0.5

                # Check for existing record
                existing = session.query(TeamDailyStats).filter(
                    TeamDailyStats.date == standings_date,
                    TeamDailyStats.team == standing.team_code,
                    TeamDailyStats.source == "nhl_api",
                ).first()

                if existing:
                    # Update existing
                    existing.games_played = standing.games_played
                    existing.wins = standing.wins
                    existing.losses = standing.losses
                    existing.ot_losses = standing.ot_losses
                    existing.points = standing.points
                    existing.xgf_pct = xgf_pct_approx
                    existing.xgf = standing.goals_for
                    existing.xga = standing.goals_against
                    # Use goal differential as a proxy for HDCF differential
                    existing.hdcf_pct = xgf_pct_approx  # Similar proxy
                else:
                    # Create new
                    stats = TeamDailyStats(
                        date=standings_date,
                        team=standing.team_code,
                        games_played=standing.games_played,
                        wins=standing.wins,
                        losses=standing.losses,
                        ot_losses=standing.ot_losses,
                        points=standing.points,
                        xgf_pct=xgf_pct_approx,
                        xgf=standing.goals_for,
                        xga=standing.goals_against,
                        hdcf_pct=xgf_pct_approx,  # Use same proxy
                        source="nhl_api",
                    )
                    session.add(stats)

        logger.debug(f"Saved standings for {len(standings)} teams")


def fetch_todays_schedule() -> list[GameInfo]:
    """Convenience function to fetch today's schedule."""
    with NHLAPIFetcher() as fetcher:
        return fetcher.fetch_schedule()


def fetch_standings() -> list[TeamStanding]:
    """Convenience function to fetch current standings."""
    with NHLAPIFetcher() as fetcher:
        return fetcher.fetch_standings()
