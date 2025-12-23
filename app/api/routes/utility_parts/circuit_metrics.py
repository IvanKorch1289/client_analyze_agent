from __future__ import annotations

from typing import Any, Dict, Optional

from fastapi import Depends, Request

from app.api.compat import fail_code, is_versioned_request
from app.api.routes.utility import limiter, utility_router
from app.config.constants import RATE_LIMIT_ADMIN_PER_MINUTE
from app.schemas.api import AppMetricsResponse
from app.services.http_client import AsyncHttpClient
from app.utility.app_metrics import app_metrics
from app.utility.auth import require_admin


@utility_router.get("/app-circuit-breaker")
async def app_circuit_breaker_status(request: Request) -> Dict[str, Any]:
    """
    Статус circuit breaker на уровне приложения (web).
    """
    breaker = getattr(request.app.state, "app_circuit_breaker", None)
    if breaker is None:
        return fail_code(
            request,
            status_code=503,
            code="app_circuit_breaker_not_configured",
            message="app circuit breaker is not configured",
        )
    return {"status": "success", "breaker": breaker.status()}


@utility_router.post("/app-circuit-breaker/reset")
@limiter.limit(f"{RATE_LIMIT_ADMIN_PER_MINUTE}/minute")
async def app_circuit_breaker_reset(request: Request, role: str = Depends(require_admin)) -> Dict[str, Any]:
    """Сбросить app-level circuit breaker. Requires admin role."""
    breaker = getattr(request.app.state, "app_circuit_breaker", None)
    if breaker is None:
        return fail_code(
            request,
            status_code=503,
            code="app_circuit_breaker_not_configured",
            message="app circuit breaker is not configured",
        )
    breaker.reset()
    return {"status": "success", "message": "app circuit breaker reset"}


@utility_router.get("/circuit-breakers")
async def get_circuit_breakers(request: Request, service: Optional[str] = None) -> Dict[str, Any]:
    try:
        http_client = await AsyncHttpClient.get_instance()
        status = http_client.get_circuit_breaker_status(service)
        return {"status": "success", "circuit_breakers": status}
    except Exception as e:
        if is_versioned_request(request):
            raise
        return {"status": "error", "message": str(e)}


@utility_router.post("/circuit-breakers/{service}/reset")
@limiter.limit(f"{RATE_LIMIT_ADMIN_PER_MINUTE}/minute")
async def reset_circuit_breaker(request: Request, service: str, role: str = Depends(require_admin)) -> Dict[str, Any]:
    """Reset circuit breaker for a service. Requires admin role."""
    try:
        http_client = await AsyncHttpClient.get_instance()
        success = http_client.reset_circuit_breaker(service)
        if success:
            return {
                "status": "success",
                "message": f"Circuit breaker for {service} reset",
            }
        return {"status": "error", "message": f"No circuit breaker found for {service}"}
    except Exception as e:
        if is_versioned_request(request):
            raise
        return {"status": "error", "message": str(e)}


@utility_router.get("/metrics")
async def get_metrics(request: Request, service: Optional[str] = None) -> Dict[str, Any]:
    try:
        http_client = await AsyncHttpClient.get_instance()
        metrics = http_client.get_metrics(service)
        return {"status": "success", "metrics": metrics}
    except Exception as e:
        if is_versioned_request(request):
            raise
        return {"status": "error", "message": str(e)}


@utility_router.post("/metrics/reset")
@limiter.limit(f"{RATE_LIMIT_ADMIN_PER_MINUTE}/minute")
async def reset_metrics(
    request: Request, service: Optional[str] = None, role: str = Depends(require_admin)
) -> Dict[str, Any]:
    """Reset HTTP metrics. Requires admin role."""
    try:
        http_client = await AsyncHttpClient.get_instance()
        http_client.reset_metrics(service)
        msg = f"Metrics reset for {service}" if service else "All metrics reset"
        return {"status": "success", "message": msg}
    except Exception as e:
        if is_versioned_request(request):
            raise
        return {"status": "error", "message": str(e)}


@utility_router.get("/app-metrics")
@limiter.limit(f"{RATE_LIMIT_ADMIN_PER_MINUTE}/minute")
async def get_app_metrics(request: Request, role: str = Depends(require_admin)) -> AppMetricsResponse:
    """Get in-process application request metrics. Requires admin role."""
    return {"status": "success", "metrics": app_metrics.snapshot()}


@utility_router.post("/app-metrics/reset")
@limiter.limit(f"{RATE_LIMIT_ADMIN_PER_MINUTE}/minute")
async def reset_app_metrics(request: Request, role: str = Depends(require_admin)) -> Dict[str, Any]:
    """Reset in-process application request metrics. Requires admin role."""
    app_metrics.reset()
    return {"status": "success", "message": "App metrics reset"}
