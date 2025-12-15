"""
Client Analysis Workflow: LangGraph workflow для анализа клиентов.
Orchestrator -> Search Agent -> Report Analyzer
"""
import asyncio
import time
from typing import Any, Dict, List, Literal, Optional, TypedDict

from langgraph.graph import END, StateGraph

from app.advanced_funcs.logging_client import logger
from app.agents.orchestrator import orchestrator_agent
from app.agents.report_analyzer import report_analyzer_agent
from app.agents.search import search_agent
from app.storage.tarantool import save_thread_to_tarantool


class ClientAnalysisState(TypedDict, total=False):
    """Состояние workflow анализа клиента."""
    session_id: str
    client_name: str
    inn: str
    additional_notes: str
    
    search_intents: List[Dict[str, str]]
    search_results: List[Dict[str, Any]]
    
    orchestrator_result: Dict[str, Any]
    report: Dict[str, Any]
    analysis_result: str
    
    error: str
    search_error: str
    
    current_step: Literal[
        "orchestrating",
        "searching",
        "analyzing",
        "completed",
        "failed"
    ]


def build_client_analysis_graph():
    """Создаёт и возвращает скомпилированный граф анализа клиента."""
    workflow = StateGraph(ClientAnalysisState)
    
    workflow.add_node("orchestrator", orchestrator_agent)
    workflow.add_node("search", search_agent)
    workflow.add_node("analyzer", report_analyzer_agent)
    
    workflow.set_entry_point("orchestrator")
    
    def route_after_orchestrator(state: Dict[str, Any]) -> str:
        if state.get("current_step") == "failed":
            return END
        return "search"
    
    workflow.add_conditional_edges(
        "orchestrator",
        route_after_orchestrator,
        {
            "search": "search",
            END: END
        }
    )
    
    workflow.add_edge("search", "analyzer")
    workflow.add_edge("analyzer", END)
    
    return workflow.compile()


async def run_client_analysis(
    client_name: str,
    inn: str = "",
    additional_notes: str = "",
    session_id: Optional[str] = None
) -> Dict[str, Any]:
    """
    Запускает workflow анализа клиента.
    
    Args:
        client_name: Название компании
        inn: ИНН компании (опционально)
        additional_notes: Дополнительные заметки (опционально)
        session_id: ID сессии (генерируется автоматически)
    
    Returns:
        Dict с результатом анализа и отчётом
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
        "orchestrator_result": {},
        "report": {},
        "analysis_result": "",
        "error": "",
        "search_error": ""
    }
    
    logger.info(f"Starting client analysis workflow: {session_id}", component="workflow")
    
    try:
        graph = build_client_analysis_graph()
        
        final_state = await graph.ainvoke(initial_state)
        
        final_state["current_step"] = final_state.get("current_step", "completed")
        
    except Exception as e:
        logger.error(f"Workflow error: {e}", component="workflow")
        final_state = {
            **initial_state,
            "error": str(e),
            "current_step": "failed"
        }
    
    try:
        thread_data = {
            "input": f"Анализ клиента: {client_name}",
            "created_at": time.time(),
            "messages": [
                {"type": "input", "data": {"client_name": client_name, "inn": inn}},
                {"type": "report", "data": final_state.get("report", {})}
            ],
            "final_state": final_state
        }
        asyncio.create_task(save_thread_to_tarantool(session_id, thread_data))
    except Exception as e:
        logger.error(f"Failed to save thread: {e}", component="workflow")
    
    return {
        "session_id": session_id,
        "client_name": client_name,
        "inn": inn,
        "status": final_state.get("current_step"),
        "report": final_state.get("report", {}),
        "summary": final_state.get("analysis_result", ""),
        "error": final_state.get("error") or final_state.get("search_error"),
        "timestamp": time.time()
    }
