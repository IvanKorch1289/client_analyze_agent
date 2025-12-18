"""
RabbitMQ broker и обработчики сообщений (FastStream).

Важно:
- Создание `RabbitBroker(...)` не подключается к RabbitMQ сразу (соединение будет
  установлено при запуске worker'а или при явном `connect()`).
- Этот модуль используется и для генерации AsyncAPI спецификации.
"""

from __future__ import annotations

from typing import Any, Dict

from faststream.rabbit import RabbitBroker

from app.config import settings
from app.messaging.models import CacheInvalidateRequest, ClientAnalysisRequest, ClientAnalysisResult
from app.services.analysis_executor import execute_client_analysis
from app.storage.tarantool import TarantoolClient
from app.utility.logging_client import logger


def get_rabbit_broker() -> RabbitBroker:
    """
    Фабрика broker'а.

    Держим в виде функции, чтобы импорт не имел побочных эффектов и было проще
    мокать в тестах.
    """
    return RabbitBroker(settings.queue.amqp_url)


broker = get_rabbit_broker()


@broker.subscriber(settings.queue.analysis_queue)
async def handle_client_analysis(msg: ClientAnalysisRequest) -> ClientAnalysisResult:
    """
    Обработчик очереди анализа клиента.

    На вход принимает `ClientAnalysisRequest`, на выход возвращает `ClientAnalysisResult`.
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


@broker.subscriber(settings.queue.cache_queue)
async def handle_cache_invalidate(msg: CacheInvalidateRequest) -> Dict[str, Any]:
    """
    Обработчик инвалидации кэша.

    Поддерживает:
    - invalidate_all = true
    - delete_by_prefix(prefix)
    """
    client = await TarantoolClient.get_instance()

    if msg.invalidate_all:
        await client.clear_cache()
        return {"status": "success", "action": "clear_cache"}

    if msg.prefix:
        await client.delete_by_prefix(msg.prefix)
        return {"status": "success", "action": "delete_by_prefix", "prefix": msg.prefix}

    return {"status": "error", "message": "prefix is required when invalidate_all=false"}

