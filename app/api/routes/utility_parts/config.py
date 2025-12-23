from __future__ import annotations

from typing import Any, Dict

from fastapi import Depends, Request

from app.api.routes.utility import limiter, utility_router
from app.config.constants import RATE_LIMIT_ADMIN_PER_MINUTE
from app.config.reload import get_reload_state, reload_settings
from app.config.settings import settings
from app.utility.auth import require_admin


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
