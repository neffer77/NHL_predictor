"""Team name normalization and mapping utilities.

This module provides the "Golden Record" mapping to normalize team names
across different data sources (NHL API, NST, MoneyPuck, Daily Faceoff).
"""

import logging
import re
from typing import Optional

logger = logging.getLogger(__name__)

# Canonical team mapping: all variations -> 3-letter code
# Includes: full names, short names, abbreviations, special characters, city names
TEAM_MAPPING = {
    # Anaheim Ducks
    "Anaheim Ducks": "ANA",
    "Anaheim": "ANA",
    "Ducks": "ANA",
    "ANA": "ANA",
    "A.N.A": "ANA",

    # Arizona Coyotes / Utah Hockey Club (2024 relocation)
    "Arizona Coyotes": "UTA",
    "Arizona": "UTA",
    "Coyotes": "UTA",
    "ARI": "UTA",
    "PHX": "UTA",
    "Utah Hockey Club": "UTA",
    "Utah HC": "UTA",
    "Utah": "UTA",
    "UTA": "UTA",

    # Boston Bruins
    "Boston Bruins": "BOS",
    "Boston": "BOS",
    "Bruins": "BOS",
    "BOS": "BOS",
    "B.O.S": "BOS",

    # Buffalo Sabres
    "Buffalo Sabres": "BUF",
    "Buffalo": "BUF",
    "Sabres": "BUF",
    "BUF": "BUF",

    # Calgary Flames
    "Calgary Flames": "CGY",
    "Calgary": "CGY",
    "Flames": "CGY",
    "CGY": "CGY",
    "CAL": "CGY",

    # Carolina Hurricanes
    "Carolina Hurricanes": "CAR",
    "Carolina": "CAR",
    "Hurricanes": "CAR",
    "Canes": "CAR",
    "CAR": "CAR",

    # Chicago Blackhawks
    "Chicago Blackhawks": "CHI",
    "Chicago": "CHI",
    "Blackhawks": "CHI",
    "Hawks": "CHI",
    "CHI": "CHI",

    # Colorado Avalanche
    "Colorado Avalanche": "COL",
    "Colorado": "COL",
    "Avalanche": "COL",
    "Avs": "COL",
    "COL": "COL",

    # Columbus Blue Jackets
    "Columbus Blue Jackets": "CBJ",
    "Columbus": "CBJ",
    "Blue Jackets": "CBJ",
    "Jackets": "CBJ",
    "CBJ": "CBJ",

    # Dallas Stars
    "Dallas Stars": "DAL",
    "Dallas": "DAL",
    "Stars": "DAL",
    "DAL": "DAL",

    # Detroit Red Wings
    "Detroit Red Wings": "DET",
    "Detroit": "DET",
    "Red Wings": "DET",
    "Wings": "DET",
    "DET": "DET",

    # Edmonton Oilers
    "Edmonton Oilers": "EDM",
    "Edmonton": "EDM",
    "Oilers": "EDM",
    "EDM": "EDM",

    # Florida Panthers
    "Florida Panthers": "FLA",
    "Florida": "FLA",
    "Panthers": "FLA",
    "FLA": "FLA",

    # Los Angeles Kings
    "Los Angeles Kings": "LAK",
    "Los Angeles": "LAK",
    "LA Kings": "LAK",
    "Kings": "LAK",
    "LAK": "LAK",
    "L.A": "LAK",
    "LA": "LAK",

    # Minnesota Wild
    "Minnesota Wild": "MIN",
    "Minnesota": "MIN",
    "Wild": "MIN",
    "MIN": "MIN",

    # Montreal Canadiens
    "Montreal Canadiens": "MTL",
    "Montréal Canadiens": "MTL",
    "Montreal": "MTL",
    "Montréal": "MTL",
    "Canadiens": "MTL",
    "Habs": "MTL",
    "MTL": "MTL",

    # Nashville Predators
    "Nashville Predators": "NSH",
    "Nashville": "NSH",
    "Predators": "NSH",
    "Preds": "NSH",
    "NSH": "NSH",
    "NAS": "NSH",

    # New Jersey Devils
    "New Jersey Devils": "NJD",
    "New Jersey": "NJD",
    "Devils": "NJD",
    "NJD": "NJD",
    "NJ": "NJD",

    # New York Islanders
    "New York Islanders": "NYI",
    "NY Islanders": "NYI",
    "Islanders": "NYI",
    "Isles": "NYI",
    "NYI": "NYI",

    # New York Rangers
    "New York Rangers": "NYR",
    "NY Rangers": "NYR",
    "Rangers": "NYR",
    "NYR": "NYR",

    # Ottawa Senators
    "Ottawa Senators": "OTT",
    "Ottawa": "OTT",
    "Senators": "OTT",
    "Sens": "OTT",
    "OTT": "OTT",

    # Philadelphia Flyers
    "Philadelphia Flyers": "PHI",
    "Philadelphia": "PHI",
    "Flyers": "PHI",
    "PHI": "PHI",

    # Pittsburgh Penguins
    "Pittsburgh Penguins": "PIT",
    "Pittsburgh": "PIT",
    "Penguins": "PIT",
    "Pens": "PIT",
    "PIT": "PIT",

    # San Jose Sharks
    "San Jose Sharks": "SJS",
    "San Jose": "SJS",
    "Sharks": "SJS",
    "SJS": "SJS",
    "SJ": "SJS",

    # Seattle Kraken
    "Seattle Kraken": "SEA",
    "Seattle": "SEA",
    "Kraken": "SEA",
    "SEA": "SEA",

    # St. Louis Blues
    "St. Louis Blues": "STL",
    "St Louis Blues": "STL",
    "St. Louis": "STL",
    "St Louis": "STL",
    "Blues": "STL",
    "STL": "STL",

    # Tampa Bay Lightning
    "Tampa Bay Lightning": "TBL",
    "Tampa Bay": "TBL",
    "Tampa": "TBL",
    "Lightning": "TBL",
    "Bolts": "TBL",
    "TBL": "TBL",
    "TB": "TBL",

    # Toronto Maple Leafs
    "Toronto Maple Leafs": "TOR",
    "Toronto": "TOR",
    "Maple Leafs": "TOR",
    "Leafs": "TOR",
    "TOR": "TOR",

    # Vancouver Canucks
    "Vancouver Canucks": "VAN",
    "Vancouver": "VAN",
    "Canucks": "VAN",
    "Nucks": "VAN",
    "VAN": "VAN",

    # Vegas Golden Knights
    "Vegas Golden Knights": "VGK",
    "Vegas": "VGK",
    "Golden Knights": "VGK",
    "Knights": "VGK",
    "VGK": "VGK",
    "LVK": "VGK",
    "Las Vegas": "VGK",

    # Washington Capitals
    "Washington Capitals": "WSH",
    "Washington": "WSH",
    "Capitals": "WSH",
    "Caps": "WSH",
    "WSH": "WSH",
    "WAS": "WSH",

    # Winnipeg Jets
    "Winnipeg Jets": "WPG",
    "Winnipeg": "WPG",
    "Jets": "WPG",
    "WPG": "WPG",
    "WIN": "WPG",
}

# Reverse mapping: 3-letter code -> full team name
TEAM_FULL_NAMES = {
    "ANA": "Anaheim Ducks",
    "UTA": "Utah Hockey Club",
    "BOS": "Boston Bruins",
    "BUF": "Buffalo Sabres",
    "CGY": "Calgary Flames",
    "CAR": "Carolina Hurricanes",
    "CHI": "Chicago Blackhawks",
    "COL": "Colorado Avalanche",
    "CBJ": "Columbus Blue Jackets",
    "DAL": "Dallas Stars",
    "DET": "Detroit Red Wings",
    "EDM": "Edmonton Oilers",
    "FLA": "Florida Panthers",
    "LAK": "Los Angeles Kings",
    "MIN": "Minnesota Wild",
    "MTL": "Montreal Canadiens",
    "NSH": "Nashville Predators",
    "NJD": "New Jersey Devils",
    "NYI": "New York Islanders",
    "NYR": "New York Rangers",
    "OTT": "Ottawa Senators",
    "PHI": "Philadelphia Flyers",
    "PIT": "Pittsburgh Penguins",
    "SJS": "San Jose Sharks",
    "SEA": "Seattle Kraken",
    "STL": "St. Louis Blues",
    "TBL": "Tampa Bay Lightning",
    "TOR": "Toronto Maple Leafs",
    "VAN": "Vancouver Canucks",
    "VGK": "Vegas Golden Knights",
    "WSH": "Washington Capitals",
    "WPG": "Winnipeg Jets",
}

# Team timezone mapping for travel calculations
TEAM_TIMEZONES = {
    "ANA": "America/Los_Angeles",
    "UTA": "America/Denver",
    "BOS": "America/New_York",
    "BUF": "America/New_York",
    "CGY": "America/Denver",
    "CAR": "America/New_York",
    "CHI": "America/Chicago",
    "COL": "America/Denver",
    "CBJ": "America/New_York",
    "DAL": "America/Chicago",
    "DET": "America/Detroit",
    "EDM": "America/Edmonton",
    "FLA": "America/New_York",
    "LAK": "America/Los_Angeles",
    "MIN": "America/Chicago",
    "MTL": "America/Montreal",
    "NSH": "America/Chicago",
    "NJD": "America/New_York",
    "NYI": "America/New_York",
    "NYR": "America/New_York",
    "OTT": "America/Toronto",
    "PHI": "America/New_York",
    "PIT": "America/New_York",
    "SJS": "America/Los_Angeles",
    "SEA": "America/Los_Angeles",
    "STL": "America/Chicago",
    "TBL": "America/New_York",
    "TOR": "America/Toronto",
    "VAN": "America/Vancouver",
    "VGK": "America/Los_Angeles",
    "WSH": "America/New_York",
    "WPG": "America/Winnipeg",
}

# All valid team codes
VALID_TEAM_CODES = set(TEAM_FULL_NAMES.keys())


def normalize_team_name(raw_name: str) -> str:
    """
    Normalize a team name from any source to standard 3-letter code.

    Args:
        raw_name: Team name in any format (full name, abbreviation, etc.)

    Returns:
        Standard 3-letter team code.

    Raises:
        ValueError: If team name cannot be resolved.

    Examples:
        >>> normalize_team_name("Montreal Canadiens")
        'MTL'
        >>> normalize_team_name("Montréal Canadiens")
        'MTL'
        >>> normalize_team_name("Habs")
        'MTL'
        >>> normalize_team_name("MTL")
        'MTL'
    """
    if not raw_name:
        raise ValueError("Team name cannot be empty")

    # Clean input
    cleaned = raw_name.strip()

    # Direct lookup
    if cleaned in TEAM_MAPPING:
        return TEAM_MAPPING[cleaned]

    # Try case-insensitive lookup
    for key, code in TEAM_MAPPING.items():
        if key.lower() == cleaned.lower():
            return code

    # Try partial match (for cases like "MTL Canadiens")
    for key, code in TEAM_MAPPING.items():
        if key.lower() in cleaned.lower() or cleaned.lower() in key.lower():
            logger.debug(f"Partial match: '{raw_name}' -> '{code}'")
            return code

    # Log warning and raise error for unrecognized team
    logger.warning(f"Unrecognized team name: '{raw_name}'")
    raise ValueError(f"Cannot resolve team name: '{raw_name}'")


def normalize_team_name_safe(raw_name: str) -> Optional[str]:
    """
    Safely normalize a team name, returning None if not found.

    Args:
        raw_name: Team name in any format.

    Returns:
        Standard 3-letter team code, or None if not found.
    """
    try:
        return normalize_team_name(raw_name)
    except ValueError:
        return None


def get_team_full_name(team_code: str) -> str:
    """
    Get the full team name from a 3-letter code.

    Args:
        team_code: Standard 3-letter team code.

    Returns:
        Full team name.

    Raises:
        ValueError: If team code is invalid.

    Examples:
        >>> get_team_full_name("MTL")
        'Montreal Canadiens'
        >>> get_team_full_name("VGK")
        'Vegas Golden Knights'
    """
    code = team_code.upper().strip()
    if code in TEAM_FULL_NAMES:
        return TEAM_FULL_NAMES[code]
    raise ValueError(f"Invalid team code: '{team_code}'")


def get_team_timezone(team_code: str) -> str:
    """
    Get the timezone for a team's home arena.

    Args:
        team_code: Standard 3-letter team code.

    Returns:
        Timezone string (e.g., 'America/New_York').

    Raises:
        ValueError: If team code is invalid.
    """
    code = team_code.upper().strip()
    if code in TEAM_TIMEZONES:
        return TEAM_TIMEZONES[code]
    raise ValueError(f"Invalid team code: '{team_code}'")


def is_valid_team_code(team_code: str) -> bool:
    """
    Check if a team code is valid.

    Args:
        team_code: Team code to validate.

    Returns:
        True if valid, False otherwise.
    """
    return team_code.upper().strip() in VALID_TEAM_CODES


def get_all_team_codes() -> list[str]:
    """
    Get a list of all valid team codes.

    Returns:
        List of 32 team codes.
    """
    return sorted(VALID_TEAM_CODES)
