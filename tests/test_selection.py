"""Tests for selection and ranking modules."""

import pytest
from datetime import date
from unittest.mock import Mock, patch, MagicMock

from src.nhl_predictor.selection.filters import (
    StayAwayFilter, FilterResult, FilteredGame
)
from src.nhl_predictor.selection.ranking import (
    EdgeRanker, RankedPick
)
from src.nhl_predictor.selection.stability import (
    StabilityChecker, StabilityMetrics, MatchupStability
)
from src.nhl_predictor.selection.selector import (
    PickSelector, FinalPick, DailyPicks
)
from src.nhl_predictor.selection.pdo_hunter import (
    PDOMismatchHunter, PDOMismatch, PDOHuntResult
)


class TestStayAwayFilter:
    """Tests for Stay Away Filter."""

    def test_filter_result_dataclass(self):
        """Test FilterResult dataclass."""
        result = FilterResult(
            passed=True,
            reason="",
            risk_level="low",
            risk_flags=[],
        )
        assert result.passed is True
        assert result.risk_level == "low"

    def test_filter_result_failed(self):
        """Test failed filter result."""
        result = FilterResult(
            passed=False,
            reason="Unconfirmed goalie",
            risk_level="high",
            risk_flags=["GOALIE_UNCONFIRMED"],
        )
        assert result.passed is False
        assert "GOALIE_UNCONFIRMED" in result.risk_flags

    def test_filtered_game_dataclass(self):
        """Test FilteredGame dataclass."""
        game = FilteredGame(
            game_id=2025020123,
            home_team="BOS",
            away_team="TOR",
            game_date=date(2025, 11, 15),
            start_time="19:00",
            home_win_prob=0.58,
            away_win_prob=0.42,
            home_goalie="Swayman",
            away_goalie="Stolarz",
            home_goalie_confirmed=True,
            away_goalie_confirmed=True,
            risk_level="low",
            risk_flags=[],
        )
        assert game.home_team == "BOS"
        assert game.home_win_prob == 0.58

    def test_filter_thresholds(self):
        """Test filter threshold constants."""
        filter_obj = StayAwayFilter()
        assert filter_obj.MIN_MODEL_PROBABILITY == 0.53
        assert filter_obj.MIN_GAMES_PLAYED == 10

    def test_filter_initialization(self):
        """Test filter initializes properly."""
        filter_obj = StayAwayFilter()
        assert filter_obj.db is not None


class TestEdgeRanker:
    """Tests for Edge Ranker."""

    def test_ranked_pick_dataclass(self):
        """Test RankedPick dataclass."""
        pick = RankedPick(
            game_id=2025020123,
            home_team="BOS",
            away_team="TOR",
            game_date=date(2025, 11, 15),
            start_time="19:00",
            pick_team="BOS",
            opponent="TOR",
            pick_side="home",
            model_probability=0.58,
            market_probability=0.52,
            edge=0.06,
            edge_percentage=6.0,
            kelly_score=0.08,
            kelly_half=0.04,
            kelly_quarter=0.02,
            confidence_rating="strong",
            confidence_score=75.0,
            expected_value=0.12,
            rank=1,
            risk_flags=[],
        )
        assert pick.pick_team == "BOS"
        assert pick.edge == 0.06
        assert pick.confidence_rating == "strong"

    def test_edge_ranker_thresholds(self):
        """Test edge ranker thresholds."""
        ranker = EdgeRanker()
        assert ranker.MIN_EDGE_THRESHOLD == 0.02
        assert ranker.EDGE_WEIGHT == 0.6
        assert ranker.PROBABILITY_WEIGHT == 0.4

    def test_calculate_edge(self):
        """Test edge calculation."""
        ranker = EdgeRanker()
        edge = ranker._calculate_edge(0.58, 0.52)
        assert edge == 0.06

    def test_ranking_score_calculation(self):
        """Test composite ranking score."""
        ranker = EdgeRanker()

        pick = Mock()
        pick.edge = 0.10  # 10% edge
        pick.model_probability = 0.65

        score = ranker._calculate_ranking_score(pick)

        # Should be positive and weighted correctly
        assert score > 0
        assert score <= 1.0


class TestStabilityChecker:
    """Tests for Stability Checker."""

    def test_stability_metrics_dataclass(self):
        """Test StabilityMetrics dataclass."""
        metrics = StabilityMetrics(
            team="BOS",
            pdo_current=1008,
            pdo_mean=1005,
            pdo_variance=5.2,
            pdo_trend="stable",
            pdo_regression_expected=-2.4,
            goalie_gsax=5.5,
            goalie_gsax_variance=1.2,
            goalie_games=30,
            goalie_stable=True,
            xgf_variance=2.1,
            scoring_variance=1.8,
            stability_score=75.0,
        )
        assert metrics.team == "BOS"
        assert metrics.stability_score == 75.0

    def test_matchup_stability_dataclass(self):
        """Test MatchupStability dataclass."""
        home_stability = StabilityMetrics(
            team="BOS",
            pdo_current=1008,
            pdo_mean=1005,
            pdo_variance=5.2,
            pdo_trend="stable",
            pdo_regression_expected=-2.4,
            goalie_gsax=5.5,
            goalie_gsax_variance=1.2,
            goalie_games=30,
            goalie_stable=True,
            xgf_variance=2.1,
            scoring_variance=1.8,
            stability_score=75.0,
        )
        away_stability = StabilityMetrics(
            team="TOR",
            pdo_current=1020,
            pdo_mean=1010,
            pdo_variance=8.5,
            pdo_trend="hot",
            pdo_regression_expected=-6.0,
            goalie_gsax=2.0,
            goalie_gsax_variance=2.5,
            goalie_games=25,
            goalie_stable=False,
            xgf_variance=3.2,
            scoring_variance=2.9,
            stability_score=55.0,
        )

        matchup = MatchupStability(
            home_team="BOS",
            away_team="TOR",
            home_stability=home_stability,
            away_stability=away_stability,
            more_stable_team="BOS",
            stability_differential=20.0,
            home_regression_risk="low",
            away_regression_risk="medium",
            stability_confidence_modifier=0.02,
        )

        assert matchup.more_stable_team == "BOS"
        assert matchup.stability_differential == 20.0

    def test_pdo_thresholds(self):
        """Test PDO stability thresholds."""
        checker = StabilityChecker()
        assert checker.PDO_STABLE_LOW == 990
        assert checker.PDO_STABLE_HIGH == 1010
        assert checker.PDO_EXTREME_LOW == 980
        assert checker.PDO_EXTREME_HIGH == 1020


class TestPickSelector:
    """Tests for Pick Selector."""

    def test_final_pick_dataclass(self):
        """Test FinalPick dataclass."""
        pick = FinalPick(
            rank=1,
            tier="STRONG",
            game_id=2025020123,
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
            goalie_name="Jeremy Swayman",
            risk_level="low",
            risk_flags=[],
            adjustments=["Stability advantage (+2%)"],
        )
        assert pick.tier == "STRONG"
        assert pick.pick_team == "BOS"

    def test_daily_picks_dataclass(self):
        """Test DailyPicks dataclass."""
        picks = DailyPicks(
            date=date(2025, 11, 15),
            generated_at=date(2025, 11, 15),
            picks=[],
            total_games=12,
            games_filtered=4,
            games_with_value=5,
            model_accuracy_7d=0.58,
            model_accuracy_30d=0.55,
            notes=["No picks meet minimum requirements"],
        )
        assert picks.total_games == 12
        assert picks.games_filtered == 4

    def test_tier_thresholds(self):
        """Test tier classification thresholds."""
        selector = PickSelector()
        assert selector.LOCK_THRESHOLD == 0.08
        assert selector.STRONG_THRESHOLD == 0.05
        assert selector.STANDARD_THRESHOLD == 0.02

    def test_get_tier(self):
        """Test tier determination."""
        selector = PickSelector()

        assert selector._get_tier(0.10) == "LOCK"
        assert selector._get_tier(0.06) == "STRONG"
        assert selector._get_tier(0.03) == "STANDARD"
        assert selector._get_tier(0.01) == "LEAN"


class TestPDOMismatchHunter:
    """Tests for PDO Mismatch Hunter."""

    def test_pdo_mismatch_dataclass(self):
        """Test PDOMismatch dataclass."""
        mismatch = PDOMismatch(
            game_id=2025020123,
            home_team="BOS",
            away_team="TOR",
            game_date=date(2025, 11, 15),
            home_pdo=995,
            away_pdo=1025,
            pdo_differential=-30,
            home_sh_pct=8.5,
            home_sv_pct=0.910,
            away_sh_pct=11.0,
            away_sv_pct=0.915,
            home_expected_regression=1.5,
            away_expected_regression=-7.5,
            value_side="home",
            value_edge=0.09,
            mismatch_severity="significant",
            explanation="PDO mismatch favors BOS",
        )
        assert mismatch.value_side == "home"
        assert mismatch.mismatch_severity == "significant"

    def test_hunt_result_dataclass(self):
        """Test PDOHuntResult dataclass."""
        result = PDOHuntResult(
            date=date(2025, 11, 15),
            games_analyzed=10,
            mismatches_found=2,
            mismatches=[],
            best_opportunity=None,
        )
        assert result.games_analyzed == 10

    def test_pdo_thresholds(self):
        """Test PDO hunter thresholds."""
        hunter = PDOMismatchHunter()
        assert hunter.LEAGUE_AVERAGE_PDO == 1000
        assert hunter.EXTREME_HIGH == 1025
        assert hunter.HIGH == 1015
        assert hunter.LOW == 985
        assert hunter.EXTREME_LOW == 975

    def test_regression_calculation(self):
        """Test regression calculation."""
        hunter = PDOMismatchHunter()

        # PDO of 1020 should regress toward 1000
        regression = hunter._calculate_regression(1020)
        assert regression < 0  # Expect to decrease

        # PDO of 980 should regress toward 1000
        regression = hunter._calculate_regression(980)
        assert regression > 0  # Expect to increase


class TestSelectionIntegration:
    """Integration tests for selection modules."""

    def test_all_selection_modules_importable(self):
        """Test all selection modules can be imported."""
        from src.nhl_predictor.selection import (
            StayAwayFilter,
            FilterResult,
            FilteredGame,
            EdgeRanker,
            RankedPick,
            StabilityChecker,
            StabilityMetrics,
            MatchupStability,
            PickSelector,
            FinalPick,
            DailyPicks,
            PDOMismatchHunter,
            PDOMismatch,
            PDOHuntResult,
        )

        assert StayAwayFilter is not None
        assert EdgeRanker is not None
        assert StabilityChecker is not None
        assert PickSelector is not None
        assert PDOMismatchHunter is not None

    def test_convenience_functions_importable(self):
        """Test convenience functions can be imported."""
        from src.nhl_predictor.selection import (
            filter_games,
            rank_daily_games,
            check_matchup_stability,
            select_picks,
            get_top_pick,
            hunt_pdo_mismatches,
            get_best_pdo_play,
        )

        assert callable(filter_games)
        assert callable(rank_daily_games)
        assert callable(select_picks)
        assert callable(hunt_pdo_mismatches)
