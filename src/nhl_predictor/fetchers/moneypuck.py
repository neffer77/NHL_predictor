"""MoneyPuck data fetcher for model predictions and advanced stats.

Downloads and parses MoneyPuck's daily CSV data dumps.
"""

import logging
from dataclasses import dataclass
from datetime import date, datetime
from io import StringIO
from typing import Optional

import pandas as pd

from .base import BaseFetcher
from ..utils.team_mapping import normalize_team_name_safe

logger = logging.getLogger(__name__)


@dataclass
class MoneyPuckGamePrediction:
    """Game prediction from MoneyPuck model."""

    game_id: Optional[int]
    date: date
    home_team: str
    away_team: str
    home_win_prob: float
    away_win_prob: float
    home_goals_expected: float
    away_goals_expected: float
    home_xgf: float
    away_xgf: float


@dataclass
class MoneyPuckTeamStats:
    """Team statistics from MoneyPuck."""

    team: str
    games_played: int

    # Expected Goals (Flurry Adjusted)
    xgf: float  # Expected Goals For
    xga: float  # Expected Goals Against
    xgf_pct: float

    # Shooting Talent
    shooting_talent: float  # Shooting Talent Above Average

    # Win metrics
    expected_wins: float
    actual_wins: int
    luck_factor: float  # Actual - Expected

    # Power rankings
    power_ranking: Optional[float]


class MoneyPuckFetcher(BaseFetcher):
    """Fetcher for MoneyPuck data."""

    # MoneyPuck CSV endpoints
    SIMULATIONS_URL = "https://moneypuck.com/moneypuck/simulations/simulations_recent.csv"
    TEAM_STATS_URL = "https://moneypuck.com/moneypuck/playerData/seasonSummary/2025/regular/teams.csv"

    def __init__(self):
        super().__init__(source_name="moneypuck")

    def fetch(self, fetch_type: str = "predictions", **kwargs):
        """
        Fetch data from MoneyPuck.

        Args:
            fetch_type: Type of data ('predictions', 'team_stats').
        """
        if fetch_type == "predictions":
            return self.fetch_game_predictions(**kwargs)
        elif fetch_type == "team_stats":
            return self.fetch_team_stats(**kwargs)
        else:
            raise ValueError(f"Unknown fetch type: {fetch_type}")

    def fetch_game_predictions(
        self,
        save_to_db: bool = True,
    ) -> list[MoneyPuckGamePrediction]:
        """
        Fetch game predictions from MoneyPuck simulations.

        Args:
            save_to_db: Whether to save to database.

        Returns:
            List of game predictions.
        """
        start_time = datetime.now()
        predictions = []

        try:
            logger.info("Fetching MoneyPuck game predictions")

            response = self.fetch_url(self.SIMULATIONS_URL)

            # Parse CSV
            df = pd.read_csv(StringIO(response.text))

            for _, row in df.iterrows():
                pred = self._parse_prediction_row(row)
                if pred:
                    predictions.append(pred)

            duration = (datetime.now() - start_time).total_seconds()

            self.log_fetch(
                fetch_type="predictions",
                status="success",
                records_fetched=len(predictions),
                duration_seconds=duration,
            )

            logger.info(f"Fetched {len(predictions)} game predictions")
            return predictions

        except Exception as e:
            duration = (datetime.now() - start_time).total_seconds()
            self.log_fetch(
                fetch_type="predictions",
                status="failed",
                error_message=str(e),
                duration_seconds=duration,
            )
            logger.error(f"Failed to fetch MoneyPuck predictions: {e}")
            raise

    def fetch_team_stats(
        self,
        save_to_db: bool = True,
    ) -> list[MoneyPuckTeamStats]:
        """
        Fetch team statistics from MoneyPuck.

        Args:
            save_to_db: Whether to save to database.

        Returns:
            List of team stats.
        """
        start_time = datetime.now()
        stats = []

        try:
            logger.info("Fetching MoneyPuck team stats")

            response = self.fetch_url(self.TEAM_STATS_URL)

            # Parse CSV
            df = pd.read_csv(StringIO(response.text))

            for _, row in df.iterrows():
                team_stat = self._parse_team_stats_row(row)
                if team_stat:
                    stats.append(team_stat)

            duration = (datetime.now() - start_time).total_seconds()

            if save_to_db and stats:
                self._save_team_stats_to_db(stats)

            self.log_fetch(
                fetch_type="team_stats",
                status="success",
                records_fetched=len(stats),
                duration_seconds=duration,
            )

            logger.info(f"Fetched stats for {len(stats)} teams")
            return stats

        except Exception as e:
            duration = (datetime.now() - start_time).total_seconds()
            self.log_fetch(
                fetch_type="team_stats",
                status="failed",
                error_message=str(e),
                duration_seconds=duration,
            )
            logger.error(f"Failed to fetch MoneyPuck team stats: {e}")
            raise

    def _parse_prediction_row(self, row: pd.Series) -> Optional[MoneyPuckGamePrediction]:
        """Parse a prediction row from CSV."""
        try:
            # Get team codes
            home_team_raw = str(row.get("homeTeam", row.get("home_team", "")))
            away_team_raw = str(row.get("awayTeam", row.get("away_team", "")))

            home_team = normalize_team_name_safe(home_team_raw)
            away_team = normalize_team_name_safe(away_team_raw)

            if not home_team or not away_team:
                return None

            # Parse date
            date_str = row.get("gameDate", row.get("date", ""))
            if date_str:
                try:
                    game_date = pd.to_datetime(date_str).date()
                except Exception:
                    game_date = date.today()
            else:
                game_date = date.today()

            # Get probabilities
            home_prob = float(row.get("homeWinProb", row.get("home_win_prob", 0.5)))
            away_prob = float(row.get("awayWinProb", row.get("away_win_prob", 0.5)))

            # Get expected goals
            home_goals = float(row.get("homeGoalsExpected", row.get("home_goals", 0)))
            away_goals = float(row.get("awayGoalsExpected", row.get("away_goals", 0)))

            # Get xG
            home_xgf = float(row.get("homeXGF", row.get("home_xgf", home_goals)))
            away_xgf = float(row.get("awayXGF", row.get("away_xgf", away_goals)))

            # Game ID if available
            game_id = row.get("gameId", row.get("game_id"))
            if pd.notna(game_id):
                game_id = int(game_id)
            else:
                game_id = None

            return MoneyPuckGamePrediction(
                game_id=game_id,
                date=game_date,
                home_team=home_team,
                away_team=away_team,
                home_win_prob=home_prob,
                away_win_prob=away_prob,
                home_goals_expected=home_goals,
                away_goals_expected=away_goals,
                home_xgf=home_xgf,
                away_xgf=away_xgf,
            )

        except Exception as e:
            logger.debug(f"Failed to parse prediction row: {e}")
            return None

    def _parse_team_stats_row(self, row: pd.Series) -> Optional[MoneyPuckTeamStats]:
        """Parse a team stats row from CSV."""
        try:
            # Get team code
            team_raw = str(row.get("team", row.get("Team", "")))
            team = normalize_team_name_safe(team_raw)

            if not team:
                return None

            # Helper for safe float/int extraction
            def safe_float(key: str, default: float = 0.0) -> float:
                val = row.get(key)
                if pd.isna(val):
                    return default
                return float(val)

            def safe_int(key: str, default: int = 0) -> int:
                val = row.get(key)
                if pd.isna(val):
                    return default
                return int(float(val))

            # Extract stats with various possible column names
            xgf = safe_float("xGoalsFor") or safe_float("xGF") or safe_float("ixG")
            xga = safe_float("xGoalsAgainst") or safe_float("xGA")
            games = safe_int("GP") or safe_int("games") or safe_int("gamesPlayed")

            xgf_pct = 0.0
            if xgf + xga > 0:
                xgf_pct = (xgf / (xgf + xga)) * 100

            return MoneyPuckTeamStats(
                team=team,
                games_played=games,
                xgf=xgf,
                xga=xga,
                xgf_pct=xgf_pct,
                shooting_talent=safe_float("shootingTalent") or safe_float("shtTalent"),
                expected_wins=safe_float("expectedWins") or safe_float("xWins"),
                actual_wins=safe_int("wins") or safe_int("W"),
                luck_factor=safe_float("luckFactor") or safe_float("luck"),
                power_ranking=safe_float("powerRanking") or safe_float("rank"),
            )

        except Exception as e:
            logger.debug(f"Failed to parse team stats row: {e}")
            return None

    def _save_team_stats_to_db(self, stats: list[MoneyPuckTeamStats]) -> None:
        """Save MoneyPuck team stats to database."""
        from ..models.database import get_db
        from ..models.schema import TeamDailyStats

        today = date.today()

        db = get_db()
        with db.session_scope() as session:
            for team_stat in stats:
                # Check for existing
                existing = session.query(TeamDailyStats).filter(
                    TeamDailyStats.date == today,
                    TeamDailyStats.team == team_stat.team,
                    TeamDailyStats.source == "moneypuck",
                ).first()

                if existing:
                    existing.xgf = team_stat.xgf
                    existing.xga = team_stat.xga
                    existing.xgf_pct = team_stat.xgf_pct
                    existing.games_played = team_stat.games_played
                    existing.wins = team_stat.actual_wins
                else:
                    record = TeamDailyStats(
                        date=today,
                        team=team_stat.team,
                        xgf=team_stat.xgf,
                        xga=team_stat.xga,
                        xgf_pct=team_stat.xgf_pct,
                        games_played=team_stat.games_played,
                        wins=team_stat.actual_wins,
                        source="moneypuck",
                    )
                    session.add(record)

        logger.debug(f"Saved MoneyPuck stats for {len(stats)} teams")


def fetch_predictions() -> list[MoneyPuckGamePrediction]:
    """Convenience function to fetch game predictions."""
    with MoneyPuckFetcher() as fetcher:
        return fetcher.fetch_game_predictions()


def fetch_team_stats() -> list[MoneyPuckTeamStats]:
    """Convenience function to fetch team stats."""
    with MoneyPuckFetcher() as fetcher:
        return fetcher.fetch_team_stats()
