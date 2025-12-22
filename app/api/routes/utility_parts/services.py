from __future__ import annotations

from typing import Any, Dict

from fastapi import Depends, Request

from app.api.routes.utility import limiter, utility_router
from app.config.constants import RATE_LIMIT_ADMIN_PER_MINUTE
from app.services.email_client import EmailClient
from app.services.openrouter_client import get_openrouter_client
from app.services.perplexity_client import PerplexityClient
from app.services.tavily_client import TavilyClient
from app.utility.auth import require_admin


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

