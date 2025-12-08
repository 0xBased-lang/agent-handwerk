"""Retry utilities with exponential backoff.

Provides resilient execution patterns for transient failures:
- Exponential backoff with jitter
- Circuit breaker pattern
- Configurable retry policies

Usage:
    from phone_agent.core.retry import retry, RetryConfig, CircuitBreaker

    @retry(max_attempts=3, base_delay=1.0)
    async def call_external_api():
        ...

    # Or with circuit breaker
    breaker = CircuitBreaker("sms_service", failure_threshold=5)
    async with breaker:
        await send_sms(...)
"""
from __future__ import annotations

import asyncio
import functools
import logging
import random
import time
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from typing import Any, Awaitable, Callable, Sequence, TypeVar

logger = logging.getLogger(__name__)

T = TypeVar("T")


class RetryExhausted(Exception):
    """Raised when all retry attempts are exhausted."""

    def __init__(self, message: str, last_error: Exception | None = None, attempts: int = 0):
        super().__init__(message)
        self.last_error = last_error
        self.attempts = attempts


class CircuitOpen(Exception):
    """Raised when circuit breaker is open."""

    def __init__(self, name: str, reset_at: datetime):
        super().__init__(f"Circuit breaker '{name}' is open, resets at {reset_at.isoformat()}")
        self.name = name
        self.reset_at = reset_at


class CircuitState(str, Enum):
    """Circuit breaker states."""

    CLOSED = "closed"  # Normal operation
    OPEN = "open"  # Failing, reject requests
    HALF_OPEN = "half_open"  # Testing if service recovered


@dataclass
class RetryConfig:
    """Configuration for retry behavior."""

    max_attempts: int = 3
    base_delay: float = 1.0  # seconds
    max_delay: float = 60.0  # seconds
    exponential_base: float = 2.0
    jitter: float = 0.1  # 10% jitter
    retryable_exceptions: tuple[type[Exception], ...] = (Exception,)
    non_retryable_exceptions: tuple[type[Exception], ...] = ()

    def calculate_delay(self, attempt: int) -> float:
        """Calculate delay for given attempt with exponential backoff and jitter.

        Args:
            attempt: Current attempt number (1-based)

        Returns:
            Delay in seconds
        """
        delay = min(
            self.base_delay * (self.exponential_base ** (attempt - 1)),
            self.max_delay,
        )

        # Add jitter (±jitter%)
        jitter_range = delay * self.jitter
        delay += random.uniform(-jitter_range, jitter_range)

        return max(0.1, delay)  # Minimum 100ms

    def should_retry(self, exception: Exception, attempt: int) -> bool:
        """Check if exception should trigger retry.

        Args:
            exception: The exception that occurred
            attempt: Current attempt number

        Returns:
            True if should retry
        """
        if attempt >= self.max_attempts:
            return False

        # Check non-retryable first
        if isinstance(exception, self.non_retryable_exceptions):
            return False

        # Check retryable
        return isinstance(exception, self.retryable_exceptions)


# Default configs for common scenarios
DEFAULT_RETRY_CONFIG = RetryConfig()

API_RETRY_CONFIG = RetryConfig(
    max_attempts=3,
    base_delay=1.0,
    max_delay=30.0,
    retryable_exceptions=(ConnectionError, TimeoutError, OSError),
)

AI_MODEL_RETRY_CONFIG = RetryConfig(
    max_attempts=2,
    base_delay=0.5,
    max_delay=5.0,
    retryable_exceptions=(RuntimeError, OSError),
)

DATABASE_RETRY_CONFIG = RetryConfig(
    max_attempts=3,
    base_delay=0.2,
    max_delay=2.0,
    retryable_exceptions=(Exception,),  # SQLAlchemy can raise various exceptions
)


def retry(
    max_attempts: int = 3,
    base_delay: float = 1.0,
    max_delay: float = 60.0,
    exponential_base: float = 2.0,
    jitter: float = 0.1,
    retryable_exceptions: tuple[type[Exception], ...] = (Exception,),
    non_retryable_exceptions: tuple[type[Exception], ...] = (),
    on_retry: Callable[[Exception, int, float], None] | None = None,
) -> Callable[[Callable[..., Awaitable[T]]], Callable[..., Awaitable[T]]]:
    """Decorator for async functions with exponential backoff retry.

    Args:
        max_attempts: Maximum number of attempts
        base_delay: Initial delay in seconds
        max_delay: Maximum delay in seconds
        exponential_base: Base for exponential backoff
        jitter: Jitter factor (0.1 = ±10%)
        retryable_exceptions: Exception types to retry on
        non_retryable_exceptions: Exception types to never retry
        on_retry: Optional callback(exception, attempt, delay) on each retry

    Usage:
        @retry(max_attempts=3, base_delay=1.0)
        async def call_api():
            ...
    """
    config = RetryConfig(
        max_attempts=max_attempts,
        base_delay=base_delay,
        max_delay=max_delay,
        exponential_base=exponential_base,
        jitter=jitter,
        retryable_exceptions=retryable_exceptions,
        non_retryable_exceptions=non_retryable_exceptions,
    )

    def decorator(func: Callable[..., Awaitable[T]]) -> Callable[..., Awaitable[T]]:
        @functools.wraps(func)
        async def wrapper(*args: Any, **kwargs: Any) -> T:
            last_exception: Exception | None = None

            for attempt in range(1, config.max_attempts + 1):
                try:
                    return await func(*args, **kwargs)

                except Exception as e:
                    last_exception = e

                    if not config.should_retry(e, attempt):
                        raise

                    delay = config.calculate_delay(attempt)

                    logger.warning(
                        f"Retry {attempt}/{config.max_attempts} for {func.__name__}: "
                        f"{type(e).__name__}: {e}. Waiting {delay:.2f}s"
                    )

                    if on_retry:
                        on_retry(e, attempt, delay)

                    await asyncio.sleep(delay)

            raise RetryExhausted(
                f"All {config.max_attempts} attempts exhausted for {func.__name__}",
                last_error=last_exception,
                attempts=config.max_attempts,
            )

        return wrapper

    return decorator


async def retry_async(
    func: Callable[..., Awaitable[T]],
    *args: Any,
    config: RetryConfig | None = None,
    on_retry: Callable[[Exception, int, float], None] | None = None,
    **kwargs: Any,
) -> T:
    """Execute async function with retry.

    Args:
        func: Async function to execute
        *args: Positional arguments for func
        config: Retry configuration
        on_retry: Optional callback on each retry
        **kwargs: Keyword arguments for func

    Returns:
        Result of func

    Raises:
        RetryExhausted: If all attempts fail
    """
    config = config or DEFAULT_RETRY_CONFIG
    last_exception: Exception | None = None

    for attempt in range(1, config.max_attempts + 1):
        try:
            return await func(*args, **kwargs)

        except Exception as e:
            last_exception = e

            if not config.should_retry(e, attempt):
                raise

            delay = config.calculate_delay(attempt)

            logger.warning(
                f"Retry {attempt}/{config.max_attempts} for {func.__name__}: "
                f"{type(e).__name__}: {e}. Waiting {delay:.2f}s"
            )

            if on_retry:
                on_retry(e, attempt, delay)

            await asyncio.sleep(delay)

    raise RetryExhausted(
        f"All {config.max_attempts} attempts exhausted for {func.__name__}",
        last_error=last_exception,
        attempts=config.max_attempts,
    )


@dataclass
class CircuitBreaker:
    """Circuit breaker for protecting against cascading failures.

    States:
    - CLOSED: Normal operation, requests pass through
    - OPEN: Service failing, requests rejected immediately
    - HALF_OPEN: Testing recovery, limited requests allowed

    Usage:
        breaker = CircuitBreaker("sms_service", failure_threshold=5)

        async with breaker:
            await send_sms(...)  # Protected by circuit breaker

        # Or manually
        if breaker.allow_request():
            try:
                result = await send_sms(...)
                breaker.record_success()
            except Exception as e:
                breaker.record_failure()
                raise
    """

    name: str
    failure_threshold: int = 5  # Failures before opening
    success_threshold: int = 2  # Successes in half-open before closing
    reset_timeout: float = 60.0  # Seconds before half-open
    half_open_max_calls: int = 3  # Max calls in half-open state

    # Internal state
    _state: CircuitState = field(default=CircuitState.CLOSED, init=False)
    _failure_count: int = field(default=0, init=False)
    _success_count: int = field(default=0, init=False)
    _last_failure_time: datetime | None = field(default=None, init=False)
    _half_open_calls: int = field(default=0, init=False)

    @property
    def state(self) -> CircuitState:
        """Get current circuit state."""
        self._check_state_transition()
        return self._state

    def _check_state_transition(self) -> None:
        """Check and perform state transitions based on time."""
        if self._state == CircuitState.OPEN and self._last_failure_time:
            elapsed = (datetime.now() - self._last_failure_time).total_seconds()
            if elapsed >= self.reset_timeout:
                self._transition_to_half_open()

    def _transition_to_open(self) -> None:
        """Transition to open state."""
        logger.warning(f"Circuit breaker '{self.name}' OPEN after {self._failure_count} failures")
        self._state = CircuitState.OPEN
        self._last_failure_time = datetime.now()

    def _transition_to_half_open(self) -> None:
        """Transition to half-open state."""
        logger.info(f"Circuit breaker '{self.name}' HALF-OPEN, testing recovery")
        self._state = CircuitState.HALF_OPEN
        self._half_open_calls = 0
        self._success_count = 0

    def _transition_to_closed(self) -> None:
        """Transition to closed state."""
        logger.info(f"Circuit breaker '{self.name}' CLOSED, service recovered")
        self._state = CircuitState.CLOSED
        self._failure_count = 0
        self._success_count = 0
        self._half_open_calls = 0
        self._last_failure_time = None

    def allow_request(self) -> bool:
        """Check if a request should be allowed.

        Returns:
            True if request is allowed
        """
        self._check_state_transition()

        if self._state == CircuitState.CLOSED:
            return True

        if self._state == CircuitState.OPEN:
            return False

        # Half-open: allow limited requests
        if self._half_open_calls < self.half_open_max_calls:
            self._half_open_calls += 1
            return True

        return False

    def record_success(self) -> None:
        """Record a successful request."""
        if self._state == CircuitState.HALF_OPEN:
            self._success_count += 1
            if self._success_count >= self.success_threshold:
                self._transition_to_closed()
        elif self._state == CircuitState.CLOSED:
            # Reset failure count on success
            self._failure_count = max(0, self._failure_count - 1)

    def record_failure(self) -> None:
        """Record a failed request."""
        self._failure_count += 1
        self._last_failure_time = datetime.now()

        if self._state == CircuitState.HALF_OPEN:
            # Any failure in half-open returns to open
            self._transition_to_open()
        elif self._state == CircuitState.CLOSED:
            if self._failure_count >= self.failure_threshold:
                self._transition_to_open()

    @property
    def reset_at(self) -> datetime | None:
        """Get time when circuit will transition to half-open."""
        if self._state == CircuitState.OPEN and self._last_failure_time:
            return self._last_failure_time + timedelta(seconds=self.reset_timeout)
        return None

    async def __aenter__(self) -> "CircuitBreaker":
        """Async context manager entry."""
        if not self.allow_request():
            raise CircuitOpen(self.name, self.reset_at or datetime.now())
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: Any,
    ) -> bool:
        """Async context manager exit."""
        if exc_val is None:
            self.record_success()
        else:
            self.record_failure()
        return False  # Don't suppress exception


# Global circuit breakers for common services
_circuit_breakers: dict[str, CircuitBreaker] = {}


def get_circuit_breaker(
    name: str,
    failure_threshold: int = 5,
    reset_timeout: float = 60.0,
) -> CircuitBreaker:
    """Get or create a circuit breaker by name.

    Args:
        name: Unique name for the circuit breaker
        failure_threshold: Failures before opening
        reset_timeout: Seconds before recovery attempt

    Returns:
        Circuit breaker instance
    """
    if name not in _circuit_breakers:
        _circuit_breakers[name] = CircuitBreaker(
            name=name,
            failure_threshold=failure_threshold,
            reset_timeout=reset_timeout,
        )
    return _circuit_breakers[name]


def get_circuit_breaker_status() -> dict[str, dict[str, Any]]:
    """Get status of all circuit breakers.

    Returns:
        Dictionary of circuit breaker statuses
    """
    return {
        name: {
            "state": breaker.state.value,
            "failure_count": breaker._failure_count,
            "reset_at": breaker.reset_at.isoformat() if breaker.reset_at else None,
        }
        for name, breaker in _circuit_breakers.items()
    }


def reset_circuit_breaker(name: str) -> bool:
    """Manually reset a circuit breaker.

    Args:
        name: Circuit breaker name

    Returns:
        True if reset, False if not found
    """
    if name in _circuit_breakers:
        _circuit_breakers[name]._transition_to_closed()
        return True
    return False
