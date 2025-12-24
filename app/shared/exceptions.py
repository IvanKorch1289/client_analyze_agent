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


class DataCollectionError(AnalyzeAgentError):
    """Error during data collection from sources."""

    pass


class AnalysisError(AnalyzeAgentError):
    """Error during analysis/report generation."""

    pass


class StorageError(AnalyzeAgentError):
    """Database/storage error."""

    pass


__all__ = [
    "AnalyzeAgentError",
    "ConfigurationError",
    "ValidationError",
    "APIError",
    "SecurityError",
    "DataCollectionError",
    "AnalysisError",
    "StorageError",
]
