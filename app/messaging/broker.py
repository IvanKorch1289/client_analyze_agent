"""
RabbitMQ broker и обработчики сообщений (FastStream).

Важно:
- Создание `RabbitBroker(...)` не подключается к RabbitMQ сразу (соединение будет
  установлено при запуске worker'а или при явном `connect()`).
- Этот модуль используется и для генерации AsyncAPI спецификации.

P1-1: Добавлена поддержка Dead Letter Queue (DLQ) для обработки failed messages.
"""

from __future__ import annotations

import os
import time
from typing import Any, Dict

from faststream.rabbit import ExchangeType, RabbitBroker, RabbitExchange, RabbitQueue

from app.config import settings
from app.messaging.models import (
    AsyncLLMQueueMessage,
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

_MAX_DELIVERY_ATTEMPTS = int(os.environ.get("MAX_DELIVERY_ATTEMPTS", "3"))

_analysis_queue = RabbitQueue(
    settings.queue.analysis_queue,
    durable=True,
    routing_key=settings.queue.analysis_queue,
    arguments={
        "x-dead-letter-exchange": "dlx",
        "x-dead-letter-routing-key": "dlq.analysis",
        "x-message-ttl": 3600000,  # 1 час TTL для сообщений
        "x-delivery-limit": _MAX_DELIVERY_ATTEMPTS,
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

_llm_queue = RabbitQueue(
    settings.queue.llm_queue,
    durable=True,
    routing_key=settings.queue.llm_queue,
    arguments={
        "x-dead-letter-exchange": "dlx",
        "x-dead-letter-routing-key": "dlq.llm",
        "x-message-ttl": 300000,  # 5 min TTL
        "x-delivery-limit": _MAX_DELIVERY_ATTEMPTS,
    },
)


@broker.subscriber(_analysis_queue)
async def handle_client_analysis(msg: ClientAnalysisRequest) -> ClientAnalysisResult:
    """
    Обработчик очереди анализа клиента.

    На вход принимает `ClientAnalysisRequest`, на выход возвращает `ClientAnalysisResult`.

    Поддержка correlation_id:
    - Входящий запрос может содержать correlation_id для отслеживания
    - Ответ возвращает тот же correlation_id для связи запрос-ответ

    P1-1: При ошибке сообщение автоматически отправляется в DLQ.
    """
    logger.info(
        f"Получено сообщение анализа: {msg.client_name} (ИНН: {msg.inn}), correlation_id={msg.correlation_id}",
        component="faststream",
    )

    result: Dict[str, Any] = await execute_client_analysis(
        client_name=msg.client_name,
        inn=msg.inn,
        additional_notes=msg.additional_notes,
        save_report=msg.save_report,
        session_id=msg.session_id,
        correlation_id=msg.correlation_id,
    )

    return ClientAnalysisResult(
        status=str(result.get("status", "unknown")),
        session_id=result.get("session_id"),
        correlation_id=result.get("correlation_id"),
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


@broker.subscriber(_llm_queue)
async def handle_async_llm_request(msg: AsyncLLMQueueMessage) -> Dict[str, Any]:
    """
    Обработчик асинхронных LLM запросов.

    Выполняет LLM вызов и отправляет результат на callback URL.
    """
    import httpx

    from app.agents.llm_manager import LLMProvider, get_llm_manager

    start_time = time.perf_counter()
    callback_payload: Dict[str, Any]

    logger.info(
        f"Processing async LLM request: {msg.request_id} (provider: {msg.provider})",
        component="faststream",
    )

    try:
        manager = get_llm_manager()

        # Map string provider to enum
        provider_map = {
            "openrouter": LLMProvider.OPENROUTER,
            "huggingface": LLMProvider.HUGGINGFACE,
            "gigachat": LLMProvider.GIGACHAT,
            "yandexgpt": LLMProvider.YANDEXGPT,
            "openllama": LLMProvider.OPENROUTER,  # Fallback
        }

        llm_provider = provider_map.get(msg.provider, LLMProvider.OPENROUTER)

        # Build full prompt
        full_prompt = msg.prompt
        if msg.system_prompt:
            full_prompt = f"{msg.system_prompt}\n\n{msg.prompt}"

        # Call LLM
        response = await manager.ainvoke_with_provider(
            prompt=full_prompt,
            provider=llm_provider,
            temperature=msg.temperature,
            max_tokens=msg.max_tokens,
        )

        processing_time = (time.perf_counter() - start_time) * 1000

        callback_payload = {
            "request_id": msg.request_id,
            "status": "success",
            "provider_used": msg.provider,
            "response": response,
            "processing_time_ms": processing_time,
            "request_metadata": msg.request_metadata,
        }

        logger.structured(
            "info",
            "async_llm_completed",
            request_id=msg.request_id,
            provider=msg.provider,
            processing_time_ms=round(processing_time, 2),
        )

    except Exception as e:
        processing_time = (time.perf_counter() - start_time) * 1000

        callback_payload = {
            "request_id": msg.request_id,
            "status": "error",
            "provider_used": msg.provider,
            "error": str(e),
            "processing_time_ms": processing_time,
            "request_metadata": msg.request_metadata,
        }

        logger.error(
            f"Async LLM request {msg.request_id} failed: {e}",
            component="faststream",
        )

    # Send callback
    try:
        headers = dict(msg.callback_headers) if msg.callback_headers else {}
        headers["Content-Type"] = "application/json"

        async with httpx.AsyncClient() as client:
            callback_response = await client.post(
                msg.callback_url,
                json=callback_payload,
                headers=headers,
                timeout=30.0,
            )
            logger.info(
                f"Callback sent for {msg.request_id}: status {callback_response.status_code}",
                component="faststream",
            )
    except Exception as e:
        logger.error(
            f"Callback failed for {msg.request_id}: {e}",
            component="faststream",
        )

    return callback_payload


# =============================================================================
# P1-1: DEAD LETTER QUEUE HANDLERS
# =============================================================================


@broker.subscriber(RabbitQueue("dlq.analysis", durable=True, routing_key="dlq.analysis"), exchange=_dlx)
async def handle_failed_analysis(msg: ClientAnalysisRequest) -> None:
    """
    P1-1: Обработчик failed сообщений из analysis очереди.

    Логирует ошибку и сохраняет в persistent storage для анализа.
    Включает correlation_id для отслеживания failed запросов.
    """
    logger.error(
        f"Failed message in DLQ: {msg.client_name} (INN: {msg.inn}), "
        f"session_id={msg.session_id}, correlation_id={msg.correlation_id}",
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
            },
        )
        logger.info("DLQ message saved to persistent storage", component="faststream_dlq")
    except Exception as e:
        logger.error(f"Failed to save DLQ message: {e}", component="faststream_dlq")


@broker.subscriber(RabbitQueue("dlq.cache", durable=True, routing_key="dlq.cache"), exchange=_dlx)
async def handle_failed_cache(msg: CacheInvalidateRequest) -> None:
    """P1-1: Обработчик failed cache invalidation сообщений."""
    logger.error(
        f"Failed cache invalidation in DLQ: prefix={msg.prefix}, invalidate_all={msg.invalidate_all}",
        component="faststream_dlq",
    )


@broker.subscriber(RabbitQueue("dlq.llm", durable=True, routing_key="dlq.llm"), exchange=_dlx)
async def handle_failed_llm(msg: AsyncLLMQueueMessage) -> None:
    """
    P1-1: Обработчик failed LLM сообщений.

    При неуспешной обработке LLM запроса:
    1. Логируем ошибку
    2. Пытаемся отправить callback с информацией об ошибке
    3. Сохраняем в persistent storage для анализа
    """
    import httpx

    logger.error(
        f"Failed LLM request in DLQ: request_id={msg.request_id}, provider={msg.provider}",
        component="faststream_dlq",
    )

    # Пытаемся уведомить callback URL об ошибке
    try:
        callback_payload = {
            "request_id": msg.request_id,
            "status": "error",
            "provider_used": msg.provider,
            "error": "Message processing failed and moved to DLQ",
            "request_metadata": msg.request_metadata,
        }

        headers = dict(msg.callback_headers) if msg.callback_headers else {}
        headers["Content-Type"] = "application/json"

        async with httpx.AsyncClient() as client:
            await client.post(
                msg.callback_url,
                json=callback_payload,
                headers=headers,
                timeout=10.0,
            )
        logger.info(f"DLQ error callback sent for {msg.request_id}", component="faststream_dlq")
    except Exception as e:
        logger.warning(f"Failed to send DLQ callback: {e}", component="faststream_dlq")

    # Сохраняем в persistent storage
    try:
        from app.storage.tarantool import TarantoolClient

        client = await TarantoolClient.get_instance()

        await client.set_persistent(
            key=f"dlq:llm:{msg.request_id}",
            value={
                "type": "failed_llm",
                "request_id": msg.request_id,
                "provider": msg.provider,
                "callback_url": msg.callback_url,
                "timestamp": time.time(),
            },
        )
    except Exception as e:
        logger.error(f"Failed to save LLM DLQ message: {e}", component="faststream_dlq")
