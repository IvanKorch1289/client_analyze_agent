"""
Backward-compatible re-export of helper utilities.

DEPRECATED: Use app.shared.toolkit.helpers directly for new code.
This module exists only for backward compatibility.
"""

from app.shared.toolkit.helpers import (
    chunk_text,
    clean_xml_dict,
    format_inn,
    get_client_ip,
    retry_async,
    safe_dict_get,
)

__all__ = [
    "clean_xml_dict",
    "get_client_ip",
    "safe_dict_get",
    "chunk_text",
    "retry_async",
    "format_inn",
]
