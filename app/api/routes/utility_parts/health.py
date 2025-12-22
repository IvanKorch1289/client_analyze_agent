from __future__ import annotations

from typing import Any, Dict, List

from app.api.routes.utility import utility_router
from app.schemas.api import HealthResponse
from app.services.http_client import AsyncHttpClient
from app.services.openrouter_client import get_openrouter_client
from app.services.perplexity_client import PerplexityClient
from app.services.tavily_client import TavilyClient


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

    # Tarantool health is handled by its own status endpoint; keep this lightweight.
    try:
        tarantool_status = "healthy"
    except Exception as e:
        tarantool_status = f"unhealthy: {str(e)}"
        issues.append(f"Tarantool: {str(e)}")

    openrouter_configured = bool(openrouter.api_key)

    # deep=true = real external checks; otherwise configuration-only.
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

