"""
Structured logging with JSON output.

Provides centralized logging with context binding and structured output
for better observability in production.
"""

import json
import logging
import sys
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Optional

from app.shared.config import settings


class JSONFormatter(logging.Formatter):
    """
    Custom formatter that outputs logs as JSON.

    Includes timestamp, level, message, and additional context.
    """

    def format(self, record: logging.LogRecord) -> str:
        """
        Format log record as JSON.

        Args:
            record: Log record

        Returns:
            JSON-formatted log string
        """
        log_data = {
            "timestamp": datetime.utcnow().isoformat() + "Z",
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }

        # Add extra fields if present
        if hasattr(record, "extra_data"):
            log_data.update(record.extra_data)

        # Add exception info if present
        if record.exc_info:
            log_data["exception"] = self.formatException(record.exc_info)

        # Add location info
        if settings.DEBUG:
            log_data["location"] = {
                "file": record.pathname,
                "line": record.lineno,
                "function": record.funcName,
            }

        return json.dumps(log_data, ensure_ascii=False)


class StructuredLogger:
    """
    Structured logger with context binding.

    Allows attaching context (user_id, request_id, etc.) that persists
    across multiple log calls.

    Examples:
        >>> logger = StructuredLogger(__name__)
        >>> logger.bind(user_id="123", request_id="req-456")
        >>> logger.info("User logged in", ip_address="192.168.1.1")
        {
            "timestamp": "2025-12-23T10:30:00Z",
            "level": "INFO",
            "logger": "app.module",
            "message": "User logged in",
            "user_id": "123",
            "request_id": "req-456",
            "ip_address": "192.168.1.1"
        }
    """

    def __init__(self, name: str):
        """
        Initialize structured logger.

        Args:
            name: Logger name (usually __name__)
        """
        self.logger = logging.getLogger(name)
        self.context: Dict[str, Any] = {}

    def bind(self, **kwargs: Any) -> "StructuredLogger":
        """
        Bind context that persists across log calls.

        Args:
            **kwargs: Context key-value pairs

        Returns:
            Self for chaining

        Examples:
            >>> logger.bind(user_id="123", request_id="req-456")
            >>> logger.info("Action performed")
        """
        self.context.update(kwargs)
        return self

    def unbind(self, *keys: str) -> "StructuredLogger":
        """
        Remove context keys.

        Args:
            *keys: Keys to remove

        Returns:
            Self for chaining
        """
        for key in keys:
            self.context.pop(key, None)
        return self

    def _log(
        self,
        level: int,
        message: str,
        exc: Optional[Exception] = None,
        **kwargs: Any,
    ) -> None:
        """
        Internal log method with context merging.

        Args:
            level: Log level (logging.INFO, etc.)
            message: Log message
            exc: Exception to include
            **kwargs: Additional context for this log call only
        """
        extra_data = {**self.context, **kwargs}

        # Create log record with extra data
        extra = {"extra_data": extra_data}

        if exc:
            self.logger.log(level, message, exc_info=exc, extra=extra)
        else:
            self.logger.log(level, message, extra=extra)

    def debug(self, message: str, exc: Optional[Exception] = None, **kwargs: Any) -> None:
        """Log debug message."""
        self._log(logging.DEBUG, message, exc, **kwargs)

    def info(self, message: str, exc: Optional[Exception] = None, **kwargs: Any) -> None:
        """Log info message."""
        self._log(logging.INFO, message, exc, **kwargs)

    def warning(self, message: str, exc: Optional[Exception] = None, **kwargs: Any) -> None:
        """Log warning message."""
        self._log(logging.WARNING, message, exc, **kwargs)

    def error(self, message: str, exc: Optional[Exception] = None, **kwargs: Any) -> None:
        """Log error message."""
        self._log(logging.ERROR, message, exc, **kwargs)

    def critical(
        self, message: str, exc: Optional[Exception] = None, **kwargs: Any
    ) -> None:
        """Log critical message."""
        self._log(logging.CRITICAL, message, exc, **kwargs)

    def log_action(
        self,
        action: str,
        status: str = "success",
        **kwargs: Any,
    ) -> None:
        """
        Log an action with standardized format.

        Args:
            action: Action name (e.g., "api_call", "user_login")
            status: Action status (success, failed, started)
            **kwargs: Additional context

        Examples:
            >>> logger.log_action("dadata_api_call", status="success", duration_ms=234)
        """
        self.info(
            f"Action: {action}",
            action=action,
            status=status,
            **kwargs,
        )


def setup_logging(
    level: Optional[str] = None,
    log_file: Optional[Path] = None,
    json_format: bool = True,
) -> None:
    """
    Setup application logging.

    Configures root logger with console and optional file output.

    Args:
        level: Log level (DEBUG, INFO, WARNING, ERROR, CRITICAL)
        log_file: Path to log file (optional)
        json_format: Use JSON formatter (default: True)

    Examples:
        >>> setup_logging(level="INFO", log_file=Path("app.log"))
    """
    level = level or settings.LOG_LEVEL
    log_level = getattr(logging, level.upper(), logging.INFO)

    # Configure root logger
    root_logger = logging.getLogger()
    root_logger.setLevel(log_level)

    # Remove existing handlers
    root_logger.handlers.clear()

    # Console handler
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(log_level)

    if json_format:
        console_handler.setFormatter(JSONFormatter())
    else:
        console_handler.setFormatter(
            logging.Formatter(
                "%(asctime)s - %(name)s - %(levelname)s - %(message)s",
                datefmt="%Y-%m-%d %H:%M:%S",
            )
        )

    root_logger.addHandler(console_handler)

    # File handler (if specified)
    if log_file:
        log_file.parent.mkdir(parents=True, exist_ok=True)
        file_handler = logging.FileHandler(log_file, encoding="utf-8")
        file_handler.setLevel(log_level)
        file_handler.setFormatter(JSONFormatter())
        root_logger.addHandler(file_handler)

    # Log startup
    logger = StructuredLogger(__name__)
    logger.info(
        "Logging initialized",
        level=level,
        json_format=json_format,
        log_file=str(log_file) if log_file else None,
    )


def get_logger(name: str) -> StructuredLogger:
    """
    Get a structured logger instance.

    Args:
        name: Logger name (usually __name__)

    Returns:
        StructuredLogger instance

    Examples:
        >>> logger = get_logger(__name__)
        >>> logger.info("Application started")
    """
    return StructuredLogger(name)


__all__ = [
    "StructuredLogger",
    "setup_logging",
    "get_logger",
    "JSONFormatter",
]

