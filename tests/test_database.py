"""Tests for database module."""

import pytest
from datetime import date, datetime

from src.nhl_predictor.models.database import Database, get_db, init_db
from src.nhl_predictor.models.schema import (
    Game,
    TeamDailyStats,
    GoalieStats,
    Prediction,
    Referee,
    RefereeAssignment,
    DataFetchLog,
)


@pytest.fixture
def test_db():
    """Create an in-memory test database."""
    db = Database(db_path=":memory:")
    db.create_tables()
    yield db
    db.drop_tables()


class TestDatabase:
    """Tests for Database class."""

    def test_create_database(self, test_db):
        """Test database creation."""
        assert test_db is not None
        assert test_db.engine is not None

    def test_create_tables(self, test_db):
        """Test table creation."""
        # Tables should already be created by fixture
        # Try to query each table
        with test_db.session_scope() as session:
            session.query(Game).all()
            session.query(TeamDailyStats).all()
            session.query(GoalieStats).all()
            session.query(Prediction).all()
            session.query(Referee).all()
            session.query(DataFetchLog).all()

    def test_session_scope_commits(self, test_db):
        """Test that session_scope commits on success."""
        with test_db.session_scope() as session:
            game = Game(
                game_id=2025020001,
                date=date(2025, 10, 15),
                season="20252026",
                game_type=2,
                home_team="MTL",
                away_team="TOR",
                game_state="scheduled",
            )
            session.add(game)

        # Verify game was committed
        with test_db.session_scope() as session:
            games = session.query(Game).all()
            assert len(games) == 1
            assert games[0].game_id == 2025020001

    def test_session_scope_rollbacks_on_error(self, test_db):
        """Test that session_scope rolls back on exception."""
        try:
            with test_db.session_scope() as session:
                game = Game(
                    game_id=2025020002,
                    date=date(2025, 10, 15),
                    season="20252026",
                    game_type=2,
                    home_team="MTL",
                    away_team="TOR",
                    game_state="scheduled",
                )
                session.add(game)
                raise ValueError("Test error")
        except ValueError:
            pass

        # Verify game was not committed
        with test_db.session_scope() as session:
            games = session.query(Game).filter(Game.game_id == 2025020002).all()
            assert len(games) == 0


class TestGameModel:
    """Tests for Game model."""

    def test_create_game(self, test_db):
        """Test creating a game record."""
        with test_db.session_scope() as session:
            game = Game(
                game_id=2025020100,
                date=date(2025, 10, 20),
                season="20252026",
                game_type=2,
                home_team="BOS",
                away_team="NYR",
                home_score=3,
                away_score=2,
                winner="BOS",
                overtime=False,
                shootout=False,
                venue="TD Garden",
                game_state="final",
            )
            session.add(game)

        with test_db.session_scope() as session:
            game = session.query(Game).filter(Game.game_id == 2025020100).first()
            assert game is not None
            assert game.home_team == "BOS"
            assert game.away_team == "NYR"
            assert game.winner == "BOS"
            assert game.game_state == "final"

    def test_game_unique_constraint(self, test_db):
        """Test that game_id is unique."""
        with test_db.session_scope() as session:
            game1 = Game(
                game_id=2025020200,
                date=date(2025, 10, 21),
                season="20252026",
                game_type=2,
                home_team="CHI",
                away_team="DET",
            )
            session.add(game1)

        with pytest.raises(Exception):  # IntegrityError
            with test_db.session_scope() as session:
                game2 = Game(
                    game_id=2025020200,  # Same ID
                    date=date(2025, 10, 22),
                    season="20252026",
                    game_type=2,
                    home_team="MIN",
                    away_team="COL",
                )
                session.add(game2)


class TestTeamDailyStats:
    """Tests for TeamDailyStats model."""

    def test_create_team_stats(self, test_db):
        """Test creating team daily stats."""
        with test_db.session_scope() as session:
            stats = TeamDailyStats(
                date=date(2025, 11, 1),
                team="MTL",
                cf_pct=52.5,
                xgf_pct=54.3,
                hdcf_pct=55.0,
                pdo=101.2,
                games_played=15,
                wins=8,
                losses=5,
                ot_losses=2,
                points=18,
                source="nst_5v5",
            )
            session.add(stats)

        with test_db.session_scope() as session:
            stats = session.query(TeamDailyStats).filter(
                TeamDailyStats.team == "MTL"
            ).first()
            assert stats is not None
            assert stats.cf_pct == 52.5
            assert stats.xgf_pct == 54.3
            assert stats.source == "nst_5v5"


class TestGoalieStats:
    """Tests for GoalieStats model."""

    def test_create_goalie_stats(self, test_db):
        """Test creating goalie stats."""
        with test_db.session_scope() as session:
            goalie = GoalieStats(
                date=date(2025, 11, 1),
                player_name="Carey Price",
                team="MTL",
                shots_against=30,
                goals_against=2,
                saves=28,
                save_pct=0.933,
                xga=2.5,
                gsax=0.5,
                is_starter=True,
                confirmation_status="confirmed",
            )
            session.add(goalie)

        with test_db.session_scope() as session:
            goalie = session.query(GoalieStats).filter(
                GoalieStats.player_name == "Carey Price"
            ).first()
            assert goalie is not None
            assert goalie.team == "MTL"
            assert goalie.gsax == 0.5
            assert goalie.is_starter is True


class TestPrediction:
    """Tests for Prediction model."""

    def test_create_prediction(self, test_db):
        """Test creating a prediction."""
        # First create a game
        with test_db.session_scope() as session:
            game = Game(
                game_id=2025020300,
                date=date(2025, 11, 5),
                season="20252026",
                game_type=2,
                home_team="TOR",
                away_team="MTL",
            )
            session.add(game)

        with test_db.session_scope() as session:
            prediction = Prediction(
                game_id=2025020300,
                home_win_prob=0.58,
                away_win_prob=0.42,
                home_implied_prob=0.55,
                away_implied_prob=0.45,
                home_edge=0.03,
                away_edge=-0.03,
                pick="TOR",
                pick_confidence=0.58,
                pick_status="top4",
                rationale="Home ice advantage, goalie mismatch",
                risk_level="low",
            )
            session.add(prediction)

        with test_db.session_scope() as session:
            pred = session.query(Prediction).filter(
                Prediction.game_id == 2025020300
            ).first()
            assert pred is not None
            assert pred.pick == "TOR"
            assert pred.pick_confidence == 0.58


class TestReferee:
    """Tests for Referee model."""

    def test_create_referee(self, test_db):
        """Test creating a referee."""
        with test_db.session_scope() as session:
            ref = Referee(
                name="Wes McCauley",
                games_officiated=500,
                home_win_pct=0.56,
                penalties_per_game=8.2,
                home_bias=0.02,
                penalty_deviation=0.7,
                bias_tag="home_friendly",
                event_level="high",
            )
            session.add(ref)

        with test_db.session_scope() as session:
            ref = session.query(Referee).filter(
                Referee.name == "Wes McCauley"
            ).first()
            assert ref is not None
            assert ref.bias_tag == "home_friendly"
            assert ref.event_level == "high"


class TestDataFetchLog:
    """Tests for DataFetchLog model."""

    def test_create_fetch_log(self, test_db):
        """Test creating a fetch log."""
        with test_db.session_scope() as session:
            log = DataFetchLog(
                source="nhl_api",
                fetch_type="schedule",
                status="success",
                records_fetched=12,
                duration_seconds=1.5,
            )
            session.add(log)

        with test_db.session_scope() as session:
            logs = session.query(DataFetchLog).filter(
                DataFetchLog.source == "nhl_api"
            ).all()
            assert len(logs) == 1
            assert logs[0].status == "success"
            assert logs[0].records_fetched == 12

    def test_fetch_log_with_error(self, test_db):
        """Test creating a failed fetch log."""
        with test_db.session_scope() as session:
            log = DataFetchLog(
                source="moneypuck",
                fetch_type="predictions",
                status="failed",
                error_message="Connection timeout",
                duration_seconds=30.0,
            )
            session.add(log)

        with test_db.session_scope() as session:
            log = session.query(DataFetchLog).filter(
                DataFetchLog.status == "failed"
            ).first()
            assert log is not None
            assert "timeout" in log.error_message.lower()
