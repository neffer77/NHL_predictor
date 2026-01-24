"""Tests for team name normalization."""

import pytest

from src.nhl_predictor.utils.team_mapping import (
    normalize_team_name,
    normalize_team_name_safe,
    get_team_full_name,
    get_team_timezone,
    is_valid_team_code,
    get_all_team_codes,
    TEAM_MAPPING,
    VALID_TEAM_CODES,
)


class TestNormalizeTeamName:
    """Tests for normalize_team_name function."""

    def test_full_team_names(self):
        """Test normalization of full team names."""
        assert normalize_team_name("Montreal Canadiens") == "MTL"
        assert normalize_team_name("Toronto Maple Leafs") == "TOR"
        assert normalize_team_name("Boston Bruins") == "BOS"
        assert normalize_team_name("Vegas Golden Knights") == "VGK"

    def test_abbreviations(self):
        """Test normalization of team abbreviations."""
        assert normalize_team_name("MTL") == "MTL"
        assert normalize_team_name("TOR") == "TOR"
        assert normalize_team_name("BOS") == "BOS"
        assert normalize_team_name("NYR") == "NYR"

    def test_short_names(self):
        """Test normalization of short team names."""
        assert normalize_team_name("Canadiens") == "MTL"
        assert normalize_team_name("Leafs") == "TOR"
        assert normalize_team_name("Bruins") == "BOS"
        assert normalize_team_name("Rangers") == "NYR"

    def test_nicknames(self):
        """Test normalization of team nicknames."""
        assert normalize_team_name("Habs") == "MTL"
        assert normalize_team_name("Bolts") == "TBL"
        assert normalize_team_name("Caps") == "WSH"
        assert normalize_team_name("Pens") == "PIT"
        assert normalize_team_name("Avs") == "COL"

    def test_special_characters(self):
        """Test normalization with special characters."""
        assert normalize_team_name("Montréal Canadiens") == "MTL"
        assert normalize_team_name("Montréal") == "MTL"

    def test_city_names(self):
        """Test normalization of city names only."""
        assert normalize_team_name("Toronto") == "TOR"
        assert normalize_team_name("Boston") == "BOS"
        assert normalize_team_name("Montreal") == "MTL"
        assert normalize_team_name("Edmonton") == "EDM"

    def test_utah_arizona_transition(self):
        """Test that Arizona Coyotes maps to Utah."""
        assert normalize_team_name("Arizona Coyotes") == "UTA"
        assert normalize_team_name("Coyotes") == "UTA"
        assert normalize_team_name("ARI") == "UTA"
        assert normalize_team_name("Utah Hockey Club") == "UTA"
        assert normalize_team_name("Utah") == "UTA"
        assert normalize_team_name("UTA") == "UTA"

    def test_case_insensitivity(self):
        """Test case insensitive matching."""
        assert normalize_team_name("MONTREAL CANADIENS") == "MTL"
        assert normalize_team_name("montreal canadiens") == "MTL"
        assert normalize_team_name("Toronto maple leafs") == "TOR"
        assert normalize_team_name("mtl") == "MTL"

    def test_whitespace_handling(self):
        """Test handling of extra whitespace."""
        assert normalize_team_name("  Montreal Canadiens  ") == "MTL"
        assert normalize_team_name("Toronto   Maple   Leafs") == "TOR"

    def test_alternative_abbreviations(self):
        """Test alternative abbreviations used by some sources."""
        assert normalize_team_name("CAL") == "CGY"  # Calgary
        assert normalize_team_name("NAS") == "NSH"  # Nashville
        assert normalize_team_name("WAS") == "WSH"  # Washington
        assert normalize_team_name("TB") == "TBL"   # Tampa Bay
        assert normalize_team_name("LA") == "LAK"   # Los Angeles
        assert normalize_team_name("NJ") == "NJD"   # New Jersey
        assert normalize_team_name("SJ") == "SJS"   # San Jose

    def test_invalid_team_raises_error(self):
        """Test that invalid team names raise ValueError."""
        with pytest.raises(ValueError):
            normalize_team_name("Invalid Team Name")

        with pytest.raises(ValueError):
            normalize_team_name("XYZ")

    def test_empty_string_raises_error(self):
        """Test that empty string raises ValueError."""
        with pytest.raises(ValueError):
            normalize_team_name("")

        with pytest.raises(ValueError):
            normalize_team_name("   ")


class TestNormalizeTeamNameSafe:
    """Tests for normalize_team_name_safe function."""

    def test_valid_team_returns_code(self):
        """Test that valid teams return codes."""
        assert normalize_team_name_safe("Montreal Canadiens") == "MTL"
        assert normalize_team_name_safe("TOR") == "TOR"

    def test_invalid_team_returns_none(self):
        """Test that invalid teams return None."""
        assert normalize_team_name_safe("Invalid Team") is None
        assert normalize_team_name_safe("XYZ") is None
        assert normalize_team_name_safe("") is None


class TestGetTeamFullName:
    """Tests for get_team_full_name function."""

    def test_valid_codes(self):
        """Test getting full names from valid codes."""
        assert get_team_full_name("MTL") == "Montreal Canadiens"
        assert get_team_full_name("TOR") == "Toronto Maple Leafs"
        assert get_team_full_name("VGK") == "Vegas Golden Knights"
        assert get_team_full_name("UTA") == "Utah Hockey Club"

    def test_case_handling(self):
        """Test that codes are case-insensitive."""
        assert get_team_full_name("mtl") == "Montreal Canadiens"
        assert get_team_full_name("Mtl") == "Montreal Canadiens"

    def test_invalid_code_raises_error(self):
        """Test that invalid codes raise ValueError."""
        with pytest.raises(ValueError):
            get_team_full_name("XYZ")


class TestGetTeamTimezone:
    """Tests for get_team_timezone function."""

    def test_eastern_teams(self):
        """Test Eastern timezone teams."""
        assert get_team_timezone("BOS") == "America/New_York"
        assert get_team_timezone("NYR") == "America/New_York"
        assert get_team_timezone("MTL") == "America/Montreal"
        assert get_team_timezone("TOR") == "America/Toronto"

    def test_central_teams(self):
        """Test Central timezone teams."""
        assert get_team_timezone("CHI") == "America/Chicago"
        assert get_team_timezone("DAL") == "America/Chicago"
        assert get_team_timezone("MIN") == "America/Chicago"

    def test_mountain_teams(self):
        """Test Mountain timezone teams."""
        assert get_team_timezone("COL") == "America/Denver"
        assert get_team_timezone("CGY") == "America/Denver"
        assert get_team_timezone("UTA") == "America/Denver"

    def test_pacific_teams(self):
        """Test Pacific timezone teams."""
        assert get_team_timezone("LAK") == "America/Los_Angeles"
        assert get_team_timezone("SJS") == "America/Los_Angeles"
        assert get_team_timezone("VGK") == "America/Los_Angeles"
        assert get_team_timezone("SEA") == "America/Los_Angeles"


class TestIsValidTeamCode:
    """Tests for is_valid_team_code function."""

    def test_valid_codes(self):
        """Test that valid codes return True."""
        assert is_valid_team_code("MTL") is True
        assert is_valid_team_code("TOR") is True
        assert is_valid_team_code("VGK") is True

    def test_case_handling(self):
        """Test case insensitivity."""
        assert is_valid_team_code("mtl") is True
        assert is_valid_team_code("Tor") is True

    def test_invalid_codes(self):
        """Test that invalid codes return False."""
        assert is_valid_team_code("XYZ") is False
        assert is_valid_team_code("INVALID") is False


class TestGetAllTeamCodes:
    """Tests for get_all_team_codes function."""

    def test_returns_32_teams(self):
        """Test that we have 32 NHL teams."""
        codes = get_all_team_codes()
        assert len(codes) == 32

    def test_codes_are_sorted(self):
        """Test that codes are sorted alphabetically."""
        codes = get_all_team_codes()
        assert codes == sorted(codes)

    def test_codes_are_3_letters(self):
        """Test that all codes are 3 letters."""
        codes = get_all_team_codes()
        assert all(len(code) == 3 for code in codes)

    def test_all_codes_are_valid(self):
        """Test that all returned codes are valid."""
        codes = get_all_team_codes()
        assert all(is_valid_team_code(code) for code in codes)


class TestTeamMappingCompleteness:
    """Tests to ensure mapping completeness."""

    def test_all_teams_have_full_name(self):
        """Test that every valid code has a full name."""
        for code in VALID_TEAM_CODES:
            assert get_team_full_name(code) is not None

    def test_all_teams_have_timezone(self):
        """Test that every valid code has a timezone."""
        for code in VALID_TEAM_CODES:
            assert get_team_timezone(code) is not None

    def test_expected_teams_present(self):
        """Test that key teams are in the mapping."""
        expected = [
            "ANA", "BOS", "BUF", "CAR", "CBJ", "CGY", "CHI", "COL",
            "DAL", "DET", "EDM", "FLA", "LAK", "MIN", "MTL", "NJD",
            "NSH", "NYI", "NYR", "OTT", "PHI", "PIT", "SEA", "SJS",
            "STL", "TBL", "TOR", "UTA", "VAN", "VGK", "WPG", "WSH",
        ]
        for code in expected:
            assert code in VALID_TEAM_CODES, f"Missing team: {code}"
