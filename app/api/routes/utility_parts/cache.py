from __future__ import annotations

from typing import Any, Dict, List

from fastapi import Depends, Request

from app.api.compat import is_versioned_request
from app.api.response import ok
from app.api.routes.utility import limiter, utility_router
from app.config.constants import RATE_LIMIT_ADMIN_PER_MINUTE
from app.storage.tarantool import TarantoolClient
from app.utility.auth import require_admin


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
        # Keep legacy keys, add normalized `data`.
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

