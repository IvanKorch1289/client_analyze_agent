"""
Administrative API Endpoints

Защищенные эндпоинты для администрирования системы:
- Управление кэшем (очистка, статистика)
- LLM статистика и аудит
- Детальные health checks
- System metrics
"""

from typing import Any, Dict, Optional

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field

from app.utility.auth import require_admin_token
from app.utility.logging_client import logger

# Lazy imports для админских операций
_tarantool_client = None
_llm_audit = None
_llm_cache = None

admin_router = APIRouter(prefix="/admin", tags=["Admin"])


# ============================================================================
# RESPONSE MODELS
# ============================================================================


class CacheStatsResponse(BaseModel):
    """Статистика кэша."""

    total_hits: int = Field(..., description="Всего cache hits")
    total_misses: int = Field(..., description="Всего cache misses")
    hit_rate_percent: float = Field(..., description="Hit rate в процентах")
    total_sets: int = Field(..., description="Всего записей")
    llm_cache_size: Optional[int] = Field(None, description="Размер LLM кэша")
    general_cache_size: Optional[int] = Field(None, description="Размер общего кэша")


class LLMStatsResponse(BaseModel):
    """Статистика LLM вызовов."""

    period_hours: int
    total_calls: int
    successful: int
    failed: int
    success_rate: float
    total_tokens: int
    avg_duration_ms: float
    pii_detected_count: int
    pii_detection_rate: float
    fallback_used_count: int
    providers: Dict[str, Dict[str, int]]


class HealthDetailedResponse(BaseModel):
    """Детальный health check."""

    status: str = Field(..., description="Общий статус: healthy/degraded/unhealthy")
    components: Dict[str, Dict[str, Any]] = Field(..., description="Статус компонентов")
    version: Optional[str] = Field(None, description="Версия приложения")
    uptime_seconds: Optional[int] = Field(None, description="Время работы")


class MessageResponse(BaseModel):
    """Общий ответ с сообщением."""

    success: bool
    message: str
    details: Optional[Dict[str, Any]] = None


# ============================================================================
# CACHE MANAGEMENT
# ============================================================================


@admin_router.post(
    "/cache/clear",
    response_model=MessageResponse,
    dependencies=[Depends(require_admin_token)],
)
async def clear_cache(source: Optional[str] = None) -> MessageResponse:
    """
    Очищает кэш (полностью или по source).

    Args:
        source: Опциональный фильтр по source (llm_cache, dadata, etc.)

    Returns:
        Сообщение о результате
    """
    try:
        global _tarantool_client
        if _tarantool_client is None:
            from app.storage.tarantool import get_tarantool_client

            _tarantool_client = get_tarantool_client

        client = await _tarantool_client()

        if source:
            # Очистка по префиксу
            deleted = await client.delete_by_prefix(f"{source}:")
            message = f"Cleared {deleted} entries for source '{source}'"
        else:
            # Полная очистка
            await client.clear_cache()
            message = "Cleared all cache entries"

        logger.info(f"Admin: {message}", component="admin_api")

        return MessageResponse(success=True, message=message)

    except Exception as e:
        logger.error(
            f"Admin cache clear error: {e}", component="admin_api", exc_info=True
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e)
        )


@admin_router.get(
    "/cache/stats",
    response_model=CacheStatsResponse,
    dependencies=[Depends(require_admin_token)],
)
async def get_cache_stats() -> CacheStatsResponse:
    """
    Получает детальную статистику кэша.

    Returns:
        Статистика кэша
    """
    try:
        global _tarantool_client, _llm_cache
        if _tarantool_client is None:
            from app.storage.tarantool import get_tarantool_client

            _tarantool_client = get_tarantool_client

        if _llm_cache is None:
            from app.shared import llm_cache as cache_mod

            _llm_cache = cache_mod

        client = await _tarantool_client()
        metrics = client.get_metrics()

        # LLM cache stats
        llm_cache_stats = await _llm_cache.get_cache_stats()

        return CacheStatsResponse(
            total_hits=metrics.hits,
            total_misses=metrics.misses,
            hit_rate_percent=metrics.hit_rate,
            total_sets=metrics.sets,
            llm_cache_size=llm_cache_stats.get("total_sets", 0),
            general_cache_size=metrics.sets,
        )

    except Exception as e:
        logger.error(
            f"Admin cache stats error: {e}", component="admin_api", exc_info=True
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e)
        )


# ============================================================================
# LLM MANAGEMENT
# ============================================================================


@admin_router.get(
    "/llm/stats",
    response_model=LLMStatsResponse,
    dependencies=[Depends(require_admin_token)],
)
async def get_llm_stats(hours: int = 24) -> LLMStatsResponse:
    """
    Получает статистику LLM вызовов за последние N часов.

    Args:
        hours: Количество часов для анализа (default: 24)

    Returns:
        Статистика LLM вызовов
    """
    try:
        global _llm_audit
        if _llm_audit is None:
            from app.shared import llm_audit as audit_mod

            _llm_audit = audit_mod

        audit_logger = _llm_audit.get_audit_logger()
        stats = await audit_logger.get_statistics(hours=hours)

        return LLMStatsResponse(**stats)

    except Exception as e:
        logger.error(
            f"Admin LLM stats error: {e}", component="admin_api", exc_info=True
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e)
        )


@admin_router.get("/llm/recent", dependencies=[Depends(require_admin_token)])
async def get_recent_llm_calls(limit: int = 50) -> Dict[str, Any]:
    """
    Получает последние N вызовов LLM.

    Args:
        limit: Количество записей (max: 100)

    Returns:
        Список последних LLM вызовов
    """
    try:
        if limit > 100:
            limit = 100

        global _llm_audit
        if _llm_audit is None:
            from app.shared import llm_audit as audit_mod

            _llm_audit = audit_mod

        audit_logger = _llm_audit.get_audit_logger()
        records = await audit_logger.get_recent_calls(limit=limit)

        # Конвертируем в dict для JSON serialization
        return {
            "count": len(records),
            "records": [
                {
                    "request_id": r.request_id,
                    "timestamp": r.timestamp,
                    "provider": r.provider,
                    "model": r.model,
                    "operation": r.operation,
                    "duration_ms": r.duration_ms,
                    "success": r.success,
                    "pii_detected": r.pii_detected,
                    "pii_types": r.pii_types,
                    "total_tokens": r.total_tokens,
                    "fallback_used": r.fallback_used,
                }
                for r in records
            ],
        }

    except Exception as e:
        logger.error(
            f"Admin recent LLM calls error: {e}", component="admin_api", exc_info=True
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e)
        )


# ============================================================================
# HEALTH CHECKS
# ============================================================================


@admin_router.get(
    "/health/detailed",
    response_model=HealthDetailedResponse,
    dependencies=[Depends(require_admin_token)],
)
async def get_detailed_health() -> HealthDetailedResponse:
    """
    Детальный health check всех компонентов системы.

    Returns:
        Детальная информация о здоровье системы
    """
    import time

    start_time = time.time()

    components = {}

    # Tarantool
    try:
        global _tarantool_client
        if _tarantool_client is None:
            from app.storage.tarantool import get_tarantool_client

            _tarantool_client = get_tarantool_client

        client = await _tarantool_client()
        # Простая проверка - получение метрик
        metrics = client.get_metrics()
        components["tarantool"] = {
            "status": "healthy",
            "hit_rate": f"{metrics.hit_rate:.2f}%",
            "entries": metrics.sets,
        }
    except Exception as e:
        components["tarantool"] = {"status": "unhealthy", "error": str(e)}

    # HTTP Client
    try:
        from app.services.http_client import AsyncHttpClient

        http_client = await AsyncHttpClient.get_instance()
        breaker_stats = http_client.get_circuit_breaker_stats()
        components["http_client"] = {
            "status": "healthy",
            "circuit_breakers": {
                name: stats.state for name, stats in breaker_stats.items()
            },
        }
    except Exception as e:
        components["http_client"] = {"status": "unhealthy", "error": str(e)}

    # LLM Manager
    try:
        from app.agents.llm_manager import get_llm_manager

        llm_manager = get_llm_manager()
        llm_health = await llm_manager.check_all_providers_health()
        components["llm"] = {"status": "healthy", "providers": llm_health}
    except Exception as e:
        components["llm"] = {"status": "unhealthy", "error": str(e)}

    # Memory Monitor
    try:
        from app.shared.memory_monitor import get_memory_monitor

        memory_monitor = get_memory_monitor()
        memory_status = memory_monitor.get_status()

        if memory_status["status"] == "healthy":
            components["memory_monitor"] = memory_status
        elif memory_status["status"] == "warning":
            components["memory_monitor"] = {**memory_status, "status": "degraded"}
        else:
            components["memory_monitor"] = memory_status
    except Exception as e:
        components["memory_monitor"] = {"status": "error", "error": str(e)}

    # Определяем общий статус
    unhealthy_count = sum(
        1 for c in components.values() if c.get("status") == "unhealthy"
    )

    if unhealthy_count == 0:
        overall_status = "healthy"
    elif unhealthy_count < len(components) / 2:
        overall_status = "degraded"
    else:
        overall_status = "unhealthy"

    return HealthDetailedResponse(
        status=overall_status,
        components=components,
        version="1.0.0",  # TODO: read from package
        uptime_seconds=int(time.time() - start_time),
    )


# ============================================================================
# SYSTEM METRICS
# ============================================================================


@admin_router.get("/metrics/system", dependencies=[Depends(require_admin_token)])
async def get_system_metrics() -> Dict[str, Any]:
    """
    Получает системные метрики (память, CPU, disk).

    Returns:
        Системные метрики
    """
    try:
        import os
        import psutil

        process = psutil.Process(os.getpid())

        memory_info = process.memory_info()
        cpu_percent = process.cpu_percent(interval=0.1)

        return {
            "memory": {
                "rss_mb": memory_info.rss / 1024 / 1024,
                "vms_mb": memory_info.vms / 1024 / 1024,
                "percent": process.memory_percent(),
            },
            "cpu": {"percent": cpu_percent, "num_threads": process.num_threads()},
            "connections": {
                "open_files": len(process.open_files()),
                "connections": len(process.connections()),
            },
        }

    except Exception as e:
        logger.error(
            f"Admin system metrics error: {e}", component="admin_api", exc_info=True
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e)
        )


__all__ = ["admin_router"]
