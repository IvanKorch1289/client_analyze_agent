"""
Client Analysis Workflow: LangGraph workflow для анализа клиентов.

ОПТИМИЗИРОВАННАЯ АРХИТЕКТУРА (Sprint 8.1):
- Orchestrator и INN-based sources (InfoSphere/Casebook) запускаются ПАРАЛЛЕЛЬНО
- Это экономит до 10s на LLM вызов orchestrator (InfoSphere/Casebook занимают до 6 минут)
- DaData по-прежнему вызывается в orchestrator для получения канонического названия

Workflow:
    ┌─────────────────────┐     ┌─────────────────────────────┐
    │ Orchestrator        │     │ INN Sources (parallel)      │
    │ (LLM ~10s + DaData) │     │ InfoSphere + Casebook       │
    └─────────────────────┘     │ (up to 6min each)           │
           ↓                    └─────────────────────────────┘
           │                               ↓
           └───────────────┬───────────────┘
                           ↓
              ┌─────────────────────┐
              │ Web Search (parallel)│
              │ Perplexity + Tavily  │
              └─────────────────────┘
                           ↓
              ┌─────────────────────┐
              │ Report Analyzer     │
              │ (LLM ~30s + CoT)    │
              └─────────────────────┘
                           ↓
              ┌─────────────────────┐
              │ File Writer         │
              └─────────────────────┘
"""

import asyncio
import time
from typing import Any, AsyncGenerator, Dict, List, Literal, Optional, TypedDict, Union

from langgraph.graph import END, StateGraph

from app.agents.data_collector import (
    data_collector_agent,
    _fetch_infosphere_wrapper,
    _fetch_casebook_wrapper,
)
from app.agents.file_writer import file_writer_agent
from app.agents.orchestrator import orchestrator_agent
from app.agents.report_analyzer import report_analyzer_agent
from app.shared.toolkit.logging import logger


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

    logger.info(f"Starting client analysis workflow: {session_id}", component="workflow")

    try:
        from app.shared.toolkit.telemetry import create_span

        _span_ctx = create_span(
            "workflow.client_analysis",
            attributes={
                "workflow.session_id": session_id,
                "workflow.client_name": client_name,
                "workflow.inn": inn or "",
                "workflow.stream": stream,
            },
        )
        _span_ctx.__enter__()
    except Exception:
        _span_ctx = None

    if stream:
        return _run_streaming_analysis(initial_state, session_id, client_name, inn)

    return _run_batch_analysis(initial_state, session_id, client_name, inn)


async def run_client_analysis_batch(
    client_name: str,
    inn: str = "",
    additional_notes: str = "",
    session_id: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Batch (non-streaming) wrapper for the client analysis workflow.

    Exists for backward compatibility with scheduler and other callers.
    """
    result = run_client_analysis_streaming(
        client_name=client_name,
        inn=inn,
        additional_notes=additional_notes,
        session_id=session_id,
        stream=False,
    )
    # run_client_analysis_streaming(stream=False) returns an awaitable result dict
    return await result


async def _run_streaming_analysis(
    initial_state: ClientAnalysisState, session_id: str, client_name: str, inn: str
) -> AsyncGenerator[Dict[str, Any], None]:
    """
    Streaming версия анализа с событиями прогресса.

    Sprint 8.1 ОПТИМИЗАЦИЯ:
    - Запускаем InfoSphere и Casebook ПАРАЛЛЕЛЬНО с orchestrator
    - Экономим ~10s на LLM вызов (orchestrator работает пока INN sources грузятся)
    - DaData вызывается внутри orchestrator для получения канонического названия
    """
    current_state = initial_state.copy()

    try:
        yield {
            "type": "progress",
            "data": {
                "step": "orchestrating",
                "message": "Формирование запросов + параллельный сбор INN данных...",
                "progress": 10,
            },
        }

        # Sprint 8.1: ПАРАЛЛЕЛЬНЫЙ ЗАПУСК orchestrator + INN sources
        # InfoSphere и Casebook не зависят от search_intents, только от INN
        early_inn_tasks = {}
        if inn and inn.isdigit() and len(inn) in (10, 12):
            logger.info(
                "Workflow: starting early INN fetch (InfoSphere + Casebook) in parallel with orchestrator",
                component="workflow",
            )
            early_inn_tasks = {
                "infosphere": asyncio.create_task(_fetch_infosphere_wrapper(inn)),
                "casebook": asyncio.create_task(_fetch_casebook_wrapper(inn)),
            }

        # Запускаем orchestrator (который внутри вызывает DaData + LLM)
        orchestrator_task = asyncio.create_task(orchestrator_agent(current_state))

        # Ждём orchestrator (INN tasks продолжают работать в фоне)
        current_state = await orchestrator_task

        intents = current_state.get("search_intents", [])
        intent_categories = [i.get("category") or i.get("query", "")[:30] for i in intents]
        yield {
            "type": "orchestrator",
            "data": {
                "step": "orchestrator_complete",
                "intents_count": len(intents),
                "intents": intent_categories,
                "early_inn_started": bool(early_inn_tasks),
                "progress": 20,
            },
        }

        if current_state.get("current_step") == "failed":
            # Отменяем early tasks если orchestrator упал
            for task in early_inn_tasks.values():
                task.cancel()
            yield {
                "type": "error",
                "data": {"error": current_state.get("error", "Ошибка оркестратора")},
            }
            return

        yield {
            "type": "progress",
            "data": {
                "step": "collecting",
                "message": "Сбор данных из веб-источников (Perplexity, Tavily)...",
                "progress": 25,
            },
        }

        # Передаём early_inn_tasks в state для data_collector
        if early_inn_tasks:
            current_state["_early_inn_tasks"] = early_inn_tasks

        current_state = await data_collector_agent(current_state)

        source_data = current_state.get("source_data", {})
        collection_stats = current_state.get("collection_stats", {})
        successful_sources = collection_stats.get("successful_sources", [])

        # Sprint 2: Live Data Preview - показываем ключевые факты сразу
        yield {
            "type": "source_preview",
            "data": {
                "step": "live_preview",
                "sources": _extract_source_previews(source_data),
                "successful_count": len(successful_sources),
                "total_count": len(source_data),
            },
        }

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

        # Sprint 2: Progressive analysis updates - показываем что LLM анализирует
        yield {
            "type": "analysis_progress",
            "data": {
                "substep": "preparing_data",
                "message": "Подготовка данных для анализа",
                "sources_ready": len(successful_sources),
                "progress": 72,
            },
        }

        # Запускаем анализ с промежуточными обновлениями
        analysis_task = asyncio.create_task(report_analyzer_agent(current_state))

        # Показываем промежуточные обновления пока LLM думает
        wait_count = 0
        thinking_messages = [
            "Анализирую финансовые показатели и статус компании",
            "Оцениваю судебные дела и исполнительные производства",
            "Проверяю репутационные риски и новости",
            "Формирую итоговую оценку рисков",
        ]

        while not analysis_task.done():
            await asyncio.sleep(3)  # Обновление каждые 3 секунды
            if not analysis_task.done():
                message_idx = min(wait_count, len(thinking_messages) - 1)
                yield {
                    "type": "analysis_progress",
                    "data": {
                        "substep": "llm_thinking",
                        "message": f"🤔 {thinking_messages[message_idx]}...",
                        "elapsed_seconds": (wait_count + 1) * 3,
                        "progress": min(75 + wait_count, 82),  # Gradually increase progress
                    },
                }
                wait_count += 1

        # Получаем результат
        current_state = await analysis_task

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
                    inn=inn,
                )
            )
        except Exception as e:
            logger.error(f"Failed to save thread: {e}", component="workflow")

    except asyncio.CancelledError:
        logger.info(f"Streaming cancelled for session {session_id}", component="workflow")
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
                inn=inn,
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


def _extract_source_previews(source_data: Dict[str, Any]) -> Dict[str, Dict[str, Any]]:
    """
    Извлекает ключевые факты из каждого источника для live preview.

    Sprint 2: Live Data Preview - показываем пользователю данные
    по мере их поступления, до генерации финального отчёта.

    Args:
        source_data: Dict с данными из всех источников

    Returns:
        Dict с preview для каждого источника:
        {
            "dadata": {"status": "success", "preview": "ООО Рога и Копыта, действующая"},
            "infosphere": {"status": "success", "preview": "Найдено 3 записи ФССП"},
            ...
        }
    """
    previews = {}

    # DaData preview
    if "dadata" in source_data:
        dadata = source_data["dadata"]
        if dadata.get("status") == "success" and "data" in dadata:
            data = dadata["data"]
            name = data.get("name", {}).get("full_with_opf") or data.get("name", {}).get("short_with_opf", "")
            status = data.get("state", {}).get("status", "")
            reg_date = data.get("state", {}).get("registration_date", "")

            status_map = {
                "ACTIVE": "✅ Действующая",
                "LIQUIDATING": "⚠️ В процессе ликвидации",
                "LIQUIDATED": "❌ Ликвидирована",
                "BANKRUPT": "🚨 Банкрот",
            }
            status_text = status_map.get(status, status)

            preview = f"{name}"
            if status:
                preview += f", {status_text}"
            if reg_date:
                preview += f" (с {reg_date})"

            previews["dadata"] = {
                "status": "success",
                "preview": preview,
                "icon": "🏢",
            }
        elif "error" in dadata:
            previews["dadata"] = {
                "status": "error",
                "preview": f"Ошибка: {dadata['error']}",
                "icon": "⚠️",
            }

    # InfoSphere preview
    if "infosphere" in source_data:
        infosphere = source_data["infosphere"]
        if infosphere.get("status") == "success" and "data" in infosphere:
            data = infosphere["data"]
            findings = []

            # Check FSSP
            if isinstance(data, list):
                fssp_records = [s for s in data if s.get("source") == "fssp"]
                if fssp_records and fssp_records[0].get("Count"):
                    count = fssp_records[0]["Count"]
                    findings.append(f"🚨 ФССП: {count} записей")

            # Check bankruptcy
            bankrot_records = [s for s in data if s.get("source") == "bankrot"] if isinstance(data, list) else []
            if bankrot_records and bankrot_records[0].get("Count"):
                findings.append("🚨 Банкротство")

            preview = ", ".join(findings) if findings else "✅ Чисто по гос. реестрам"
            previews["infosphere"] = {
                "status": "success",
                "preview": preview,
                "icon": "🏛️",
            }
        elif "error" in infosphere:
            previews["infosphere"] = {
                "status": "error",
                "preview": f"Ошибка: {infosphere['error']}",
                "icon": "⚠️",
            }

    # Casebook preview
    if "casebook" in source_data:
        casebook = source_data["casebook"]
        if casebook.get("status") == "success" and "data" in casebook:
            cases = casebook["data"]
            cases_count = len(cases) if isinstance(cases, list) else 0

            if cases_count > 0:
                preview = f"⚖️ Найдено {cases_count} судебных дел"
            else:
                preview = "✅ Судебных дел не найдено"

            previews["casebook"] = {
                "status": "success",
                "preview": preview,
                "icon": "⚖️",
            }
        elif "error" in casebook:
            previews["casebook"] = {
                "status": "error",
                "preview": f"Ошибка: {casebook['error']}",
                "icon": "⚠️",
            }

    # Perplexity preview
    if "perplexity" in source_data:
        perplexity = source_data["perplexity"]
        if perplexity.get("status") == "success" and "data" in perplexity:
            data = perplexity["data"]
            answer = data.get("answer", "") if isinstance(data, dict) else ""

            # Extract first sentence or first 150 chars
            preview = answer.split(".")[0][:150] if answer else "Данные получены"
            if len(answer) > 150:
                preview += "..."

            previews["perplexity"] = {
                "status": "success",
                "preview": preview,
                "icon": "🔍",
            }
        elif "error" in perplexity:
            previews["perplexity"] = {
                "status": "error",
                "preview": f"Ошибка: {perplexity['error']}",
                "icon": "⚠️",
            }

    # Tavily preview
    if "tavily" in source_data:
        tavily = source_data["tavily"]
        if tavily.get("status") == "success" and "data" in tavily:
            data = tavily["data"]
            results_count = len(data.get("results", [])) if isinstance(data, dict) else 0

            preview = f"📰 Найдено {results_count} новостей и статей" if results_count > 0 else "Новостей не найдено"

            previews["tavily"] = {
                "status": "success",
                "preview": preview,
                "icon": "📰",
            }
        elif "error" in tavily:
            previews["tavily"] = {
                "status": "error",
                "preview": f"Ошибка: {tavily['error']}",
                "icon": "⚠️",
            }

    return previews
