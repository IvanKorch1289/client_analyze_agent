"""
Единый исполнитель анализа клиента (worker/scheduler/MCP).
"""

from __future__ import annotations

from typing import Any, Dict, Optional

from app.utility.logging_client import logger


async def execute_client_analysis(
    client_name: str,
    inn: str,
    additional_notes: str = "",
    *,
    save_report: bool = True,
    session_id: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Запустить workflow анализа клиента и (опционально) сохранить отчёт в Tarantool.

    Это “единый источник правды” для:
    - APScheduler задач
    - FastStream worker (RabbitMQ listener)
    - MCP tools

    Args:
        client_name: Название контрагента
        inn: ИНН (10/12 цифр) или пусто
        additional_notes: Доп. контекст
        save_report: Сохранять ли отчёт в `reports` space (best-effort)
        session_id: Явный session_id (если нужен внешний трекинг)

    Returns:
        dict: Результат workflow (как возвращает `run_client_analysis_batch`)
    """
    from app.agents.client_workflow import run_client_analysis_batch
    from app.storage.tarantool import TarantoolClient

    logger.info(
        f"Запуск анализа клиента: {client_name} (ИНН: {inn})",
        component="analysis_executor",
    )

    result = await run_client_analysis_batch(
        client_name=client_name,
        inn=inn,
        additional_notes=additional_notes,
        session_id=session_id,
    )

    if not save_report:
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
    except Exception as e:
        logger.error(
            f"Не удалось сохранить отчёт: {e}",
            component="analysis_executor",
        )

    return result

