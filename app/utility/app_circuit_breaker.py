"""
Backward-compatible re-export of circuit breaker utilities.

DEPRECATED: Use app.shared.toolkit.circuit_breaker directly for new code.
This module exists only for backward compatibility.
"""

from app.shared.toolkit.circuit_breaker import (
    AppCircuitBreaker,
    AppCircuitBreakerConfig,
    AppCircuitBreakerMiddleware,
)

__all__ = [
    "AppCircuitBreakerConfig",
    "AppCircuitBreaker",
    "AppCircuitBreakerMiddleware",
]
