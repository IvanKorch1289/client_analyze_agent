"""
Administrative API Endpoints

Защищенные эндпоинты для администрирования системы:
- Управление кэшем (очистка, статистика)
- LLM статистика и аудит
- Детальные health checks
- System metrics
"""

from typing import Any, Dict, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field

from app.config.constants import APP_VERSION
from app.utility.auth import require_admin
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
    dependencies=[Depends(require_admin)],
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
        logger.error(f"Admin cache clear error: {e}", component="admin_api", exc_info=True)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))


@admin_router.get(
    "/cache/stats",
    response_model=CacheStatsResponse,
    dependencies=[Depends(require_admin)],
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
        logger.error(f"Admin cache stats error: {e}", component="admin_api", exc_info=True)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))


# ============================================================================
# LLM MANAGEMENT
# ============================================================================


@admin_router.get(
    "/llm/stats",
    response_model=LLMStatsResponse,
    dependencies=[Depends(require_admin)],
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
        logger.error(f"Admin LLM stats error: {e}", component="admin_api", exc_info=True)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))


@admin_router.get("/llm/recent", dependencies=[Depends(require_admin)])
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
        logger.error(f"Admin recent LLM calls error: {e}", component="admin_api", exc_info=True)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))


# ============================================================================
# HEALTH CHECKS
# ============================================================================


@admin_router.get(
    "/health/detailed",
    response_model=HealthDetailedResponse,
    dependencies=[Depends(require_admin)],
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
            "circuit_breakers": {name: stats.state for name, stats in breaker_stats.items()},
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
    unhealthy_count = sum(1 for c in components.values() if c.get("status") == "unhealthy")

    if unhealthy_count == 0:
        overall_status = "healthy"
    elif unhealthy_count < len(components) / 2:
        overall_status = "degraded"
    else:
        overall_status = "unhealthy"

    return HealthDetailedResponse(
        status=overall_status,
        components=components,
        version=APP_VERSION,
        uptime_seconds=int(time.time() - start_time),
    )


# ============================================================================
# SYSTEM METRICS
# ============================================================================


@admin_router.get("/metrics/system", dependencies=[Depends(require_admin)])
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
        logger.error(f"Admin system metrics error: {e}", component="admin_api", exc_info=True)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))


@admin_router.get("/metrics/connection-pool", dependencies=[Depends(require_admin)])
async def get_connection_pool_stats() -> Dict[str, Any]:
    """
    Получает статистику HTTP connection pool для мониторинга эффективности.

    Sprint 2: Connection pooling monitoring endpoint.

    Returns:
        Метрики connection pool:
        - connections_count: активные соединения
        - max_connections: максимум параллельных
        - pool_utilization_pct: процент использования пула
        - http2_enabled: поддержка HTTP/2
    """
    try:
        from app.services.http_client import AsyncHttpClient

        client = await AsyncHttpClient.get_instance()
        stats = client.get_connection_pool_stats()

        return {
            "status": "success",
            "connection_pool": stats,
            "optimization": "pooling_enabled",
            "notes": [
                "Connection pool optimized for high throughput",
                "max_connections: 100",
                "max_keepalive_connections: 50",
            ],
        }

    except Exception as e:
        logger.error(f"Connection pool stats error: {e}", component="admin_api", exc_info=True)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))


# ============================================================================
# LLM AUDIT
# ============================================================================


@admin_router.get("/audit/llm", dependencies=[Depends(require_admin)])
async def get_llm_audit(
    period: int = Query(24, description="Период в часах", ge=1, le=720),
    limit: int = Query(100, description="Лимит записей", ge=1, le=1000),
) -> Dict[str, Any]:
    """
    Получает audit trail LLM вызовов для compliance и мониторинга.

    Endpoint для детального просмотра всех LLM вызовов:
    - Хэши промптов/ответов (не сами тексты для безопасности)
    - Detected PII types
    - Privacy mode
    - Duration, success rate, fallback usage
    - Провайдеры и модели

    Args:
        period: Период в часах (default: 24, max: 720 = 30 дней)
        limit: Количество записей (default: 100, max: 1000)

    Returns:
        Dict с statistics и recent_calls

    Example:
        GET /admin/audit/llm?period=24&limit=50
    """
    try:
        from app.shared.llm_audit import get_audit_logger

        audit_logger = get_audit_logger()

        # Получаем статистику за период
        statistics = await audit_logger.get_statistics(hours=period)

        # Получаем недавние вызовы
        recent_calls_records = await audit_logger.get_recent_calls(limit=limit)

        # Фильтруем по периоду
        from datetime import datetime, timedelta, timezone

        cutoff = datetime.now(timezone.utc) - timedelta(hours=period)

        recent_calls = []
        for record in recent_calls_records:
            try:
                timestamp = datetime.fromisoformat(record.timestamp.replace("Z", "+00:00"))
                if timestamp < cutoff:
                    continue
            except Exception:
                # Если ошибка парсинга timestamp, включаем запись
                pass

            recent_calls.append(
                {
                    "timestamp": record.timestamp,
                    "request_id": record.request_id,
                    "provider": record.provider,
                    "model": record.model,
                    "operation": record.operation,
                    "duration_ms": record.duration_ms,
                    "success": record.success,
                    "error": record.error,
                    "pii_detected": record.pii_detected,
                    "pii_types": record.pii_types,
                    "prompt_hash": record.prompt_hash,
                    "response_hash": record.response_hash,
                    "privacy_mode": record.privacy_mode,
                    "tokens": record.total_tokens,
                    "temperature": record.temperature,
                    "fallback_used": record.fallback_used,
                }
            )

        return {
            "status": "success",
            "period_hours": period,
            "limit": limit,
            "statistics": statistics,
            "recent_calls_count": len(recent_calls),
            "recent_calls": recent_calls,
        }

    except Exception as e:
        logger.error(f"LLM Audit retrieval failed: {e}", exc_info=True, component="admin_api")
        return {
            "status": "error",
            "message": str(e),
            "statistics": None,
            "recent_calls": [],
        }


# ============================================================================
# NEW ENDPOINTS - Sprint 3
# ============================================================================


@admin_router.post("/llm/test-provider/{provider}", dependencies=[Depends(require_admin)])
async def test_llm_provider(provider: str) -> Dict[str, Any]:
    """
    Тестирование конкретного LLM провайдера.

    Отправляет тестовый запрос в указанный LLM и возвращает результат.
    Полезно для диагностики проблем с fallback цепочкой.

    Args:
        provider: Имя провайдера (openrouter, huggingface, gigachat, yandexgpt)

    Returns:
        {
            "provider": str,
            "status": "success" | "error",
            "response_preview": str,
            "duration_ms": float,
            "error": str | None
        }

    Example:
        POST /admin/llm/test-provider/openrouter
        → {"provider": "openrouter", "status": "success", "duration_ms": 1250.5}
    """
    import time

    from app.agents.llm_manager import LLMProvider, get_llm_manager

    # Проверка валидности провайдера
    try:
        provider_enum = LLMProvider(provider)
    except ValueError:
        available = [p.value for p in LLMProvider]
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Неизвестный провайдер: {provider}. Доступные: {available}",
        )

    manager = get_llm_manager()

    start_time = time.time()
    try:
        # Простой тестовый запрос
        test_prompt = "Ответь 'OK' если получил это сообщение"
        response = await manager.ainvoke_with_provider(prompt=test_prompt, provider=provider_enum, mask_pii=False)

        duration_ms = (time.time() - start_time) * 1000

        logger.info(
            f"LLM provider test successful: {provider}",
            component="admin_api",
            duration_ms=duration_ms,
        )

        return {
            "provider": provider,
            "status": "success",
            "response_preview": response[:200] if response else "[пустой ответ]",
            "duration_ms": round(duration_ms, 2),
            "error": None,
        }

    except Exception as e:
        duration_ms = (time.time() - start_time) * 1000

        logger.error(
            f"LLM provider test failed: {provider} - {e}",
            exc_info=True,
            component="admin_api",
        )

        return {
            "provider": provider,
            "status": "error",
            "response_preview": None,
            "duration_ms": round(duration_ms, 2),
            "error": str(e),
        }


@admin_router.get("/storage/disk-usage", dependencies=[Depends(require_admin)])
async def get_disk_usage() -> Dict[str, Any]:
    """
    Использование дискового пространства.

    Мониторинг размера отчетов, логов, временных файлов.

    Returns:
        {
            "reports": {"path": str, "size_mb": float, "file_count": int},
            "logs": {"path": str, "size_mb": float, "file_count": int},
            "temp": {"path": str, "size_mb": float, "file_count": int}
        }

    Example:
        GET /admin/storage/disk-usage
        → {"reports": {"size_mb": 125.5, "file_count": 350}, ...}
    """
    from pathlib import Path

    def get_dir_size(path: Path) -> int:
        """Рекурсивный подсчет размера директории в байтах."""
        total = 0
        try:
            for entry in path.rglob("*"):
                if entry.is_file():
                    total += entry.stat().st_size
        except PermissionError:
            logger.warning(f"Permission denied accessing {path}", component="admin_api")
        return total

    def get_file_count(path: Path) -> int:
        """Подсчет количества файлов в директории."""
        try:
            return len([f for f in path.rglob("*") if f.is_file()])
        except PermissionError:
            return 0

    # Директории для проверки
    reports_dir = Path("./reports")
    logs_dir = Path("./logs")
    temp_dir = Path("./temp")

    result = {}

    for name, directory in [
        ("reports", reports_dir),
        ("logs", logs_dir),
        ("temp", temp_dir),
    ]:
        if directory.exists():
            size_bytes = get_dir_size(directory)
            result[name] = {
                "path": str(directory.absolute()),
                "exists": True,
                "size_bytes": size_bytes,
                "size_mb": round(size_bytes / 1024 / 1024, 2),
                "file_count": get_file_count(directory),
            }
        else:
            result[name] = {
                "path": str(directory.absolute()),
                "exists": False,
                "size_bytes": 0,
                "size_mb": 0.0,
                "file_count": 0,
            }

    # Общая статистика
    total_size_mb = sum(d["size_mb"] for d in result.values())
    total_files = sum(d["file_count"] for d in result.values())

    return {
        "status": "success",
        "total_size_mb": round(total_size_mb, 2),
        "total_file_count": total_files,
        "directories": result,
    }


@admin_router.post("/storage/cleanup", dependencies=[Depends(require_admin)])
async def cleanup_old_files(days: int = Query(30, ge=1, le=365)) -> Dict[str, Any]:
    """
    Очистка файлов старше N дней.

    Удаляет старые файлы из директорий reports, logs, temp.

    Args:
        days: Удалить файлы старше указанного количества дней (1-365)

    Returns:
        {
            "status": "completed",
            "deleted_files_count": int,
            "cutoff_days": int,
            "deleted_by_directory": Dict[str, int]
        }

    Example:
        POST /admin/storage/cleanup?days=30
        → {"status": "completed", "deleted_files_count": 42, ...}
    """
    import time
    from pathlib import Path

    cutoff_time = time.time() - (days * 86400)
    deleted_files = []
    deleted_by_dir = {"reports": 0, "logs": 0, "temp": 0}

    for dir_name in ["reports", "logs", "temp"]:
        directory = Path(f"./{dir_name}")

        if not directory.exists():
            logger.info(f"Directory {directory} does not exist, skipping", component="admin_api")
            continue

        for file_path in directory.rglob("*"):
            if not file_path.is_file():
                continue

            try:
                # Проверка возраста файла
                if file_path.stat().st_mtime < cutoff_time:
                    file_path.unlink()
                    deleted_files.append(str(file_path))
                    deleted_by_dir[dir_name] += 1

                    logger.debug(f"Deleted old file: {file_path}", component="admin_api")

            except Exception as e:
                logger.error(
                    f"Failed to delete {file_path}: {e}",
                    exc_info=True,
                    component="admin_api",
                )

    logger.info(
        f"Storage cleanup completed: {len(deleted_files)} files deleted (>{days} days old)",
        component="admin_api",
        deleted_by_dir=deleted_by_dir,
    )

    return {
        "status": "completed",
        "deleted_files_count": len(deleted_files),
        "cutoff_days": days,
        "deleted_by_directory": deleted_by_dir,
    }


@admin_router.post("/cache/warmup", dependencies=[Depends(require_admin)])
async def warmup_cache() -> Dict[str, Any]:
    """
    Прогрев кэша популярными запросами.

    Полезно после рестарта сервиса или очистки кэша.
    Загружает в кэш данные для часто запрашиваемых компаний.

    Returns:
        {
            "status": "completed",
            "queries_warmed": int,
            "details": List[Dict[str, Any]]
        }

    Example:
        POST /admin/cache/warmup
        → {"status": "completed", "queries_warmed": 5, ...}
    """
    # Популярные ИНН для прогрева (примеры крупных компаний РФ)
    popular_inns = [
        "7707083893",  # Сбербанк
        "7736050003",  # ВТБ
        "7702070139",  # Газпром
        "7717329710",  # Яндекс
        "7729563872",  # Mail.ru Group (VK)
    ]

    results = []

    for inn in popular_inns:
        try:
            # Пробуем загрузить из кэша или сделать запрос
            from app.services.external_api.dadata import fetch_from_dadata

            result = await fetch_from_dadata(inn=inn)

            if result.get("success"):
                results.append(
                    {
                        "inn": inn,
                        "status": "success",
                        "company_name": result.get("data", {}).get("name", {}).get("short_with_opf", "N/A"),
                    }
                )
                logger.debug(f"Cache warmed for INN: {inn}", component="admin_api")
            else:
                results.append({"inn": inn, "status": "not_found", "company_name": None})

        except Exception as e:
            logger.error(
                f"Failed to warm cache for INN {inn}: {e}",
                exc_info=True,
                component="admin_api",
            )
            results.append({"inn": inn, "status": "error", "error": str(e)})

    successful_count = sum(1 for r in results if r["status"] == "success")

    logger.info(
        f"Cache warmup completed: {successful_count}/{len(popular_inns)} successful",
        component="admin_api",
    )

    return {
        "status": "completed",
        "queries_warmed": successful_count,
        "total_attempted": len(popular_inns),
        "details": results,
    }


__all__ = ["admin_router"]
