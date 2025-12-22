from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, Optional


@dataclass(frozen=True)
class ServiceStatus:
    """
    Small normalized status object for external/internal services.

    This is intentionally additive: callers can still return their legacy keys,
    but can embed this normalized structure for consistency.
    """

    configured: bool
    available: bool
    status: str  # e.g. "ready" | "not_configured" | "error"
    error: Optional[str] = None
    latency_ms: Optional[float] = None
    integration: Optional[str] = None
    extra: Optional[Dict[str, Any]] = None

    def to_dict(self) -> Dict[str, Any]:
        payload: Dict[str, Any] = {
            "configured": bool(self.configured),
            "available": bool(self.available),
            "status": self.status,
        }
        if self.error is not None:
            payload["error"] = self.error
        if self.latency_ms is not None:
            payload["latency_ms"] = self.latency_ms
        if self.integration is not None:
            payload["integration"] = self.integration
        if self.extra:
            payload.update(self.extra)
        return payload


def status_not_configured(*, error: str, integration: Optional[str] = None, **extra: Any) -> Dict[str, Any]:
    return ServiceStatus(
        configured=False,
        available=False,
        status="not_configured",
        error=error,
        integration=integration,
        extra=extra or None,
    ).to_dict()


def status_ready(*, latency_ms: Optional[float] = None, integration: Optional[str] = None, **extra: Any) -> Dict[str, Any]:
    return ServiceStatus(
        configured=True,
        available=True,
        status="ready",
        latency_ms=latency_ms,
        integration=integration,
        extra=extra or None,
    ).to_dict()


def status_error(
    *,
    configured: bool = True,
    error: str,
    latency_ms: Optional[float] = None,
    integration: Optional[str] = None,
    **extra: Any,
) -> Dict[str, Any]:
    return ServiceStatus(
        configured=bool(configured),
        available=False,
        status="error",
        error=error,
        latency_ms=latency_ms,
        integration=integration,
        extra=extra or None,
    ).to_dict()

