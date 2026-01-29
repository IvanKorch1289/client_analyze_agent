"""
Публикация сообщений в RabbitMQ через FastStream broker.

Этот модуль нужен, чтобы backend/MCP могли отправлять задачи в очередь (а обработка
шла в отдельном worker процессе).
"""

from __future__ import annotations

import asyncio
from typing import Optional

from faststream.rabbit import RabbitBroker

from app.config import settings
from app.messaging.models import (
    AsyncLLMQueueMessage,
    CacheInvalidateRequest,
    ClientAnalysisRequest,
)


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

    async def close(self) -> None:
        """Закрывает соединение с RabbitMQ (вызывать при shutdown)."""
        if self._connected:
            try:
                await self._broker.close()
            except Exception:
                pass
            self._connected = False

    async def publish_client_analysis(
        self,
        *,
        client_name: str,
        inn: str = "",
        additional_notes: str = "",
        session_id: Optional[str] = None,
        correlation_id: Optional[str] = None,
        save_report: bool = True,
    ) -> None:
        """
        Публикация запроса на анализ клиента в очередь.

        Args:
            client_name: Название компании
            inn: ИНН компании
            additional_notes: Дополнительные заметки
            session_id: ID сессии для трекинга
            correlation_id: ID корреляции для связи запрос-ответ при async взаимодействии
            save_report: Сохранить отчёт в Tarantool
        """
        await self._ensure_connected()
        msg = ClientAnalysisRequest(
            client_name=client_name,
            inn=inn,
            additional_notes=additional_notes,
            session_id=session_id,
            correlation_id=correlation_id,
            save_report=save_report,
        )
        await self._broker.publish(msg, queue=settings.queue.analysis_queue)

    async def publish_cache_invalidate(self, *, prefix: Optional[str] = None, invalidate_all: bool = False) -> None:
        await self._ensure_connected()
        msg = CacheInvalidateRequest(prefix=prefix, invalidate_all=invalidate_all)
        await self._broker.publish(msg, queue=settings.queue.cache_queue)

    async def publish_async_llm_request(
        self,
        *,
        request_id: str,
        prompt: str,
        provider: str,
        callback_url: str,
        system_prompt: Optional[str] = None,
        callback_headers: Optional[dict] = None,
        temperature: float = 0.7,
        max_tokens: int = 4096,
        request_metadata: Optional[dict] = None,
    ) -> None:
        """Publish async LLM request to queue."""
        import time

        await self._ensure_connected()
        msg = AsyncLLMQueueMessage(
            request_id=request_id,
            prompt=prompt,
            system_prompt=system_prompt,
            provider=provider,
            callback_url=callback_url,
            callback_headers=callback_headers,
            temperature=temperature,
            max_tokens=max_tokens,
            request_metadata=request_metadata,
            created_at=time.time(),
        )
        await self._broker.publish(msg, queue=settings.queue.llm_queue)


_publisher: Optional[RabbitPublisher] = None


def get_rabbit_publisher() -> RabbitPublisher:
    global _publisher
    if _publisher is None:
        _publisher = RabbitPublisher()
    return _publisher
