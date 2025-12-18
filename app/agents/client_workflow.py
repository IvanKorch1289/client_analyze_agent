"""
Client Analysis Workflow: LangGraph workflow для анализа клиентов.
Orchestrator -> Data Collector (parallel: Casebook, InfoSphere, DaData, Perplexity, Tavily)
             -> Report Analyzer -> File Writer
"""

import asyncio
import time
from typing import Any, AsyncGenerator, Dict, List, Literal, Optional, TypedDict, Union

from langgraph.graph import END, StateGraph

from app.agents.data_collector import data_collector_agent
from app.agents.file_writer import file_writer_agent
from app.agents.orchestrator import orchestrator_agent
from app.agents.report_analyzer import report_analyzer_agent
from app.storage.tarantool import save_thread_to_tarantool
from app.utility.logging_client import logger


class ClientAnalysisState(TypedDict, total=False):
    """Состояние workflow анализа клиента."""

    session_id: str
    client_name: str
    inn: str
    additional_notes: str

    search_intents: List[Dict[str, str]]
    search_results: List[Dict[str, Any]]
    source_data: Dict[str, Any]
    collection_stats: Dict[str, Any]

    orchestrator_result: Dict[str, Any]
    report: Dict[str, Any]
    analysis_result: str
    saved_files: Dict[str, str]

    error: str
    search_error: str

    current_step: Literal[
        "orchestrating",
        "collecting",
        "searching",
        "analyzing",
        "saving",
        "completed",
        "failed",
    ]


def build_client_analysis_graph():
    """
    Создаёт и возвращает скомпилированный граф анализа клиента.

    Архитектура:
        orchestrator -> data_collector (parallel API calls) -> analyzer -> file_writer
    """
    workflow = StateGraph(ClientAnalysisState)

    workflow.add_node("orchestrator", orchestrator_agent)
    workflow.add_node("data_collector", data_collector_agent)
    workflow.add_node("analyzer", report_analyzer_agent)
    workflow.add_node("file_writer", file_writer_agent)

    workflow.set_entry_point("orchestrator")

    def route_after_orchestrator(state: Dict[str, Any]) -> str:
        if state.get("current_step") == "failed":
            return END
        return "data_collector"

    workflow.add_conditional_edges(
        "orchestrator",
        route_after_orchestrator,
        {"data_collector": "data_collector", END: END},
    )

    workflow.add_edge("data_collector", "analyzer")
    workflow.add_edge("analyzer", "file_writer")
    workflow.add_edge("file_writer", END)

    return workflow.compile()


def run_client_analysis_streaming(
    client_name: str,
    inn: str = "",
    additional_notes: str = "",
    session_id: Optional[str] = None,
    stream: bool = False,
) -> Union[AsyncGenerator[Dict[str, Any], None], Any]:
    """
    Запускает workflow анализа клиента с поддержкой streaming.

    Args:
        client_name: Название компании
        inn: ИНН компании (опционально)
        additional_notes: Дополнительные заметки (опционально)
        session_id: ID сессии (генерируется автоматически)
        stream: Если True, возвращает AsyncGenerator с событиями прогресса

    Returns:
        AsyncGenerator с событиями (stream=True) или Coroutine для batch анализа
    """
    if not session_id:
        session_id = f"analysis_{int(time.time())}"

    initial_state: ClientAnalysisState = {
        "session_id": session_id,
        "client_name": client_name,
        "inn": inn,
        "additional_notes": additional_notes,
        "current_step": "orchestrating",
        "search_intents": [],
        "search_results": [],
        "source_data": {},
        "collection_stats": {},
        "orchestrator_result": {},
        "report": {},
        "analysis_result": "",
        "saved_files": {},
        "error": "",
        "search_error": "",
    }

    logger.info(
        f"Starting client analysis workflow: {session_id}", component="workflow"
    )

    if stream:
        return _run_streaming_analysis(initial_state, session_id, client_name, inn)

    return _run_batch_analysis(initial_state, session_id, client_name, inn)


async def _run_streaming_analysis(
    initial_state: ClientAnalysisState, session_id: str, client_name: str, inn: str
) -> AsyncGenerator[Dict[str, Any], None]:
    """Streaming версия анализа с событиями прогресса."""
    current_state = initial_state.copy()

    try:
        yield {
            "type": "progress",
            "data": {
                "step": "orchestrating",
                "message": "Формирование поисковых запросов...",
                "progress": 10,
            },
        }

        current_state = await orchestrator_agent(current_state)

        intents = current_state.get("search_intents", [])
        intent_categories = [
            i.get("category") or i.get("query", "")[:30] for i in intents
        ]
        yield {
            "type": "orchestrator",
            "data": {
                "step": "orchestrator_complete",
                "intents_count": len(intents),
                "intents": intent_categories,
                "progress": 20,
            },
        }

        if current_state.get("current_step") == "failed":
            yield {
                "type": "error",
                "data": {"error": current_state.get("error", "Ошибка оркестратора")},
            }
            return

        yield {
            "type": "progress",
            "data": {
                "step": "collecting",
                "message": "Сбор данных из всех источников (Casebook, DaData, InfoSphere, Perplexity, Tavily)...",
                "progress": 25,
            },
        }

        current_state = await data_collector_agent(current_state)

        source_data = current_state.get("source_data", {})
        collection_stats = current_state.get("collection_stats", {})
        successful_sources = collection_stats.get("successful_sources", [])

        yield {
            "type": "data_collected",
            "data": {
                "step": "data_collection_complete",
                "sources": list(source_data.keys()),
                "successful": successful_sources,
                "duration_ms": collection_stats.get("duration_ms", 0),
                "progress": 60,
            },
        }

        yield {
            "type": "progress",
            "data": {
                "step": "analyzing",
                "message": "Формирование отчёта и оценка рисков...",
                "successful_sources": len(successful_sources),
                "total_sources": len(source_data),
                "progress": 70,
            },
        }

        current_state = await report_analyzer_agent(current_state)

        report = current_state.get("report", {})
        risk = report.get("risk_assessment", {})

        yield {
            "type": "report",
            "data": {
                "step": "report_complete",
                "risk_score": risk.get("score", 0),
                "risk_level": risk.get("level", "unknown"),
                "findings_count": len(report.get("findings", [])),
                "progress": 85,
            },
        }

        yield {
            "type": "progress",
            "data": {
                "step": "saving",
                "message": "Сохранение отчёта в файл...",
                "progress": 90,
            },
        }

        current_state = await file_writer_agent(current_state)

        saved_files = current_state.get("saved_files", {})

        final_result = {
            "session_id": session_id,
            "client_name": client_name,
            "inn": inn,
            "status": "completed",
            "report": report,
            "summary": current_state.get("analysis_result", ""),
            "saved_files": saved_files,
            "timestamp": time.time(),
        }

        yield {"type": "result", "data": final_result}

        try:
            # Сохраняем через ThreadsRepository для лучшей структуры данных
            from app.storage.tarantool import TarantoolClient
            
            client = await TarantoolClient.get_instance()
            threads_repo = client.get_threads_repository()
            
            thread_data = {
                "input": f"Анализ клиента: {client_name}",
                "created_at": time.time(),
                "messages": [
                    {"type": "input", "data": {"client_name": client_name, "inn": inn}},
                    {"type": "report", "data": report},
                ],
                "saved_files": saved_files,
                "client_name": client_name,
                "inn": inn,
            }
            
            asyncio.create_task(
                threads_repo.save_thread(
                    thread_id=session_id,
                    thread_data=thread_data,
                    client_name=client_name,
                    inn=inn
                )
            )
        except Exception as e:
            logger.error(f"Failed to save thread: {e}", component="workflow")

    except asyncio.CancelledError:
        logger.info(
            f"Streaming cancelled for session {session_id}", component="workflow"
        )
        raise
    except Exception as e:
        logger.error(f"Streaming workflow error: {e}", component="workflow")
        yield {"type": "error", "data": {"error": str(e), "session_id": session_id}}


async def _run_batch_analysis(
    initial_state: ClientAnalysisState, session_id: str, client_name: str, inn: str
) -> Dict[str, Any]:
    """Обычная batch версия анализа."""
    try:
        graph = build_client_analysis_graph()
        final_state = await graph.ainvoke(initial_state)
        final_state["current_step"] = final_state.get("current_step", "completed")

    except Exception as e:
        logger.error(f"Workflow error: {e}", component="workflow")
        final_state = {**initial_state, "error": str(e), "current_step": "failed"}

    try:
        # Сохраняем через ThreadsRepository
        from app.storage.tarantool import TarantoolClient
        
        client_inst = await TarantoolClient.get_instance()
        threads_repo = client_inst.get_threads_repository()
        
        thread_data = {
            "input": f"Анализ клиента: {client_name}",
            "created_at": time.time(),
            "messages": [
                {"type": "input", "data": {"client_name": client_name, "inn": inn}},
                {"type": "report", "data": final_state.get("report", {})},
            ],
            "final_state": final_state,
            "client_name": client_name,
            "inn": inn,
        }
        
        asyncio.create_task(
            threads_repo.save_thread(
                thread_id=session_id,
                thread_data=thread_data,
                client_name=client_name,
                inn=inn
            )
        )
    except Exception as e:
        logger.error(f"Failed to save thread: {e}", component="workflow")

    return {
        "session_id": session_id,
        "client_name": client_name,
        "inn": inn,
        "status": final_state.get("current_step"),
        "report": final_state.get("report", {}),
        "summary": final_state.get("analysis_result", ""),
        "saved_files": final_state.get("saved_files", {}),
        "error": final_state.get("error") or final_state.get("search_error"),
        "timestamp": time.time(),
    }
