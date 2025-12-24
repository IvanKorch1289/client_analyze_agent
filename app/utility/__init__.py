"""
app.utility package exports.

DEPRECATED: This module re-exports from app.shared.toolkit for backward compatibility.
Please use app.shared.toolkit directly for new code.

Важно: избегаем импортов, которые тянут Tarantool при инициализации пакета,
чтобы не создавать циклические импорты (app.storage.tarantool <-> app.utility.cache).
"""

from app.shared.toolkit.logging import (
    AppLogger,
    generate_request_id,
    get_request_id,
    logger,
    set_request_id,
)


def __getattr__(name: str):
    # Lazy exports to prevent circular imports at package import time.
    if name == "clean_xml_dict":
        from app.shared.toolkit.helpers import clean_xml_dict as _clean_xml_dict

        return _clean_xml_dict
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


__all__ = [
    "AppLogger",
    "logger",
    "get_request_id",
    "set_request_id",
    "generate_request_id",
    "clean_xml_dict",
]
