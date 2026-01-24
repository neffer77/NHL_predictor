"""Pytest configuration and fixtures."""

import pytest
from datetime import date, datetime
from pathlib import Path
from typing import Generator

import sys
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))


@pytest.fixture
def sample_date() -> date:
    """Sample date for testing."""
    return date(2026, 1, 15)


@pytest.fixture
def sample_teams() -> dict:
    """Sample team data."""
    return {
        "home": "BOS",
        "away": "TOR",
        "home_full": "Boston Bruins",
        "away_full": "Toronto Maple Leafs",
    }


@pytest.fixture
def sample_game_data(sample_date, sample_teams) -> dict:
    """Sample game data for testing."""
    return {
        "game_id": 2025020123,
        "date": sample_date,
        "home_team": sample_teams["home"],
        "away_team": sample_teams["away"],
        "start_time": "19:00",
        "venue": "TD Garden",
    }


@pytest.fixture
def sample_team_stats() -> dict:
    """Sample team statistics."""
    return {
        "team": "BOS",
        "games_played": 45,
        "xgf_pct": 54.2,
        "hdcf_pct": 52.8,
        "cf_pct": 51.5,
        "pdo": 1012,
        "sh_pct": 10.2,
        "sv_pct": 0.912,
    }


@pytest.fixture
def sample_goalie_stats() -> dict:
    """Sample goalie statistics."""
    return {
        "name": "Jeremy Swayman",
        "team": "BOS",
        "games": 35,
        "gsax": 8.5,
        "save_pct": 0.918,
        "goals_against_avg": 2.35,
    }


@pytest.fixture
def sample_prediction() -> dict:
    """Sample prediction data."""
    return {
        "home_win_prob": 0.58,
        "away_win_prob": 0.42,
        "home_edge": 0.05,
        "away_edge": -0.03,
        "kelly_score": 0.06,
    }


@pytest.fixture
def mock_db(tmp_path) -> Generator:
    """Create a temporary test database."""
    from nhl_predictor.models.database import Database

    db_path = tmp_path / "test_nhl.db"
    db = Database(str(db_path))
    db.create_tables()

    yield db

    # Cleanup
    if db_path.exists():
        db_path.unlink()


@pytest.fixture
def populated_db(mock_db, sample_date, sample_teams):
    """Database with sample data."""
    from nhl_predictor.models.schema import Game, TeamDailyStats, GoalieStats

    with mock_db.session_scope() as session:
        # Add a game
        game = Game(
            game_id=2025020123,
            date=sample_date,
            home_team=sample_teams["home"],
            away_team=sample_teams["away"],
            home_score=3,
            away_score=2,
            winner=sample_teams["home"],
        )
        session.add(game)

        # Add team stats
        for team in [sample_teams["home"], sample_teams["away"]]:
            stats = TeamDailyStats(
                date=sample_date,
                team=team,
                games_played=45,
                xgf_pct=52.0 + (2 if team == sample_teams["home"] else 0),
                hdcf_pct=51.5,
                cf_pct=50.5,
                pdo=1005,
            )
            session.add(stats)

    return mock_db
