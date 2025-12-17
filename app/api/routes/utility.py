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

from app.services.http_client import AsyncHttpClient
from app.services.openrouter_client import get_openrouter_client
from app.services.perplexity_client import PerplexityClient
from app.services.tavily_client import TavilyClient
from app.utility.auth import get_current_role, require_admin, Role
from app.utility.tcp_client import get_tcp_client, TCPClientConfig
from app.utility.pdf_generator import generate_analysis_pdf, save_pdf_report
from app.storage.tarantool import TarantoolClient

utility_router = APIRouter(
    prefix="/utility",
    tags=["Утилиты"],
    responses={404: {"description": "Не найдено"}},
)


class PerplexityRequest(BaseModel):
    query: str
    search_recency: str = "month"


class TavilyRequest(BaseModel):
    query: str
    search_depth: str = "basic"
    max_results: int = 5
    include_answer: bool = True
    include_domains: Optional[List[str]] = None
    exclude_domains: Optional[List[str]] = None


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
async def reset_circuit_breaker(service: str) -> Dict[str, Any]:
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
async def reset_metrics(service: Optional[str] = None) -> Dict[str, Any]:
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


@utility_router.post("/perplexity/search")
async def perplexity_search(request: PerplexityRequest):
    client = PerplexityClient.get_instance()

    if not client.is_configured():
        return {"status": "error", "message": "Perplexity API key не настроен"}

    result = await client.ask(
        question=request.query, search_recency_filter=request.search_recency
    )

    if result.get("success"):
        return {
            "status": "success",
            "content": result.get("content", ""),
            "citations": result.get("citations", []),
            "model": result.get("model"),
        }
    return {"status": "error", "message": result.get("error", "Неизвестная ошибка")}


@utility_router.get("/perplexity/status")
async def perplexity_status():
    client = PerplexityClient.get_instance()
    status = await client.get_status()
    return status


@utility_router.post("/tavily/search")
async def tavily_search(request: TavilyRequest):
    client = TavilyClient.get_instance()

    if not client.is_configured():
        return {
            "status": "error",
            "message": "Tavily API key не настроен. Добавьте TAVILY_TOKEN в секреты.",
        }

    result = await client.search(
        query=request.query,
        search_depth=request.search_depth,
        max_results=request.max_results,
        include_answer=request.include_answer,
        include_domains=request.include_domains,
        exclude_domains=request.exclude_domains,
    )

    if result.get("success"):
        return {
            "status": "success",
            "answer": result.get("answer", ""),
            "results": result.get("results", []),
            "query": request.query,
            "cached": result.get("cached", False),
        }
    return {"status": "error", "message": result.get("error", "Неизвестная ошибка")}


@utility_router.get("/tavily/status")
async def tavily_status():
    client = TavilyClient.get_instance()
    status = await client.get_status()
    return status


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


class TCPMessageRequest(BaseModel):
    message: Dict[str, Any]
    wait_response: bool = False


class TCPConnectRequest(BaseModel):
    host: str = "localhost"
    port: int = 9000


@utility_router.get("/tcp/status")
async def tcp_status() -> Dict[str, Any]:
    try:
        client = await get_tcp_client()
        return {
            "status": "success",
            "connected": client.is_connected,
            "state": client.state.value,
            "metrics": client.metrics.to_dict(),
            "config": {
                "host": client.config.host,
                "port": client.config.port,
            },
        }
    except Exception as e:
        return {"status": "error", "message": str(e)}


@utility_router.post("/tcp/connect")
async def tcp_connect(request: TCPConnectRequest) -> Dict[str, Any]:
    try:
        config = TCPClientConfig(host=request.host, port=request.port)
        client = await get_tcp_client(config)
        success = await client.connect()
        return {
            "status": "success" if success else "failed",
            "connected": client.is_connected,
            "host": request.host,
            "port": request.port,
        }
    except Exception as e:
        return {"status": "error", "message": str(e)}


@utility_router.post("/tcp/disconnect")
async def tcp_disconnect() -> Dict[str, Any]:
    try:
        client = await get_tcp_client()
        await client.disconnect()
        return {"status": "success", "connected": False}
    except Exception as e:
        return {"status": "error", "message": str(e)}


@utility_router.post("/tcp/send")
async def tcp_send_message(request: TCPMessageRequest) -> Dict[str, Any]:
    try:
        client = await get_tcp_client()
        if not client.is_connected:
            return {"status": "error", "message": "Not connected to TCP server"}
        
        result = await client.send_message(request.message, wait_response=request.wait_response)
        return {
            "status": "success",
            "result": result,
            "metrics": client.metrics.to_dict(),
        }
    except Exception as e:
        return {"status": "error", "message": str(e)}


@utility_router.post("/tcp/send-async")
async def tcp_send_async(request: TCPMessageRequest) -> Dict[str, Any]:
    """Send message asynchronously via TCP."""
    try:
        client = await get_tcp_client()
        await client.send_message_async(request.message)
        return {
            "status": "queued",
            "message": "Message added to send queue",
            "queue_size": client._message_queue.qsize(),
        }
    except Exception as e:
        return {"status": "error", "message": str(e)}


@utility_router.get("/tcp/healthcheck")
async def tcp_healthcheck() -> Dict[str, Any]:
    """
    Healthcheck for TCP message server.
    
    Attempts to send a ping and checks connection state.
    """
    try:
        client = await get_tcp_client()
        
        health_status = {
            "connected": client.is_connected,
            "state": client.state.value,
            "config": {
                "host": client.config.host,
                "port": client.config.port,
            },
        }
        
        if client.is_connected:
            import time
            ping_msg = {"type": "ping", "timestamp": time.time()}
            response = await client.send_message(ping_msg, wait_response=True)
            
            health_status["ping_response"] = response is not None
            health_status["status"] = "healthy" if response else "degraded"
        else:
            health_status["status"] = "disconnected"
            health_status["ping_response"] = False
        
        metrics = client.metrics.to_dict()
        health_status["metrics"] = {
            "messages_sent": metrics.get("messages_sent", 0),
            "messages_received": metrics.get("messages_received", 0),
            "failed_sends": metrics.get("failed_sends", 0),
            "reconnections": metrics.get("reconnections", 0),
        }
        
        return health_status
    except Exception as e:
        return {
            "status": "error",
            "connected": False,
            "message": str(e),
        }


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
        "is_authorized": role in (Role.ADMIN, Role.VIEWER),
    }
