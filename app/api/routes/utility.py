from typing import Any, Dict, List, Optional

from fastapi import APIRouter
from pydantic import BaseModel

from app.services.http_client import AsyncHttpClient
from app.services.perplexity_client import PerplexityClient
from app.services.tavily_client import TavilyClient
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
    issues: List[str] = []

    try:
        http_client = await AsyncHttpClient.get_instance()
        http_status = "healthy"
        
        cb_status = http_client.get_circuit_breaker_status()
        open_breakers = [
            name for name, cb in cb_status.items()
            if isinstance(cb, dict) and cb.get("state") == "open"
        ]
        if open_breakers:
            issues.append(f"Circuit breakers open: {', '.join(open_breakers)}")
    except Exception as e:
        http_status = f"unhealthy: {str(e)}"
        issues.append(f"HTTP client: {str(e)}")

    try:
        tarantool = await TarantoolClient.get_instance()
        tarantool_status = "healthy"
    except Exception as e:
        tarantool_status = f"unhealthy: {str(e)}"
        issues.append(f"Tarantool: {str(e)}")

    perplexity_status = "ready" if perplexity.is_configured() else "not_configured"
    tavily_status = "ready" if tavily.is_configured() else "not_configured"

    if not perplexity.is_configured():
        issues.append("Perplexity API not configured")
    if not tavily.is_configured():
        issues.append("Tavily API not configured")

    overall_status = "healthy" if not issues else "degraded"

    return {
        "status": overall_status,
        "issues": issues if issues else None,
        "components": {
            "http_client": http_status,
            "tarantool": tarantool_status,
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
            return {"status": "success", "message": f"Circuit breaker for {service} reset"}
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
async def validate_cache(confirm: bool):
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
        return {
            "status": "error",
            "message": "Perplexity API key не настроен"
        }

    result = await client.ask(
        question=request.query,
        search_recency_filter=request.search_recency
    )

    if result.get("success"):
        return {
            "status": "success",
            "content": result.get("content", ""),
            "citations": result.get("citations", []),
            "model": result.get("model")
        }
    return {
        "status": "error",
        "message": result.get("error", "Неизвестная ошибка")
    }


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
            "message": "Tavily API key не настроен. Добавьте TAVILY_TOKEN в секреты."
        }

    result = await client.search(
        query=request.query,
        search_depth=request.search_depth,
        max_results=request.max_results,
        include_answer=request.include_answer,
        include_domains=request.include_domains,
        exclude_domains=request.exclude_domains
    )

    if result.get("success"):
        return {
            "status": "success",
            "answer": result.get("answer", ""),
            "results": result.get("results", []),
            "query": request.query,
            "cached": result.get("cached", False)
        }
    return {
        "status": "error",
        "message": result.get("error", "Неизвестная ошибка")
    }


@utility_router.get("/tavily/status")
async def tavily_status():
    client = TavilyClient.get_instance()
    status = await client.get_status()
    return status


@utility_router.post("/tavily/cache/clear")
async def clear_tavily_cache():
    client = TavilyClient.get_instance()
    client.clear_cache()
    return {"status": "success", "message": "Tavily cache cleared"}


@utility_router.post("/perplexity/cache/clear")
async def clear_perplexity_cache():
    client = PerplexityClient.get_instance()
    client.clear_cache()
    return {"status": "success", "message": "Perplexity cache cleared"}


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
async def reset_cache_metrics() -> Dict[str, Any]:
    try:
        tarantool = await TarantoolClient.get_instance()
        tarantool.reset_metrics()
        return {"status": "success", "message": "Cache metrics reset"}
    except Exception as e:
        return {"status": "error", "message": str(e)}


@utility_router.delete("/cache/prefix/{prefix}")
async def delete_cache_by_prefix(prefix: str) -> Dict[str, Any]:
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
        
        is_fallback = getattr(tarantool, '_fallback_mode', False)
        
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
