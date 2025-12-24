"""
Centralized API error handling (best practices).

Goals:
- consistent error response shape
- include request_id for correlation
- avoid leaking internal exception details on 500
"""

from __future__ import annotations

from typing import Any, Dict, Optional

from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from slowapi.errors import RateLimitExceeded

from app.utility.logging_client import get_request_id, logger, set_request_id


def _ensure_request_id() -> str:
    rid = get_request_id()
    if rid:
        return rid
    return set_request_id()


def _error_payload(
    *,
    code: str,
    message: str,
    request_id: str,
    details: Optional[Any] = None,
) -> Dict[str, Any]:
    # Keep it stable and explicit (future-proof for clients).
    payload: Dict[str, Any] = {
        "status": "error",
        "error": {
            "code": code,
            "message": message,
            "request_id": request_id,
        },
    }
    if details is not None:
        payload["error"]["details"] = details
    return payload


def install_error_handlers(app: FastAPI) -> None:
    """
    Attach consistent error handlers to a FastAPI app (root or sub-app).
    """

    @app.exception_handler(HTTPException)
    async def http_exception_handler(request: Request, exc: HTTPException) -> JSONResponse:
        rid = _ensure_request_id()
        # FastAPI uses exc.detail for client-facing messages.
        # Allow dict-form details to carry a stable error code (Wave 2, additive).
        code = "http_error"
        details: Optional[Any] = None
        if isinstance(exc.detail, dict):
            code = str(exc.detail.get("code") or code)
            message = str(exc.detail.get("message") or "Request failed")
            details = exc.detail.get("details")
        else:
            message = exc.detail if isinstance(exc.detail, str) else "Request failed"
        return JSONResponse(
            status_code=exc.status_code,
            content=_error_payload(
                code=code,
                message=message,
                request_id=rid,
                details=(
                    details
                    if details is not None
                    else ({"detail": exc.detail} if not isinstance(exc.detail, str) else None)
                ),
            ),
            headers={"X-Request-ID": rid},
        )

    @app.exception_handler(RequestValidationError)
    async def validation_exception_handler(request: Request, exc: RequestValidationError) -> JSONResponse:
        rid = _ensure_request_id()
        return JSONResponse(
            status_code=422,
            content=_error_payload(
                code="validation_error",
                message="Validation error",
                request_id=rid,
                details=exc.errors(),
            ),
            headers={"X-Request-ID": rid},
        )

    @app.exception_handler(RateLimitExceeded)
    async def rate_limit_exception_handler(request: Request, exc: RateLimitExceeded) -> JSONResponse:
        rid = _ensure_request_id()
        # Don't expose internal limiter state; keep a stable message.
        return JSONResponse(
            status_code=429,
            content=_error_payload(
                code="rate_limited",
                message="Too many requests",
                request_id=rid,
            ),
            headers={"X-Request-ID": rid},
        )

    @app.exception_handler(Exception)
    async def unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
        rid = _ensure_request_id()
        logger.log_exception(
            exc,
            component="http",
            context={
                "path": str(request.url.path),
                "method": request.method,
            },
        )
        return JSONResponse(
            status_code=500,
            content=_error_payload(
                code="internal_error",
                message="Internal server error",
                request_id=rid,
            ),
            headers={"X-Request-ID": rid},
        )
