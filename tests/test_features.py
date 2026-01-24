"""Tests for feature engineering modules."""

import pytest
from datetime import date, timedelta
from unittest.mock import Mock, patch, MagicMock

from src.nhl_predictor.features.xg_aggregator import XGAggregator, TeamXGMetrics
from src.nhl_predictor.features.hdcf_calculator import HDCFCalculator, TeamHDCFMetrics
from src.nhl_predictor.features.gsax_calculator import GSAxCalculator, GoalieGSAxMetrics, GoalieMatchup
from src.nhl_predictor.features.pdo_tracker import PDOTracker, TeamPDOMetrics
from src.nhl_predictor.features.schedule_analyzer import ScheduleAnalyzer, TeamScheduleContext
from src.nhl_predictor.features.referee_analyzer import RefereeAnalyzer, RefereeBiasAnalysis
from src.nhl_predictor.features.powerplay_analyzer import PowerPlayAnalyzer, TeamPowerPlayMetrics
from src.nhl_predictor.features.contextual_adjustments import (
    ContextualAdjuster, InjuryImpact, DesperationFactor
)


class TestXGAggregator:
    """Tests for XG aggregator."""

    def test_team_xg_metrics_dataclass(self):
        """Test TeamXGMetrics dataclass."""
        metrics = TeamXGMetrics(
            team="MTL",
            games_played=20,
            xgf=45.5,
            xga=42.0,
            xgf_pct=52.0,
            xgf_per_game=2.275,
            xga_per_game=2.1,
        )
        assert metrics.team == "MTL"
        assert metrics.xgf_pct == 52.0
        assert metrics.games_played == 20

    def test_aggregator_initialization(self):
        """Test aggregator can be initialized."""
        aggregator = XGAggregator()
        assert aggregator.db is not None


class TestHDCFCalculator:
    """Tests for HDCF calculator."""

    def test_hdcf_metrics_dataclass(self):
        """Test TeamHDCFMetrics dataclass."""
        metrics = TeamHDCFMetrics(
            team="BOS",
            games_played=25,
            hdcf=120.0,
            hdca=95.0,
            hdcf_pct=55.8,
            hdcf_per_game=4.8,
            hdca_per_game=3.8,
            is_counter_attack=False,
        )
        assert metrics.team == "BOS"
        assert metrics.hdcf_pct == 55.8

    def test_counter_attack_detection(self):
        """Test counter-attack profile detection."""
        calculator = HDCFCalculator()

        # Low CF, High HDCF = counter-attack
        is_counter = calculator._detect_counter_attack_profile(45.0, 54.0)
        assert is_counter is True

        # High CF, High HDCF = not counter-attack
        is_counter = calculator._detect_counter_attack_profile(55.0, 54.0)
        assert is_counter is False

        # Low CF, Low HDCF = not counter-attack
        is_counter = calculator._detect_counter_attack_profile(45.0, 48.0)
        assert is_counter is False


class TestGSAxCalculator:
    """Tests for GSAx calculator."""

    def test_goalie_metrics_dataclass(self):
        """Test GoalieGSAxMetrics dataclass."""
        metrics = GoalieGSAxMetrics(
            player_name="Carey Price",
            team="MTL",
            games_played=30,
            games_started=28,
            gsax_season=8.5,
            gsax_per_game=0.28,
            gsax_rolling_10=4.2,
            gsax_rolling_20=6.8,
            is_hot=True,
            is_cold=False,
        )
        assert metrics.player_name == "Carey Price"
        assert metrics.is_hot is True
        assert metrics.gsax_rolling_10 == 4.2

    def test_goalie_matchup_dataclass(self):
        """Test GoalieMatchup dataclass."""
        home_goalie = GoalieGSAxMetrics(
            player_name="Jeremy Swayman",
            team="BOS",
            games_played=35,
            games_started=35,
            gsax_season=12.0,
            gsax_per_game=0.34,
            gsax_rolling_10=5.5,
            gsax_rolling_20=10.0,
            is_hot=True,
            is_cold=False,
        )
        away_goalie = GoalieGSAxMetrics(
            player_name="Igor Shesterkin",
            team="NYR",
            games_played=40,
            games_started=40,
            gsax_season=15.0,
            gsax_per_game=0.375,
            gsax_rolling_10=3.0,
            gsax_rolling_20=8.0,
            is_hot=False,
            is_cold=False,
        )

        matchup = GoalieMatchup(
            home_goalie=home_goalie,
            away_goalie=away_goalie,
            gsax_differential=2.5,
            advantage="home",
            is_mismatch=False,
        )

        assert matchup.advantage == "home"
        assert matchup.gsax_differential == 2.5

    def test_hot_cold_thresholds(self):
        """Test hot/cold goalie thresholds."""
        calculator = GSAxCalculator()

        assert calculator.HOT_THRESHOLD == 3.0
        assert calculator.COLD_THRESHOLD == -3.0
        assert calculator.MISMATCH_THRESHOLD == 5.0


class TestPDOTracker:
    """Tests for PDO tracker."""

    def test_pdo_metrics_dataclass(self):
        """Test TeamPDOMetrics dataclass."""
        metrics = TeamPDOMetrics(
            team="TOR",
            games_played=30,
            pdo=1025.0,
            shooting_pct=10.5,
            save_pct=92.0,
            pdo_deviation=25.0,
            is_lucky=True,
            is_unlucky=False,
            expected_regression=-12.5,
        )
        assert metrics.team == "TOR"
        assert metrics.is_lucky is True
        assert metrics.expected_regression == -12.5

    def test_pdo_thresholds(self):
        """Test PDO thresholds."""
        tracker = PDOTracker()

        assert tracker.LEAGUE_AVG_PDO == 1000.0
        assert tracker.LUCKY_THRESHOLD == 1020.0
        assert tracker.UNLUCKY_THRESHOLD == 980.0
        assert tracker.EXTREME_LUCKY == 1040.0
        assert tracker.EXTREME_UNLUCKY == 960.0


class TestScheduleAnalyzer:
    """Tests for schedule analyzer."""

    def test_schedule_context_dataclass(self):
        """Test TeamScheduleContext dataclass."""
        context = TeamScheduleContext(
            team="EDM",
            game_date=date(2025, 11, 15),
            rest_days=1,
            is_back_to_back=False,
            is_three_in_four=True,
            is_four_in_six=False,
            last_game_location="VAN",
            games_on_road_trip=3,
            is_first_home_after_road=False,
            timezone_change=0,
            previous_game_date=date(2025, 11, 14),
            previous_opponent="VAN",
            previous_was_home=False,
            fatigue_score=0.5,
            travel_score=0.2,
        )
        assert context.team == "EDM"
        assert context.is_three_in_four is True
        assert context.fatigue_score == 0.5

    def test_fatigue_score_calculation(self):
        """Test fatigue score calculation."""
        analyzer = ScheduleAnalyzer()

        # Back-to-back with 3-in-4 = high fatigue
        score = analyzer._calculate_fatigue_score(0, True, False)
        assert score >= 0.7

        # Well rested = low fatigue
        score = analyzer._calculate_fatigue_score(3, False, False)
        assert score == 0.0

    def test_travel_score_calculation(self):
        """Test travel score calculation."""
        analyzer = ScheduleAnalyzer()

        # Cross-country travel + long road trip
        score = analyzer._calculate_travel_score(3, 5)
        assert score >= 0.7

        # No travel impact
        score = analyzer._calculate_travel_score(0, 0)
        assert score == 0.0

    def test_timezone_offsets(self):
        """Test timezone offset mapping."""
        analyzer = ScheduleAnalyzer()

        assert "America/New_York" in analyzer.TIMEZONE_OFFSETS
        assert "America/Los_Angeles" in analyzer.TIMEZONE_OFFSETS
        assert analyzer.TIMEZONE_OFFSETS["America/Los_Angeles"] == -3


class TestRefereeAnalyzer:
    """Tests for referee analyzer."""

    def test_neutral_analysis(self):
        """Test neutral analysis when no referee data."""
        analyzer = RefereeAnalyzer()
        analysis = analyzer._create_neutral_analysis()

        assert analysis.bias_tag == "neutral"
        assert analysis.event_level == "average"
        assert analysis.home_adjustment == 1.0

    def test_league_averages(self):
        """Test league average constants."""
        analyzer = RefereeAnalyzer()

        assert analyzer.LEAGUE_AVG_HOME_WIN_PCT == 0.54
        assert analyzer.LEAGUE_AVG_PENALTIES == 7.5


class TestPowerPlayAnalyzer:
    """Tests for power play analyzer."""

    def test_pp_metrics_dataclass(self):
        """Test TeamPowerPlayMetrics dataclass."""
        metrics = TeamPowerPlayMetrics(
            team="EDM",
            pp_pct=28.5,
            pp_opportunities=100,
            pp_xg_per_60=10.5,
            pk_pct=82.0,
            times_shorthanded=95,
            pp_luck=2.0,
            is_pp_breakout_candidate=False,
            is_pp_regression_candidate=False,
            penalty_differential=5.0,
        )
        assert metrics.team == "EDM"
        assert metrics.pp_pct == 28.5

    def test_expected_pp_calculation(self):
        """Test expected PP% from xG."""
        analyzer = PowerPlayAnalyzer()

        # 8.0 xG/60 should give ~20% PP
        expected = analyzer._calculate_expected_pp_pct(8.0)
        assert expected == 20.0

        # Higher xG = higher expected PP
        expected = analyzer._calculate_expected_pp_pct(10.0)
        assert expected == 25.0


class TestContextualAdjuster:
    """Tests for contextual adjustments."""

    def test_injury_impact_dataclass(self):
        """Test InjuryImpact dataclass."""
        impact = InjuryImpact(
            team="TOR",
            has_key_injury=True,
            mvp_out=True,
            injured_players=["Auston Matthews"],
            scoring_impact=0.30,
            adjustment_factor=0.90,
        )
        assert impact.team == "TOR"
        assert impact.mvp_out is True
        assert impact.adjustment_factor == 0.90

    def test_elite_shooters_mapping(self):
        """Test elite shooters are mapped."""
        adjuster = ContextualAdjuster()

        assert "TOR" in adjuster.ELITE_SHOOTERS
        assert "EDM" in adjuster.ELITE_SHOOTERS
        assert "Auston Matthews" in adjuster.ELITE_SHOOTERS["TOR"]
        assert "Connor McDavid" in adjuster.ELITE_SHOOTERS["EDM"]

    def test_injury_impact_assessment(self):
        """Test injury impact calculation."""
        adjuster = ContextualAdjuster()

        # MVP out
        impact = adjuster.assess_injury_impact("TOR", ["Auston Matthews"])
        assert impact.mvp_out is True
        assert impact.adjustment_factor == 0.90

        # Key player out
        impact = adjuster.assess_injury_impact("TOR", ["Mitch Marner"])
        assert impact.has_key_injury is True
        assert impact.adjustment_factor == 0.95

        # No injuries
        impact = adjuster.assess_injury_impact("TOR", [])
        assert impact.has_key_injury is False
        assert impact.adjustment_factor == 1.0

    def test_desperation_factor_dataclass(self):
        """Test DesperationFactor dataclass."""
        factor = DesperationFactor(
            team="OTT",
            games_played=70,
            points=85,
            playoff_cutoff_points=82,
            points_from_cutoff=3,
            is_desperate=True,
            is_eliminated=False,
            is_clinched=False,
            desperation_adjustment=1.02,
        )
        assert factor.team == "OTT"
        assert factor.is_desperate is True
        assert factor.desperation_adjustment == 1.02

    def test_coach_system_classification(self):
        """Test system classification thresholds."""
        adjuster = ContextualAdjuster()

        # Low event = combined xG < 4.5
        # High event = combined xG > 5.5
        # These are tested implicitly through the classify_coach_system method


class TestFeatureIntegration:
    """Integration tests for feature modules."""

    def test_all_features_importable(self):
        """Test all feature modules can be imported."""
        from src.nhl_predictor.features import (
            XGAggregator,
            HDCFCalculator,
            GSAxCalculator,
            PDOTracker,
            ScheduleAnalyzer,
            RefereeAnalyzer,
            PowerPlayAnalyzer,
            ContextualAdjuster,
        )

        # All classes should be importable
        assert XGAggregator is not None
        assert HDCFCalculator is not None
        assert GSAxCalculator is not None
        assert PDOTracker is not None
        assert ScheduleAnalyzer is not None
        assert RefereeAnalyzer is not None
        assert PowerPlayAnalyzer is not None
        assert ContextualAdjuster is not None

    def test_convenience_functions_importable(self):
        """Test convenience functions can be imported."""
        from src.nhl_predictor.features import (
            get_team_xg,
            get_matchup_xg,
            get_team_hdcf,
            get_matchup_hdcf,
            get_goalie_gsax,
            get_matchup_goalie_analysis,
            get_team_pdo,
            get_pdo_mismatch,
            find_regression_candidates,
            get_schedule_context,
            get_matchup_schedule,
            find_scheduled_losses,
            get_referee_analysis,
            get_special_teams,
            get_matchup_special_teams,
            assess_injury_impact,
            assess_desperation,
            classify_system,
        )

        # All functions should be importable
        assert callable(get_team_xg)
        assert callable(get_matchup_hdcf)
        assert callable(find_regression_candidates)
        assert callable(assess_injury_impact)
