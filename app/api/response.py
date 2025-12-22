"""
API response helpers (Wave 2).

Goal:
- introduce a consistent success envelope (`status`, `data`, `message`)
- keep backward compatibility by allowing legacy top-level fields
"""

from __future__ import annotations

from typing import Any, Dict, Optional


def ok(*, data: Any = None, message: Optional[str] = None, **legacy_fields: Any) -> Dict[str, Any]:
    """
    Success response.

    `legacy_fields` allows gradual adoption without breaking existing clients:
    we keep existing top-level keys (e.g. `metrics`, `reports`, etc.) and also
    provide normalized `data`.
    """
    payload: Dict[str, Any] = {"status": "success", **legacy_fields}
    if message is not None:
        payload["message"] = message
    payload["data"] = data
    return payload

