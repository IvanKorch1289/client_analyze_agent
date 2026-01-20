"""
Backward-compatible re-export of logging utilities.

DEPRECATED: Use app.shared.toolkit.logging directly for new code.
This module exists only for backward compatibility.
"""

from app.shared.toolkit.logging import (
    AppLogger,
    LOGS_DIR,
    TimedOperation,
    app_logger,
    generate_request_id,
    get_request_id,
    logger,
    request_id_var,
    set_request_id,
)

__all__ = [
    "AppLogger",
    "TimedOperation",
    "logger",
    "generate_request_id",
    "get_request_id",
    "set_request_id",
    "app_logger",
    "request_id_var",
    "LOGS_DIR",
]
