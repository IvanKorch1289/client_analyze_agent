import asyncio
import json
import re
import time
import uuid
from datetime import datetime
from typing import Any, AsyncGenerator, Dict, Optional

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from slowapi.util import get_remote_address

from app.agents.client_workflow import run_client_analysis_streaming
from app.api.rate_limit import create_limiter
from app.config.constants import (
    RATE_LIMIT_ANALYZE_CLIENT_PER_MINUTE,
    RATE_LIMIT_SEARCH_PER_MINUTE,
)
from app.services.analysis_executor import execute_client_analysis
from app.utility.logging_client import logger

agent_router = APIRouter(prefix="/agent", tags=["Агент"])


# P2: Task registry для отслеживания и отмены задач анализа
_running_tasks: Dict[str, asyncio.Task] = {}


def _register_task(session_id: str, task: asyncio.Task) -> None:
    """Регистрация задачи анализа."""
    _running_tasks[session_id] = task
    logger.debug(f"Task registered: {session_id}", component="agent_api")


def _unregister_task(session_id: str) -> None:
    """Удаление задачи из реестра."""
    if session_id in _running_tasks:
        del _running_tasks[session_id]
        logger.debug(f"Task unregistered: {session_id}", component="agent_api")


def _get_running_task(session_id: str) -> Optional[asyncio.Task]:
    """Получить запущенную задачу по session_id."""
    return _running_tasks.get(session_id)

# Rate limiter для агентских эндпоинтов
limiter = create_limiter(get_remote_address)


class ClientAnalysisRequest(BaseModel):
    client_name: str
    inn: Optional[str] = ""
    additional_notes: Optional[str] = ""


class PromptRequest(BaseModel):
    """Back-compat endpoint payload for Streamlit UI."""

    prompt: str


@agent_router.get("/thread_history/{thread_id}")
@limiter.limit(f"{RATE_LIMIT_SEARCH_PER_MINUTE}/minute")
async def get_thread_history(request: Request, thread_id: str):
    from app.storage.tarantool import TarantoolClient

    client = await TarantoolClient.get_instance()
    threads_repo = client.get_threads_repository()

    # Используем ThreadsRepository
    result = await threads_repo.get(thread_id)
    if not result:
        raise HTTPException(status_code=404, detail="Тред не найден")
    return result


@agent_router.post("/analyze-client")
@limiter.limit(f"{RATE_LIMIT_ANALYZE_CLIENT_PER_MINUTE}/minute")
async def analyze_client(request: Request, data: ClientAnalysisRequest, stream: bool = False):
    """
    Анализирует клиента через Perplexity AI.
    Выполняет параллельный поиск и создаёт отчёт с оценкой рисков.

    Args:
        request: FastAPI Request object (для rate limiting)
        data: Данные запроса с информацией о клиенте
        stream: Если True, возвращает SSE stream с прогрессом
    """
    from app.services.perplexity_client import PerplexityClient

    logger.structured(
        "debug",
        "agent_analyze_request",
        component="agent_api",
        client_name=data.client_name,
        inn=data.inn or "",
        stream=bool(stream),
    )

    client = PerplexityClient.get_instance()
    if not client.is_configured():
        raise HTTPException(
            status_code=503,
            detail="Perplexity API key не настроен. Добавьте PERPLEXITY_API_KEY в секреты.",
        )

    if stream:
        return StreamingResponse(
            _stream_client_analysis(
                client_name=data.client_name,
                inn=data.inn or "",
                additional_notes=data.additional_notes or "",
            ),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
                "X-Accel-Buffering": "no",
            },
        )

    try:
        # Централизованный executor (единый путь для HTTP/RMQ/MCP/scheduler).
        result = await execute_client_analysis(
            client_name=data.client_name,
            inn=data.inn or "",
            additional_notes=data.additional_notes or "",
            save_report=True,
        )
        logger.structured(
            "debug",
            "agent_analyze_response",
            component="agent_api",
            status=result.get("status"),
            session_id=result.get("session_id"),
        )
        return result
    except Exception as e:
        logger.error(f"Client analysis error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Ошибка анализа: {str(e)}") from e


@agent_router.post("/prompt")
@limiter.limit(f"{RATE_LIMIT_SEARCH_PER_MINUTE}/minute")
async def prompt_agent(request: Request, data: PromptRequest) -> Dict[str, Any]:
    """
    Backward-compatible endpoint for the Streamlit "Запрос агенту" page.

    Accepts a free-form prompt and runs the client analysis workflow.
    """
    prompt = (data.prompt or "").strip()
    if not prompt:
        raise HTTPException(status_code=400, detail="prompt is required")

    # Extract INN if present
    inn_match = re.search(r"\b(\d{10}|\d{12})\b", prompt)
    inn = inn_match.group(1) if inn_match else ""

    # Heuristic client name: prompt without INN + common leading verbs
    client_name = prompt
    if inn:
        client_name = re.sub(rf"\b{re.escape(inn)}\b", "", client_name).strip()
    client_name = re.sub(r"^\s*(проанализируй|анализ|проверь|проверка)\s+", "", client_name, flags=re.I).strip()
    if not client_name:
        client_name = prompt

    result = await execute_client_analysis(
        client_name=client_name,
        inn=inn,
        additional_notes="",
        save_report=True,
    )

    # Streamlit expects {response, thread_id, tools_used, timestamp}
    return {
        "response": result.get("summary", "") or "",
        "thread_id": result.get("session_id", ""),
        "tools_used": True,
        "timestamp": datetime.utcnow().isoformat(),
        "raw_result": result,
    }


async def _stream_client_analysis(client_name: str, inn: str, additional_notes: str) -> AsyncGenerator[str, None]:
    """Генератор SSE событий для streaming анализа."""
    # P2: UUID для уникальности session_id (предотвращение коллизий при параллельных запусках)
    session_id = f"analysis_{uuid.uuid4().hex[:12]}_{int(time.time())}"

    def format_sse(event: str, data: Dict[str, Any]) -> str:
        return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"

    yield format_sse(
        "start",
        {
            "session_id": session_id,
            "client_name": client_name,
            "message": "Начинаем анализ клиента...",
            "cancellable": True,  # P2: Сообщаем клиенту, что анализ можно отменить
        },
    )

    generator = None
    current_task = asyncio.current_task()
    
    # P2: Регистрируем текущую задачу для возможности отмены
    if current_task:
        _register_task(session_id, current_task)
    
    try:
        generator = run_client_analysis_streaming(
            client_name=client_name,
            inn=inn,
            additional_notes=additional_notes,
            session_id=session_id,
            stream=True,
        )
        async for event in generator:
            yield format_sse(event["type"], event["data"])

        yield format_sse("complete", {"session_id": session_id, "status": "completed"})

    except asyncio.CancelledError:
        logger.info(f"Analysis cancelled via API: {session_id}", component="agent_api")
        yield format_sse("cancelled", {"session_id": session_id, "message": "Анализ отменён"})
        if generator:
            await generator.aclose()
    except Exception as e:
        logger.error(f"Streaming error: {e}", exc_info=True)
        yield format_sse("error", {"error": str(e), "session_id": session_id})
    finally:
        # P2: Удаляем задачу из реестра при завершении
        _unregister_task(session_id)
        if generator:
            try:
                await generator.aclose()
            except Exception as e:
                logger.error(f"Error closing streaming generator: {e}", exc_info=True)


@agent_router.get("/threads")
@limiter.limit(f"{RATE_LIMIT_SEARCH_PER_MINUTE}/minute")
async def list_threads(request: Request) -> Dict[str, Any]:
    from app.storage.tarantool import TarantoolClient

    try:
        client = await TarantoolClient.get_instance()
        threads_repo = client.get_threads_repository()

        # Используем ThreadsRepository
        threads_list = await threads_repo.list(limit=50)

        threads = [
            {
                "thread_id": item.get("thread_id", ""),
                "user_prompt": (
                    item.get("thread_data", {}).get("input", "")[:100] + "..."
                    if len(item.get("thread_data", {}).get("input", "")) > 100
                    else item.get("thread_data", {}).get("input", "")
                ),
                "created_at": (
                    datetime.fromtimestamp(item.get("created_at", 0)).isoformat()
                    if item.get("created_at")
                    else "Неизвестно"
                ),
                "message_count": (
                    len(item.get("thread_data", {}).get("messages", []))
                    if isinstance(item.get("thread_data"), dict)
                    else 0
                ),
                "client_name": item.get("client_name", ""),
                "inn": item.get("inn", ""),
            }
            for item in threads_list
        ]
        return {
            "total": len(threads),
            "threads": sorted(threads, key=lambda x: x.get("created_at", ""), reverse=True),
        }
    except Exception as e:
        logger.error(f"Ошибка получения тредов: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Ошибка получения списка тредов") from e


# P2: Cancellation support для долгих анализов
@agent_router.delete("/analyze/{session_id}")
async def cancel_analysis(request: Request, session_id: str) -> Dict[str, Any]:
    """
    Отменить запущенный анализ по session_id.
    
    P2: Реализация поддержки отмены долгих задач анализа.
    
    Returns:
        Статус отмены задачи
    """
    task = _get_running_task(session_id)
    
    if task is None:
        raise HTTPException(
            status_code=404,
            detail=f"Анализ с session_id '{session_id}' не найден или уже завершён"
        )
    
    if task.done():
        _unregister_task(session_id)
        return {
            "status": "already_completed",
            "session_id": session_id,
            "message": "Анализ уже завершён"
        }
    
    task.cancel()
    
    try:
        await asyncio.wait_for(asyncio.shield(task), timeout=5.0)
    except asyncio.CancelledError:
        pass
    except asyncio.TimeoutError:
        logger.warning(f"Task {session_id} cancellation timed out", component="agent_api")
    except Exception as e:
        logger.error(f"Error during task cancellation: {e}", component="agent_api")
    finally:
        _unregister_task(session_id)
    
    logger.info(f"Analysis cancelled: {session_id}", component="agent_api")
    
    return {
        "status": "cancelled",
        "session_id": session_id,
        "message": "Анализ успешно отменён"
    }


@agent_router.get("/analyze/running")
async def list_running_analyses(request: Request) -> Dict[str, Any]:
    """
    Получить список запущенных анализов.
    
    P2: Мониторинг активных задач для возможности их отмены.
    
    Returns:
        Список активных анализов с их session_id
    """
    running = []
    completed = []
    
    for session_id, task in list(_running_tasks.items()):
        if task.done():
            completed.append(session_id)
            _unregister_task(session_id)
        else:
            running.append({
                "session_id": session_id,
                "status": "running",
            })
    
    return {
        "running_count": len(running),
        "running_analyses": running,
        "cleaned_up": len(completed),
    }
