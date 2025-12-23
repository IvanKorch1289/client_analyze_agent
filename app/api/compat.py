"""
Compatibility helpers for gradual API hardening.

Rule:
- v1 (mounted under /api/v1) should behave like a "proper" API: HTTP status codes for errors.
- legacy (unversioned) endpoints should keep backward compatible payloads where possible.
"""

from __future__ import annotations

from typing import Any, Dict, Optional

from fastapi import HTTPException, Request


def is_versioned_request(request: Request) -> bool:
    # Mounted sub-app sets root_path (e.g. "/api/v1").
    return bool(request.scope.get("root_path"))


def legacy_error_payload(message: str, *, details: Optional[Any] = None) -> Dict[str, Any]:
    payload: Dict[str, Any] = {"status": "error", "message": message}
    if details is not None:
        payload["details"] = details
    return payload


def fail(
    request: Request,
    *,
    status_code: int,
    message: str,
    details: Optional[Any] = None,
) -> Dict[str, Any]:
    """
    Fail in a version-aware way.
    - v1: raise HTTPException(status_code)
    - legacy: return {status:error, message:...}
    """
    if is_versioned_request(request):
        raise HTTPException(status_code=status_code, detail=message)
    return legacy_error_payload(message, details=details)


def fail_code(
    request: Request,
    *,
    status_code: int,
    code: str,
    message: str,
    details: Optional[Any] = None,
) -> Dict[str, Any]:
    """
    Fail with a stable error code (Wave 2, additive).

    - v1: raises HTTPException with dict `detail` (handled by error_handlers.py)
    - legacy: returns {status:error, message, error_code, details?}
    """
    if is_versioned_request(request):
        raise HTTPException(
            status_code=status_code,
            detail={
                "code": code,
                "message": message,
                "details": details,
            },
        )
    payload = legacy_error_payload(message, details=details)
    payload["error_code"] = code
    return payload
