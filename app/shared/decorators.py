"""
Error handling decorators and utilities.

Provides reusable decorators for:
- Retry with exponential backoff
- Timeout handling
- Circuit breaker pattern
- Error logging and metrics
"""

import asyncio
import functools
import time
from typing import Any, Callable, Optional, Tuple, Type, TypeVar, Union

from app.utility.logging_client import logger

T = TypeVar("T")
F = TypeVar("F", bound=Callable[..., Any])


class RetryExhausted(Exception):
    """Raised when all retry attempts have been exhausted."""

    def __init__(self, attempts: int, last_error: Exception):
        self.attempts = attempts
        self.last_error = last_error
        super().__init__(f"All {attempts} retry attempts exhausted. Last error: {last_error}")


def retry(
    max_attempts: int = 3,
    delay: float = 1.0,
    backoff: float = 2.0,
    exceptions: Tuple[Type[Exception], ...] = (Exception,),
    on_retry: Optional[Callable[[int, Exception], None]] = None,
) -> Callable[[F], F]:
    """
    Decorator for retrying a function with exponential backoff.

    Args:
        max_attempts: Maximum number of attempts
        delay: Initial delay between attempts (seconds)
        backoff: Multiplier for delay after each attempt
        exceptions: Tuple of exception types to catch and retry
        on_retry: Optional callback called on each retry (attempt_num, exception)

    Returns:
        Decorated function

    Example:
        @retry(max_attempts=3, delay=1.0, backoff=2.0)
        async def fetch_data():
            ...
    """

    def decorator(func: F) -> F:
        @functools.wraps(func)
        async def async_wrapper(*args: Any, **kwargs: Any) -> Any:
            last_error = None
            current_delay = delay

            for attempt in range(1, max_attempts + 1):
                try:
                    return await func(*args, **kwargs)
                except exceptions as e:
                    last_error = e

                    if attempt == max_attempts:
                        raise RetryExhausted(max_attempts, e) from e

                    if on_retry:
                        on_retry(attempt, e)

                    logger.warning(
                        f"Retry {attempt}/{max_attempts} for {func.__name__}: {e}",
                        component="retry",
                    )

                    await asyncio.sleep(current_delay)
                    current_delay *= backoff

            raise RetryExhausted(max_attempts, last_error)

        @functools.wraps(func)
        def sync_wrapper(*args: Any, **kwargs: Any) -> Any:
            last_error = None
            current_delay = delay

            for attempt in range(1, max_attempts + 1):
                try:
                    return func(*args, **kwargs)
                except exceptions as e:
                    last_error = e

                    if attempt == max_attempts:
                        raise RetryExhausted(max_attempts, e) from e

                    if on_retry:
                        on_retry(attempt, e)

                    logger.warning(
                        f"Retry {attempt}/{max_attempts} for {func.__name__}: {e}",
                        component="retry",
                    )

                    time.sleep(current_delay)
                    current_delay *= backoff

            raise RetryExhausted(max_attempts, last_error)

        if asyncio.iscoroutinefunction(func):
            return async_wrapper  # type: ignore
        return sync_wrapper  # type: ignore

    return decorator


def timeout(
    seconds: float,
    error_message: Optional[str] = None,
) -> Callable[[F], F]:
    """
    Decorator for adding timeout to async functions.

    Args:
        seconds: Timeout in seconds
        error_message: Custom error message

    Returns:
        Decorated function

    Example:
        @timeout(30.0)
        async def slow_operation():
            ...
    """

    def decorator(func: F) -> F:
        @functools.wraps(func)
        async def wrapper(*args: Any, **kwargs: Any) -> Any:
            try:
                return await asyncio.wait_for(
                    func(*args, **kwargs),
                    timeout=seconds,
                )
            except asyncio.TimeoutError:
                msg = error_message or f"{func.__name__} timed out after {seconds}s"
                logger.error(msg, component="timeout")
                raise TimeoutError(msg)

        return wrapper  # type: ignore

    return decorator


def log_errors(
    component: str = "unknown",
    reraise: bool = True,
    default: Any = None,
) -> Callable[[F], F]:
    """
    Decorator for logging errors with context.

    Args:
        component: Component name for logging
        reraise: Whether to re-raise the exception
        default: Default value to return if not reraising

    Returns:
        Decorated function

    Example:
        @log_errors(component="data_fetcher", reraise=False, default={})
        async def fetch_data():
            ...
    """

    def decorator(func: F) -> F:
        @functools.wraps(func)
        async def async_wrapper(*args: Any, **kwargs: Any) -> Any:
            try:
                return await func(*args, **kwargs)
            except Exception as e:
                logger.error(
                    f"Error in {func.__name__}: {e}",
                    component=component,
                    exc_info=True,
                )
                if reraise:
                    raise
                return default

        @functools.wraps(func)
        def sync_wrapper(*args: Any, **kwargs: Any) -> Any:
            try:
                return func(*args, **kwargs)
            except Exception as e:
                logger.error(
                    f"Error in {func.__name__}: {e}",
                    component=component,
                    exc_info=True,
                )
                if reraise:
                    raise
                return default

        if asyncio.iscoroutinefunction(func):
            return async_wrapper  # type: ignore
        return sync_wrapper  # type: ignore

    return decorator


def measure_time(
    component: str = "unknown",
    log_args: bool = False,
) -> Callable[[F], F]:
    """
    Decorator for measuring and logging execution time.

    Args:
        component: Component name for logging
        log_args: Whether to log function arguments

    Returns:
        Decorated function

    Example:
        @measure_time(component="data_collector")
        async def collect_data():
            ...
    """

    def decorator(func: F) -> F:
        @functools.wraps(func)
        async def async_wrapper(*args: Any, **kwargs: Any) -> Any:
            start = time.perf_counter()
            try:
                result = await func(*args, **kwargs)
                elapsed = (time.perf_counter() - start) * 1000

                log_data = {
                    "function": func.__name__,
                    "duration_ms": round(elapsed, 2),
                }
                if log_args:
                    log_data["args"] = str(args)[:100]
                    log_data["kwargs"] = str(kwargs)[:100]

                logger.debug(
                    f"{func.__name__} completed in {elapsed:.2f}ms",
                    component=component,
                    **log_data,
                )
                return result

            except Exception as e:
                elapsed = (time.perf_counter() - start) * 1000
                logger.error(
                    f"{func.__name__} failed after {elapsed:.2f}ms: {e}",
                    component=component,
                )
                raise

        @functools.wraps(func)
        def sync_wrapper(*args: Any, **kwargs: Any) -> Any:
            start = time.perf_counter()
            try:
                result = func(*args, **kwargs)
                elapsed = (time.perf_counter() - start) * 1000
                logger.debug(
                    f"{func.__name__} completed in {elapsed:.2f}ms",
                    component=component,
                )
                return result
            except Exception as e:
                elapsed = (time.perf_counter() - start) * 1000
                logger.error(
                    f"{func.__name__} failed after {elapsed:.2f}ms: {e}",
                    component=component,
                )
                raise

        if asyncio.iscoroutinefunction(func):
            return async_wrapper  # type: ignore
        return sync_wrapper  # type: ignore

    return decorator


def graceful_degradation(
    fallback_value: Any = None,
    fallback_func: Optional[Callable[..., Any]] = None,
    exceptions: Tuple[Type[Exception], ...] = (Exception,),
) -> Callable[[F], F]:
    """
    Decorator for graceful degradation on failure.

    Args:
        fallback_value: Value to return on failure
        fallback_func: Function to call on failure (receives original args)
        exceptions: Exception types to catch

    Returns:
        Decorated function

    Example:
        @graceful_degradation(fallback_value={"status": "unavailable"})
        async def get_external_data():
            ...
    """

    def decorator(func: F) -> F:
        @functools.wraps(func)
        async def async_wrapper(*args: Any, **kwargs: Any) -> Any:
            try:
                return await func(*args, **kwargs)
            except exceptions as e:
                logger.warning(
                    f"Graceful degradation for {func.__name__}: {e}",
                    component="degradation",
                )
                if fallback_func:
                    return fallback_func(*args, **kwargs)
                return fallback_value

        @functools.wraps(func)
        def sync_wrapper(*args: Any, **kwargs: Any) -> Any:
            try:
                return func(*args, **kwargs)
            except exceptions as e:
                logger.warning(
                    f"Graceful degradation for {func.__name__}: {e}",
                    component="degradation",
                )
                if fallback_func:
                    return fallback_func(*args, **kwargs)
                return fallback_value

        if asyncio.iscoroutinefunction(func):
            return async_wrapper  # type: ignore
        return sync_wrapper  # type: ignore

    return decorator


# Compose multiple decorators
def compose(*decorators: Callable[[F], F]) -> Callable[[F], F]:
    """
    Compose multiple decorators into one.

    Args:
        *decorators: Decorators to compose (applied right to left)

    Returns:
        Composed decorator

    Example:
        @compose(
            retry(max_attempts=3),
            timeout(30.0),
            log_errors(component="api"),
        )
        async def api_call():
            ...
    """

    def decorator(func: F) -> F:
        for dec in reversed(decorators):
            func = dec(func)
        return func

    return decorator
