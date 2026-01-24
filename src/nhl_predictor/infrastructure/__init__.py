"""Infrastructure and Operations modules for NHL Predictor."""

from .scheduler import (
    JobOrchestrator,
    JobResult,
    create_orchestrator,
    run_scheduler,
)

from .freshness import (
    FreshnessMonitor,
    FreshnessStatus,
    SourceFreshness,
    FreshnessReport,
    check_data_freshness,
    get_freshness_status,
)

from .logging_config import (
    LoggerFactory,
    StructuredFormatter,
    ConsoleFormatter,
    ErrorAggregator,
    MetricsCollector,
    setup_logging,
    get_logger,
    get_error_aggregator,
    get_metrics_collector,
)

from .config_manager import (
    ConfigManager,
    AppConfig,
    DatabaseConfig,
    FetcherConfig,
    ScheduleConfig,
    ModelConfig,
    NotificationConfig,
    LoggingConfig,
    init_config,
    get_app_config,
    reload_config,
    create_default_config,
)

from .backtest import (
    Backtester,
    BacktestConfig,
    BacktestResult,
    BacktestPick,
    BacktestDay,
    run_backtest,
)

from .resilience import (
    RetryConfig,
    RetryError,
    CircuitBreaker,
    CircuitBreakerConfig,
    CircuitBreakerRegistry,
    CircuitState,
    CircuitOpenError,
    FallbackHandler,
    GracefulDegradation,
    with_retry,
    get_circuit_breaker,
    get_fallback_handler,
    get_degradation_handler,
    resilient_fetch,
)

__all__ = [
    # Scheduler
    "JobOrchestrator",
    "JobResult",
    "create_orchestrator",
    "run_scheduler",
    # Freshness
    "FreshnessMonitor",
    "FreshnessStatus",
    "SourceFreshness",
    "FreshnessReport",
    "check_data_freshness",
    "get_freshness_status",
    # Logging
    "LoggerFactory",
    "StructuredFormatter",
    "ConsoleFormatter",
    "ErrorAggregator",
    "MetricsCollector",
    "setup_logging",
    "get_logger",
    "get_error_aggregator",
    "get_metrics_collector",
    # Config
    "ConfigManager",
    "AppConfig",
    "DatabaseConfig",
    "FetcherConfig",
    "ScheduleConfig",
    "ModelConfig",
    "NotificationConfig",
    "LoggingConfig",
    "init_config",
    "get_app_config",
    "reload_config",
    "create_default_config",
    # Backtest
    "Backtester",
    "BacktestConfig",
    "BacktestResult",
    "BacktestPick",
    "BacktestDay",
    "run_backtest",
    # Resilience
    "RetryConfig",
    "RetryError",
    "CircuitBreaker",
    "CircuitBreakerConfig",
    "CircuitBreakerRegistry",
    "CircuitState",
    "CircuitOpenError",
    "FallbackHandler",
    "GracefulDegradation",
    "with_retry",
    "get_circuit_breaker",
    "get_fallback_handler",
    "get_degradation_handler",
    "resilient_fetch",
]
