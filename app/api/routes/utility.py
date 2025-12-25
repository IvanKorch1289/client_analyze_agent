"""
Utility API routes.

Consolidated module containing all utility endpoints grouped by functionality:
- Health & Status
- Authentication
- Cache & Tarantool
- Circuit Breakers & Metrics
- Configuration
- Services (Perplexity, Tavily, OpenRouter, Email)
- Reports (PDF generation)
- Telemetry (Traces, Logs)
- Queue (RabbitMQ monitoring)
- AsyncAPI
"""

from __future__ import annotations

import json
import os
import time
from typing import Any, Dict, List, Optional
from urllib.parse import urlparse

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import FileResponse, HTMLResponse
from slowapi import Limiter

from app.api.compat import fail_code, is_versioned_request
from app.api.response import ok
from app.config.constants import RATE_LIMIT_ADMIN_PER_MINUTE
from app.config.reload import get_reload_state, reload_settings
from app.config.settings import settings
from app.schemas import (
    AppMetricsResponse,
    HealthComponents,
    HealthComponentPerplexity,
    HealthComponentTavily,
    HealthResponse,
    HealthServiceInfo,
    PDFReportRequest,
)
from app.services.email_client import EmailClient
from app.services.http_client import AsyncHttpClient
from app.services.openrouter_client import get_openrouter_client
from app.services.perplexity_client import PerplexityClient
from app.services.tavily_client import TavilyClient
from app.storage.tarantool import TarantoolClient
from app.utility.app_metrics import app_metrics
from app.utility.auth import Role, get_current_role, require_admin
from app.utility.helpers import get_client_ip
from app.utility.logging_client import logger
from app.utility.pdf_generator import save_pdf_report
from app.utility.telemetry import get_log_store, get_span_exporter

utility_router = APIRouter(
    prefix="/utility",
    tags=["Утилиты"],
    responses={404: {"description": "Не найдено"}},
)

limiter = Limiter(key_func=get_client_ip)

__all__ = ["utility_router"]


# =============================================================================
# HEALTH & STATUS ENDPOINTS
# =============================================================================


@utility_router.get("/health")
async def health_check(deep: bool = False) -> HealthResponse:
    perplexity = PerplexityClient.get_instance()
    tavily = TavilyClient.get_instance()
    openrouter = get_openrouter_client()
    issues: List[str] = []

    try:
        http_client = await AsyncHttpClient.get_instance()
        http_status = "healthy"

        cb_status = http_client.get_circuit_breaker_status()
        open_breakers = [name for name, cb in cb_status.items() if isinstance(cb, dict) and cb.get("state") == "open"]
        if open_breakers:
            issues.append(f"Circuit breakers open: {', '.join(open_breakers)}")
    except Exception as e:
        http_status = f"unhealthy: {str(e)}"
        issues.append(f"HTTP client: {str(e)}")

    try:
        tarantool_status = "healthy"
    except Exception as e:
        tarantool_status = f"unhealthy: {str(e)}"
        issues.append(f"Tarantool: {str(e)}")

    openrouter_configured = bool(openrouter.api_key)

    if deep:
        perplexity_h = await perplexity.healthcheck()
        tavily_h = await tavily.healthcheck()
        openrouter_h = await openrouter.check_status()

        perplexity_status = perplexity_h.get("status", "unknown")
        tavily_status = tavily_h.get("status", "unknown")
        openrouter_status = "ready" if openrouter_h.get("available") else "error"

        if not perplexity_h.get("available"):
            issues.append(f"Perplexity unavailable: {perplexity_h.get('error')}")
        if not tavily_h.get("available"):
            issues.append(f"Tavily unavailable: {tavily_h.get('error')}")
        if not openrouter_h.get("available"):
            issues.append(f"OpenRouter unavailable: {openrouter_h.get('error')}")
    else:
        perplexity_status = "ready" if perplexity.is_configured() else "not_configured"
        tavily_status = "ready" if tavily.is_configured() else "not_configured"
        openrouter_status = "ready" if openrouter_configured else "not_configured"

        if not perplexity.is_configured():
            issues.append("Perplexity API not configured")
        if not tavily.is_configured():
            issues.append("Tavily API not configured")
        if not openrouter_configured:
            issues.append("OpenRouter API not configured")

    overall_status = "healthy" if not issues else "degraded"

    return HealthResponse(
        status=overall_status,
        issues=issues if issues else None,
        components=HealthComponents(
            http_client=http_status,
            tarantool=tarantool_status,
            openrouter=HealthServiceInfo(
                configured=openrouter_configured,
                status=openrouter_status,
                model=openrouter.model,
            ),
            perplexity=HealthComponentPerplexity(
                configured=perplexity.is_configured(),
                status=perplexity_status,
            ),
            tavily=HealthComponentTavily(
                configured=tavily.is_configured(),
                status=tavily_status,
            ),
        ),
    )


# =============================================================================
# AUTHENTICATION ENDPOINTS
# =============================================================================


@utility_router.get("/auth/role")
async def get_auth_role(role: str = Depends(get_current_role)) -> Dict[str, Any]:
    """
    Get current authentication role.
    """
    return {
        "role": role,
        "is_admin": role == Role.ADMIN,
    }


# =============================================================================
# CACHE & TARANTOOL ENDPOINTS
# =============================================================================


@utility_router.get("/validate_cache")
@limiter.limit(f"{RATE_LIMIT_ADMIN_PER_MINUTE}/minute")
async def validate_cache(request: Request, confirm: bool, role: str = Depends(require_admin)):
    """
    Invalidate all cache keys. Requires admin role.
    """
    client = await TarantoolClient.get_instance()
    await client.invalidate_all_keys(confirm)
    return {
        "status": "success",
        "message": "Кэш инвалидирован" if confirm else "Операция отменена",
    }


@utility_router.get("/cache/metrics")
async def get_cache_metrics(request: Request) -> Dict[str, Any]:
    try:
        tarantool = await TarantoolClient.get_instance()
        metrics = tarantool.get_metrics()
        config = tarantool.get_config()
        cache_size = tarantool.get_cache_size()
        return ok(
            data={"metrics": metrics, "config": config, "cache_size": cache_size},
            metrics=metrics,
            config=config,
            cache_size=cache_size,
        )
    except Exception as e:
        if is_versioned_request(request):
            raise
        return {"status": "error", "message": str(e)}


@utility_router.post("/cache/metrics/reset")
@limiter.limit(f"{RATE_LIMIT_ADMIN_PER_MINUTE}/minute")
async def reset_cache_metrics(request: Request, role: str = Depends(require_admin)) -> Dict[str, Any]:
    """Reset cache metrics. Requires admin role."""
    try:
        tarantool = await TarantoolClient.get_instance()
        tarantool.reset_metrics()
        return {"status": "success", "message": "Cache metrics reset"}
    except Exception as e:
        if is_versioned_request(request):
            raise
        return {"status": "error", "message": str(e)}


@utility_router.delete("/cache/prefix/{prefix}")
@limiter.limit(f"{RATE_LIMIT_ADMIN_PER_MINUTE}/minute")
async def delete_cache_by_prefix(request: Request, prefix: str, role: str = Depends(require_admin)) -> Dict[str, Any]:
    """Delete cache keys by prefix. Requires admin role."""
    try:
        tarantool = await TarantoolClient.get_instance()
        await tarantool.delete_by_prefix(prefix)
        return {"status": "success", "message": f"Deleted keys with prefix: {prefix}"}
    except Exception as e:
        if is_versioned_request(request):
            raise
        return {"status": "error", "message": str(e)}


@utility_router.get("/cache/entries")
@limiter.limit(f"{RATE_LIMIT_ADMIN_PER_MINUTE}/minute")
async def get_cache_entries(
    request: Request,
    limit: int = 10,
    role: str = Depends(require_admin),
) -> Dict[str, Any]:
    """Get first N cache entries. Requires admin role."""
    client = await TarantoolClient.get_instance()
    entries = await client.get_entries(limit=limit)
    return {
        "status": "success",
        "entries": entries,
        "count": len(entries),
    }


@utility_router.get("/tarantool/status")
async def tarantool_status(request: Request) -> Dict[str, Any]:
    try:
        tarantool = await TarantoolClient.get_instance()
        metrics = tarantool.get_metrics()
        config = tarantool.get_config()
        cache_size = tarantool.get_cache_size()

        is_fallback = getattr(tarantool, "_fallback_mode", False)

        return {
            "status": "success",
            "available": True,
            "mode": "in-memory" if is_fallback else "tarantool",
            "connection": {
                "host": config.get("host", "N/A"),
                "port": config.get("port", "N/A"),
                "fallback": is_fallback,
            },
            "cache": {
                "size": cache_size,
                "hits": metrics.get("hits", 0),
                "misses": metrics.get("misses", 0),
                "hit_rate": metrics.get("hit_rate", 0),
            },
            "compression": {
                "enabled": config.get("compression_enabled", False),
                "threshold": config.get("compression_threshold", 0),
                "compressed_count": metrics.get("compressed_count", 0),
                "bytes_saved": metrics.get("bytes_saved", 0),
            },
        }
    except Exception as e:
        if is_versioned_request(request):
            raise
        return {
            "status": "error",
            "available": False,
            "mode": "unavailable",
            "message": str(e),
        }


# =============================================================================
# CIRCUIT BREAKERS & METRICS ENDPOINTS
# =============================================================================


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
    """Получить метрики запросов приложения. Требуется роль администратора."""
    return AppMetricsResponse(status="success", metrics=app_metrics.snapshot())


@utility_router.post("/app-metrics/reset")
@limiter.limit(f"{RATE_LIMIT_ADMIN_PER_MINUTE}/minute")
async def reset_app_metrics(request: Request, role: str = Depends(require_admin)) -> Dict[str, Any]:
    """Reset in-process application request metrics. Requires admin role."""
    app_metrics.reset()
    return {"status": "success", "message": "App metrics reset"}


# =============================================================================
# CONFIGURATION ENDPOINTS
# =============================================================================


def _redact(obj: Any) -> Any:
    """
    Best-effort redaction for config snapshots.
    """
    sensitive = ("password", "token", "secret", "api_key", "key", "dsn")
    if isinstance(obj, dict):
        out: Dict[str, Any] = {}
        for k, v in obj.items():
            ks = str(k).lower()
            if any(s in ks for s in sensitive):
                out[k] = "***"
            else:
                out[k] = _redact(v)
        return out
    if isinstance(obj, list):
        return [_redact(x) for x in obj]
    return obj


@utility_router.get("/config")
@limiter.limit(f"{RATE_LIMIT_ADMIN_PER_MINUTE}/minute")
async def get_config_snapshot(request: Request, role: str = Depends(require_admin)) -> Dict[str, Any]:
    """
    Get current effective settings snapshot (redacted) + last reload info.
    Requires admin role.
    """
    snapshot = {
        "app": settings.app.model_dump(),
        "scheduler": settings.scheduler.model_dump(),
        "secure": settings.secure.model_dump(),
        "http_base": settings.http_base.model_dump(),
        "tarantool": settings.tarantool.model_dump(),
        "mongo": settings.mongo.model_dump(),
        "redis": settings.redis.model_dump(),
        "queue": settings.queue.model_dump(),
        "celery": settings.celery.model_dump(),
        "mail": settings.mail.model_dump(),
        "grpc": settings.grpc.model_dump(),
        "tasks": settings.tasks.model_dump(),
        "storage": settings.storage.model_dump(),
        "logging": settings.logging.model_dump(),
        "external_api": {
            "dadata": settings.dadata.model_dump(),
            "casebook": settings.casebook.model_dump(),
            "infosphere": settings.infosphere.model_dump(),
            "perplexity": settings.perplexity.model_dump(),
            "tavily": settings.tavily.model_dump(),
            "openrouter": settings.openrouter.model_dump(),
            "huggingface": settings.huggingface.model_dump(),
            "gigachat": settings.gigachat.model_dump(),
        },
    }
    return {
        "status": "success",
        "reload": get_reload_state(),
        "config": _redact(snapshot),
    }


@utility_router.post("/config/reload")
@limiter.limit(f"{RATE_LIMIT_ADMIN_PER_MINUTE}/minute")
async def force_config_reload(request: Request, role: str = Depends(require_admin)) -> Dict[str, Any]:
    """Force config reload immediately. Requires admin role."""
    reload_settings(reason="manual_api")
    return {"status": "success", "reload": get_reload_state()}


# =============================================================================
# SERVICES STATUS ENDPOINTS (Perplexity, Tavily, OpenRouter, Email)
# =============================================================================


@utility_router.get("/perplexity/status")
async def perplexity_status():
    client = PerplexityClient.get_instance()
    return await client.healthcheck()


@utility_router.get("/tavily/status")
async def tavily_status():
    client = TavilyClient.get_instance()
    return await client.healthcheck()


@utility_router.post("/tavily/cache/clear")
@limiter.limit(f"{RATE_LIMIT_ADMIN_PER_MINUTE}/minute")
async def clear_tavily_cache(request: Request, role: str = Depends(require_admin)):
    """Clear Tavily cache. Requires admin role."""
    client = TavilyClient.get_instance()
    client.clear_cache()
    return {"status": "success", "message": "Tavily cache cleared"}


@utility_router.post("/perplexity/cache/clear")
@limiter.limit(f"{RATE_LIMIT_ADMIN_PER_MINUTE}/minute")
async def clear_perplexity_cache(request: Request, role: str = Depends(require_admin)):
    """Clear Perplexity cache. Requires admin role."""
    client = PerplexityClient.get_instance()
    client.clear_cache()
    return {"status": "success", "message": "Perplexity cache cleared"}


@utility_router.get("/openrouter/status")
async def openrouter_status() -> Dict[str, Any]:
    client = get_openrouter_client()
    status = await client.check_status()
    return {
        "status": "success" if status.get("available") else "error",
        "available": status.get("available", False),
        "model": status.get("model", client.model),
        "error": status.get("error"),
    }


@utility_router.get("/email/status")
async def email_status() -> Dict[str, Any]:
    """Get email service status and health check."""
    client = EmailClient.get_instance()
    return client.get_status()


@utility_router.get("/email/healthcheck")
async def email_healthcheck() -> Dict[str, Any]:
    """Perform SMTP server health check."""
    client = EmailClient.get_instance()
    return client.check_health()


# =============================================================================
# REPORTS ENDPOINTS (PDF generation)
# =============================================================================


def _relative_path_for(request: Request, *, route_name: str, **params: Any) -> str:
    """
    Return a URL path relative to current API root (without root_path).

    - For legacy (unversioned) routes: root_path == "" → returned path is unchanged
    - For versioned sub-app (/api/v1): root_path == "/api/v1" → strip it so clients
      that already use a versioned base URL don't end up with a double prefix.
    """
    absolute = str(request.url_for(route_name, **params))
    path = urlparse(absolute).path
    root_path = request.scope.get("root_path") or ""
    if root_path and path.startswith(root_path):
        return path[len(root_path) :] or "/"
    return path


@utility_router.post("/reports/pdf")
async def generate_pdf_report(http_request: Request, payload: PDFReportRequest) -> Dict[str, Any]:
    """Generate PDF report from analysis data."""
    try:
        filepath = save_pdf_report(
            report_data=payload.report_data,
            client_name=payload.client_name,
            inn=payload.inn,
            session_id=payload.session_id,
        )

        filename = os.path.basename(filepath)
        return {
            "status": "success",
            "filepath": filepath,
            "filename": filename,
            "download_url": _relative_path_for(http_request, route_name="download_report", filename=filename),
        }
    except Exception as e:
        if is_versioned_request(http_request):
            raise
        return {"status": "error", "message": str(e)}


@utility_router.get("/reports/download/{filename}")
async def download_report(filename: str):
    """Download PDF report file."""
    filepath = os.path.join("reports", filename)

    if not os.path.exists(filepath):
        raise HTTPException(status_code=404, detail="Report not found")

    return FileResponse(
        filepath,
        media_type="application/pdf",
        filename=filename,
    )


@utility_router.get("/reports/list")
async def list_reports(http_request: Request) -> Dict[str, Any]:
    """List all available reports."""
    reports_dir = "reports"

    if not os.path.exists(reports_dir):
        return {"status": "success", "reports": []}

    reports = []
    for filename in os.listdir(reports_dir):
        filepath = os.path.join(reports_dir, filename)
        if os.path.isfile(filepath):
            reports.append(
                {
                    "filename": filename,
                    "size_bytes": os.path.getsize(filepath),
                    "created": os.path.getctime(filepath),
                    "download_url": _relative_path_for(http_request, route_name="download_report", filename=filename),
                }
            )

    reports.sort(key=lambda x: x["created"], reverse=True)

    return {"status": "success", "reports": reports, "count": len(reports)}


@utility_router.delete("/reports/{filename}")
@limiter.limit(f"{RATE_LIMIT_ADMIN_PER_MINUTE}/minute")
async def delete_report(request: Request, filename: str, role: str = Depends(require_admin)) -> Dict[str, Any]:
    """Delete a report file. Requires admin role."""
    filepath = os.path.join("reports", filename)

    if not os.path.exists(filepath):
        raise HTTPException(status_code=404, detail="Report not found")

    try:
        os.remove(filepath)
        return {"status": "success", "message": f"Report {filename} deleted"}
    except Exception as e:
        if is_versioned_request(request):
            raise
        return {"status": "error", "message": str(e)}


# =============================================================================
# TELEMETRY ENDPOINTS (Traces, Logs)
# =============================================================================


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


# =============================================================================
# QUEUE ENDPOINTS (RabbitMQ monitoring) - P1-2
# =============================================================================


@utility_router.get("/queue/stats")
async def get_queue_stats() -> Dict[str, Any]:
    """
    P1-2: Получить статистику очередей RabbitMQ.

    Returns:
        Статистика по всем очередям (длина, consumers, rate)
    """
    try:
        import httpx

        mgmt_url = settings.queue.amqp_url.replace("amqp://", "http://").replace(":5672", ":15672")
        auth = ("admin", "admin123")

        async with httpx.AsyncClient(timeout=5.0) as client:
            resp = await client.get(f"{mgmt_url}/api/queues/%2f", auth=auth)
            resp.raise_for_status()
            queues = resp.json()

            stats = {}
            for queue in queues:
                name = queue["name"]
                message_stats = queue.get("message_stats", {})

                stats[name] = {
                    "messages": queue.get("messages", 0),
                    "messages_ready": queue.get("messages_ready", 0),
                    "messages_unacknowledged": queue.get("messages_unacknowledged", 0),
                    "consumers": queue.get("consumers", 0),
                    "state": queue.get("state", "unknown"),
                    "rate": {
                        "publish": message_stats.get("publish_details", {}).get("rate", 0),
                        "deliver": message_stats.get("deliver_details", {}).get("rate", 0),
                    },
                }

            return {
                "status": "ok",
                "timestamp": time.time(),
                "queues": stats,
                "total_messages": sum(q["messages"] for q in stats.values()),
                "total_consumers": sum(q["consumers"] for q in stats.values()),
            }

    except Exception as e:
        logger.error(f"Failed to fetch RabbitMQ stats: {e}", component="rabbitmq_monitor")
        return {
            "status": "error",
            "error": str(e),
            "queues": {},
        }


@utility_router.get("/queue/health")
async def check_queue_health() -> Dict[str, Any]:
    """
    P1-2: Health check для очередей RabbitMQ.

    Алерты:
    - Очередь > 100 сообщений
    - Нет consumers
    - DLQ > 10 сообщений
    """
    stats = await get_queue_stats()

    if stats["status"] == "error":
        raise HTTPException(status_code=503, detail="Cannot connect to RabbitMQ Management API")

    alerts = []

    for name, queue_stats in stats["queues"].items():
        if queue_stats["messages"] > 100:
            alerts.append(
                {
                    "severity": "warning",
                    "queue": name,
                    "reason": f"Queue has {queue_stats['messages']} messages (threshold: 100)",
                }
            )

        if queue_stats["consumers"] == 0 and queue_stats["messages"] > 0:
            alerts.append(
                {
                    "severity": "critical",
                    "queue": name,
                    "reason": "No consumers but queue has messages",
                }
            )

        if name.startswith("dlq.") and queue_stats["messages"] > 10:
            alerts.append(
                {
                    "severity": "critical",
                    "queue": name,
                    "reason": f"DLQ has {queue_stats['messages']} failed messages (threshold: 10)",
                }
            )

    return {
        "status": "healthy" if not alerts else "degraded",
        "alerts": alerts,
        "total_queues": len(stats["queues"]),
        "total_messages": stats["total_messages"],
        "total_consumers": stats.get("total_consumers", 0),
        "timestamp": stats["timestamp"],
    }


@utility_router.get("/queue/dlq-stats")
@limiter.limit(f"{RATE_LIMIT_ADMIN_PER_MINUTE}/minute")
async def get_dlq_stats(request: Request, role: str = Depends(require_admin)) -> Dict[str, Any]:
    """
    P1-2: Получить статистику Dead Letter Queue из Tarantool.
    
    Возвращает количество failed messages и последние 10 ошибок.
    Требуется роль администратора.
    """
    try:
        tarantool = await TarantoolClient.get_instance()
        
        analysis_failures = []
        cache_failures = []
        
        if tarantool.is_connected:
            all_keys = await tarantool.get_all_persistent_keys()
            
            for key in all_keys:
                if key.startswith("dlq:analysis:"):
                    value = await tarantool.get_persistent(key)
                    if value:
                        analysis_failures.append({
                            "key": key,
                            "timestamp": value.get("timestamp"),
                            "message": value.get("message", {}),
                        })
                elif key.startswith("dlq:cache:"):
                    value = await tarantool.get_persistent(key)
                    if value:
                        cache_failures.append({
                            "key": key,
                            "timestamp": value.get("timestamp"),
                            "message": value.get("message", {}),
                        })
        
        analysis_failures.sort(key=lambda x: x.get("timestamp", 0), reverse=True)
        cache_failures.sort(key=lambda x: x.get("timestamp", 0), reverse=True)
        
        return {
            "status": "success",
            "analysis_dlq": {
                "total_count": len(analysis_failures),
                "recent": analysis_failures[:10],
            },
            "cache_dlq": {
                "total_count": len(cache_failures),
                "recent": cache_failures[:10],
            },
            "total_failed": len(analysis_failures) + len(cache_failures),
            "storage_connected": tarantool.is_connected,
        }
    except Exception as e:
        logger.error(f"Failed to get DLQ stats: {e}", component="dlq_monitor")
        if is_versioned_request(request):
            raise
        return {
            "status": "error",
            "error": str(e),
            "analysis_dlq": {"total_count": 0, "recent": []},
            "cache_dlq": {"total_count": 0, "recent": []},
        }


# =============================================================================
# ASYNCAPI ENDPOINTS
# =============================================================================


@utility_router.get("/asyncapi.json")
async def get_asyncapi_spec(request: Request) -> Dict[str, Any]:
    """
    AsyncAPI спецификация очередей (RabbitMQ/FastStream).
    """
    try:
        from faststream.specification import AsyncAPI

        from app.messaging.broker import broker

        spec = AsyncAPI(broker, title="Client Analysis Messaging", version="1.0.0").to_specification()
        return json.loads(spec.to_json())
    except Exception as e:
        if is_versioned_request(request):
            raise
        return {"status": "error", "message": str(e)}


@utility_router.get("/asyncapi")
async def get_asyncapi_html() -> HTMLResponse:
    """HTML-представление AsyncAPI."""
    from faststream.specification import (
        AsyncAPI,
    )
    from faststream.specification import (
        get_asyncapi_html as _get_asyncapi_html,
    )

    from app.messaging.broker import broker

    spec = AsyncAPI(broker, title="Client Analysis Messaging", version="1.0.0").to_specification()
    html = _get_asyncapi_html(spec)
    return HTMLResponse(content=html)
