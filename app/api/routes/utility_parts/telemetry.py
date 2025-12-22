from __future__ import annotations

from typing import Any, Dict, Optional

from fastapi import Depends, Request

from app.api.compat import fail_code
from app.api.routes.utility import limiter, utility_router
from app.config.constants import RATE_LIMIT_ADMIN_PER_MINUTE
from app.utility.auth import require_admin
from app.utility.telemetry import get_log_store, get_span_exporter


@utility_router.get("/traces")
@limiter.limit(f"{RATE_LIMIT_ADMIN_PER_MINUTE}/minute")
async def get_traces(
    request: Request,
    limit: int = 50,
    since_minutes: Optional[int] = None,
    role: str = Depends(require_admin),
) -> Dict[str, Any]:
    """Get recent traces. Requires admin role."""
    exporter = get_span_exporter()
    if not exporter:
        return fail_code(
            request,
            status_code=503,
            code="telemetry_not_initialized",
            message="Telemetry not initialized",
        )

    spans = exporter.get_spans(limit=limit, since_minutes=since_minutes)
    stats = exporter.get_trace_stats()

    return {
        "status": "success",
        "spans": spans,
        "count": len(spans),
        "stats": stats,
    }


@utility_router.get("/traces/stats")
@limiter.limit(f"{RATE_LIMIT_ADMIN_PER_MINUTE}/minute")
async def get_trace_stats(request: Request, role: str = Depends(require_admin)) -> Dict[str, Any]:
    """Get trace statistics. Requires admin role."""
    exporter = get_span_exporter()
    if not exporter:
        return fail_code(
            request,
            status_code=503,
            code="telemetry_not_initialized",
            message="Telemetry not initialized",
        )

    return {"status": "success", "stats": exporter.get_trace_stats()}


@utility_router.post("/traces/clear")
@limiter.limit(f"{RATE_LIMIT_ADMIN_PER_MINUTE}/minute")
async def clear_traces(request: Request, role: str = Depends(require_admin)) -> Dict[str, Any]:
    """Clear all stored traces. Requires admin role."""
    exporter = get_span_exporter()
    if not exporter:
        return fail_code(
            request,
            status_code=503,
            code="telemetry_not_initialized",
            message="Telemetry not initialized",
        )

    exporter.clear()
    return {"status": "success", "message": "Traces cleared"}


@utility_router.get("/logs")
@limiter.limit(f"{RATE_LIMIT_ADMIN_PER_MINUTE}/minute")
async def get_logs(
    request: Request,
    limit: int = 100,
    since_minutes: Optional[int] = None,
    level: Optional[str] = None,
    role: str = Depends(require_admin),
) -> Dict[str, Any]:
    """Get application logs. Requires admin role."""
    log_store = get_log_store()
    if not log_store:
        return fail_code(
            request,
            status_code=503,
            code="log_store_not_initialized",
            message="Log store not initialized",
        )

    logs = log_store.get_logs(limit=limit, since_minutes=since_minutes, level=level)
    stats = log_store.get_stats()

    return {
        "status": "success",
        "logs": logs,
        "count": len(logs),
        "stats": stats,
    }


@utility_router.get("/logs/stats")
@limiter.limit(f"{RATE_LIMIT_ADMIN_PER_MINUTE}/minute")
async def get_log_stats(request: Request, role: str = Depends(require_admin)) -> Dict[str, Any]:
    """Get log statistics. Requires admin role."""
    log_store = get_log_store()
    if not log_store:
        return fail_code(
            request,
            status_code=503,
            code="log_store_not_initialized",
            message="Log store not initialized",
        )

    return {"status": "success", "stats": log_store.get_stats()}


@utility_router.post("/logs/clear")
@limiter.limit(f"{RATE_LIMIT_ADMIN_PER_MINUTE}/minute")
async def clear_logs(request: Request, role: str = Depends(require_admin)) -> Dict[str, Any]:
    """Clear all stored logs. Requires admin role."""
    log_store = get_log_store()
    if not log_store:
        return fail_code(
            request,
            status_code=503,
            code="log_store_not_initialized",
            message="Log store not initialized",
        )

    log_store.clear()
    return {"status": "success", "message": "Logs cleared"}

