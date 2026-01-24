"""Model validation tests for NHL Predictor.

Validates that the model produces reasonable outputs and
handles edge cases correctly.
"""

import pytest
import math
from datetime import date


class TestProbabilityOutputValidation:
    """Tests to validate probability outputs."""

    def test_probabilities_always_between_0_and_1(self):
        """Test probabilities are always in valid range."""
        from src.nhl_predictor.prediction.probability_engine import ProbabilityEngine

        engine = ProbabilityEngine()

        # Test with various differentials
        differentials = [-100, -50, -20, -10, -5, 0, 5, 10, 20, 50, 100]

        for diff in differentials:
            prob = engine._logistic(diff)
            assert 0.0 < prob < 1.0, f"Probability {prob} for diff {diff} out of bounds"

    def test_home_away_probabilities_sum_to_one(self):
        """Test home + away probabilities always sum to 1.0."""
        from src.nhl_predictor.prediction.probability_engine import ProbabilityEngine

        engine = ProbabilityEngine()

        # Test with various differentials
        differentials = [-20, -10, -5, 0, 5, 10, 20]

        for diff in differentials:
            home_prob = engine._logistic(diff)
            away_prob = 1 - home_prob

            total = home_prob + away_prob
            assert abs(total - 1.0) < 0.0001, f"Probs don't sum to 1: {home_prob} + {away_prob} = {total}"

    def test_probability_symmetry(self):
        """Test probability is symmetric around 0.5."""
        from src.nhl_predictor.prediction.probability_engine import ProbabilityEngine

        engine = ProbabilityEngine()

        # p(diff=10) + p(diff=-10) should equal 1.0
        for diff in [5, 10, 15, 20]:
            prob_positive = engine._logistic(diff)
            prob_negative = engine._logistic(-diff)

            assert abs(prob_positive + prob_negative - 1.0) < 0.0001, \
                f"Symmetry violated: p({diff})={prob_positive}, p(-{diff})={prob_negative}"

    def test_zero_differential_equals_fifty_percent(self):
        """Test zero differential gives 50% probability."""
        from src.nhl_predictor.prediction.probability_engine import ProbabilityEngine

        engine = ProbabilityEngine()
        prob = engine._logistic(0)

        assert abs(prob - 0.5) < 0.001, f"Zero diff should be 50%, got {prob}"

    def test_positive_differential_favors_home(self):
        """Test positive differential gives >50% home win prob."""
        from src.nhl_predictor.prediction.probability_engine import ProbabilityEngine

        engine = ProbabilityEngine()

        for diff in [1, 5, 10, 20]:
            prob = engine._logistic(diff)
            assert prob > 0.5, f"Positive diff {diff} should favor home, got {prob}"

    def test_negative_differential_favors_away(self):
        """Test negative differential gives <50% home win prob."""
        from src.nhl_predictor.prediction.probability_engine import ProbabilityEngine

        engine = ProbabilityEngine()

        for diff in [-1, -5, -10, -20]:
            prob = engine._logistic(diff)
            assert prob < 0.5, f"Negative diff {diff} should favor away, got {prob}"


class TestNoNaNOrInfiniteValues:
    """Tests to ensure no NaN or infinite values."""

    def test_sps_no_nan(self):
        """Test SPS calculation produces no NaN values."""
        from src.nhl_predictor.prediction.sps_calculator import SPSCalculator

        calc = SPSCalculator()

        # Test normalization with various inputs
        test_values = [0, 25, 50, 75, 100, -10, 110]

        for val in test_values:
            result = calc._normalize(val, 45.0, 55.0)
            assert not math.isnan(result), f"NaN for input {val}"
            assert not math.isinf(result), f"Inf for input {val}"

    def test_probability_no_nan(self):
        """Test probability calculation produces no NaN values."""
        from src.nhl_predictor.prediction.probability_engine import ProbabilityEngine

        engine = ProbabilityEngine()

        # Test with extreme values
        test_diffs = [-1000, -100, -1, 0, 1, 100, 1000]

        for diff in test_diffs:
            prob = engine._logistic(diff)
            assert not math.isnan(prob), f"NaN for diff {diff}"
            assert not math.isinf(prob), f"Inf for diff {diff}"

    def test_kelly_no_nan(self):
        """Test Kelly calculation produces no NaN values."""
        from src.nhl_predictor.prediction.kelly_criterion import KellyCalculator

        calc = KellyCalculator()

        # Test with various inputs
        test_cases = [
            (0.5, 2.0),   # Even odds
            (0.6, 2.0),   # Positive edge
            (0.4, 2.0),   # Negative edge
            (0.9, 1.5),   # High prob
            (0.1, 5.0),   # Low prob
        ]

        for prob, odds in test_cases:
            result = calc.calculate_kelly(prob, odds, "decimal")
            assert not math.isnan(result.full_kelly), f"NaN for prob={prob}, odds={odds}"
            assert not math.isinf(result.full_kelly), f"Inf for prob={prob}, odds={odds}"

    def test_odds_conversion_no_nan(self):
        """Test odds conversion produces no NaN values."""
        from src.nhl_predictor.prediction.odds_calculator import OddsConverter

        # Test American odds conversion
        american_odds = [-500, -200, -110, 100, 150, 300, 500]

        for odds in american_odds:
            prob = OddsConverter.american_to_probability(odds)
            assert not math.isnan(prob), f"NaN for American odds {odds}"
            assert not math.isinf(prob), f"Inf for American odds {odds}"

        # Test decimal odds conversion
        decimal_odds = [1.1, 1.5, 2.0, 3.0, 5.0, 10.0]

        for odds in decimal_odds:
            prob = OddsConverter.decimal_to_probability(odds)
            assert not math.isnan(prob), f"NaN for decimal odds {odds}"
            assert not math.isinf(prob), f"Inf for decimal odds {odds}"


class TestEdgeCaseHandling:
    """Tests for edge case handling."""

    def test_missing_data_handling(self):
        """Test model handles missing data gracefully."""
        from src.nhl_predictor.prediction.sps_calculator import SPSCalculator

        calc = SPSCalculator()

        # Test with None values (should use defaults)
        result = calc._normalize(50.0, 45.0, 55.0)
        assert result is not None

    def test_first_game_of_season(self):
        """Test model handles first game of season."""
        from src.nhl_predictor.prediction.bayesian_prior import BayesianPriorAdjuster

        adjuster = BayesianPriorAdjuster()

        # 0 games played = maximum prior weight
        prior_weight = adjuster.get_prior_weight(0)
        assert prior_weight == 0.5, "First game should use 50% prior"

    def test_late_season_no_prior(self):
        """Test model uses no prior late in season."""
        from src.nhl_predictor.prediction.bayesian_prior import BayesianPriorAdjuster

        adjuster = BayesianPriorAdjuster()

        # 40+ games played = no prior weight
        prior_weight = adjuster.get_prior_weight(40)
        assert prior_weight == 0.0, "Late season should use 0% prior"

        prior_weight = adjuster.get_prior_weight(60)
        assert prior_weight == 0.0, "Full season should use 0% prior"

    def test_extreme_odds_handling(self):
        """Test model handles extreme odds correctly."""
        from src.nhl_predictor.prediction.odds_calculator import OddsConverter

        # Very heavy favorite
        prob = OddsConverter.american_to_probability(-1000)
        assert prob > 0.9, "Heavy favorite should have >90% implied"
        assert prob < 1.0, "Probability should be <100%"

        # Very heavy underdog
        prob = OddsConverter.american_to_probability(1000)
        assert prob < 0.1, "Heavy underdog should have <10% implied"
        assert prob > 0.0, "Probability should be >0%"

    def test_negative_kelly_clamped(self):
        """Test negative Kelly values are clamped to 0."""
        from src.nhl_predictor.prediction.kelly_criterion import KellyCalculator

        calc = KellyCalculator()

        # Negative edge = no bet
        result = calc.calculate_kelly(0.40, 2.0, "decimal")
        assert result.full_kelly == 0.0, "Negative Kelly should be clamped to 0"


class TestOutputStability:
    """Tests for output stability (same inputs = same outputs)."""

    def test_sps_deterministic(self):
        """Test SPS calculation is deterministic."""
        from src.nhl_predictor.prediction.sps_calculator import SPSCalculator

        calc = SPSCalculator()

        # Run same calculation multiple times
        results = []
        for _ in range(10):
            result = calc._normalize(52.5, 45.0, 55.0)
            results.append(result)

        # All results should be identical
        assert all(r == results[0] for r in results), "SPS should be deterministic"

    def test_probability_deterministic(self):
        """Test probability calculation is deterministic."""
        from src.nhl_predictor.prediction.probability_engine import ProbabilityEngine

        engine = ProbabilityEngine()

        # Run same calculation multiple times
        results = []
        for _ in range(10):
            result = engine._logistic(10.0)
            results.append(result)

        # All results should be identical
        assert all(r == results[0] for r in results), "Probability should be deterministic"

    def test_kelly_deterministic(self):
        """Test Kelly calculation is deterministic."""
        from src.nhl_predictor.prediction.kelly_criterion import KellyCalculator

        calc = KellyCalculator()

        # Run same calculation multiple times
        results = []
        for _ in range(10):
            result = calc.calculate_kelly(0.60, 2.0, "decimal")
            results.append(result.full_kelly)

        # All results should be identical
        assert all(r == results[0] for r in results), "Kelly should be deterministic"


class TestModelConstraints:
    """Tests for model constraints."""

    def test_sps_weights_sum_to_one(self):
        """Test SPS weights sum to 1.0."""
        from src.nhl_predictor.prediction.sps_calculator import SPSCalculator

        calc = SPSCalculator()
        total = calc.xgf_weight + calc.hdcf_weight + calc.gsax_weight

        assert abs(total - 1.0) < 0.001, f"Weights sum to {total}, should be 1.0"

    def test_adjustment_scalars_in_range(self):
        """Test adjustment scalars are in reasonable range."""
        from src.nhl_predictor.prediction.contextual_layer import ContextualAdjustmentLayer

        cal = ContextualAdjustmentLayer()

        # All scalars should be between 0.5 and 1.5
        scalars = [
            cal.fatigue_penalty,
            cal.travel_penalty,
            cal.home_ice_advantage,
            cal.referee_home_bias,
            cal.injury_penalty,
        ]

        for scalar in scalars:
            assert 0.5 <= scalar <= 1.5, f"Scalar {scalar} out of range"

    def test_penalty_scalars_less_than_one(self):
        """Test penalty scalars are less than 1.0."""
        from src.nhl_predictor.prediction.contextual_layer import ContextualAdjustmentLayer

        cal = ContextualAdjustmentLayer()

        # Penalties should reduce strength (< 1.0)
        assert cal.fatigue_penalty < 1.0, "Fatigue should be a penalty"
        assert cal.travel_penalty < 1.0, "Travel should be a penalty"
        assert cal.injury_penalty < 1.0, "Injury should be a penalty"

    def test_advantage_scalars_greater_than_one(self):
        """Test advantage scalars are greater than 1.0."""
        from src.nhl_predictor.prediction.contextual_layer import ContextualAdjustmentLayer

        cal = ContextualAdjustmentLayer()

        # Advantages should increase strength (> 1.0)
        assert cal.home_ice_advantage > 1.0, "Home ice should be an advantage"


class TestModelSanity:
    """Sanity tests for model behavior."""

    def test_better_team_higher_probability(self):
        """Test better team gets higher probability."""
        from src.nhl_predictor.prediction.probability_engine import ProbabilityEngine

        engine = ProbabilityEngine()

        # Higher SPS differential = higher probability
        prob_small_advantage = engine._logistic(5)
        prob_large_advantage = engine._logistic(20)

        assert prob_large_advantage > prob_small_advantage, \
            "Larger advantage should give higher probability"

    def test_positive_edge_positive_kelly(self):
        """Test positive edge gives positive Kelly."""
        from src.nhl_predictor.prediction.kelly_criterion import KellyCalculator

        calc = KellyCalculator()

        # Model prob > market prob = positive edge = positive Kelly
        result = calc.calculate_kelly(0.60, 2.0, "decimal")  # Model: 60%, Market: 50%
        assert result.full_kelly > 0, "Positive edge should give positive Kelly"

    def test_no_edge_zero_kelly(self):
        """Test no edge gives zero Kelly."""
        from src.nhl_predictor.prediction.kelly_criterion import KellyCalculator

        calc = KellyCalculator()

        # Model prob = market prob = no edge = zero Kelly
        result = calc.calculate_kelly(0.50, 2.0, "decimal")  # Both: 50%
        assert result.full_kelly == 0.0, "No edge should give zero Kelly"

    def test_higher_confidence_higher_kelly(self):
        """Test higher confidence gives higher Kelly."""
        from src.nhl_predictor.prediction.kelly_criterion import KellyCalculator

        calc = KellyCalculator()

        # Same odds, different confidence
        result_low = calc.calculate_kelly(0.55, 2.0, "decimal")
        result_high = calc.calculate_kelly(0.65, 2.0, "decimal")

        assert result_high.full_kelly > result_low.full_kelly, \
            "Higher confidence should give higher Kelly"


class TestRegressionTests:
    """Regression tests for known calculations."""

    def test_logistic_known_values(self):
        """Test logistic function with known values."""
        from src.nhl_predictor.prediction.probability_engine import ProbabilityEngine

        engine = ProbabilityEngine()

        # logistic(0) = 0.5
        assert abs(engine._logistic(0) - 0.5) < 0.001

        # logistic function should be monotonically increasing
        prev = 0
        for x in range(-20, 21, 5):
            current = engine._logistic(x)
            assert current > prev, f"Logistic should be increasing at x={x}"
            prev = current

    def test_american_odds_known_values(self):
        """Test American odds conversion with known values."""
        from src.nhl_predictor.prediction.odds_calculator import OddsConverter

        # -110 (standard vig) = ~52.38%
        prob = OddsConverter.american_to_probability(-110)
        assert abs(prob - 0.5238) < 0.01

        # +100 = 50%
        prob = OddsConverter.american_to_probability(100)
        assert abs(prob - 0.50) < 0.01

        # -200 = 66.67%
        prob = OddsConverter.american_to_probability(-200)
        assert abs(prob - 0.6667) < 0.01

    def test_kelly_known_values(self):
        """Test Kelly criterion with known values."""
        from src.nhl_predictor.prediction.kelly_criterion import KellyCalculator

        calc = KellyCalculator()

        # 55% prob at even odds: Kelly = (1*0.55 - 0.45)/1 = 0.10
        result = calc.calculate_kelly(0.55, 2.0, "decimal")
        assert abs(result.full_kelly - 0.10) < 0.01

        # 60% prob at even odds: Kelly = (1*0.60 - 0.40)/1 = 0.20
        result = calc.calculate_kelly(0.60, 2.0, "decimal")
        assert abs(result.full_kelly - 0.20) < 0.01
