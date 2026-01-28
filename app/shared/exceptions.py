"""
Custom exceptions for the application.

Centralized exception hierarchy for better error handling and debugging.
"""

from typing import Any, Dict, Optional


class AnalyzeAgentError(Exception):
    """Base exception for all application errors."""

    def __init__(
        self,
        message: str,
        details: Optional[Dict[str, Any]] = None,
        original_error: Optional[Exception] = None,
    ):
        """
        Initialize base exception.

        Args:
            message: Human-readable error message
            details: Additional context (dict)
            original_error: Original exception if wrapped
        """
        super().__init__(message)
        self.message = message
        self.details = details or {}
        self.original_error = original_error

    def __str__(self) -> str:
        """String representation with details."""
        base = self.message
        if self.details:
            base += f" | Details: {self.details}"
        if self.original_error:
            base += f" | Caused by: {type(self.original_error).__name__}"
        return base


class ConfigurationError(AnalyzeAgentError):
    """Configuration or settings error."""

    pass


class ValidationError(AnalyzeAgentError):
    """Data validation error."""

    pass


class APIError(AnalyzeAgentError):
    """External API error."""

    def __init__(
        self,
        message: str,
        status_code: Optional[int] = None,
        api_name: Optional[str] = None,
        details: Optional[Dict[str, Any]] = None,
        original_error: Optional[Exception] = None,
    ):
        """
        Initialize API error.

        Args:
            message: Error message
            status_code: HTTP status code
            api_name: Name of the API (e.g., "DaData", "Casebook")
            details: Additional context
            original_error: Original exception
        """
        super().__init__(message, details, original_error)
        self.status_code = status_code
        self.api_name = api_name

    def __str__(self) -> str:
        """String representation with API info."""
        base = super().__str__()
        if self.api_name:
            base = f"[{self.api_name}] {base}"
        if self.status_code:
            base += f" (HTTP {self.status_code})"
        return base


class SecurityError(AnalyzeAgentError):
    """Security-related error (injection attempts, unauthorized access)."""

    pass


class PIIMaskingError(SecurityError):
    """
    Ошибка маскирования персональных данных (PII).

    Возникает при невозможности безопасно замаскировать PII перед отправкой в LLM.
    При возникновении этой ошибки запрос к LLM ДОЛЖЕН быть заблокирован.
    """

    def __init__(
        self,
        message: str = "PII masking failed",
        original_error: Exception | None = None,
    ):
        super().__init__(message)
        self.original_error = original_error


class DataCollectionError(AnalyzeAgentError):
    """Error during data collection from sources."""

    pass


class AnalysisError(AnalyzeAgentError):
    """Error during analysis/report generation."""

    pass


class StorageError(AnalyzeAgentError):
    """Database/storage error."""

    pass


class CacheError(StorageError):
    """Cache-specific error (Tarantool cache operations)."""

    pass


class LLMError(AnalyzeAgentError):
    """LLM-related error."""

    def __init__(
        self,
        message: str,
        provider: Optional[str] = None,
        model: Optional[str] = None,
        details: Optional[Dict[str, Any]] = None,
        original_error: Optional[Exception] = None,
    ):
        """
        Initialize LLM error.

        Args:
            message: Error message
            provider: LLM provider name (e.g., "OpenRouter", "GigaChat")
            model: Model name (e.g., "claude-3.5-sonnet")
            details: Additional context
            original_error: Original exception
        """
        super().__init__(message, details, original_error)
        self.provider = provider
        self.model = model

    def __str__(self) -> str:
        """String representation with LLM info."""
        base = super().__str__()
        if self.provider:
            base = f"[{self.provider}] {base}"
        if self.model:
            base += f" (model: {self.model})"
        return base


class RateLimitError(APIError):
    """Rate limit exceeded error."""

    def __init__(
        self,
        message: str = "Rate limit exceeded",
        retry_after: Optional[int] = None,
        api_name: Optional[str] = None,
        details: Optional[Dict[str, Any]] = None,
        original_error: Optional[Exception] = None,
    ):
        """
        Initialize rate limit error.

        Args:
            message: Error message
            retry_after: Seconds to wait before retry
            api_name: Name of the API
            details: Additional context
            original_error: Original exception
        """
        super().__init__(
            message,
            status_code=429,
            api_name=api_name,
            details=details,
            original_error=original_error,
        )
        self.retry_after = retry_after


class CircuitBreakerError(AnalyzeAgentError):
    """Circuit breaker is open, service unavailable."""

    def __init__(
        self,
        service_name: str,
        message: Optional[str] = None,
        details: Optional[Dict[str, Any]] = None,
    ):
        """
        Initialize circuit breaker error.

        Args:
            service_name: Name of the service
            message: Error message (auto-generated if not provided)
            details: Additional context
        """
        msg = message or f"Circuit breaker open for service: {service_name}"
        super().__init__(msg, details)
        self.service_name = service_name


__all__ = [
    "AnalyzeAgentError",
    "ConfigurationError",
    "ValidationError",
    "APIError",
    "SecurityError",
    "DataCollectionError",
    "AnalysisError",
    "StorageError",
    "CacheError",
    "LLMError",
    "RateLimitError",
    "CircuitBreakerError",
]
