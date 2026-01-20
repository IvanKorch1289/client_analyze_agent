"""
Shared utilities and modules.

This package provides:
- decorators: Error handling decorators (retry, timeout, etc.)
- types: TypedDict definitions for better type safety
- prometheus_metrics: Prometheus metrics collection
- pii_protection: PII detection and masking
- llm_audit: LLM audit logging
- llm_cache: LLM response caching
"""

from app.shared.decorators import (
    compose,
    graceful_degradation,
    log_errors,
    measure_time,
    retry,
    timeout,
    RetryExhausted,
)

__all__ = [
    # Decorators
    "retry",
    "timeout",
    "log_errors",
    "measure_time",
    "graceful_degradation",
    "compose",
    "RetryExhausted",
]
