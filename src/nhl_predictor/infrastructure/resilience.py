"""Error Recovery and Resilience.

Implements retry logic, circuit breakers, and graceful degradation
for handling failures in network operations and data processing.
"""

import logging
import time
from dataclasses import dataclass
from datetime import datetime, timedelta
from enum import Enum
from functools import wraps
from typing import Any, Callable, Optional, TypeVar

logger = logging.getLogger(__name__)

T = TypeVar("T")


class CircuitState(Enum):
    """Circuit breaker states."""

    CLOSED = "closed"  # Normal operation
    OPEN = "open"  # Failing, reject requests
    HALF_OPEN = "half_open"  # Testing if recovered


@dataclass
class RetryConfig:
    """Configuration for retry behavior."""

    max_retries: int = 3
    base_delay: float = 1.0  # Base delay in seconds
    max_delay: float = 60.0  # Maximum delay
    exponential_base: float = 2.0  # Exponential backoff base
    jitter: bool = True  # Add randomness to delays

    # Exceptions to retry on
    retryable_exceptions: tuple = (
        ConnectionError,
        TimeoutError,
        OSError,
    )


@dataclass
class CircuitBreakerConfig:
    """Configuration for circuit breaker."""

    failure_threshold: int = 5  # Failures before opening
    success_threshold: int = 2  # Successes to close
    timeout: float = 60.0  # Seconds before half-open


class RetryError(Exception):
    """Raised when all retries are exhausted."""

    def __init__(self, message: str, last_exception: Optional[Exception] = None):
        super().__init__(message)
        self.last_exception = last_exception


class CircuitOpenError(Exception):
    """Raised when circuit breaker is open."""

    def __init__(self, message: str, reset_time: datetime):
        super().__init__(message)
        self.reset_time = reset_time


def with_retry(
    max_retries: int = 3,
    base_delay: float = 1.0,
    exponential_base: float = 2.0,
    retryable_exceptions: tuple = (Exception,),
) -> Callable:
    """
    Decorator for retry with exponential backoff.

    Args:
        max_retries: Maximum number of retry attempts.
        base_delay: Initial delay between retries.
        exponential_base: Base for exponential backoff.
        retryable_exceptions: Exceptions that trigger retry.

    Returns:
        Decorated function.
    """
    def decorator(func: Callable[..., T]) -> Callable[..., T]:
        @wraps(func)
        def wrapper(*args, **kwargs) -> T:
            last_exception = None

            for attempt in range(max_retries + 1):
                try:
                    return func(*args, **kwargs)

                except retryable_exceptions as e:
                    last_exception = e

                    if attempt < max_retries:
                        delay = base_delay * (exponential_base ** attempt)

                        # Add jitter
                        import random
                        delay *= (0.5 + random.random())

                        logger.warning(
                            f"{func.__name__} failed (attempt {attempt + 1}/"
                            f"{max_retries + 1}): {e}. "
                            f"Retrying in {delay:.1f}s..."
                        )
                        time.sleep(delay)
                    else:
                        logger.error(
                            f"{func.__name__} failed after {max_retries + 1} "
                            f"attempts: {e}"
                        )

            raise RetryError(
                f"All {max_retries + 1} attempts failed for {func.__name__}",
                last_exception,
            )

        return wrapper
    return decorator


class CircuitBreaker:
    """
    Circuit breaker pattern implementation.

    Prevents repeated calls to failing services by "opening"
    the circuit after threshold failures.
    """

    def __init__(
        self,
        name: str,
        config: Optional[CircuitBreakerConfig] = None,
    ):
        """
        Initialize circuit breaker.

        Args:
            name: Name for this circuit.
            config: Circuit breaker configuration.
        """
        self.name = name
        self.config = config or CircuitBreakerConfig()

        self._state = CircuitState.CLOSED
        self._failure_count = 0
        self._success_count = 0
        self._last_failure_time: Optional[datetime] = None

    @property
    def state(self) -> CircuitState:
        """Get current state, checking for timeout."""
        if self._state == CircuitState.OPEN:
            if self._should_attempt_reset():
                self._state = CircuitState.HALF_OPEN
                logger.info(f"Circuit {self.name} entering half-open state")

        return self._state

    def _should_attempt_reset(self) -> bool:
        """Check if timeout has passed for reset attempt."""
        if self._last_failure_time is None:
            return True

        elapsed = (datetime.now() - self._last_failure_time).total_seconds()
        return elapsed >= self.config.timeout

    def call(self, func: Callable[..., T], *args, **kwargs) -> T:
        """
        Execute function through circuit breaker.

        Args:
            func: Function to execute.
            *args: Function arguments.
            **kwargs: Function keyword arguments.

        Returns:
            Function result.

        Raises:
            CircuitOpenError: If circuit is open.
        """
        state = self.state

        if state == CircuitState.OPEN:
            reset_time = self._last_failure_time + timedelta(
                seconds=self.config.timeout
            )
            raise CircuitOpenError(
                f"Circuit {self.name} is open",
                reset_time,
            )

        try:
            result = func(*args, **kwargs)
            self._on_success()
            return result

        except Exception as e:
            self._on_failure()
            raise

    def _on_success(self) -> None:
        """Handle successful call."""
        self._failure_count = 0

        if self._state == CircuitState.HALF_OPEN:
            self._success_count += 1

            if self._success_count >= self.config.success_threshold:
                self._state = CircuitState.CLOSED
                self._success_count = 0
                logger.info(f"Circuit {self.name} closed after recovery")

    def _on_failure(self) -> None:
        """Handle failed call."""
        self._failure_count += 1
        self._success_count = 0
        self._last_failure_time = datetime.now()

        if self._state == CircuitState.HALF_OPEN:
            self._state = CircuitState.OPEN
            logger.warning(f"Circuit {self.name} reopened after failure")

        elif self._failure_count >= self.config.failure_threshold:
            self._state = CircuitState.OPEN
            logger.warning(
                f"Circuit {self.name} opened after "
                f"{self._failure_count} failures"
            )

    def reset(self) -> None:
        """Manually reset circuit breaker."""
        self._state = CircuitState.CLOSED
        self._failure_count = 0
        self._success_count = 0
        self._last_failure_time = None
        logger.info(f"Circuit {self.name} manually reset")


class CircuitBreakerRegistry:
    """Registry for managing multiple circuit breakers."""

    def __init__(self):
        """Initialize registry."""
        self._breakers: dict[str, CircuitBreaker] = {}

    def get_or_create(
        self,
        name: str,
        config: Optional[CircuitBreakerConfig] = None,
    ) -> CircuitBreaker:
        """Get existing circuit breaker or create new one."""
        if name not in self._breakers:
            self._breakers[name] = CircuitBreaker(name, config)

        return self._breakers[name]

    def get_all_status(self) -> dict[str, dict]:
        """Get status of all circuit breakers."""
        return {
            name: {
                "state": breaker.state.value,
                "failure_count": breaker._failure_count,
                "last_failure": (
                    breaker._last_failure_time.isoformat()
                    if breaker._last_failure_time else None
                ),
            }
            for name, breaker in self._breakers.items()
        }

    def reset_all(self) -> None:
        """Reset all circuit breakers."""
        for breaker in self._breakers.values():
            breaker.reset()


# Global registry
_circuit_registry = CircuitBreakerRegistry()


def get_circuit_breaker(name: str) -> CircuitBreaker:
    """Get a circuit breaker by name."""
    return _circuit_registry.get_or_create(name)


class FallbackHandler:
    """Handles fallback to cached data when live fetch fails."""

    def __init__(self):
        """Initialize fallback handler."""
        self._cache: dict[str, Any] = {}
        self._cache_times: dict[str, datetime] = {}

    def cache_result(self, key: str, data: Any) -> None:
        """Cache a successful result."""
        self._cache[key] = data
        self._cache_times[key] = datetime.now()

    def get_cached(
        self,
        key: str,
        max_age_hours: float = 24,
    ) -> Optional[Any]:
        """
        Get cached data if available and not too old.

        Args:
            key: Cache key.
            max_age_hours: Maximum age in hours.

        Returns:
            Cached data or None.
        """
        if key not in self._cache:
            return None

        cache_time = self._cache_times.get(key)
        if cache_time:
            age = (datetime.now() - cache_time).total_seconds() / 3600
            if age > max_age_hours:
                return None

        return self._cache[key]

    def with_fallback(
        self,
        key: str,
        func: Callable[..., T],
        max_age_hours: float = 24,
        *args,
        **kwargs,
    ) -> tuple[T, bool]:
        """
        Execute function with fallback to cache.

        Args:
            key: Cache key.
            func: Function to execute.
            max_age_hours: Maximum cache age.
            *args: Function arguments.
            **kwargs: Function keyword arguments.

        Returns:
            Tuple of (result, from_cache).
        """
        try:
            result = func(*args, **kwargs)
            self.cache_result(key, result)
            return result, False

        except Exception as e:
            logger.warning(f"Live fetch failed for {key}: {e}")

            cached = self.get_cached(key, max_age_hours)
            if cached is not None:
                logger.info(f"Using cached data for {key}")
                return cached, True

            raise


class GracefulDegradation:
    """
    Manages graceful degradation of predictions
    when data is incomplete or stale.
    """

    def __init__(self):
        """Initialize graceful degradation handler."""
        self._degradation_flags: dict[str, bool] = {}
        self._confidence_modifiers: dict[str, float] = {}

    def set_degraded(
        self,
        component: str,
        confidence_modifier: float = 0.9,
    ) -> None:
        """
        Mark a component as degraded.

        Args:
            component: Component name.
            confidence_modifier: Modifier to apply to predictions.
        """
        self._degradation_flags[component] = True
        self._confidence_modifiers[component] = confidence_modifier
        logger.warning(
            f"Component {component} marked as degraded "
            f"(confidence modifier: {confidence_modifier})"
        )

    def clear_degraded(self, component: str) -> None:
        """Clear degraded status for a component."""
        self._degradation_flags.pop(component, None)
        self._confidence_modifiers.pop(component, None)
        logger.info(f"Component {component} degradation cleared")

    def is_degraded(self, component: str) -> bool:
        """Check if component is degraded."""
        return self._degradation_flags.get(component, False)

    def get_confidence_modifier(self) -> float:
        """
        Get combined confidence modifier for all degraded components.

        Returns:
            Combined modifier (multiply with base confidence).
        """
        if not self._confidence_modifiers:
            return 1.0

        # Multiply all modifiers together
        modifier = 1.0
        for m in self._confidence_modifiers.values():
            modifier *= m

        return modifier

    def can_generate_predictions(self) -> bool:
        """
        Check if predictions can be generated.

        Returns False if critical components are degraded.
        """
        critical_components = ["team_stats", "schedule"]

        for component in critical_components:
            if self._degradation_flags.get(component, False):
                return False

        return True

    def get_status(self) -> dict:
        """Get degradation status."""
        return {
            "degraded_components": list(self._degradation_flags.keys()),
            "confidence_modifier": self.get_confidence_modifier(),
            "can_generate_predictions": self.can_generate_predictions(),
        }


# Global instances
_fallback_handler: Optional[FallbackHandler] = None
_degradation_handler: Optional[GracefulDegradation] = None


def get_fallback_handler() -> FallbackHandler:
    """Get global fallback handler."""
    global _fallback_handler
    if _fallback_handler is None:
        _fallback_handler = FallbackHandler()
    return _fallback_handler


def get_degradation_handler() -> GracefulDegradation:
    """Get global degradation handler."""
    global _degradation_handler
    if _degradation_handler is None:
        _degradation_handler = GracefulDegradation()
    return _degradation_handler


def resilient_fetch(
    fetch_func: Callable[..., T],
    cache_key: str,
    circuit_name: Optional[str] = None,
    max_retries: int = 3,
    cache_hours: float = 24,
    *args,
    **kwargs,
) -> tuple[T, dict]:
    """
    Execute a fetch with full resilience stack.

    Applies: retry -> circuit breaker -> fallback cache.

    Args:
        fetch_func: Function to execute.
        cache_key: Key for caching.
        circuit_name: Circuit breaker name.
        max_retries: Maximum retries.
        cache_hours: Maximum cache age.
        *args: Function arguments.
        **kwargs: Function keyword arguments.

    Returns:
        Tuple of (result, metadata).
    """
    metadata = {
        "from_cache": False,
        "retries": 0,
        "circuit_state": None,
    }

    fallback = get_fallback_handler()
    degradation = get_degradation_handler()

    # Get circuit breaker if specified
    circuit = get_circuit_breaker(circuit_name) if circuit_name else None

    if circuit:
        metadata["circuit_state"] = circuit.state.value

        if circuit.state == CircuitState.OPEN:
            # Try cache first when circuit is open
            cached = fallback.get_cached(cache_key, cache_hours)
            if cached is not None:
                metadata["from_cache"] = True
                degradation.set_degraded(cache_key, 0.95)
                return cached, metadata

    # Try with retries
    last_exception = None
    for attempt in range(max_retries + 1):
        try:
            if circuit:
                result = circuit.call(fetch_func, *args, **kwargs)
            else:
                result = fetch_func(*args, **kwargs)

            fallback.cache_result(cache_key, result)
            degradation.clear_degraded(cache_key)
            return result, metadata

        except CircuitOpenError:
            break

        except Exception as e:
            last_exception = e
            metadata["retries"] = attempt + 1

            if attempt < max_retries:
                delay = 2 ** attempt
                time.sleep(delay)

    # All attempts failed, try cache
    cached = fallback.get_cached(cache_key, cache_hours)
    if cached is not None:
        metadata["from_cache"] = True
        degradation.set_degraded(cache_key, 0.9)
        logger.warning(f"Using cached data for {cache_key} after fetch failure")
        return cached, metadata

    # No cache available
    raise RetryError(
        f"Fetch failed and no cache available for {cache_key}",
        last_exception,
    )
