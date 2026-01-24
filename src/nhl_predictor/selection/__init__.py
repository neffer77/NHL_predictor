"""Selection and Ranking Engine for NHL predictions."""

from .filters import (
    StayAwayFilter,
    FilterResult,
    FilteredGame,
    filter_games,
)

from .ranking import (
    EdgeRanker,
    RankedPick,
    rank_daily_games,
)

from .stability import (
    StabilityChecker,
    StabilityMetrics,
    MatchupStability,
    check_matchup_stability,
)

from .selector import (
    PickSelector,
    FinalPick,
    DailyPicks,
    select_picks,
    get_top_pick,
)

from .pdo_hunter import (
    PDOMismatchHunter,
    PDOMismatch,
    PDOHuntResult,
    hunt_pdo_mismatches,
    get_best_pdo_play,
)

__all__ = [
    # Filters
    "StayAwayFilter",
    "FilterResult",
    "FilteredGame",
    "filter_games",
    # Ranking
    "EdgeRanker",
    "RankedPick",
    "rank_daily_games",
    # Stability
    "StabilityChecker",
    "StabilityMetrics",
    "MatchupStability",
    "check_matchup_stability",
    # Selector
    "PickSelector",
    "FinalPick",
    "DailyPicks",
    "select_picks",
    "get_top_pick",
    # PDO Hunter
    "PDOMismatchHunter",
    "PDOMismatch",
    "PDOHuntResult",
    "hunt_pdo_mismatches",
    "get_best_pdo_play",
]
