"""Tests for prediction engine modules."""

import pytest
import math
from datetime import date

from src.nhl_predictor.prediction.sps_calculator import (
    SPSCalculator, TeamSPS, MatchupSPS
)
from src.nhl_predictor.prediction.contextual_layer import (
    ContextualAdjustmentLayer, AdjustmentFactors, AdjustedTeamSPS
)
from src.nhl_predictor.prediction.probability_engine import (
    ProbabilityEngine, WinProbability
)
from src.nhl_predictor.prediction.odds_calculator import (
    OddsConverter, EdgeCalculator, MarketOdds, EdgeAnalysis
)
from src.nhl_predictor.prediction.kelly_criterion import (
    KellyCalculator, KellyResult
)
from src.nhl_predictor.prediction.bayesian_prior import (
    BayesianPriorAdjuster, BayesianAdjustedMetrics
)
from src.nhl_predictor.prediction.calibration import (
    ModelCalibrator, CalibrationMetrics
)


class TestSPSCalculator:
    """Tests for SPS Calculator."""

    def test_sps_initialization(self):
        """Test SPS calculator initializes with correct weights."""
        calc = SPSCalculator()
        total = calc.xgf_weight + calc.hdcf_weight + calc.gsax_weight
        assert abs(total - 1.0) < 0.01

    def test_sps_custom_weights(self):
        """Test SPS calculator with custom weights."""
        calc = SPSCalculator(xgf_weight=0.5, hdcf_weight=0.3, gsax_weight=0.2)
        assert calc.xgf_weight == 0.5
        assert calc.hdcf_weight == 0.3
        assert calc.gsax_weight == 0.2

    def test_normalize_function(self):
        """Test value normalization."""
        calc = SPSCalculator()

        # Test boundary values
        assert calc._normalize(45.0, 45.0, 55.0) == 0.0
        assert calc._normalize(55.0, 45.0, 55.0) == 100.0
        assert calc._normalize(50.0, 45.0, 55.0) == 50.0

        # Test clamping
        assert calc._normalize(40.0, 45.0, 55.0) == 0.0
        assert calc._normalize(60.0, 45.0, 55.0) == 100.0

    def test_team_sps_dataclass(self):
        """Test TeamSPS dataclass."""
        sps = TeamSPS(
            team="MTL",
            date=date(2025, 11, 1),
            xgf_score=55.0,
            hdcf_score=52.0,
            gsax_score=60.0,
            xgf_weight=0.45,
            hdcf_weight=0.25,
            gsax_weight=0.30,
            sps=55.55,
            xgf_pct=52.5,
            hdcf_pct=51.0,
            goalie_gsax=3.5,
            goalie_name="Carey Price",
        )
        assert sps.team == "MTL"
        assert sps.sps == 55.55


class TestContextualAdjustmentLayer:
    """Tests for Contextual Adjustment Layer."""

    def test_adjustment_factors_defaults(self):
        """Test AdjustmentFactors default values."""
        factors = AdjustmentFactors()
        assert factors.home_ice == 1.0
        assert factors.fatigue == 1.0
        assert factors.travel == 1.0
        assert factors.total_multiplier == 1.0
        assert factors.is_back_to_back is False

    def test_adjustment_factors_calculation(self):
        """Test total multiplier calculation."""
        factors = AdjustmentFactors(
            home_ice=1.04,
            fatigue=0.88,
            travel=0.94,
            referee=1.0,
            injury=1.0,
            desperation=1.0,
            shooting_talent=1.0,
        )
        factors.total_multiplier = (
            factors.home_ice * factors.fatigue * factors.travel
        )
        # 1.04 * 0.88 * 0.94 ≈ 0.86
        assert factors.total_multiplier < 1.0

    def test_cal_initialization(self):
        """Test CAL initializes properly."""
        cal = ContextualAdjustmentLayer()
        assert cal.fatigue_penalty == 0.88
        assert cal.travel_penalty == 0.94
        assert cal.home_ice_advantage == 1.04


class TestProbabilityEngine:
    """Tests for Probability Engine."""

    def test_logistic_function(self):
        """Test logistic probability conversion."""
        engine = ProbabilityEngine()

        # No differential = 50%
        assert abs(engine._logistic(0) - 0.5) < 0.01

        # Positive differential = >50% home
        assert engine._logistic(10) > 0.5

        # Negative differential = <50% home
        assert engine._logistic(-10) < 0.5

        # Symmetry check
        assert abs(engine._logistic(10) + engine._logistic(-10) - 1.0) < 0.01

    def test_probability_bounds(self):
        """Test probability stays in bounds."""
        engine = ProbabilityEngine()

        # Even extreme values should be bounded
        assert 0.01 <= engine._logistic(100) <= 0.99
        assert 0.01 <= engine._logistic(-100) <= 0.99

    def test_win_probability_dataclass(self):
        """Test WinProbability dataclass."""
        prob = WinProbability(
            home_team="BOS",
            away_team="NYR",
            game_date=date(2025, 11, 15),
            home_win_prob=0.58,
            away_win_prob=0.42,
            confidence_level="high",
            data_quality=0.85,
            home_adjusted_sps=55.0,
            away_adjusted_sps=48.0,
            sps_differential=7.0,
        )
        assert prob.home_win_prob + prob.away_win_prob == 1.0
        assert prob.confidence_level == "high"


class TestOddsConverter:
    """Tests for Odds Converter."""

    def test_american_to_probability_favorite(self):
        """Test American odds conversion for favorite."""
        # -150 means risk 150 to win 100
        # Implied prob = 150 / 250 = 0.60
        prob = OddsConverter.american_to_probability(-150)
        assert abs(prob - 0.60) < 0.01

    def test_american_to_probability_underdog(self):
        """Test American odds conversion for underdog."""
        # +150 means risk 100 to win 150
        # Implied prob = 100 / 250 = 0.40
        prob = OddsConverter.american_to_probability(150)
        assert abs(prob - 0.40) < 0.01

    def test_american_to_probability_even(self):
        """Test American odds conversion for even."""
        # +100 or -100 = 50%
        prob_plus = OddsConverter.american_to_probability(100)
        prob_minus = OddsConverter.american_to_probability(-100)
        assert abs(prob_plus - 0.50) < 0.01
        assert abs(prob_minus - 0.50) < 0.01

    def test_probability_to_american_favorite(self):
        """Test probability to American odds for favorite."""
        odds = OddsConverter.probability_to_american(0.60)
        assert odds < 0  # Should be negative (favorite)
        assert abs(odds + 150) < 5  # Approximately -150

    def test_probability_to_american_underdog(self):
        """Test probability to American odds for underdog."""
        odds = OddsConverter.probability_to_american(0.40)
        assert odds > 0  # Should be positive (underdog)
        assert abs(odds - 150) < 5  # Approximately +150

    def test_decimal_to_probability(self):
        """Test decimal odds conversion."""
        # 2.50 decimal = 40% implied
        prob = OddsConverter.decimal_to_probability(2.50)
        assert abs(prob - 0.40) < 0.01

        # 1.50 decimal = 66.7% implied
        prob = OddsConverter.decimal_to_probability(1.50)
        assert abs(prob - 0.667) < 0.01

    def test_remove_vig(self):
        """Test vig removal."""
        # If both implied at 52.5% (105% total), true probs are 50% each
        home_true, away_true = OddsConverter.remove_vig(0.525, 0.525)
        assert abs(home_true - 0.50) < 0.01
        assert abs(away_true - 0.50) < 0.01


class TestEdgeCalculator:
    """Tests for Edge Calculator."""

    def test_edge_analysis_dataclass(self):
        """Test EdgeAnalysis dataclass."""
        edge = EdgeAnalysis(
            home_team="TOR",
            away_team="MTL",
            game_date=date(2025, 11, 20),
            model_home_prob=0.58,
            model_away_prob=0.42,
            market_home_prob=0.52,
            market_away_prob=0.48,
            home_edge=0.06,
            away_edge=-0.06,
            has_value=True,
            value_side="home",
            edge_magnitude=0.06,
            edge_category="strong",
        )
        assert edge.has_value is True
        assert edge.value_side == "home"
        assert edge.edge_category == "strong"

    def test_edge_thresholds(self):
        """Test edge category thresholds."""
        calc = EdgeCalculator()
        assert calc.STRONG_EDGE == 0.05
        assert calc.MODERATE_EDGE == 0.02


class TestKellyCalculator:
    """Tests for Kelly Criterion Calculator."""

    def test_kelly_formula(self):
        """Test Kelly formula calculation."""
        calc = KellyCalculator()

        # 60% prob at +100 odds (2.0 decimal)
        # Kelly = (1 * 0.6 - 0.4) / 1 = 0.20
        result = calc.calculate_kelly(0.60, 100, "american")
        assert abs(result.full_kelly - 0.20) < 0.01

    def test_kelly_negative_edge(self):
        """Test Kelly returns 0 for negative edge."""
        calc = KellyCalculator()

        # 40% prob at +100 odds = negative EV
        result = calc.calculate_kelly(0.40, 100, "american")
        assert result.full_kelly == 0.0

    def test_kelly_half_quarter(self):
        """Test half and quarter Kelly."""
        calc = KellyCalculator()

        result = calc.calculate_kelly(0.60, 100, "american")
        assert abs(result.half_kelly - result.full_kelly * 0.5) < 0.001
        assert abs(result.quarter_kelly - result.full_kelly * 0.25) < 0.001

    def test_confidence_rating(self):
        """Test confidence rating thresholds."""
        calc = KellyCalculator()

        # High Kelly = lock
        assert calc._get_confidence_rating(0.10) == "lock"
        assert calc._get_confidence_rating(0.06) == "strong"
        assert calc._get_confidence_rating(0.03) == "standard"
        assert calc._get_confidence_rating(0.015) == "lean"
        assert calc._get_confidence_rating(0.005) == "pass"

    def test_kelly_result_dataclass(self):
        """Test KellyResult dataclass."""
        result = KellyResult(
            probability=0.60,
            decimal_odds=2.0,
            full_kelly=0.20,
            half_kelly=0.10,
            quarter_kelly=0.05,
            confidence_rating="strong",
            confidence_score=65.0,
            expected_value=0.20,
        )
        assert result.confidence_rating == "strong"
        assert result.expected_value == 0.20


class TestBayesianPrior:
    """Tests for Bayesian Prior Adjuster."""

    def test_prior_weight_early_season(self):
        """Test prior weight in early season."""
        adjuster = BayesianPriorAdjuster()

        # 0 games = 50% prior weight
        assert adjuster.get_prior_weight(0) == 0.5

        # 10 games = 37.5% prior weight (roughly)
        weight = adjuster.get_prior_weight(10)
        assert 0.3 <= weight <= 0.4

    def test_prior_weight_late_season(self):
        """Test prior weight phases out."""
        adjuster = BayesianPriorAdjuster()

        # 40+ games = 0% prior weight
        assert adjuster.get_prior_weight(40) == 0.0
        assert adjuster.get_prior_weight(50) == 0.0

    def test_regress_to_mean(self):
        """Test regression calculation."""
        adjuster = BayesianPriorAdjuster()

        # 50% weight on each
        result = adjuster.regress_to_mean(60.0, 50.0, 0.5)
        assert result == 55.0

        # Full current weight
        result = adjuster.regress_to_mean(60.0, 50.0, 0.0)
        assert result == 60.0

        # Full prior weight
        result = adjuster.regress_to_mean(60.0, 50.0, 1.0)
        assert result == 50.0

    def test_prior_data_lookup(self):
        """Test prior data retrieval."""
        adjuster = BayesianPriorAdjuster()

        # Known team
        prior = adjuster.get_prior_data("BOS")
        assert prior["xgf_pct"] > 50.0  # Boston is good

        # Unknown team gets league average
        prior = adjuster.get_prior_data("UNKNOWN")
        assert prior["xgf_pct"] == 50.0

    def test_adjusted_metrics_dataclass(self):
        """Test BayesianAdjustedMetrics dataclass."""
        metrics = BayesianAdjustedMetrics(
            team="MTL",
            games_played=15,
            current_xgf_pct=48.0,
            current_hdcf_pct=47.0,
            current_pdo=995.0,
            prior_xgf_pct=48.0,
            prior_hdcf_pct=47.5,
            prior_pdo=997.0,
            current_weight=0.625,
            prior_weight=0.375,
            adjusted_xgf_pct=48.0,
            adjusted_hdcf_pct=47.2,
            adjusted_pdo=995.75,
        )
        assert metrics.team == "MTL"
        assert metrics.current_weight + metrics.prior_weight == 1.0


class TestModelCalibrator:
    """Tests for Model Calibrator."""

    def test_empty_metrics(self):
        """Test empty metrics generation."""
        calibrator = ModelCalibrator()
        metrics = calibrator._empty_metrics("30d")

        assert metrics.period == "30d"
        assert metrics.predictions_count == 0
        assert metrics.accuracy == 0.0

    def test_brier_score_calculation(self):
        """Test Brier score calculation logic."""
        # Perfect prediction: prob=1.0, outcome=1 -> score=0
        # Worst prediction: prob=1.0, outcome=0 -> score=1
        # 50/50 prediction: prob=0.5, outcome either -> score=0.25

        calibrator = ModelCalibrator()

        # Mock prediction with correct result
        class MockPred:
            pick_confidence = 0.70
            pick_correct = True

        preds = [MockPred()]
        brier = calibrator._calculate_brier_score(preds)
        # (0.70 - 1.0)^2 = 0.09
        assert abs(brier - 0.09) < 0.01

    def test_calibration_metrics_dataclass(self):
        """Test CalibrationMetrics dataclass."""
        metrics = CalibrationMetrics(
            period="30d",
            predictions_count=100,
            games_with_outcome=100,
            accuracy=0.58,
            home_accuracy=0.60,
            away_accuracy=0.55,
            brier_score=0.22,
            log_loss=0.65,
            high_confidence_accuracy=0.62,
            medium_confidence_accuracy=0.54,
        )
        assert metrics.accuracy == 0.58
        assert metrics.brier_score == 0.22


class TestPredictionIntegration:
    """Integration tests for prediction modules."""

    def test_all_modules_importable(self):
        """Test all prediction modules can be imported."""
        from src.nhl_predictor.prediction import (
            SPSCalculator,
            ContextualAdjustmentLayer,
            ProbabilityEngine,
            OddsConverter,
            EdgeCalculator,
            KellyCalculator,
            BayesianPriorAdjuster,
            ModelCalibrator,
        )

        assert SPSCalculator is not None
        assert ContextualAdjustmentLayer is not None
        assert ProbabilityEngine is not None
        assert OddsConverter is not None
        assert EdgeCalculator is not None
        assert KellyCalculator is not None
        assert BayesianPriorAdjuster is not None
        assert ModelCalibrator is not None

    def test_convenience_functions_importable(self):
        """Test convenience functions can be imported."""
        from src.nhl_predictor.prediction import (
            calculate_sps,
            calculate_matchup_sps,
            apply_contextual_adjustments,
            calculate_win_probability,
            calculate_edge,
            american_to_probability,
            probability_to_american,
            calculate_kelly,
            get_pick_confidence,
            adjust_for_sample_size,
            get_prior_weight,
            get_calibration_metrics,
            record_prediction,
        )

        assert callable(calculate_sps)
        assert callable(calculate_win_probability)
        assert callable(calculate_kelly)
        assert callable(american_to_probability)
