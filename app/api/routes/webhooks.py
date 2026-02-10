"""
Webhook management API endpoints (Phase 6).

Register, unregister, and inspect webhook endpoints.
View delivery history for debugging and monitoring.
"""

from typing import Any, Dict, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status

from app.schemas.requests import WebhookRegisterRequest
from app.shared.audit_trail import audit_log
from app.shared.toolkit.auth import Permission, require_permission
from app.shared.webhooks import webhook_manager

webhooks_router = APIRouter(prefix="/webhooks", tags=["Webhooks"])


@webhooks_router.post(
    "",
    dependencies=[Depends(require_permission(Permission.ADMIN_WEBHOOKS))],
)
async def register_webhook(
    request: WebhookRegisterRequest,
    role: str = Depends(require_permission(Permission.ADMIN_WEBHOOKS)),
) -> Dict[str, Any]:
    """
    Register a new webhook endpoint.

    The endpoint will receive POST requests for subscribed events.
    Optionally provide an HMAC secret for payload signature verification.
    """
    endpoint = webhook_manager.register(
        url=request.url,
        events=request.events,
        secret=request.secret,
        description=request.description,
    )

    audit_log.record(
        action="webhook.register",
        role=role,
        details={
            "webhook_id": endpoint.id,
            "url": request.url,
            "events": request.events,
        },
    )

    return {
        "status": "success",
        "webhook": {
            "id": endpoint.id,
            "url": endpoint.url,
            "events": endpoint.events,
            "has_secret": bool(endpoint.secret),
            "description": endpoint.description,
        },
    }


@webhooks_router.get(
    "",
    dependencies=[Depends(require_permission(Permission.ADMIN_WEBHOOKS))],
)
async def list_webhooks() -> Dict[str, Any]:
    """List all registered webhook endpoints."""
    endpoints = webhook_manager.list_endpoints()
    return {
        "status": "success",
        "count": len(endpoints),
        "webhooks": endpoints,
    }


@webhooks_router.delete(
    "/{webhook_id}",
    dependencies=[Depends(require_permission(Permission.ADMIN_WEBHOOKS))],
)
async def unregister_webhook(
    webhook_id: str,
    role: str = Depends(require_permission(Permission.ADMIN_WEBHOOKS)),
) -> Dict[str, Any]:
    """Unregister a webhook endpoint by ID."""
    removed = webhook_manager.unregister(webhook_id)

    if not removed:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Webhook {webhook_id} not found",
        )

    audit_log.record(
        action="webhook.unregister",
        role=role,
        details={"webhook_id": webhook_id},
    )

    return {"status": "success", "message": f"Webhook {webhook_id} removed"}


@webhooks_router.get(
    "/deliveries",
    dependencies=[Depends(require_permission(Permission.ADMIN_WEBHOOKS))],
)
async def get_deliveries(
    webhook_id: Optional[str] = Query(None, description="Filter by webhook ID"),
    limit: int = Query(50, ge=1, le=200, description="Max deliveries to return"),
) -> Dict[str, Any]:
    """Get webhook delivery history for debugging."""
    deliveries = webhook_manager.get_deliveries(webhook_id=webhook_id, limit=limit)
    return {
        "status": "success",
        "count": len(deliveries),
        "deliveries": deliveries,
    }


__all__ = ["webhooks_router"]
