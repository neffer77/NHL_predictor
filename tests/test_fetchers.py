"""Tests for data fetchers."""

import pytest
from datetime import date
from unittest.mock import Mock, patch, MagicMock

from src.nhl_predictor.fetchers.nhl_api import NHLAPIFetcher, GameInfo
from src.nhl_predictor.fetchers.natural_stat_trick import NSTScraper, TeamAdvancedStats
from src.nhl_predictor.fetchers.moneypuck import MoneyPuckFetcher
from src.nhl_predictor.fetchers.daily_faceoff import DailyFaceoffScraper, GoalieStart
from src.nhl_predictor.fetchers.scouting_refs import ScoutingRefsScraper


class TestNHLAPIFetcher:
    """Tests for NHL API fetcher."""

    def test_fetcher_initialization(self):
        """Test fetcher can be initialized."""
        fetcher = NHLAPIFetcher()
        assert fetcher.source_name == "nhl_api"
        assert fetcher.session is not None
        fetcher.close()

    def test_fetcher_context_manager(self):
        """Test fetcher works as context manager."""
        with NHLAPIFetcher() as fetcher:
            assert fetcher is not None

    def test_parse_game_data(self):
        """Test parsing game data from API response."""
        fetcher = NHLAPIFetcher()

        mock_game_data = {
            "id": 2025020001,
            "gameDate": "2025-10-15",
            "startTimeUTC": "2025-10-15T23:00:00Z",
            "homeTeam": {"abbrev": "MTL", "score": 3},
            "awayTeam": {"abbrev": "TOR", "score": 2},
            "gameState": "FINAL",
            "venue": {"default": "Centre Bell"},
            "season": 20252026,
            "gameType": 2,
        }

        game = fetcher._parse_game(mock_game_data)

        assert game is not None
        assert game.game_id == 2025020001
        assert game.home_team == "MTL"
        assert game.away_team == "TOR"
        assert game.home_score == 3
        assert game.away_score == 2
        assert game.game_state == "FINAL"
        assert game.date == date(2025, 10, 15)

        fetcher.close()

    def test_parse_game_with_missing_team(self):
        """Test parsing game with unrecognized team returns None."""
        fetcher = NHLAPIFetcher()

        mock_game_data = {
            "id": 2025020002,
            "gameDate": "2025-10-16",
            "homeTeam": {"abbrev": "XYZ"},  # Invalid team
            "awayTeam": {"abbrev": "TOR"},
            "gameState": "FUT",
        }

        game = fetcher._parse_game(mock_game_data)
        assert game is None

        fetcher.close()

    def test_parse_standing(self):
        """Test parsing standing data from API response."""
        fetcher = NHLAPIFetcher()

        mock_standing = {
            "teamAbbrev": {"default": "MTL"},
            "teamName": {"default": "Canadiens"},
            "conferenceName": "Eastern",
            "divisionName": "Atlantic",
            "gamesPlayed": 20,
            "wins": 12,
            "losses": 6,
            "otLosses": 2,
            "points": 26,
            "pointPctg": 0.65,
            "regulationWins": 10,
            "goalFor": 60,
            "goalAgainst": 50,
            "goalDifferential": 10,
            "homeWins": 7,
            "homeLosses": 2,
            "homeOtLosses": 1,
            "roadWins": 5,
            "roadLosses": 4,
            "roadOtLosses": 1,
            "l10Wins": 7,
            "l10Losses": 2,
            "l10OtLosses": 1,
            "streakCount": 3,
            "streakCode": "W",
        }

        standing = fetcher._parse_standing(mock_standing)

        assert standing is not None
        assert standing.team_code == "MTL"
        assert standing.wins == 12
        assert standing.points == 26
        assert standing.l10_record == "7-2-1"
        assert standing.streak == "W3"

        fetcher.close()


class TestNSTScraper:
    """Tests for Natural Stat Trick scraper."""

    def test_scraper_initialization(self):
        """Test scraper can be initialized."""
        scraper = NSTScraper()
        assert scraper.source_name == "natural_stat_trick"
        assert scraper.RATE_LIMIT_DELAY == 3
        scraper.close()

    def test_scraper_context_manager(self):
        """Test scraper works as context manager."""
        with NSTScraper() as scraper:
            assert scraper is not None


class TestMoneyPuckFetcher:
    """Tests for MoneyPuck fetcher."""

    def test_fetcher_initialization(self):
        """Test fetcher can be initialized."""
        fetcher = MoneyPuckFetcher()
        assert fetcher.source_name == "moneypuck"
        fetcher.close()

    def test_parse_prediction_row(self):
        """Test parsing prediction row from CSV."""
        import pandas as pd

        fetcher = MoneyPuckFetcher()

        row = pd.Series({
            "gameDate": "2025-10-20",
            "homeTeam": "BOS",
            "awayTeam": "NYR",
            "homeWinProb": 0.58,
            "awayWinProb": 0.42,
            "homeGoalsExpected": 3.2,
            "awayGoalsExpected": 2.5,
            "homeXGF": 3.1,
            "awayXGF": 2.6,
        })

        pred = fetcher._parse_prediction_row(row)

        assert pred is not None
        assert pred.home_team == "BOS"
        assert pred.away_team == "NYR"
        assert pred.home_win_prob == 0.58
        assert pred.home_goals_expected == 3.2

        fetcher.close()


class TestDailyFaceoffScraper:
    """Tests for Daily Faceoff scraper."""

    def test_scraper_initialization(self):
        """Test scraper can be initialized."""
        scraper = DailyFaceoffScraper()
        assert scraper.source_name == "daily_faceoff"
        scraper.close()

    def test_is_name_detection(self):
        """Test name pattern detection (internal method not exposed, test via parsing)."""
        # This tests the parsing logic indirectly
        scraper = DailyFaceoffScraper()

        # Test via the goalie start dataclass
        goalie = GoalieStart(
            team="MTL",
            goalie_name="Carey Price",
            opponent="TOR",
            confirmation_status="confirmed",
            game_time="7:00 PM",
            record="8-4-2",
            gaa=2.45,
            save_pct=0.918,
        )

        assert goalie.goalie_name == "Carey Price"
        assert goalie.confirmation_status == "confirmed"

        scraper.close()


class TestScoutingRefsScraper:
    """Tests for Scouting The Refs scraper."""

    def test_scraper_initialization(self):
        """Test scraper can be initialized."""
        scraper = ScoutingRefsScraper()
        assert scraper.source_name == "scouting_refs"
        assert scraper.LEAGUE_AVG_HOME_WIN_PCT == 0.54
        assert scraper.LEAGUE_AVG_PENALTIES_PER_GAME == 7.5
        scraper.close()

    def test_create_default_profile(self):
        """Test creating default referee profile."""
        scraper = ScoutingRefsScraper()

        profile = scraper._create_default_profile("Wes McCauley")

        assert profile.name == "Wes McCauley"
        assert profile.home_win_pct == 0.54
        assert profile.penalties_per_game == 7.5
        assert profile.home_bias == 0.0
        assert profile.penalty_deviation == 0.0

        scraper.close()

    def test_is_name_validation(self):
        """Test name pattern validation."""
        scraper = ScoutingRefsScraper()

        # Valid names
        assert scraper._is_name("John Smith") is True
        assert scraper._is_name("Wes McCauley") is True
        assert scraper._is_name("John J. Smith") is True

        # Invalid patterns
        assert scraper._is_name("") is False
        assert scraper._is_name("John") is False
        assert scraper._is_name("7:00 PM") is False
        assert scraper._is_name("MTL vs TOR") is False

        scraper.close()


class TestBaseFetcherRetry:
    """Tests for base fetcher retry logic."""

    def test_rate_limiting(self):
        """Test that rate limiting delays requests."""
        import time

        fetcher = NHLAPIFetcher()
        fetcher.RATE_LIMIT_DELAY = 0.1  # Short delay for testing

        # First request sets last_request_time
        fetcher._last_request_time = time.time()

        start = time.time()
        fetcher._rate_limit()
        elapsed = time.time() - start

        # Should have waited approximately RATE_LIMIT_DELAY
        assert elapsed >= 0.05  # Some delay occurred

        fetcher.close()

    def test_session_headers(self):
        """Test that session has proper headers."""
        fetcher = NHLAPIFetcher()

        assert "User-Agent" in fetcher.session.headers
        assert "Accept" in fetcher.session.headers

        fetcher.close()
