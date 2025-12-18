"""
MCP server на базе fastMCP.

Назначение:
- дать внешним агентам/оркестраторам единый интерфейс для вызова функций приложения
  (анализ, управление кэшем, публикация задач в очередь).

Запуск:
    python -m app.mcp_server.main
"""

from __future__ import annotations

import os
from typing import Any, Dict, Optional

from fastmcp import FastMCP

from app.messaging.publisher import get_rabbit_publisher
from app.services.analysis_executor import execute_client_analysis


MCP_HOST = os.getenv("MCP_HOST", "0.0.0.0")
MCP_PORT = int(os.getenv("MCP_PORT", "8011"))
MCP_PATH = os.getenv("MCP_PATH", "/mcp")

mcp = FastMCP(
    name="client-analysis-mcp",
    instructions=(
        "MCP сервер для системы анализа контрагентов. "
        "Содержит tools для запуска анализа и управления инфраструктурой."
    ),
    host=MCP_HOST,
    port=MCP_PORT,
    sse_path=MCP_PATH,
)


@mcp.tool(
    name="run_client_analysis",
    title="Запустить анализ клиента (in-process)",
    description=(
        "Запускает workflow анализа клиента напрямую в текущем процессе. "
        "Подходит для интерактивного использования. Для нагрузки лучше queue_*."
    ),
)
async def run_client_analysis(
    client_name: str,
    inn: str = "",
    additional_notes: str = "",
    save_report: bool = True,
    session_id: Optional[str] = None,
) -> Dict[str, Any]:
    return await execute_client_analysis(
        client_name=client_name,
        inn=inn,
        additional_notes=additional_notes,
        save_report=save_report,
        session_id=session_id,
    )


@mcp.tool(
    name="queue_client_analysis",
    title="Поставить анализ клиента в очередь (RabbitMQ)",
    description="Публикует сообщение в RabbitMQ очередь анализа (FastStream worker).",
)
async def queue_client_analysis(
    client_name: str,
    inn: str = "",
    additional_notes: str = "",
    save_report: bool = True,
    session_id: Optional[str] = None,
) -> Dict[str, Any]:
    await get_rabbit_publisher().publish_client_analysis(
        client_name=client_name,
        inn=inn,
        additional_notes=additional_notes,
        save_report=save_report,
        session_id=session_id,
    )
    return {"status": "accepted", "queued": True}


@mcp.tool(
    name="queue_cache_invalidate",
    title="Инвалидировать кэш через очередь (RabbitMQ)",
    description="Публикует команду инвалидации кэша в RabbitMQ очередь.",
)
async def queue_cache_invalidate(
    prefix: Optional[str] = None,
    invalidate_all: bool = False,
) -> Dict[str, Any]:
    await get_rabbit_publisher().publish_cache_invalidate(
        prefix=prefix,
        invalidate_all=invalidate_all,
    )
    return {"status": "accepted", "queued": True}


@mcp.tool(
    name="get_asyncapi_spec",
    title="Получить AsyncAPI спецификацию",
    description="Возвращает AsyncAPI JSON для RabbitMQ/FastStream.",
)
async def get_asyncapi_spec() -> Dict[str, Any]:
    import json
    from faststream.specification import AsyncAPI

    from app.messaging.broker import broker

    spec = AsyncAPI(broker, title="Client Analysis Messaging", version="1.0.0").to_specification()
    return json.loads(spec.to_json())


def main() -> None:
    # SSE транспорт удобен для HTTP-интеграций и дебага.
    mcp.run(transport="sse", host=MCP_HOST, port=MCP_PORT, path=MCP_PATH)


if __name__ == "__main__":
    main()

