"""
Webhook notification system (Phase 6.5).

Sends HTTP POST notifications when analysis completes.
Supports retry with exponential backoff, HMAC signature verification,
and dead-letter logging for failed deliveries.

Usage:
    from app.shared.webhooks import webhook_manager

    # Register a webhook
    webhook_manager.register("https://example.com/hook", events=["analysis.completed"])

    # Dispatch event
    await webhook_manager.dispatch("analysis.completed", payload={...})
"""

from __future__ import annotations

import hashlib
import hmac
import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from app.shared.toolkit.logging import logger


@dataclass
class WebhookEndpoint:
    """Registered webhook endpoint."""

    id: str
    url: str
    events: List[str]
    secret: Optional[str] = None
    enabled: bool = True
    created_at: float = field(default_factory=time.time)
    description: str = ""


@dataclass
class WebhookDelivery:
    """Record of a webhook delivery attempt."""

    id: str
    webhook_id: str
    event: str
    payload: Dict[str, Any]
    status: str  # pending, success, failed
    attempt: int = 0
    status_code: Optional[int] = None
    error: Optional[str] = None
    delivered_at: Optional[float] = None
    created_at: float = field(default_factory=time.time)


class WebhookManager:
    """Manages webhook registrations and event dispatch."""

    MAX_RETRIES = 3
    RETRY_DELAYS = [2, 5, 15]  # seconds

    def __init__(self):
        self._endpoints: Dict[str, WebhookEndpoint] = {}
        self._deliveries: List[WebhookDelivery] = []

    def register(
        self,
        url: str,
        events: List[str],
        secret: Optional[str] = None,
        description: str = "",
    ) -> WebhookEndpoint:
        """Register a new webhook endpoint.

        Args:
            url: URL to POST events to
            events: List of event types to subscribe to
            secret: Optional HMAC secret for signature verification
            description: Human-readable description

        Returns:
            Registered WebhookEndpoint
        """
        endpoint = WebhookEndpoint(
            id=str(uuid.uuid4())[:8],
            url=url,
            events=events,
            secret=secret,
            description=description,
        )
        self._endpoints[endpoint.id] = endpoint
        logger.info(
            f"Webhook registered: {endpoint.id} -> {url} events={events}",
            component="webhooks",
        )
        return endpoint

    def unregister(self, webhook_id: str) -> bool:
        """Unregister a webhook endpoint."""
        if webhook_id in self._endpoints:
            del self._endpoints[webhook_id]
            logger.info(f"Webhook unregistered: {webhook_id}", component="webhooks")
            return True
        return False

    def list_endpoints(self) -> List[Dict[str, Any]]:
        """List all registered webhook endpoints."""
        return [
            {
                "id": ep.id,
                "url": ep.url,
                "events": ep.events,
                "enabled": ep.enabled,
                "has_secret": bool(ep.secret),
                "description": ep.description,
            }
            for ep in self._endpoints.values()
        ]

    @staticmethod
    def _sign_payload(payload_bytes: bytes, secret: str) -> str:
        """Generate HMAC-SHA256 signature for payload."""
        return hmac.new(
            secret.encode("utf-8"),
            payload_bytes,
            hashlib.sha256,
        ).hexdigest()

    async def dispatch(self, event: str, payload: Dict[str, Any]) -> int:
        """Dispatch an event to all matching webhooks.

        Args:
            event: Event type (e.g., "analysis.completed")
            payload: Event payload dict

        Returns:
            Number of webhooks notified
        """
        matching = [ep for ep in self._endpoints.values() if ep.enabled and event in ep.events]

        if not matching:
            return 0

        count = 0
        for endpoint in matching:
            delivery = WebhookDelivery(
                id=str(uuid.uuid4())[:8],
                webhook_id=endpoint.id,
                event=event,
                payload=payload,
                status="pending",
            )

            success = await self._deliver(endpoint, delivery)
            if success:
                count += 1
            self._deliveries.append(delivery)

        logger.info(
            f"Webhook dispatch: event={event} matched={len(matching)} delivered={count}",
            component="webhooks",
        )
        return count

    async def _deliver(
        self,
        endpoint: WebhookEndpoint,
        delivery: WebhookDelivery,
    ) -> bool:
        """Attempt to deliver a webhook with retries.

        Returns True on success, False on final failure.
        """
        import json

        payload_bytes = json.dumps(delivery.payload, ensure_ascii=False, default=str).encode("utf-8")

        headers = {
            "Content-Type": "application/json",
            "X-Webhook-Event": delivery.event,
            "X-Webhook-Delivery": delivery.id,
        }
        if endpoint.secret:
            headers["X-Webhook-Signature"] = "sha256=" + self._sign_payload(payload_bytes, endpoint.secret)

        for attempt in range(self.MAX_RETRIES):
            delivery.attempt = attempt + 1
            try:
                import asyncio

                try:
                    import httpx

                    async with httpx.AsyncClient(timeout=10.0) as client:
                        response = await client.post(
                            endpoint.url,
                            content=payload_bytes,
                            headers=headers,
                        )
                        delivery.status_code = response.status_code
                        if 200 <= response.status_code < 300:
                            delivery.status = "success"
                            delivery.delivered_at = time.time()
                            return True
                        delivery.error = f"HTTP {response.status_code}"
                except ImportError:
                    # httpx not available, mark as failed gracefully
                    delivery.error = "httpx not installed"
                    delivery.status = "failed"
                    logger.warning(
                        f"Webhook delivery skipped (httpx not installed): {endpoint.url}",
                        component="webhooks",
                    )
                    return False

            except Exception as e:
                delivery.error = str(e)
                logger.warning(
                    f"Webhook delivery failed (attempt {attempt + 1}): {endpoint.url}: {e}",
                    component="webhooks",
                )

            if attempt < self.MAX_RETRIES - 1:
                import asyncio

                await asyncio.sleep(self.RETRY_DELAYS[attempt])

        delivery.status = "failed"
        logger.error(
            f"Webhook delivery exhausted retries: {endpoint.url} event={delivery.event}",
            component="webhooks",
        )
        return False

    def get_deliveries(
        self,
        webhook_id: Optional[str] = None,
        limit: int = 50,
    ) -> List[Dict[str, Any]]:
        """Get delivery history."""
        deliveries = self._deliveries
        if webhook_id:
            deliveries = [d for d in deliveries if d.webhook_id == webhook_id]

        return [
            {
                "id": d.id,
                "webhook_id": d.webhook_id,
                "event": d.event,
                "status": d.status,
                "attempt": d.attempt,
                "status_code": d.status_code,
                "error": d.error,
                "delivered_at": d.delivered_at,
                "created_at": d.created_at,
            }
            for d in deliveries[-limit:]
        ]


# Global singleton
webhook_manager = WebhookManager()
