"""
app.utility package exports.

Важно: избегаем импортов, которые тянут Tarantool при инициализации пакета,
чтобы не создавать циклические импорты (app.storage.tarantool <-> app.utility.cache).
"""

from app.utility.logging_client import (
    AppLogger,
    generate_request_id,
    get_request_id,
    logger,
    set_request_id,
)


def __getattr__(name: str):
    # Lazy exports to prevent circular imports at package import time.
    if name == "cache_response":
        from app.utility.cache import cache_response as _cache_response

        return _cache_response
    if name == "clean_xml_dict":
        from app.utility.helpers import clean_xml_dict as _clean_xml_dict

        return _clean_xml_dict
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")

__all__ = [
    "AppLogger",
    "logger",
    "get_request_id",
    "set_request_id",
    "generate_request_id",
    "cache_response",
    "clean_xml_dict",
]
