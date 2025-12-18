"""
Публикация сообщений в RabbitMQ через FastStream broker.

Этот модуль нужен, чтобы backend/MCP могли отправлять задачи в очередь (а обработка
шла в отдельном worker процессе).
"""

from __future__ import annotations

import asyncio
from typing import Any, Dict, Optional

from faststream.rabbit import RabbitBroker

from app.config import settings
from app.messaging.models import CacheInvalidateRequest, ClientAnalysisRequest


class RabbitPublisher:
    """
    Лёгкий publisher с ленивым подключением.

    Примечание:
    - Подключение создаётся при первом publish.
    - В рамках FastAPI процесса держим один broker, чтобы не создавать TCP-соединения
      для каждого publish.
    """

    def __init__(self) -> None:
        self._broker = RabbitBroker(settings.queue.amqp_url)
        self._lock = asyncio.Lock()
        self._connected = False

    async def _ensure_connected(self) -> None:
        if self._connected:
            return
        async with self._lock:
            if self._connected:
                return
            await self._broker.connect()
            self._connected = True

    async def publish_client_analysis(
        self,
        *,
        client_name: str,
        inn: str = "",
        additional_notes: str = "",
        session_id: Optional[str] = None,
        save_report: bool = True,
    ) -> None:
        await self._ensure_connected()
        msg = ClientAnalysisRequest(
            client_name=client_name,
            inn=inn,
            additional_notes=additional_notes,
            session_id=session_id,
            save_report=save_report,
        )
        await self._broker.publish(msg, queue=settings.queue.analysis_queue)

    async def publish_cache_invalidate(
        self, *, prefix: Optional[str] = None, invalidate_all: bool = False
    ) -> None:
        await self._ensure_connected()
        msg = CacheInvalidateRequest(prefix=prefix, invalidate_all=invalidate_all)
        await self._broker.publish(msg, queue=settings.queue.cache_queue)


_publisher: Optional[RabbitPublisher] = None


def get_rabbit_publisher() -> RabbitPublisher:
    global _publisher
    if _publisher is None:
        _publisher = RabbitPublisher()
    return _publisher

