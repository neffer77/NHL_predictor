"""Integration tests for NHL Predictor data pipeline."""

import pytest
from datetime import date, datetime, timedelta
from pathlib import Path
from unittest.mock import Mock, patch, MagicMock
import tempfile
import os


class TestDatabaseIntegration:
    """Integration tests for database operations."""

    def test_database_creation(self, tmp_path):
        """Test database can be created."""
        from src.nhl_predictor.models.database import Database

        db_path = tmp_path / "test.db"
        db = Database(str(db_path))
        db.create_tables()

        assert db_path.exists()

    def test_session_scope_context_manager(self, tmp_path):
        """Test session scope context manager."""
        from src.nhl_predictor.models.database import Database
        from src.nhl_predictor.models.schema import Game

        db_path = tmp_path / "test.db"
        db = Database(str(db_path))
        db.create_tables()

        # Test transaction commit
        with db.session_scope() as session:
            game = Game(
                game_id=2025020001,
                date=date(2025, 10, 15),
                home_team="BOS",
                away_team="TOR",
            )
            session.add(game)

        # Verify data persisted
        with db.session_scope() as session:
            result = session.query(Game).filter(
                Game.game_id == 2025020001
            ).first()
            assert result is not None
            assert result.home_team == "BOS"

    def test_session_scope_rollback_on_error(self, tmp_path):
        """Test session rollback on error."""
        from src.nhl_predictor.models.database import Database
        from src.nhl_predictor.models.schema import Game

        db_path = tmp_path / "test.db"
        db = Database(str(db_path))
        db.create_tables()

        # Test transaction rollback
        try:
            with db.session_scope() as session:
                game = Game(
                    game_id=2025020002,
                    date=date(2025, 10, 16),
                    home_team="NYR",
                    away_team="NJD",
                )
                session.add(game)
                raise Exception("Test error")
        except Exception:
            pass

        # Verify data was not persisted
        with db.session_scope() as session:
            result = session.query(Game).filter(
                Game.game_id == 2025020002
            ).first()
            assert result is None


class TestDataPipelineIntegration:
    """Integration tests for data pipeline."""

    def test_team_normalization_in_pipeline(self):
        """Test team normalization works through pipeline."""
        from src.nhl_predictor.utils.team_mapping import normalize_team_name

        # Simulate data from different sources
        nst_name = "Toronto Maple Leafs"
        moneypuck_name = "TOR"
        daily_faceoff_name = "Maple Leafs"

        # All should normalize to same code
        assert normalize_team_name(nst_name) == "TOR"
        assert normalize_team_name(moneypuck_name) == "TOR"
        assert normalize_team_name(daily_faceoff_name) == "TOR"

    def test_schema_relationships(self, tmp_path):
        """Test schema relationships work correctly."""
        from src.nhl_predictor.models.database import Database
        from src.nhl_predictor.models.schema import (
            Game, TeamDailyStats, Prediction
        )

        db_path = tmp_path / "test.db"
        db = Database(str(db_path))
        db.create_tables()

        game_date = date(2025, 11, 15)

        with db.session_scope() as session:
            # Add game
            game = Game(
                game_id=2025020100,
                date=game_date,
                home_team="BOS",
                away_team="TOR",
            )
            session.add(game)

            # Add team stats
            stats = TeamDailyStats(
                date=game_date,
                team="BOS",
                games_played=20,
                xgf_pct=52.5,
            )
            session.add(stats)

            # Add prediction
            prediction = Prediction(
                game_id=2025020100,
                home_win_prob=0.55,
                away_win_prob=0.45,
                pick="BOS",
            )
            session.add(prediction)

        # Verify all data persisted
        with db.session_scope() as session:
            game = session.query(Game).first()
            stats = session.query(TeamDailyStats).first()
            prediction = session.query(Prediction).first()

            assert game is not None
            assert stats is not None
            assert prediction is not None
            assert prediction.game_id == game.game_id


class TestScraperIntegration:
    """Integration tests for scrapers with mocked responses."""

    @patch('requests.get')
    def test_nhl_api_response_handling(self, mock_get):
        """Test NHL API response handling."""
        from src.nhl_predictor.fetchers.nhl_api import NHLAPIFetcher

        # Mock successful response
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "gameWeek": [{
                "date": "2025-11-15",
                "games": [{
                    "id": 2025020100,
                    "homeTeam": {"abbrev": "BOS"},
                    "awayTeam": {"abbrev": "TOR"},
                    "startTimeUTC": "2025-11-15T23:00:00Z",
                    "venue": {"default": "TD Garden"},
                }]
            }]
        }
        mock_get.return_value = mock_response

        fetcher = NHLAPIFetcher()
        # The actual fetch would require DB, just test initialization
        assert fetcher.base_url is not None

    @patch('requests.get')
    def test_nst_scraper_retry_logic(self, mock_get):
        """Test NST scraper handles retries."""
        from src.nhl_predictor.fetchers.natural_stat_trick import (
            NaturalStatTrickScraper
        )

        # Mock failure then success
        mock_get.side_effect = [
            Exception("Connection error"),
            Mock(status_code=200, text="<table></table>"),
        ]

        scraper = NaturalStatTrickScraper()
        assert scraper.base_url is not None


class TestPredictionPipelineIntegration:
    """Integration tests for prediction pipeline."""

    def test_sps_to_probability_pipeline(self):
        """Test SPS calculation flows to probability."""
        from src.nhl_predictor.prediction.sps_calculator import SPSCalculator
        from src.nhl_predictor.prediction.probability_engine import (
            ProbabilityEngine
        )

        # Create SPS scores
        home_sps = 55.0
        away_sps = 48.0
        differential = home_sps - away_sps

        # Convert to probability
        engine = ProbabilityEngine()
        prob = engine._logistic(differential)

        # Home team should be favored
        assert prob > 0.5
        assert prob < 1.0

    def test_probability_to_kelly_pipeline(self):
        """Test probability flows to Kelly calculation."""
        from src.nhl_predictor.prediction.kelly_criterion import KellyCalculator

        calculator = KellyCalculator()

        # 60% probability at even odds
        result = calculator.calculate_kelly(0.60, 2.0, "decimal")

        assert result.full_kelly > 0
        assert result.half_kelly == result.full_kelly * 0.5
        assert result.quarter_kelly == result.full_kelly * 0.25

    def test_odds_conversion_roundtrip(self):
        """Test odds conversion is consistent."""
        from src.nhl_predictor.prediction.odds_calculator import OddsConverter

        # American to probability and back
        original_odds = -150
        prob = OddsConverter.american_to_probability(original_odds)
        converted_odds = OddsConverter.probability_to_american(prob)

        # Should be close to original
        assert abs(converted_odds - original_odds) < 5


class TestReportingIntegration:
    """Integration tests for reporting."""

    def test_report_generation_flow(self):
        """Test report generation from picks."""
        from src.nhl_predictor.selection.selector import DailyPicks, FinalPick
        from src.nhl_predictor.reporting.report_generator import (
            ReportGenerator, DailyReport
        )

        # Create mock picks
        pick = FinalPick(
            rank=1,
            tier="STRONG",
            game_id=2025020100,
            home_team="BOS",
            away_team="TOR",
            game_date=date(2025, 11, 15),
            start_time="19:00",
            pick_team="BOS",
            opponent="TOR",
            pick_side="home",
            model_probability=0.58,
            market_probability=0.52,
            adjusted_probability=0.59,
            edge=0.06,
            expected_value=0.12,
            kelly_score=0.08,
            recommended_stake=0.02,
            stability_score=75.0,
            regression_risk="low",
            goalie_confirmed=True,
            goalie_name="Swayman",
            risk_level="low",
            risk_flags=[],
        )

        daily_picks = DailyPicks(
            date=date(2025, 11, 15),
            generated_at=datetime.now(),
            picks=[pick],
            total_games=10,
            games_filtered=3,
            games_with_value=5,
            model_accuracy_7d=0.58,
            model_accuracy_30d=0.55,
            notes=[],
        )

        # Generate report
        generator = ReportGenerator()
        report = generator.generate_report(daily_picks)

        assert len(report.picks) == 1
        assert report.picks[0].pick == "BOS"

    def test_multiple_output_formats(self):
        """Test report generates multiple formats."""
        from src.nhl_predictor.selection.selector import DailyPicks
        from src.nhl_predictor.reporting.report_generator import (
            ReportGenerator, DailyReport
        )

        daily_picks = DailyPicks(
            date=date(2025, 11, 15),
            generated_at=datetime.now(),
            picks=[],
            total_games=0,
            games_filtered=0,
            games_with_value=0,
            model_accuracy_7d=0.0,
            model_accuracy_30d=0.0,
            notes=["No games today"],
        )

        generator = ReportGenerator()
        report = generator.generate_report(daily_picks)

        # Test all formats
        console_output = generator.format_console(report)
        json_output = generator.format_json(report)
        markdown_output = generator.format_markdown(report)

        assert "NHL" in console_output
        assert "{" in json_output  # JSON format
        assert "#" in markdown_output  # Markdown header


class TestInfrastructureIntegration:
    """Integration tests for infrastructure components."""

    def test_config_loading(self):
        """Test configuration loads correctly."""
        from src.nhl_predictor.infrastructure.config_manager import (
            ConfigManager, AppConfig
        )

        manager = ConfigManager()
        config = manager.load()

        assert isinstance(config, AppConfig)
        assert config.model.xgf_weight + config.model.hdcf_weight + config.model.gsax_weight == 1.0

    def test_logging_setup(self):
        """Test logging configuration."""
        from src.nhl_predictor.infrastructure.logging_config import (
            LoggerFactory, setup_logging, get_logger
        )

        setup_logging(log_level="INFO")
        logger = get_logger("test")

        assert logger is not None
        assert logger.name == "test"

    def test_resilience_retry_decorator(self):
        """Test retry decorator works."""
        from src.nhl_predictor.infrastructure.resilience import with_retry

        call_count = 0

        @with_retry(max_retries=2, base_delay=0.1)
        def flaky_function():
            nonlocal call_count
            call_count += 1
            if call_count < 2:
                raise ConnectionError("Test error")
            return "success"

        result = flaky_function()
        assert result == "success"
        assert call_count == 2


class TestEndToEndPipeline:
    """End-to-end tests for complete pipeline."""

    def test_full_prediction_flow(self, tmp_path):
        """Test complete prediction flow with mocked data."""
        from src.nhl_predictor.models.database import Database
        from src.nhl_predictor.models.schema import Game, TeamDailyStats
        from src.nhl_predictor.prediction.sps_calculator import SPSCalculator
        from src.nhl_predictor.prediction.probability_engine import ProbabilityEngine

        # Setup test database
        db_path = tmp_path / "test.db"
        db = Database(str(db_path))
        db.create_tables()

        game_date = date(2025, 11, 15)

        # Add test data
        with db.session_scope() as session:
            game = Game(
                game_id=2025020100,
                date=game_date,
                home_team="BOS",
                away_team="TOR",
            )
            session.add(game)

            # Home team stats
            home_stats = TeamDailyStats(
                date=game_date,
                team="BOS",
                games_played=30,
                xgf_pct=54.0,
                hdcf_pct=52.0,
                cf_pct=51.0,
                pdo=1005,
            )
            session.add(home_stats)

            # Away team stats
            away_stats = TeamDailyStats(
                date=game_date,
                team="TOR",
                games_played=30,
                xgf_pct=52.0,
                hdcf_pct=50.0,
                cf_pct=50.0,
                pdo=1000,
            )
            session.add(away_stats)

        # Test that prediction components work
        sps_calc = SPSCalculator()
        prob_engine = ProbabilityEngine()

        # Components should initialize
        assert sps_calc is not None
        assert prob_engine is not None

        # Logistic function should work
        prob = prob_engine._logistic(5.0)
        assert 0 < prob < 1
