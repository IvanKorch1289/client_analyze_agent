"""
Единый исполнитель анализа клиента (worker/scheduler/MCP).
"""

from __future__ import annotations

import asyncio
from typing import Any, Dict, Optional

from app.config.settings import settings
from app.utility.logging_client import logger

# Максимальное время выполнения анализа (секунды). Конфигурируется через APP_ANALYSIS_TIMEOUT_SECONDS.
ANALYSIS_TIMEOUT_SECONDS = settings.app.analysis_timeout_seconds


async def execute_client_analysis(
    client_name: str,
    inn: str,
    additional_notes: str = "",
    *,
    save_report: bool = True,
    session_id: Optional[str] = None,
    correlation_id: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Запустить workflow анализа клиента и (опционально) сохранить отчёт в Tarantool.

    Это "единый источник правды" для:
    - APScheduler задач
    - FastStream worker (RabbitMQ listener)
    - MCP tools
    - HTTP API routes

    Args:
        client_name: Название контрагента
        inn: ИНН (10/12 цифр) или пусто
        additional_notes: Доп. контекст
        save_report: Сохранять ли отчёт в `reports` space (best-effort)
        session_id: Явный session_id (если нужен внешний трекинг)
        correlation_id: ID корреляции для связи запрос-ответ при async взаимодействии

    Returns:
        dict: Результат workflow (как возвращает `run_client_analysis_batch`)
              Включает correlation_id в ответе, если он был передан
    """
    from app.agents.client_workflow import run_client_analysis_batch
    from app.storage.tarantool import TarantoolClient

    logger.info(
        f"Запуск анализа клиента: {client_name} (ИНН: {inn})",
        component="analysis_executor",
    )
    logger.structured(
        "debug",
        "analysis_execute_start",
        component="analysis_executor",
        client_name=client_name,
        inn=inn,
        save_report=bool(save_report),
        session_id=session_id,
        correlation_id=correlation_id,
    )

    try:
        result = await asyncio.wait_for(
            run_client_analysis_batch(
                client_name=client_name,
                inn=inn,
                additional_notes=additional_notes,
                session_id=session_id,
            ),
            timeout=ANALYSIS_TIMEOUT_SECONDS,
        )
    except asyncio.TimeoutError:
        logger.error(
            f"Analysis timed out after {ANALYSIS_TIMEOUT_SECONDS}s for {client_name}",
            component="analysis_executor",
        )
        result = {
            "status": "error",
            "error": f"Analysis timed out after {ANALYSIS_TIMEOUT_SECONDS}s",
            "client_name": client_name,
            "inn": inn,
        }

    # Добавляем correlation_id в результат для отслеживания запрос-ответ
    if correlation_id:
        result["correlation_id"] = correlation_id

    if not save_report:
        logger.structured(
            "debug",
            "analysis_execute_end",
            component="analysis_executor",
            status=result.get("status"),
            session_id=result.get("session_id"),
            correlation_id=correlation_id,
            saved_report=False,
        )
        return result

    try:
        # Сохраняем результат в Tarantool (best-effort).
        # Если Tarantool недоступен, workflow всё равно полезен (отдаём результат).
        client = await TarantoolClient.get_instance()
        if result.get("status") == "completed" and result.get("report"):
            reports_repo = client.get_reports_repository()
            report_id = await reports_repo.create_from_workflow_result(result)
            logger.info(
                f"Отчёт сохранён: {report_id}",
                component="analysis_executor",
            )
            logger.structured(
                "debug",
                "analysis_report_saved",
                component="analysis_executor",
                report_id=report_id,
                session_id=result.get("session_id"),
            )
    except Exception as e:
        logger.error(
            f"Не удалось сохранить отчёт: {e}",
            component="analysis_executor",
        )

    logger.structured(
        "debug",
        "analysis_execute_end",
        component="analysis_executor",
        status=result.get("status"),
        session_id=result.get("session_id"),
        correlation_id=correlation_id,
        saved_report=True,
    )
    return result
