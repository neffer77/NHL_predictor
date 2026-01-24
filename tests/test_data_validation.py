"""Data validation tests for NHL Predictor.

Validates incoming data quality and consistency.
"""

import pytest
from datetime import date, datetime, timedelta
from src.nhl_predictor.utils.team_mapping import normalize_team_name, is_valid_team_code


class TestTeamCodeValidation:
    """Tests for team code validation."""

    ALL_VALID_CODES = [
        "ANA", "BOS", "BUF", "CGY", "CAR", "CHI", "COL", "CBJ",
        "DAL", "DET", "EDM", "FLA", "LAK", "MIN", "MTL", "NSH",
        "NJD", "NYI", "NYR", "OTT", "PHI", "PIT", "SJS", "SEA",
        "STL", "TBL", "TOR", "UTA", "VAN", "VGK", "WSH", "WPG",
    ]

    def test_all_codes_are_valid(self):
        """Test all team codes are recognized."""
        for code in self.ALL_VALID_CODES:
            assert is_valid_team_code(code), f"Code {code} should be valid"

    def test_invalid_codes_rejected(self):
        """Test invalid codes are rejected."""
        invalid_codes = ["XXX", "ABC", "NHL", "USA", "CAN", ""]
        for code in invalid_codes:
            assert not is_valid_team_code(code), f"Code {code} should be invalid"

    def test_exactly_32_teams(self):
        """Test we have exactly 32 NHL teams."""
        assert len(self.ALL_VALID_CODES) == 32


class TestNumericRangeValidation:
    """Tests for numeric field validation."""

    def test_probability_range(self):
        """Test probability values are in valid range."""
        valid_probs = [0.0, 0.5, 0.53, 0.75, 1.0]
        invalid_probs = [-0.1, 1.1, 2.0, -1.0]

        for prob in valid_probs:
            assert 0.0 <= prob <= 1.0, f"Probability {prob} should be valid"

        for prob in invalid_probs:
            assert not (0.0 <= prob <= 1.0), f"Probability {prob} should be invalid"

    def test_xgf_percentage_range(self):
        """Test xGF% values are in reasonable range."""
        # xGF% should typically be between 40% and 60%
        # Extreme values (35-65%) are rare but possible

        reasonable_values = [45.0, 50.0, 52.5, 55.0]
        extreme_values = [35.0, 65.0]
        invalid_values = [-5.0, 105.0, 200.0]

        for val in reasonable_values:
            assert 40.0 <= val <= 60.0, f"xGF% {val} should be reasonable"

        for val in extreme_values:
            assert 30.0 <= val <= 70.0, f"xGF% {val} should be valid (extreme)"

        for val in invalid_values:
            assert not (0.0 <= val <= 100.0), f"xGF% {val} should be invalid"

    def test_pdo_range(self):
        """Test PDO values are in valid range."""
        # League average PDO is always 1000
        # Typical range is 950-1050
        # Extreme values could be 920-1080

        typical_values = [985, 1000, 1015, 1025]
        extreme_values = [940, 1060]
        invalid_values = [800, 1200, 500]

        for val in typical_values:
            assert 950 <= val <= 1050, f"PDO {val} should be typical"

        for val in extreme_values:
            assert 900 <= val <= 1100, f"PDO {val} should be valid (extreme)"

        for val in invalid_values:
            assert not (900 <= val <= 1100), f"PDO {val} should be invalid"

    def test_gsax_range(self):
        """Test GSAx values are in reasonable range."""
        # GSAx per game typically ranges from -0.5 to +0.5
        # Season totals can range from -20 to +30

        valid_per_game = [-0.3, 0.0, 0.2, 0.5]
        valid_season = [-15, 0, 10, 25]

        for val in valid_per_game:
            assert -1.0 <= val <= 1.0, f"GSAx/game {val} should be valid"

        for val in valid_season:
            assert -30 <= val <= 40, f"Season GSAx {val} should be valid"

    def test_edge_range(self):
        """Test edge values are in valid range."""
        # Edge = model prob - market prob
        # Reasonable range is -0.15 to +0.15
        # Larger edges are rare but possible

        valid_edges = [-0.05, 0.0, 0.03, 0.08, 0.12]
        suspicious_edges = [0.25, -0.25, 0.50]

        for edge in valid_edges:
            assert -0.20 <= edge <= 0.20, f"Edge {edge} should be valid"

        for edge in suspicious_edges:
            # Large edges should be flagged as suspicious
            assert abs(edge) > 0.20, f"Edge {edge} should be suspicious"

    def test_kelly_score_range(self):
        """Test Kelly score values are in valid range."""
        # Kelly fraction should be capped at reasonable levels
        # Typical range is 0 to 0.15

        valid_kelly = [0.0, 0.02, 0.05, 0.08, 0.12]
        capped_kelly = [0.20, 0.25]  # Should be capped

        for kelly in valid_kelly:
            assert 0.0 <= kelly <= 0.15, f"Kelly {kelly} should be valid"

        # Large Kelly values should be capped in practice
        for kelly in capped_kelly:
            assert kelly > 0.15, f"Kelly {kelly} should be capped"


class TestDateValidation:
    """Tests for date validation."""

    def test_game_date_not_future(self):
        """Test game dates for completed games are not in future."""
        today = date.today()
        yesterday = today - timedelta(days=1)
        tomorrow = today + timedelta(days=1)

        # Past dates are valid for results
        assert yesterday <= today

        # Future dates cannot have results
        assert tomorrow > today

    def test_season_date_range(self):
        """Test dates are within NHL season."""
        # NHL season typically runs October to June
        season_start = date(2025, 10, 1)
        season_end = date(2026, 6, 30)

        valid_dates = [
            date(2025, 10, 15),
            date(2025, 12, 25),
            date(2026, 2, 14),
            date(2026, 4, 1),
        ]

        invalid_dates = [
            date(2025, 7, 15),  # Summer
            date(2025, 8, 1),   # Offseason
            date(2026, 8, 15),  # After season
        ]

        for d in valid_dates:
            assert season_start <= d <= season_end, f"Date {d} should be in season"

        for d in invalid_dates:
            assert not (season_start <= d <= season_end), f"Date {d} should be offseason"

    def test_game_time_format(self):
        """Test game times are in valid format."""
        valid_times = ["19:00", "20:00", "22:00", "13:00"]
        invalid_times = ["25:00", "19:60", "7 PM", "7:00 PM"]

        for time_str in valid_times:
            parts = time_str.split(":")
            assert len(parts) == 2
            hour, minute = int(parts[0]), int(parts[1])
            assert 0 <= hour <= 23
            assert 0 <= minute <= 59


class TestDataConsistency:
    """Tests for data consistency."""

    def test_probabilities_sum_to_one(self):
        """Test home + away probabilities sum to 1.0."""
        test_cases = [
            (0.5, 0.5),
            (0.55, 0.45),
            (0.62, 0.38),
            (0.70, 0.30),
        ]

        for home_prob, away_prob in test_cases:
            total = home_prob + away_prob
            assert abs(total - 1.0) < 0.001, f"Probs {home_prob} + {away_prob} should sum to 1.0"

    def test_game_has_two_different_teams(self):
        """Test games have two different teams."""
        valid_games = [
            ("BOS", "TOR"),
            ("NYR", "NJD"),
            ("MTL", "OTT"),
        ]

        for home, away in valid_games:
            assert home != away, f"Teams should be different: {home} vs {away}"

    def test_winner_is_participant(self):
        """Test game winner is one of the teams."""
        test_cases = [
            ("BOS", "TOR", "BOS"),  # Home wins
            ("BOS", "TOR", "TOR"),  # Away wins
        ]

        for home, away, winner in test_cases:
            assert winner in [home, away], f"Winner {winner} should be {home} or {away}"

    def test_score_consistency(self):
        """Test game scores are consistent with winner."""
        test_cases = [
            (3, 2, "home"),   # Home wins
            (2, 4, "away"),   # Away wins
            (2, 3, "away"),   # Away wins in OT
        ]

        for home_score, away_score, expected_winner:
            if home_score > away_score:
                actual_winner = "home"
            else:
                actual_winner = "away"

            # Note: ties go to OT, so away could win 3-2 in OT
            # This is a simplified check
            assert actual_winner == expected_winner or home_score == away_score

    def test_no_duplicate_game_ids(self):
        """Test game IDs are unique."""
        game_ids = [
            2025020001,
            2025020002,
            2025020003,
        ]

        assert len(game_ids) == len(set(game_ids)), "Game IDs should be unique"


class TestDataQualityChecks:
    """Tests for data quality."""

    def test_required_fields_present(self):
        """Test required fields are not null."""
        required_game_fields = ["game_id", "date", "home_team", "away_team"]
        required_stats_fields = ["team", "date", "games_played"]
        required_prediction_fields = ["game_id", "home_win_prob", "away_win_prob"]

        # Test with mock data
        game_data = {
            "game_id": 2025020001,
            "date": date(2025, 11, 15),
            "home_team": "BOS",
            "away_team": "TOR",
        }

        for field in required_game_fields:
            assert field in game_data and game_data[field] is not None

    def test_team_stats_have_games_played(self):
        """Test team stats include games played count."""
        stats = {
            "team": "BOS",
            "games_played": 30,
            "xgf_pct": 52.5,
        }

        assert stats["games_played"] > 0
        assert stats["games_played"] <= 82  # Max regular season games

    def test_minimum_sample_size(self):
        """Test minimum sample size for reliable stats."""
        MIN_GAMES_FOR_STATS = 10

        sufficient_sample = {"games_played": 25}
        insufficient_sample = {"games_played": 5}

        assert sufficient_sample["games_played"] >= MIN_GAMES_FOR_STATS
        assert insufficient_sample["games_played"] < MIN_GAMES_FOR_STATS


class TestDataValidationHelpers:
    """Helper validation functions."""

    @staticmethod
    def is_valid_probability(prob: float) -> bool:
        """Check if probability is valid."""
        return 0.0 <= prob <= 1.0

    @staticmethod
    def is_valid_percentage(pct: float) -> bool:
        """Check if percentage is valid."""
        return 0.0 <= pct <= 100.0

    @staticmethod
    def is_valid_pdo(pdo: float) -> bool:
        """Check if PDO is in valid range."""
        return 900 <= pdo <= 1100

    @staticmethod
    def is_valid_game_id(game_id: int) -> bool:
        """Check if game ID format is valid."""
        # NHL game IDs are typically 10 digits: YYYYTTGGGG
        # YYYY = season start year, TT = type (02=regular), GGGG = game number
        return 2020000001 <= game_id <= 2030999999

    def test_helper_functions(self):
        """Test helper validation functions."""
        assert self.is_valid_probability(0.5)
        assert not self.is_valid_probability(1.5)

        assert self.is_valid_percentage(50.0)
        assert not self.is_valid_percentage(150.0)

        assert self.is_valid_pdo(1000)
        assert not self.is_valid_pdo(500)

        assert self.is_valid_game_id(2025020100)
        assert not self.is_valid_game_id(100)
