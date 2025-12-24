"""
MCP server на базе fastMCP.

Назначение:
- дать внешним агентам/оркестраторам единый интерфейс для вызова функций приложения
  (анализ, управление кэшем, публикация задач в очередь, управление файлами).

Запуск:
    python -m app.mcp_server.main
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any, Dict, List, Optional

from fastmcp import FastMCP
from fastmcp.prompts.prompt import Message

from app.services.app_actions import dispatch_cache_invalidate, dispatch_client_analysis

MCP_HOST = os.getenv("MCP_HOST", "0.0.0.0")
MCP_PORT = int(os.getenv("MCP_PORT", "8011"))
MCP_PATH = os.getenv("MCP_PATH", "/mcp")

# Ограничения файловых операций (безопасность MCP tools).
MCP_FILES_ROOT = Path(os.getenv("MCP_FILES_ROOT", os.getcwd())).resolve()
MCP_MAX_FILE_BYTES = int(os.getenv("MCP_MAX_FILE_BYTES", "1048576"))  # 1MB

mcp = FastMCP(
    name="client-analysis-mcp",
    instructions=(
        "MCP сервер для системы анализа контрагентов. "
        "Содержит tools для запуска анализа, управления кэшем и безопасных файловых операций."
    ),
    host=MCP_HOST,
    port=MCP_PORT,
    sse_path=MCP_PATH,
)


def _resolve_under_root(relative_path: str) -> Path:
    """
    Безопасно резолвит путь относительно корня MCP файлов.

    Защита от path traversal: итоговый путь должен лежать внутри MCP_FILES_ROOT.
    """
    rel = (relative_path or "").lstrip("/").strip()
    p = (MCP_FILES_ROOT / rel).resolve()
    if MCP_FILES_ROOT not in p.parents and p != MCP_FILES_ROOT:
        raise ValueError("path is outside MCP_FILES_ROOT")
    return p


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
    return await dispatch_client_analysis(
        client_name=client_name,
        inn=inn,
        additional_notes=additional_notes,
        save_report=save_report,
        session_id=session_id,
        prefer_queue=False,
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
    return await dispatch_client_analysis(
        client_name=client_name,
        inn=inn,
        additional_notes=additional_notes,
        save_report=save_report,
        session_id=session_id,
        prefer_queue=True,
    )


@mcp.tool(
    name="queue_cache_invalidate",
    title="Инвалидировать кэш через очередь (RabbitMQ)",
    description="Публикует команду инвалидации кэша в RabbitMQ очередь.",
)
async def queue_cache_invalidate(
    prefix: Optional[str] = None,
    invalidate_all: bool = False,
) -> Dict[str, Any]:
    return await dispatch_cache_invalidate(
        prefix=prefix,
        invalidate_all=invalidate_all,
        prefer_queue=True,
    )


@mcp.tool(
    name="cache_invalidate",
    title="Инвалидировать кэш (auto)",
    description="Инвалидирует кэш напрямую или через очередь (в зависимости от настроек).",
)
async def cache_invalidate(
    prefix: Optional[str] = None,
    invalidate_all: bool = False,
) -> Dict[str, Any]:
    return await dispatch_cache_invalidate(
        prefix=prefix,
        invalidate_all=invalidate_all,
        prefer_queue=None,
    )


@mcp.tool(
    name="fs_read_text",
    title="Прочитать текстовый файл",
    description="Безопасно читает файл внутри MCP_FILES_ROOT (с лимитом размера).",
)
async def fs_read_text(path: str, max_bytes: Optional[int] = None) -> Dict[str, Any]:
    p = _resolve_under_root(path)
    if not p.exists() or not p.is_file():
        return {"status": "error", "message": "file not found"}

    limit = int(max_bytes) if max_bytes is not None else MCP_MAX_FILE_BYTES
    size = p.stat().st_size
    if size > limit:
        return {
            "status": "error",
            "message": f"file too large: {size} bytes (limit {limit})",
        }

    content = p.read_text(encoding="utf-8", errors="replace")
    return {"status": "success", "path": str(p), "size_bytes": size, "content": content}


@mcp.tool(
    name="fs_write_text",
    title="Записать текстовый файл",
    description="Создаёт/перезаписывает файл внутри MCP_FILES_ROOT (с лимитом размера).",
)
async def fs_write_text(
    path: str,
    content: str,
    overwrite: bool = False,
    create_dirs: bool = True,
) -> Dict[str, Any]:
    p = _resolve_under_root(path)
    if p.exists() and not overwrite:
        return {"status": "error", "message": "file exists (set overwrite=true)"}

    data = content.encode("utf-8", errors="replace")
    if len(data) > MCP_MAX_FILE_BYTES:
        return {
            "status": "error",
            "message": f"content too large (limit {MCP_MAX_FILE_BYTES})",
        }

    if create_dirs:
        p.parent.mkdir(parents=True, exist_ok=True)

    p.write_text(content, encoding="utf-8")
    return {"status": "success", "path": str(p), "size_bytes": p.stat().st_size}


@mcp.tool(
    name="fs_replace_text",
    title="Заменить фрагмент в текстовом файле",
    description="Выполняет замену подстроки (old -> new) внутри файла MCP_FILES_ROOT.",
)
async def fs_replace_text(
    path: str,
    old: str,
    new: str,
    count: int = 1,
) -> Dict[str, Any]:
    p = _resolve_under_root(path)
    if not p.exists() or not p.is_file():
        return {"status": "error", "message": "file not found"}

    text = p.read_text(encoding="utf-8", errors="replace")
    if old not in text:
        return {"status": "error", "message": "old fragment not found"}

    replaced = text.replace(old, new, int(count))
    data = replaced.encode("utf-8", errors="replace")
    if len(data) > MCP_MAX_FILE_BYTES:
        return {
            "status": "error",
            "message": f"result too large (limit {MCP_MAX_FILE_BYTES})",
        }

    p.write_text(replaced, encoding="utf-8")
    return {"status": "success", "path": str(p), "replaced": True}


@mcp.tool(
    name="fs_list",
    title="Список файлов/директорий",
    description="Показывает содержимое директории внутри MCP_FILES_ROOT (без рекурсии).",
)
async def fs_list(path: str = ".", limit: int = 200) -> Dict[str, Any]:
    p = _resolve_under_root(path)
    if not p.exists() or not p.is_dir():
        return {"status": "error", "message": "directory not found"}

    items: List[Dict[str, Any]] = []
    for i, child in enumerate(sorted(p.iterdir(), key=lambda x: x.name)):
        if i >= int(limit):
            break
        try:
            st = child.stat()
            items.append(
                {
                    "name": child.name,
                    "is_dir": child.is_dir(),
                    "size_bytes": st.st_size if child.is_file() else None,
                    "mtime": st.st_mtime,
                }
            )
        except Exception:
            continue
    return {"status": "success", "path": str(p), "items": items, "count": len(items)}


@mcp.tool(
    name="fs_delete",
    title="Удалить файл",
    description="Удаляет файл внутри MCP_FILES_ROOT.",
)
async def fs_delete(path: str) -> Dict[str, Any]:
    p = _resolve_under_root(path)
    if not p.exists() or not p.is_file():
        return {"status": "error", "message": "file not found"}
    p.unlink(missing_ok=True)
    return {"status": "success", "deleted": True, "path": str(p)}


async def _build_asyncapi_spec() -> Dict[str, Any]:
    from faststream.specification import AsyncAPI

    from app.messaging.broker import broker

    spec = AsyncAPI(broker, title="Client Analysis Messaging", version="1.0.0").to_specification()
    return json.loads(spec.to_json())


@mcp.tool(
    name="get_asyncapi_spec",
    title="Получить AsyncAPI спецификацию",
    description="Возвращает AsyncAPI JSON для RabbitMQ/FastStream.",
)
async def get_asyncapi_spec() -> Dict[str, Any]:
    return await _build_asyncapi_spec()


@mcp.resource(
    "app://openapi.json",
    title="OpenAPI спецификация",
    description="OpenAPI JSON, который генерирует FastAPI backend.",
    mime_type="application/json",
    tags={"spec"},
)
async def openapi_resource() -> Dict[str, Any]:
    # Генерируем спецификацию напрямую из приложения (без HTTP вызова).
    from app.main import app

    return app.openapi()


@mcp.resource(
    "app://asyncapi.json",
    title="AsyncAPI спецификация",
    description="AsyncAPI JSON для очередей RabbitMQ/FastStream.",
    mime_type="application/json",
    tags={"spec"},
)
async def asyncapi_resource() -> Dict[str, Any]:
    return await _build_asyncapi_spec()


@mcp.prompt(
    name="prompt_analyze_company",
    title="Промпт: анализ контрагента",
    description="Готовый промпт для вызова tool `run_client_analysis` или `queue_client_analysis`.",
    tags={"prompt", "analysis"},
)
def prompt_analyze_company(client_name: str, inn: str = "", notes: str = ""):
    return [
        Message(
            "Ты работаешь с системой анализа контрагентов.\n"
            "Выполни анализ и верни краткое резюме + риск-оценку.\n\n"
            f"client_name: {client_name}\n"
            f"inn: {inn}\n"
            f"additional_notes: {notes}\n\n"
            "Если нужна асинхронная обработка — используй tool `queue_client_analysis`.\n"
            "Если нужен результат сразу — используй tool `run_client_analysis`."
        )
    ]


@mcp.prompt(
    name="prompt_cache_invalidate",
    title="Промпт: инвалидация кэша",
    description="Промпт для выбора между точечной/полной инвалидацией кэша.",
    tags={"prompt", "cache"},
)
def prompt_cache_invalidate(prefix: str = "search:", invalidate_all: bool = False):
    return [
        Message(
            "Инвалидируй кэш безопасно.\n\n"
            f"prefix: {prefix}\n"
            f"invalidate_all: {invalidate_all}\n\n"
            "Используй tool `cache_invalidate` (auto) или `queue_cache_invalidate` (через очередь)."
        )
    ]


def main() -> None:
    # SSE транспорт удобен для HTTP-интеграций и дебага.
    mcp.run(transport="sse", host=MCP_HOST, port=MCP_PORT, path=MCP_PATH)


if __name__ == "__main__":
    main()
