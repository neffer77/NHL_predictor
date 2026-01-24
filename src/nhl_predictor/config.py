"""Configuration management for NHL Predictor."""

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional


@dataclass
class DatabaseConfig:
    """Database configuration."""

    path: str = field(
        default_factory=lambda: os.environ.get(
            "NHL_PREDICTOR_DB",
            str(Path(__file__).parent.parent.parent / "data" / "nhl_predictor.db")
        )
    )
    echo: bool = False


@dataclass
class FetcherConfig:
    """Fetcher configuration."""

    max_retries: int = 3
    retry_backoff: float = 2.0
    request_timeout: int = 30
    rate_limit_delay: float = 2.0


@dataclass
class ScheduleConfig:
    """Scheduler configuration."""

    # Times in 24-hour format
    schedule_fetch_time: str = "08:00"
    nst_fetch_time: str = "09:00"
    moneypuck_fetch_time: str = "10:00"
    refs_fetch_time: str = "12:00"
    predictions_time: str = "14:00"

    # Goalie check interval (minutes)
    goalie_check_interval: int = 60


@dataclass
class ModelConfig:
    """Model weights configuration."""

    # Statistical Power Score weights
    xgf_weight: float = 0.45
    hdcf_weight: float = 0.25
    gsax_weight: float = 0.30

    # Contextual Adjustment Layer scalars
    fatigue_penalty: float = 0.88  # B2B reduction
    travel_penalty: float = 0.94  # >2 timezone
    home_ice_advantage: float = 1.04
    referee_home_bias: float = 1.03
    injury_penalty: float = 0.90

    # Selection thresholds
    min_confidence: float = 0.53  # Minimum model probability
    picks_per_day: int = 4


@dataclass
class Config:
    """Main application configuration."""

    database: DatabaseConfig = field(default_factory=DatabaseConfig)
    fetcher: FetcherConfig = field(default_factory=FetcherConfig)
    schedule: ScheduleConfig = field(default_factory=ScheduleConfig)
    model: ModelConfig = field(default_factory=ModelConfig)

    # Season settings
    current_season: str = "20252026"

    # Logging
    log_level: str = field(
        default_factory=lambda: os.environ.get("NHL_LOG_LEVEL", "INFO")
    )


# Global config instance
_config: Optional[Config] = None


def get_config() -> Config:
    """Get the global configuration instance."""
    global _config
    if _config is None:
        _config = Config()
    return _config


def set_config(config: Config) -> None:
    """Set the global configuration instance."""
    global _config
    _config = config
