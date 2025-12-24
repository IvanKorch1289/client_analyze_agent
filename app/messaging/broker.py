"""
RabbitMQ broker и обработчики сообщений (FastStream).

Важно:
- Создание `RabbitBroker(...)` не подключается к RabbitMQ сразу (соединение будет
  установлено при запуске worker'а или при явном `connect()`).
- Этот модуль используется и для генерации AsyncAPI спецификации.

P1-1: Добавлена поддержка Dead Letter Queue (DLQ) для обработки failed messages.
"""

from __future__ import annotations

import time
from typing import Any, Dict

from faststream.rabbit import ExchangeType, RabbitBroker, RabbitExchange, RabbitQueue

from app.config import settings
from app.messaging.models import (
    CacheInvalidateRequest,
    ClientAnalysisRequest,
    ClientAnalysisResult,
)
from app.services.analysis_executor import execute_client_analysis
from app.services.app_actions import dispatch_cache_invalidate
from app.utility.logging_client import logger


def get_rabbit_broker() -> RabbitBroker:
    """
    Фабрика broker'а с настройкой DLQ (Dead Letter Queue).
    
    P1-1: При ошибке обработки сообщение отправляется в DLX (Dead Letter Exchange),
    откуда попадает в dlq.* очередь для дальнейшего анализа.
    
    Держим в виде функции, чтобы импорт не имел побочных эффектов и было проще
    мокать в тестах.
    """
    return RabbitBroker(settings.queue.amqp_url)


broker = get_rabbit_broker()


# P1-1: Настройка очередей с DLQ поддержкой
_dlx = RabbitExchange("dlx", type=ExchangeType.TOPIC, durable=True)

_analysis_queue = RabbitQueue(
    settings.queue.analysis_queue,
    durable=True,
    routing_key=settings.queue.analysis_queue,
    arguments={
        "x-dead-letter-exchange": "dlx",
        "x-dead-letter-routing-key": "dlq.analysis",
        "x-message-ttl": 3600000,  # 1 час TTL для сообщений
    },
)

_cache_queue = RabbitQueue(
    settings.queue.cache_queue,
    durable=True,
    routing_key=settings.queue.cache_queue,
    arguments={
        "x-dead-letter-exchange": "dlx",
        "x-dead-letter-routing-key": "dlq.cache",
    },
)


@broker.subscriber(_analysis_queue)
async def handle_client_analysis(msg: ClientAnalysisRequest) -> ClientAnalysisResult:
    """
    Обработчик очереди анализа клиента.

    На вход принимает `ClientAnalysisRequest`, на выход возвращает `ClientAnalysisResult`.
    
    P1-1: При ошибке сообщение автоматически отправляется в DLQ.
    """
    logger.info(
        f"Получено сообщение анализа: {msg.client_name} (ИНН: {msg.inn})",
        component="faststream",
    )

    result: Dict[str, Any] = await execute_client_analysis(
        client_name=msg.client_name,
        inn=msg.inn,
        additional_notes=msg.additional_notes,
        save_report=msg.save_report,
        session_id=msg.session_id,
    )

    return ClientAnalysisResult(
        status=str(result.get("status", "unknown")),
        session_id=result.get("session_id"),
        summary=result.get("summary"),
        raw_result=result,
    )


@broker.subscriber(_cache_queue)
async def handle_cache_invalidate(msg: CacheInvalidateRequest) -> Dict[str, Any]:
    """
    Обработчик инвалидации кэша.

    Поддерживает:
    - invalidate_all = true
    - delete_by_prefix(prefix)
    
    P1-1: При ошибке сообщение автоматически отправляется в DLQ.
    """
    # В воркере выполняем строго "напрямую", чтобы не зациклиться на публикации.
    return await dispatch_cache_invalidate(
        prefix=msg.prefix,
        invalidate_all=msg.invalidate_all,
        prefer_queue=False,
    )


# =============================================================================
# P1-1: DEAD LETTER QUEUE HANDLERS
# =============================================================================

@broker.subscriber(
    RabbitQueue("dlq.analysis", durable=True, routing_key="dlq.analysis"),
    exchange=_dlx
)
async def handle_failed_analysis(msg: ClientAnalysisRequest) -> None:
    """
    P1-1: Обработчик failed сообщений из analysis очереди.
    
    Логирует ошибку и сохраняет в persistent storage для анализа.
    """
    logger.error(
        f"Failed message in DLQ: {msg.client_name} (INN: {msg.inn}), session_id={msg.session_id}",
        component="faststream_dlq",
    )
    
    # Сохраняем в Tarantool для дальнейшего анализа
    try:
        from app.storage.tarantool import TarantoolClient
        client = await TarantoolClient.get_instance()
        
        await client.set_persistent(
            key=f"dlq:analysis:{msg.session_id or int(time.time())}",
            value={
                "type": "failed_analysis",
                "message": msg.model_dump(),
                "timestamp": time.time(),
            }
        )
        logger.info(f"DLQ message saved to persistent storage", component="faststream_dlq")
    except Exception as e:
        logger.error(f"Failed to save DLQ message: {e}", component="faststream_dlq")


@broker.subscriber(
    RabbitQueue("dlq.cache", durable=True, routing_key="dlq.cache"),
    exchange=_dlx
)
async def handle_failed_cache(msg: CacheInvalidateRequest) -> None:
    """P1-1: Обработчик failed cache invalidation сообщений."""
    logger.error(
        f"Failed cache invalidation in DLQ: prefix={msg.prefix}, invalidate_all={msg.invalidate_all}",
        component="faststream_dlq"
    )
