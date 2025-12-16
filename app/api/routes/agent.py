import asyncio
import json
import time
import uuid
from datetime import datetime
from typing import Any, AsyncGenerator, Dict, Optional

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from app.advanced_funcs.logging_client import logger
from app.agents.client_workflow import run_client_analysis_streaming
from app.agents.workflow import AgentState, invoke_graph_with_persistence

agent_router = APIRouter(prefix="/agent", tags=["Агент"])


class ClientAnalysisRequest(BaseModel):
    client_name: str
    inn: Optional[str] = ""
    additional_notes: Optional[str] = ""


@agent_router.post("/prompt")
async def process_prompt(request: Request, body: dict):
    """Принимает prompt, запускает граф, возвращает ответ."""
    thread_id = body.get("thread_id") or f"thread_{uuid.uuid4().hex}"
    user_input = body.get("prompt")
    if not user_input:
        raise HTTPException(status_code=400, detail="Prompt обязателен")

    llm = getattr(request.app.state, "llm", None)
    if llm is None:
        raise HTTPException(
            status_code=503,
            detail="LLM не настроен. Требуется GIGACHAT_TOKEN для работы этого endpoint. "
            "Используйте /agent/analyze-client для анализа клиентов через Perplexity.",
        )

    initial_state: AgentState = {
        "session_id": thread_id,
        "user_input": user_input,
        "llm": llm,
        "current_step": "planning",
        "plan": "",
        "tool_sequence": [],
        "tool_results": [],
        "analysis_result": "",
        "requires_confirmation": False,
        "saved_file_path": "",
        "is_confirmed": False,
        "feedback": "",
    }

    try:
        final_state = await invoke_graph_with_persistence(thread_id, initial_state)
        response_text = final_state.get(
            "analysis_result", "Не удалось сгенерировать ответ."
        )

        return {
            "response": response_text,
            "thread_id": thread_id,
            "tools_used": len(final_state.get("tool_results", [])) > 0,
            "timestamp": datetime.now().isoformat(),
        }

    except Exception as e:
        logger.error(f"Ошибка в process_prompt: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Ошибка агента: {str(e)}") from e


@agent_router.get("/thread_history/{thread_id}")
async def get_thread_history(thread_id: str):
    from app.storage.tarantool import TarantoolClient

    client = await TarantoolClient.get_instance()
    key = f"thread:{thread_id}" if not thread_id.startswith("thread:") else thread_id
    result = await client.get_persistent(key)
    if not result:
        raise HTTPException(status_code=404, detail="Тред не найден")
    return result


@agent_router.post("/analyze-client")
async def analyze_client(request: ClientAnalysisRequest, stream: bool = False):
    """
    Анализирует клиента через Perplexity AI.
    Выполняет параллельный поиск и создаёт отчёт с оценкой рисков.

    Args:
        stream: Если True, возвращает SSE stream с прогрессом
    """
    from app.services.perplexity_client import PerplexityClient

    client = PerplexityClient.get_instance()
    if not client.is_configured():
        raise HTTPException(
            status_code=503,
            detail="Perplexity API key не настроен. Добавьте PERPLEXITY_API_KEY в секреты.",
        )

    if stream:
        return StreamingResponse(
            _stream_client_analysis(
                client_name=request.client_name,
                inn=request.inn or "",
                additional_notes=request.additional_notes or "",
            ),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
                "X-Accel-Buffering": "no",
            },
        )

    try:
        coro = run_client_analysis_streaming(
            client_name=request.client_name,
            inn=request.inn or "",
            additional_notes=request.additional_notes or "",
        )
        result = await coro
        return result
    except Exception as e:
        logger.error(f"Client analysis error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Ошибка анализа: {str(e)}") from e


async def _stream_client_analysis(
    client_name: str, inn: str, additional_notes: str
) -> AsyncGenerator[str, None]:
    """Генератор SSE событий для streaming анализа."""
    session_id = f"analysis_{int(time.time())}"

    def format_sse(event: str, data: Dict[str, Any]) -> str:
        return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"

    yield format_sse(
        "start",
        {
            "session_id": session_id,
            "client_name": client_name,
            "message": "Начинаем анализ клиента...",
        },
    )

    generator = None
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
        logger.info(f"Client disconnected from stream: {session_id}")
        if generator:
            await generator.aclose()
    except Exception as e:
        logger.error(f"Streaming error: {e}", exc_info=True)
        yield format_sse("error", {"error": str(e), "session_id": session_id})
    finally:
        if generator:
            try:
                await generator.aclose()
            except Exception as e:
                logger.error(f"Error closing streaming generator: {e}", exc_info=True)


@agent_router.get("/threads")
async def list_threads() -> Dict[str, Any]:
    from app.storage.tarantool import TarantoolClient

    try:
        client = await TarantoolClient.get_instance()
        threads_data = await client.scan_threads()
        threads = [
            {
                "thread_id": item["key"].replace("thread:", ""),
                "user_prompt": (
                    item["input"][:100] + "..."
                    if len(item["input"]) > 100
                    else item["input"]
                ),
                "created_at": (
                    datetime.fromtimestamp(item["created_at"]).isoformat()
                    if item["created_at"]
                    else "Неизвестно"
                ),
                "message_count": item["message_count"],
            }
            for item in threads_data
        ]
        return {
            "total": len(threads),
            "threads": sorted(
                threads, key=lambda x: x.get("created_at", ""), reverse=True
            ),
        }
    except Exception as e:
        logger.error(f"Ошибка получения тредов: {e}", exc_info=True)
        raise HTTPException(
            status_code=500, detail="Ошибка получения списка тредов"
        ) from e
