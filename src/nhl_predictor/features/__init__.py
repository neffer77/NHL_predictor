"""Feature engineering modules for NHL predictions."""

from .xg_aggregator import (
    XGAggregator,
    TeamXGMetrics,
    get_team_xg,
    get_matchup_xg,
)

from .hdcf_calculator import (
    HDCFCalculator,
    TeamHDCFMetrics,
    get_team_hdcf,
    get_matchup_hdcf,
)

from .gsax_calculator import (
    GSAxCalculator,
    GoalieGSAxMetrics,
    GoalieMatchup,
    get_goalie_gsax,
    get_matchup_goalie_analysis,
)

from .pdo_tracker import (
    PDOTracker,
    TeamPDOMetrics,
    get_team_pdo,
    get_pdo_mismatch,
    find_regression_candidates,
)

from .schedule_analyzer import (
    ScheduleAnalyzer,
    TeamScheduleContext,
    ScheduleMatchup,
    get_schedule_context,
    get_matchup_schedule,
    find_scheduled_losses,
)

from .referee_analyzer import (
    RefereeAnalyzer,
    RefereeBiasAnalysis,
    get_referee_analysis,
)

from .powerplay_analyzer import (
    PowerPlayAnalyzer,
    TeamPowerPlayMetrics,
    SpecialTeamsMatchup,
    get_special_teams,
    get_matchup_special_teams,
)

from .contextual_adjustments import (
    ContextualAdjuster,
    InjuryImpact,
    ShootingTalentMetrics,
    CoachSystemProfile,
    DesperationFactor,
    assess_injury_impact,
    assess_desperation,
    classify_system,
)

__all__ = [
    # xG
    "XGAggregator",
    "TeamXGMetrics",
    "get_team_xg",
    "get_matchup_xg",
    # HDCF
    "HDCFCalculator",
    "TeamHDCFMetrics",
    "get_team_hdcf",
    "get_matchup_hdcf",
    # GSAx
    "GSAxCalculator",
    "GoalieGSAxMetrics",
    "GoalieMatchup",
    "get_goalie_gsax",
    "get_matchup_goalie_analysis",
    # PDO
    "PDOTracker",
    "TeamPDOMetrics",
    "get_team_pdo",
    "get_pdo_mismatch",
    "find_regression_candidates",
    # Schedule
    "ScheduleAnalyzer",
    "TeamScheduleContext",
    "ScheduleMatchup",
    "get_schedule_context",
    "get_matchup_schedule",
    "find_scheduled_losses",
    # Referee
    "RefereeAnalyzer",
    "RefereeBiasAnalysis",
    "get_referee_analysis",
    # Power Play
    "PowerPlayAnalyzer",
    "TeamPowerPlayMetrics",
    "SpecialTeamsMatchup",
    "get_special_teams",
    "get_matchup_special_teams",
    # Contextual
    "ContextualAdjuster",
    "InjuryImpact",
    "ShootingTalentMetrics",
    "CoachSystemProfile",
    "DesperationFactor",
    "assess_injury_impact",
    "assess_desperation",
    "classify_system",
]
