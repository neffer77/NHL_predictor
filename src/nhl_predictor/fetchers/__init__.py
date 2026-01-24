"""Data fetchers for various NHL data sources."""

from .base import BaseFetcher
from .nhl_api import NHLAPIFetcher, fetch_todays_schedule, fetch_standings
from .natural_stat_trick import NSTScraper, fetch_team_stats
from .moneypuck import MoneyPuckFetcher, fetch_predictions, fetch_team_stats as fetch_moneypuck_stats
from .daily_faceoff import DailyFaceoffScraper, fetch_starting_goalies, get_confirmed_starters
from .scouting_refs import ScoutingRefsScraper, fetch_referee_assignments

__all__ = [
    # Base
    "BaseFetcher",
    # NHL API
    "NHLAPIFetcher",
    "fetch_todays_schedule",
    "fetch_standings",
    # Natural Stat Trick
    "NSTScraper",
    "fetch_team_stats",
    # MoneyPuck
    "MoneyPuckFetcher",
    "fetch_predictions",
    "fetch_moneypuck_stats",
    # Daily Faceoff
    "DailyFaceoffScraper",
    "fetch_starting_goalies",
    "get_confirmed_starters",
    # Scouting The Refs
    "ScoutingRefsScraper",
    "fetch_referee_assignments",
]
