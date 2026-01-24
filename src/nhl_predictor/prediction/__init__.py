"""Prediction engine modules for NHL predictions."""

from .sps_calculator import (
    SPSCalculator,
    TeamSPS,
    MatchupSPS,
    calculate_sps,
    calculate_matchup_sps,
)

from .contextual_layer import (
    ContextualAdjustmentLayer,
    AdjustmentFactors,
    AdjustedTeamSPS,
    AdjustedMatchup,
    apply_contextual_adjustments,
)

from .probability_engine import (
    ProbabilityEngine,
    WinProbability,
    calculate_win_probability,
)

from .odds_calculator import (
    OddsConverter,
    EdgeCalculator,
    MarketOdds,
    EdgeAnalysis,
    calculate_edge,
    american_to_probability,
    probability_to_american,
)

from .kelly_criterion import (
    KellyCalculator,
    KellyResult,
    calculate_kelly,
    get_pick_confidence,
)

from .bayesian_prior import (
    BayesianPriorAdjuster,
    BayesianAdjustedMetrics,
    adjust_for_sample_size,
    get_prior_weight,
)

from .calibration import (
    ModelCalibrator,
    CalibrationMetrics,
    CalibrationBucket,
    get_calibration_metrics,
    record_prediction,
)

__all__ = [
    # SPS
    "SPSCalculator",
    "TeamSPS",
    "MatchupSPS",
    "calculate_sps",
    "calculate_matchup_sps",
    # CAL
    "ContextualAdjustmentLayer",
    "AdjustmentFactors",
    "AdjustedTeamSPS",
    "AdjustedMatchup",
    "apply_contextual_adjustments",
    # Probability
    "ProbabilityEngine",
    "WinProbability",
    "calculate_win_probability",
    # Odds
    "OddsConverter",
    "EdgeCalculator",
    "MarketOdds",
    "EdgeAnalysis",
    "calculate_edge",
    "american_to_probability",
    "probability_to_american",
    # Kelly
    "KellyCalculator",
    "KellyResult",
    "calculate_kelly",
    "get_pick_confidence",
    # Bayesian
    "BayesianPriorAdjuster",
    "BayesianAdjustedMetrics",
    "adjust_for_sample_size",
    "get_prior_weight",
    # Calibration
    "ModelCalibrator",
    "CalibrationMetrics",
    "CalibrationBucket",
    "get_calibration_metrics",
    "record_prediction",
]
