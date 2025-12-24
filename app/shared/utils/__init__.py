"""
Common utilities used across the application.

DEPRECATED: This module re-exports from app.shared.toolkit for backward compatibility.
Please use app.shared.toolkit directly for new code.
"""

from app.shared.toolkit.formatters import (
    format_csv,
    format_json,
    format_ts,
    truncate,
)
from app.shared.toolkit.helpers import chunk_text, retry_async, safe_dict_get
from app.shared.toolkit.parsers import parse_csv, parse_json

__all__ = [
    # Formatters
    "format_json",
    "format_csv",
    "format_ts",
    "truncate",
    # Helpers
    "chunk_text",
    "retry_async",
    "safe_dict_get",
    # Parsers
    "parse_json",
    "parse_csv",
]
