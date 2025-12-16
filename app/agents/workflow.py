import asyncio
import time
from typing import List, Literal, TypedDict

from langchain_core.runnables import Runnable
from langgraph.graph import END, StateGraph

from app.advanced_funcs.logging_client import logger
from app.agents.analyzer import analyzer_agent
from app.agents.executor import tool_executor_agent
from app.agents.planner import planner_agent
from app.storage.tarantool import save_thread_to_tarantool


class AgentState(TypedDict):
    session_id: str
    user_input: str
    plan: str
    tool_sequence: List[str]
    tool_results: List[dict]
    analysis_result: str
    requires_confirmation: bool
    saved_file_path: str
    is_confirmed: bool
    feedback: str
    current_step: Literal[
        "planning",
        "executing_tools",
        "analyzing",
        "saving",
        "awaiting_confirmation",
        "completed",
        "feedback_received",
        "failed",
    ]
    llm: Runnable


def build_persistent_graph():
    """Создаёт и возвращает скомпилированный граф."""
    workflow = StateGraph(AgentState)
    workflow.add_node("planner", planner_agent)
    workflow.add_node("tool_executor", tool_executor_agent)
    workflow.add_node("analyzer", analyzer_agent)

    # Установка начальной точки
    workflow.set_entry_point("planner")

    # Линейный поток: планирование → выполнение → анализ
    workflow.add_edge("planner", "tool_executor")
    workflow.add_edge("tool_executor", "analyzer")

    # Завершаем граф после анализа — saver и feedback пока не реализованы
    workflow.add_edge("analyzer", END)

    return workflow.compile()


async def invoke_graph_with_persistence(session_id: str, initial_state: dict = None) -> dict:
    """Запускает граф асинхронно и сохраняет результат в Tarantool."""
    graph = build_persistent_graph()

    if not initial_state:
        raise ValueError("Начальное состояние обязательно")

    try:
        final_state = await graph.ainvoke(initial_state)
        final_state["current_step"] = final_state.get("current_step", "completed")
    except Exception as e:
        logger.error(f"Ошибка выполнения графа: {e}")
        final_state = {**initial_state, "error": str(e), "current_step": "failed"}

    try:
        serializable_state = _make_serializable(final_state)
        thread_data = {
            "input": final_state.get("user_input", ""),
            "created_at": time.time(),
            "messages": [
                {
                    "type": "ai",
                    "data": {
                        "content": final_state.get("analysis_result", "Нет анализа")
                    },
                },
                {
                    "type": "tool_results",
                    "data": {"content": str(final_state.get("tool_results", []))},
                },
            ],
            "final_state": serializable_state,
        }

        asyncio.create_task(save_thread_to_tarantool(session_id, thread_data))
        logger.info(f"Состояние графа сохранено в Tarantool: thread:{session_id}")

    except Exception as e:
        logger.error(f"Не удалось сохранить состояние в Tarantool: {e}")

    return final_state


def _make_serializable(obj, max_depth=10):
    """Фильтрует не-сериализуемые объекты из состояния."""
    if max_depth <= 0:
        return str(obj)
    
    if obj is None or isinstance(obj, (str, int, float, bool)):
        return obj
    elif isinstance(obj, dict):
        return {k: _make_serializable(v, max_depth - 1) for k, v in obj.items()
                if not k.startswith('_') and k != 'llm'}
    elif isinstance(obj, (list, tuple)):
        return [_make_serializable(item, max_depth - 1) for item in obj]
    else:
        try:
            import json
            json.dumps(obj)
            return obj
        except (TypeError, ValueError):
            return f"<{type(obj).__name__}>"
