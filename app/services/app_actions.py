"""
Централизованные actions для переиспользования:
- как tools (MCP)
- в HTTP эндпоинтах
- в RabbitMQ worker (FastStream)
- в отложенных задачах (APScheduler)

Идея: все “что делать” живёт здесь, а “как вызвать” (HTTP/RMQ/MCP) — снаружи.
"""

from __future__ import annotations

from typing import Any, Dict, Optional

from app.config import settings
from app.messaging.publisher import get_rabbit_publisher
from app.services.analysis_executor import execute_client_analysis
from app.storage.tarantool import TarantoolClient


async def dispatch_client_analysis(
    *,
    client_name: str,
    inn: str = "",
    additional_notes: str = "",
    save_report: bool = True,
    session_id: Optional[str] = None,
    prefer_queue: Optional[bool] = None,
) -> Dict[str, Any]:
    """
    Выполнить анализ синхронно или поставить в очередь.

    prefer_queue:
      - None: автоматически (settings.queue.enabled)
      - True: принудительно очередь (если доступна)
      - False: принудительно in-process
    """
    use_queue = settings.queue.enabled if prefer_queue is None else bool(prefer_queue)

    if use_queue:
        await get_rabbit_publisher().publish_client_analysis(
            client_name=client_name,
            inn=inn,
            additional_notes=additional_notes,
            save_report=save_report,
            session_id=session_id,
        )
        return {
            "status": "accepted",
            "queued": True,
            "queue": settings.queue.analysis_queue,
            "session_id": session_id,
        }

    result = await execute_client_analysis(
        client_name=client_name,
        inn=inn,
        additional_notes=additional_notes,
        save_report=save_report,
        session_id=session_id,
    )
    result["queued"] = False
    return result


async def dispatch_cache_invalidate(
    *,
    prefix: Optional[str] = None,
    invalidate_all: bool = False,
    prefer_queue: Optional[bool] = None,
) -> Dict[str, Any]:
    """
    Инвалидировать кэш напрямую или через очередь.
    """
    use_queue = settings.queue.enabled if prefer_queue is None else bool(prefer_queue)

    if use_queue:
        await get_rabbit_publisher().publish_cache_invalidate(
            prefix=prefix,
            invalidate_all=invalidate_all,
        )
        return {
            "status": "accepted",
            "queued": True,
            "queue": settings.queue.cache_queue,
            "prefix": prefix,
            "invalidate_all": invalidate_all,
        }

    client = await TarantoolClient.get_instance()
    if invalidate_all:
        await client.clear_cache()
        return {"status": "success", "queued": False, "action": "clear_cache"}

    if prefix:
        await client.delete_by_prefix(prefix)
        return {
            "status": "success",
            "queued": False,
            "action": "delete_by_prefix",
            "prefix": prefix,
        }

    return {"status": "error", "queued": False, "message": "prefix is required"}
