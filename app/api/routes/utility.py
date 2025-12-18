"""
Utility API routes for system monitoring, caching, and service management.

Provides endpoints for health checks, circuit breaker management,
cache operations, and external service status monitoring.
"""

import os
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel

from app.services.email_client import EmailClient
from app.services.http_client import AsyncHttpClient
from app.services.openrouter_client import get_openrouter_client
from app.services.perplexity_client import PerplexityClient
from app.services.tavily_client import TavilyClient
from app.storage.tarantool import TarantoolClient
from app.utility.auth import Role, get_current_role, require_admin
from app.utility.pdf_generator import save_pdf_report
from app.utility.telemetry import get_log_store, get_span_exporter

utility_router = APIRouter(
    prefix="/utility",
    tags=["Утилиты"],
    responses={404: {"description": "Не найдено"}},
)


@utility_router.get("/health")
async def health_check() -> Dict[str, Any]:
    perplexity = PerplexityClient.get_instance()
    tavily = TavilyClient.get_instance()
    openrouter = get_openrouter_client()
    issues: List[str] = []

    try:
        http_client = await AsyncHttpClient.get_instance()
        http_status = "healthy"

        cb_status = http_client.get_circuit_breaker_status()
        open_breakers = [
            name
            for name, cb in cb_status.items()
            if isinstance(cb, dict) and cb.get("state") == "open"
        ]
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

    perplexity_status = "ready" if perplexity.is_configured() else "not_configured"
    tavily_status = "ready" if tavily.is_configured() else "not_configured"
    openrouter_configured = bool(openrouter.api_key)
    openrouter_status = "ready" if openrouter_configured else "not_configured"

    if not perplexity.is_configured():
        issues.append("Perplexity API not configured")
    if not tavily.is_configured():
        issues.append("Tavily API not configured")
    if not openrouter_configured:
        issues.append("OpenRouter API not configured")

    overall_status = "healthy" if not issues else "degraded"

    return {
        "status": overall_status,
        "issues": issues if issues else None,
        "components": {
            "http_client": http_status,
            "tarantool": tarantool_status,
            "openrouter": {
                "configured": openrouter_configured,
                "status": openrouter_status,
                "model": openrouter.model,
            },
            "perplexity": {
                "configured": perplexity.is_configured(),
                "status": perplexity_status,
            },
            "tavily": {
                "configured": tavily.is_configured(),
                "status": tavily_status,
            },
        },
    }


@utility_router.get("/circuit-breakers")
async def get_circuit_breakers(service: Optional[str] = None) -> Dict[str, Any]:
    try:
        http_client = await AsyncHttpClient.get_instance()
        status = http_client.get_circuit_breaker_status(service)
        return {"status": "success", "circuit_breakers": status}
    except Exception as e:
        return {"status": "error", "message": str(e)}


@utility_router.post("/circuit-breakers/{service}/reset")
async def reset_circuit_breaker(service: str, role: str = Depends(require_admin)) -> Dict[str, Any]:
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
        return {"status": "error", "message": str(e)}


@utility_router.get("/metrics")
async def get_metrics(service: Optional[str] = None) -> Dict[str, Any]:
    try:
        http_client = await AsyncHttpClient.get_instance()
        metrics = http_client.get_metrics(service)
        return {"status": "success", "metrics": metrics}
    except Exception as e:
        return {"status": "error", "message": str(e)}


@utility_router.post("/metrics/reset")
async def reset_metrics(service: Optional[str] = None, role: str = Depends(require_admin)) -> Dict[str, Any]:
    """Reset HTTP metrics. Requires admin role."""
    try:
        http_client = await AsyncHttpClient.get_instance()
        http_client.reset_metrics(service)
        msg = f"Metrics reset for {service}" if service else "All metrics reset"
        return {"status": "success", "message": msg}
    except Exception as e:
        return {"status": "error", "message": str(e)}


@utility_router.get("/validate_cache")
async def validate_cache(confirm: bool, role: str = Depends(require_admin)):
    """
    Invalidate all cache keys. Requires admin role.
    
    Args:
        confirm: Must be True to execute the operation.
        role: User role from authentication.
    """
    client = await TarantoolClient.get_instance()
    await client.invalidate_all_keys(confirm)
    return {
        "status": "success",
        "message": "Кэш инвалидирован" if confirm else "Операция отменена",
    }


@utility_router.get("/perplexity/status")
async def perplexity_status():
    client = PerplexityClient.get_instance()
    # Реальная проверка доступности сервиса (тестовый запрос).
    return await client.healthcheck()


@utility_router.get("/tavily/status")
async def tavily_status():
    client = TavilyClient.get_instance()
    # Реальная проверка доступности сервиса (тестовый запрос).
    return await client.healthcheck()


@utility_router.post("/tavily/cache/clear")
async def clear_tavily_cache(role: str = Depends(require_admin)):
    """Clear Tavily cache. Requires admin role."""
    client = TavilyClient.get_instance()
    client.clear_cache()
    return {"status": "success", "message": "Tavily cache cleared"}


@utility_router.post("/perplexity/cache/clear")
async def clear_perplexity_cache(role: str = Depends(require_admin)):
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


@utility_router.get("/cache/metrics")
async def get_cache_metrics() -> Dict[str, Any]:
    try:
        tarantool = await TarantoolClient.get_instance()
        metrics = tarantool.get_metrics()
        config = tarantool.get_config()
        cache_size = tarantool.get_cache_size()
        return {
            "status": "success",
            "metrics": metrics,
            "config": config,
            "cache_size": cache_size,
        }
    except Exception as e:
        return {"status": "error", "message": str(e)}


@utility_router.post("/cache/metrics/reset")
async def reset_cache_metrics(role: str = Depends(require_admin)) -> Dict[str, Any]:
    """Reset cache metrics. Requires admin role."""
    try:
        tarantool = await TarantoolClient.get_instance()
        tarantool.reset_metrics()
        return {"status": "success", "message": "Cache metrics reset"}
    except Exception as e:
        return {"status": "error", "message": str(e)}


@utility_router.delete("/cache/prefix/{prefix}")
async def delete_cache_by_prefix(prefix: str, role: str = Depends(require_admin)) -> Dict[str, Any]:
    """Delete cache keys by prefix. Requires admin role."""
    try:
        tarantool = await TarantoolClient.get_instance()
        await tarantool.delete_by_prefix(prefix)
        return {"status": "success", "message": f"Deleted keys with prefix: {prefix}"}
    except Exception as e:
        return {"status": "error", "message": str(e)}


@utility_router.get("/tarantool/status")
async def tarantool_status() -> Dict[str, Any]:
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
        return {
            "status": "error",
            "available": False,
            "mode": "unavailable",
            "message": str(e),
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


class PDFReportRequest(BaseModel):
    """Request body for PDF report generation."""
    client_name: str
    inn: Optional[str] = None
    session_id: Optional[str] = None
    report_data: Dict[str, Any]


@utility_router.post("/reports/pdf")
async def generate_pdf_report(request: PDFReportRequest) -> Dict[str, Any]:
    """
    Generate PDF report from analysis data.
    
    Args:
        request: Report data with client info and analysis results.
        
    Returns:
        Path to generated PDF file.
    """
    try:
        filepath = save_pdf_report(
            report_data=request.report_data,
            client_name=request.client_name,
            inn=request.inn,
            session_id=request.session_id,
        )
        
        return {
            "status": "success",
            "filepath": filepath,
            "filename": os.path.basename(filepath),
            "download_url": f"/utility/reports/download/{os.path.basename(filepath)}",
        }
    except Exception as e:
        return {"status": "error", "message": str(e)}


@utility_router.get("/reports/download/{filename}")
async def download_report(filename: str):
    """
    Download PDF report file.
    
    Args:
        filename: Name of the PDF file to download.
    """
    filepath = os.path.join("reports", filename)
    
    if not os.path.exists(filepath):
        raise HTTPException(status_code=404, detail="Report not found")
    
    return FileResponse(
        filepath,
        media_type="application/pdf",
        filename=filename,
    )


@utility_router.get("/reports/list")
async def list_reports() -> Dict[str, Any]:
    """List all available reports."""
    reports_dir = "reports"
    
    if not os.path.exists(reports_dir):
        return {"status": "success", "reports": []}
    
    reports = []
    for filename in os.listdir(reports_dir):
        filepath = os.path.join(reports_dir, filename)
        if os.path.isfile(filepath):
            reports.append({
                "filename": filename,
                "size_bytes": os.path.getsize(filepath),
                "created": os.path.getctime(filepath),
                "download_url": f"/utility/reports/download/{filename}",
            })
    
    reports.sort(key=lambda x: x["created"], reverse=True)
    
    return {"status": "success", "reports": reports, "count": len(reports)}


@utility_router.delete("/reports/{filename}")
async def delete_report(filename: str, role: str = Depends(require_admin)) -> Dict[str, Any]:
    """Delete a report file. Requires admin role."""
    filepath = os.path.join("reports", filename)
    
    if not os.path.exists(filepath):
        raise HTTPException(status_code=404, detail="Report not found")
    
    try:
        os.remove(filepath)
        return {"status": "success", "message": f"Report {filename} deleted"}
    except Exception as e:
        return {"status": "error", "message": str(e)}


@utility_router.get("/auth/role")
async def get_auth_role(role: str = Depends(get_current_role)) -> Dict[str, Any]:
    """
    Get current authentication role.
    
    Returns the user's role based on the X-Auth-Token header.
    """
    return {
        "role": role,
        "is_admin": role == Role.ADMIN,
    }


@utility_router.get("/cache/entries")
async def get_cache_entries(
    limit: int = 10,
    role: str = Depends(require_admin)
) -> Dict[str, Any]:
    """
    Get first N cache entries. Requires admin role.
    
    Args:
        limit: Maximum number of entries to return (default: 10)
    """
    client = await TarantoolClient.get_instance()
    entries = await client.get_entries(limit=limit)
    return {
        "status": "success",
        "entries": entries,
        "count": len(entries),
    }


@utility_router.get("/traces")
async def get_traces(
    limit: int = 50,
    since_minutes: Optional[int] = None,
    role: str = Depends(require_admin)
) -> Dict[str, Any]:
    """
    Get recent traces. Requires admin role.
    
    Args:
        limit: Maximum number of traces to return (default: 50)
        since_minutes: Only return traces from last N minutes
    """
    exporter = get_span_exporter()
    if not exporter:
        return {"status": "error", "message": "Telemetry not initialized"}
    
    spans = exporter.get_spans(limit=limit, since_minutes=since_minutes)
    stats = exporter.get_trace_stats()
    
    return {
        "status": "success",
        "spans": spans,
        "count": len(spans),
        "stats": stats
    }


@utility_router.get("/traces/stats")
async def get_trace_stats(role: str = Depends(require_admin)) -> Dict[str, Any]:
    """Get trace statistics. Requires admin role."""
    exporter = get_span_exporter()
    if not exporter:
        return {"status": "error", "message": "Telemetry not initialized"}
    
    return {"status": "success", "stats": exporter.get_trace_stats()}


@utility_router.post("/traces/clear")
async def clear_traces(role: str = Depends(require_admin)) -> Dict[str, Any]:
    """Clear all stored traces. Requires admin role."""
    exporter = get_span_exporter()
    if not exporter:
        return {"status": "error", "message": "Telemetry not initialized"}
    
    exporter.clear()
    return {"status": "success", "message": "Traces cleared"}


@utility_router.get("/logs")
async def get_logs(
    limit: int = 100,
    since_minutes: Optional[int] = None,
    level: Optional[str] = None,
    role: str = Depends(require_admin)
) -> Dict[str, Any]:
    """
    Get application logs. Requires admin role.
    
    Args:
        limit: Maximum number of logs to return (default: 100)
        since_minutes: Only return logs from last N minutes
        level: Filter by log level (DEBUG, INFO, WARNING, ERROR)
    """
    log_store = get_log_store()
    if not log_store:
        return {"status": "error", "message": "Log store not initialized"}
    
    logs = log_store.get_logs(limit=limit, since_minutes=since_minutes, level=level)
    stats = log_store.get_stats()
    
    return {
        "status": "success",
        "logs": logs,
        "count": len(logs),
        "stats": stats
    }


@utility_router.get("/logs/stats")
async def get_log_stats(role: str = Depends(require_admin)) -> Dict[str, Any]:
    """Get log statistics. Requires admin role."""
    log_store = get_log_store()
    if not log_store:
        return {"status": "error", "message": "Log store not initialized"}
    
    return {"status": "success", "stats": log_store.get_stats()}


@utility_router.post("/logs/clear")
async def clear_logs(role: str = Depends(require_admin)) -> Dict[str, Any]:
    """Clear all stored logs. Requires admin role."""
    log_store = get_log_store()
    if not log_store:
        return {"status": "error", "message": "Log store not initialized"}
    
    log_store.clear()
    return {"status": "success", "message": "Logs cleared"}
