"""Logging and Monitoring System.

Comprehensive logging configuration with structured logging,
log rotation, and error aggregation.
"""

import json
import logging
import logging.handlers
import sys
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

from ..config import get_config


class StructuredFormatter(logging.Formatter):
    """JSON structured log formatter."""

    def format(self, record: logging.LogRecord) -> str:
        """Format log record as JSON."""
        log_data = {
            "timestamp": datetime.utcnow().isoformat() + "Z",
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "module": record.module,
            "function": record.funcName,
            "line": record.lineno,
        }

        # Add exception info if present
        if record.exc_info:
            log_data["exception"] = self.formatException(record.exc_info)

        # Add extra fields
        if hasattr(record, "extra_data"):
            log_data["extra"] = record.extra_data

        return json.dumps(log_data)


class ConsoleFormatter(logging.Formatter):
    """Colored console formatter."""

    COLORS = {
        "DEBUG": "\033[36m",     # Cyan
        "INFO": "\033[32m",      # Green
        "WARNING": "\033[33m",   # Yellow
        "ERROR": "\033[31m",     # Red
        "CRITICAL": "\033[35m",  # Magenta
    }
    RESET = "\033[0m"

    def format(self, record: logging.LogRecord) -> str:
        """Format with colors for console."""
        color = self.COLORS.get(record.levelname, "")
        record.levelname = f"{color}{record.levelname}{self.RESET}"

        return super().format(record)


class LoggerFactory:
    """Factory for creating configured loggers."""

    _initialized = False
    _log_dir: Optional[Path] = None

    @classmethod
    def setup(
        cls,
        log_dir: Optional[str] = None,
        log_level: str = "INFO",
        json_format: bool = False,
        console_output: bool = True,
    ) -> None:
        """
        Set up logging configuration.

        Args:
            log_dir: Directory for log files.
            log_level: Minimum log level.
            json_format: Use JSON structured logging.
            console_output: Also output to console.
        """
        if cls._initialized:
            return

        # Set up log directory
        if log_dir:
            cls._log_dir = Path(log_dir)
        else:
            cls._log_dir = Path(__file__).parent.parent.parent.parent / "logs"

        cls._log_dir.mkdir(parents=True, exist_ok=True)

        # Get root logger
        root_logger = logging.getLogger()
        root_logger.setLevel(getattr(logging, log_level.upper()))

        # Clear existing handlers
        root_logger.handlers = []

        # Console handler
        if console_output:
            console_handler = logging.StreamHandler(sys.stdout)
            console_handler.setLevel(logging.INFO)

            if json_format:
                console_handler.setFormatter(StructuredFormatter())
            else:
                console_handler.setFormatter(ConsoleFormatter(
                    "%(asctime)s - %(levelname)s - %(name)s - %(message)s",
                    datefmt="%H:%M:%S",
                ))

            root_logger.addHandler(console_handler)

        # File handlers with rotation
        cls._add_file_handler(
            root_logger,
            "nhl_predictor.log",
            log_level,
            json_format,
        )

        # Separate handlers for different components
        cls._setup_component_loggers(json_format)

        cls._initialized = True

    @classmethod
    def _add_file_handler(
        cls,
        logger: logging.Logger,
        filename: str,
        level: str,
        json_format: bool,
    ) -> None:
        """Add rotating file handler to logger."""
        log_path = cls._log_dir / filename

        handler = logging.handlers.TimedRotatingFileHandler(
            log_path,
            when="midnight",
            interval=1,
            backupCount=30,  # Keep 30 days
            encoding="utf-8",
        )
        handler.setLevel(getattr(logging, level.upper()))

        if json_format:
            handler.setFormatter(StructuredFormatter())
        else:
            handler.setFormatter(logging.Formatter(
                "%(asctime)s - %(levelname)s - %(name)s - %(message)s",
                datefmt="%Y-%m-%d %H:%M:%S",
            ))

        logger.addHandler(handler)

    @classmethod
    def _setup_component_loggers(cls, json_format: bool) -> None:
        """Set up separate loggers for different components."""
        components = {
            "fetchers": "fetchers.log",
            "model": "model.log",
            "predictions": "predictions.log",
        }

        for component, filename in components.items():
            logger = logging.getLogger(f"nhl_predictor.{component}")

            # Add component-specific file handler
            log_path = cls._log_dir / filename

            handler = logging.handlers.TimedRotatingFileHandler(
                log_path,
                when="midnight",
                interval=1,
                backupCount=30,
                encoding="utf-8",
            )

            if json_format:
                handler.setFormatter(StructuredFormatter())
            else:
                handler.setFormatter(logging.Formatter(
                    "%(asctime)s - %(levelname)s - %(name)s - %(message)s",
                    datefmt="%Y-%m-%d %H:%M:%S",
                ))

            logger.addHandler(handler)

    @classmethod
    def get_logger(cls, name: str) -> logging.Logger:
        """Get a logger by name."""
        if not cls._initialized:
            config = get_config()
            cls.setup(log_level=config.log_level)

        return logging.getLogger(name)


class ErrorAggregator:
    """Aggregates and reports errors."""

    def __init__(self):
        """Initialize error aggregator."""
        self._errors: list[dict] = []
        self._max_errors = 1000

    def add_error(
        self,
        source: str,
        error: Exception,
        context: Optional[dict] = None,
    ) -> None:
        """
        Add an error to the aggregator.

        Args:
            source: Error source (module/function).
            error: The exception.
            context: Additional context.
        """
        error_data = {
            "timestamp": datetime.now().isoformat(),
            "source": source,
            "type": type(error).__name__,
            "message": str(error),
            "context": context or {},
        }

        self._errors.append(error_data)

        # Trim if too many
        if len(self._errors) > self._max_errors:
            self._errors = self._errors[-self._max_errors:]

    def get_recent_errors(
        self,
        limit: int = 50,
        source: Optional[str] = None,
    ) -> list[dict]:
        """
        Get recent errors.

        Args:
            limit: Maximum number of errors.
            source: Filter by source.

        Returns:
            List of error dictionaries.
        """
        errors = self._errors

        if source:
            errors = [e for e in errors if e["source"] == source]

        return errors[-limit:]

    def get_error_summary(self) -> dict:
        """Get summary of errors by type and source."""
        summary = {
            "total_errors": len(self._errors),
            "by_type": {},
            "by_source": {},
        }

        for error in self._errors:
            # By type
            error_type = error["type"]
            summary["by_type"][error_type] = (
                summary["by_type"].get(error_type, 0) + 1
            )

            # By source
            source = error["source"]
            summary["by_source"][source] = (
                summary["by_source"].get(source, 0) + 1
            )

        return summary

    def clear(self) -> None:
        """Clear all aggregated errors."""
        self._errors = []


class MetricsCollector:
    """Collects and reports operational metrics."""

    def __init__(self):
        """Initialize metrics collector."""
        self._metrics: dict[str, list] = {}
        self._counters: dict[str, int] = {}

    def record_metric(
        self,
        name: str,
        value: float,
        tags: Optional[dict] = None,
    ) -> None:
        """
        Record a metric value.

        Args:
            name: Metric name.
            value: Metric value.
            tags: Optional tags.
        """
        if name not in self._metrics:
            self._metrics[name] = []

        self._metrics[name].append({
            "timestamp": datetime.now().isoformat(),
            "value": value,
            "tags": tags or {},
        })

        # Keep last 1000 values
        if len(self._metrics[name]) > 1000:
            self._metrics[name] = self._metrics[name][-1000:]

    def increment_counter(self, name: str, amount: int = 1) -> None:
        """Increment a counter."""
        self._counters[name] = self._counters.get(name, 0) + amount

    def get_counter(self, name: str) -> int:
        """Get counter value."""
        return self._counters.get(name, 0)

    def get_metric_stats(self, name: str) -> Optional[dict]:
        """Get statistics for a metric."""
        if name not in self._metrics or not self._metrics[name]:
            return None

        values = [m["value"] for m in self._metrics[name]]

        return {
            "name": name,
            "count": len(values),
            "min": min(values),
            "max": max(values),
            "avg": sum(values) / len(values),
            "latest": values[-1],
        }

    def get_all_stats(self) -> dict:
        """Get all metric statistics."""
        return {
            "metrics": {
                name: self.get_metric_stats(name)
                for name in self._metrics
            },
            "counters": dict(self._counters),
        }


# Global instances
_error_aggregator: Optional[ErrorAggregator] = None
_metrics_collector: Optional[MetricsCollector] = None


def get_error_aggregator() -> ErrorAggregator:
    """Get global error aggregator."""
    global _error_aggregator
    if _error_aggregator is None:
        _error_aggregator = ErrorAggregator()
    return _error_aggregator


def get_metrics_collector() -> MetricsCollector:
    """Get global metrics collector."""
    global _metrics_collector
    if _metrics_collector is None:
        _metrics_collector = MetricsCollector()
    return _metrics_collector


def setup_logging(
    log_level: str = "INFO",
    json_format: bool = False,
) -> None:
    """Convenience function to set up logging."""
    LoggerFactory.setup(log_level=log_level, json_format=json_format)


def get_logger(name: str) -> logging.Logger:
    """Convenience function to get a logger."""
    return LoggerFactory.get_logger(name)
