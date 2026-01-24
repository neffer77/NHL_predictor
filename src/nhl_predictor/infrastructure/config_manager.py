"""Configuration Management.

Loads configuration from files and environment variables
with validation and hot-reload support.
"""

import json
import logging
import os
from dataclasses import asdict, dataclass, field, fields
from pathlib import Path
from typing import Any, Optional, TypeVar

logger = logging.getLogger(__name__)

T = TypeVar("T")


@dataclass
class DatabaseConfig:
    """Database configuration."""

    path: str = ""
    echo: bool = False
    pool_size: int = 5
    pool_timeout: int = 30

    def __post_init__(self):
        if not self.path:
            self.path = str(
                Path(__file__).parent.parent.parent.parent
                / "data" / "nhl_predictor.db"
            )


@dataclass
class FetcherConfig:
    """Data fetcher configuration."""

    max_retries: int = 3
    retry_backoff: float = 2.0
    request_timeout: int = 30
    rate_limit_delay: float = 2.0

    # Source URLs
    nhl_api_base: str = "https://api-web.nhle.com/v1"
    nst_base: str = "https://www.naturalstattrick.com"
    moneypuck_base: str = "https://moneypuck.com"
    daily_faceoff_base: str = "https://www.dailyfaceoff.com"
    scouting_refs_base: str = "https://scoutingtherefs.com"


@dataclass
class ScheduleConfig:
    """Job scheduler configuration."""

    schedule_fetch_time: str = "08:00"
    nst_fetch_time: str = "09:00"
    moneypuck_fetch_time: str = "10:00"
    refs_fetch_time: str = "12:00"
    predictions_time: str = "14:00"
    goalie_check_interval: int = 60
    outcome_update_time: str = "23:00"


@dataclass
class ModelConfig:
    """Model weights and thresholds."""

    # Statistical Power Score weights
    xgf_weight: float = 0.45
    hdcf_weight: float = 0.25
    gsax_weight: float = 0.30

    # Contextual Adjustment Layer scalars
    fatigue_penalty: float = 0.88
    travel_penalty: float = 0.94
    home_ice_advantage: float = 1.04
    referee_home_bias: float = 1.03
    injury_penalty: float = 0.90

    # Selection thresholds
    min_confidence: float = 0.53
    min_edge: float = 0.02
    picks_per_day: int = 4

    # Kelly criterion
    kelly_fraction: float = 0.25

    # Bayesian prior settings
    prior_games_threshold: int = 40
    initial_prior_weight: float = 0.50


@dataclass
class NotificationConfig:
    """Notification settings."""

    email_enabled: bool = False
    smtp_host: str = ""
    smtp_port: int = 587
    smtp_user: str = ""
    smtp_password: str = ""
    email_from: str = ""
    email_to: list = field(default_factory=list)

    webhook_enabled: bool = False
    webhook_url: str = ""
    webhook_type: str = "slack"


@dataclass
class LoggingConfig:
    """Logging configuration."""

    level: str = "INFO"
    format: str = "standard"  # "standard" or "json"
    log_dir: str = ""
    max_days: int = 30


@dataclass
class AppConfig:
    """Main application configuration."""

    database: DatabaseConfig = field(default_factory=DatabaseConfig)
    fetcher: FetcherConfig = field(default_factory=FetcherConfig)
    schedule: ScheduleConfig = field(default_factory=ScheduleConfig)
    model: ModelConfig = field(default_factory=ModelConfig)
    notifications: NotificationConfig = field(default_factory=NotificationConfig)
    logging: LoggingConfig = field(default_factory=LoggingConfig)

    # Season settings
    current_season: str = "20252026"
    season_start_date: str = "2025-10-04"

    # Feature flags
    enable_backtest_mode: bool = False
    enable_debug_endpoints: bool = False


class ConfigManager:
    """Manages application configuration."""

    ENV_PREFIX = "NHL_"

    def __init__(self, config_path: Optional[str] = None):
        """
        Initialize configuration manager.

        Args:
            config_path: Path to config file (JSON or YAML).
        """
        self.config_path = Path(config_path) if config_path else None
        self._config: Optional[AppConfig] = None
        self._file_mtime: float = 0

    def load(self) -> AppConfig:
        """
        Load configuration from file and environment.

        Returns:
            Loaded AppConfig.
        """
        # Start with defaults
        config_dict: dict[str, Any] = {}

        # Load from file if specified
        if self.config_path and self.config_path.exists():
            config_dict = self._load_file(self.config_path)
            self._file_mtime = self.config_path.stat().st_mtime

        # Override with environment variables
        config_dict = self._apply_env_overrides(config_dict)

        # Build config object
        self._config = self._build_config(config_dict)

        # Validate
        self._validate(self._config)

        logger.info(f"Configuration loaded from {self.config_path or 'defaults'}")

        return self._config

    def _load_file(self, path: Path) -> dict:
        """Load configuration from file."""
        content = path.read_text()

        if path.suffix in [".yaml", ".yml"]:
            try:
                import yaml
                return yaml.safe_load(content) or {}
            except ImportError:
                logger.warning("PyYAML not installed, trying JSON")

        # Default to JSON
        return json.loads(content)

    def _apply_env_overrides(self, config: dict) -> dict:
        """Apply environment variable overrides."""
        env_mappings = {
            "NHL_DB_PATH": ("database", "path"),
            "NHL_LOG_LEVEL": ("logging", "level"),
            "NHL_SEASON": ("current_season",),
            "NHL_PICKS_PER_DAY": ("model", "picks_per_day"),
            "NHL_MIN_CONFIDENCE": ("model", "min_confidence"),
            "NHL_XGF_WEIGHT": ("model", "xgf_weight"),
            "NHL_HDCF_WEIGHT": ("model", "hdcf_weight"),
            "NHL_GSAX_WEIGHT": ("model", "gsax_weight"),
            "NHL_EMAIL_ENABLED": ("notifications", "email_enabled"),
            "NHL_SMTP_HOST": ("notifications", "smtp_host"),
            "NHL_SMTP_PORT": ("notifications", "smtp_port"),
            "NHL_SMTP_USER": ("notifications", "smtp_user"),
            "NHL_SMTP_PASSWORD": ("notifications", "smtp_password"),
            "NHL_WEBHOOK_URL": ("notifications", "webhook_url"),
            "NHL_WEBHOOK_ENABLED": ("notifications", "webhook_enabled"),
        }

        for env_var, path in env_mappings.items():
            value = os.environ.get(env_var)
            if value is not None:
                self._set_nested(config, path, self._parse_value(value))

        return config

    def _parse_value(self, value: str) -> Any:
        """Parse string value to appropriate type."""
        # Boolean
        if value.lower() in ("true", "yes", "1"):
            return True
        if value.lower() in ("false", "no", "0"):
            return False

        # Number
        try:
            if "." in value:
                return float(value)
            return int(value)
        except ValueError:
            pass

        return value

    def _set_nested(self, config: dict, path: tuple, value: Any) -> None:
        """Set a nested configuration value."""
        current = config

        for key in path[:-1]:
            if key not in current:
                current[key] = {}
            current = current[key]

        current[path[-1]] = value

    def _build_config(self, config_dict: dict) -> AppConfig:
        """Build AppConfig from dictionary."""
        return AppConfig(
            database=DatabaseConfig(**config_dict.get("database", {})),
            fetcher=FetcherConfig(**config_dict.get("fetcher", {})),
            schedule=ScheduleConfig(**config_dict.get("schedule", {})),
            model=ModelConfig(**config_dict.get("model", {})),
            notifications=NotificationConfig(**config_dict.get("notifications", {})),
            logging=LoggingConfig(**config_dict.get("logging", {})),
            current_season=config_dict.get("current_season", "20252026"),
            season_start_date=config_dict.get("season_start_date", "2025-10-04"),
            enable_backtest_mode=config_dict.get("enable_backtest_mode", False),
            enable_debug_endpoints=config_dict.get("enable_debug_endpoints", False),
        )

    def _validate(self, config: AppConfig) -> None:
        """Validate configuration values."""
        errors = []

        # Validate model weights sum to 1.0
        weight_sum = (
            config.model.xgf_weight +
            config.model.hdcf_weight +
            config.model.gsax_weight
        )
        if abs(weight_sum - 1.0) > 0.01:
            errors.append(
                f"Model weights must sum to 1.0, got {weight_sum:.2f}"
            )

        # Validate ranges
        if not 0.5 <= config.model.min_confidence <= 0.7:
            errors.append(
                f"min_confidence should be between 0.5 and 0.7, "
                f"got {config.model.min_confidence}"
            )

        if not 1 <= config.model.picks_per_day <= 10:
            errors.append(
                f"picks_per_day should be between 1 and 10, "
                f"got {config.model.picks_per_day}"
            )

        # Validate scalars
        for scalar_name in ["fatigue_penalty", "travel_penalty", "injury_penalty"]:
            value = getattr(config.model, scalar_name)
            if not 0.5 <= value <= 1.0:
                errors.append(
                    f"{scalar_name} should be between 0.5 and 1.0, got {value}"
                )

        if errors:
            for error in errors:
                logger.warning(f"Config validation: {error}")

    def get(self) -> AppConfig:
        """Get current configuration."""
        if self._config is None:
            return self.load()
        return self._config

    def reload(self) -> AppConfig:
        """Force reload configuration."""
        self._config = None
        return self.load()

    def check_for_changes(self) -> bool:
        """
        Check if config file has changed.

        Returns:
            True if file has been modified.
        """
        if not self.config_path or not self.config_path.exists():
            return False

        current_mtime = self.config_path.stat().st_mtime
        return current_mtime > self._file_mtime

    def hot_reload(self) -> Optional[AppConfig]:
        """
        Reload configuration if file has changed.

        Returns:
            New config if reloaded, None otherwise.
        """
        if self.check_for_changes():
            logger.info("Config file changed, reloading...")
            return self.reload()
        return None

    def to_dict(self) -> dict:
        """Convert current config to dictionary."""
        if self._config is None:
            self.load()
        return asdict(self._config)

    def save(self, path: Optional[Path] = None) -> None:
        """
        Save current configuration to file.

        Args:
            path: Output path (defaults to original config_path).
        """
        output_path = path or self.config_path
        if not output_path:
            raise ValueError("No output path specified")

        config_dict = self.to_dict()

        if output_path.suffix in [".yaml", ".yml"]:
            try:
                import yaml
                content = yaml.dump(config_dict, default_flow_style=False)
            except ImportError:
                output_path = output_path.with_suffix(".json")
                content = json.dumps(config_dict, indent=2)
        else:
            content = json.dumps(config_dict, indent=2)

        output_path.write_text(content)
        logger.info(f"Configuration saved to {output_path}")


# Global configuration manager
_config_manager: Optional[ConfigManager] = None


def init_config(config_path: Optional[str] = None) -> AppConfig:
    """Initialize global configuration."""
    global _config_manager
    _config_manager = ConfigManager(config_path)
    return _config_manager.load()


def get_app_config() -> AppConfig:
    """Get application configuration."""
    global _config_manager
    if _config_manager is None:
        _config_manager = ConfigManager()
    return _config_manager.get()


def reload_config() -> AppConfig:
    """Reload configuration."""
    global _config_manager
    if _config_manager is None:
        _config_manager = ConfigManager()
    return _config_manager.reload()


def create_default_config(path: str) -> None:
    """Create a default configuration file."""
    manager = ConfigManager()
    manager.load()  # Load defaults
    manager.save(Path(path))
