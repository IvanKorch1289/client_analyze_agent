"""
Shared schemas for agents.

TypedDict definitions for LangGraph state and data structures.
"""

from typing import Any, Dict, List, Literal, TypedDict


class ClientAnalysisState(TypedDict, total=False):
    """
    Состояние workflow анализа клиента.

    Используется в LangGraph для передачи данных между агентами.
    """

    # Input data
    session_id: str
    client_name: str
    inn: str
    additional_notes: str

    # Orchestrator output
    search_intents: List[Dict[str, str]]
    orchestrator_result: Dict[str, Any]

    # Data Collector output
    search_results: List[Dict[str, Any]]
    source_data: Dict[str, Any]
    collection_stats: Dict[str, Any]

    # Report Analyzer output
    report: Dict[str, Any]
    analysis_result: str

    # File Writer output
    saved_files: Dict[str, str]

    # Error handling
    error: str
    search_error: str

    # Workflow state
    current_step: Literal[
        "orchestrating",
        "collecting",
        "searching",
        "analyzing",
        "saving",
        "completed",
        "failed",
    ]


class SearchIntent(TypedDict):
    """Поисковый запрос для data collector."""

    id: str  # unique identifier (legal, court, finance, etc.)
    category: str  # legal, court, finance, news_year, reputation, affiliates
    query: str  # actual search query
    description: str  # human-readable description


class SearchResult(TypedDict, total=False):
    """Результат поиска из одного источника."""

    source: Literal["perplexity", "tavily", "dadata", "casebook", "infosphere"]
    intent_id: str
    success: bool
    content: str
    citations: List[str]
    results: List[Dict[str, Any]]
    error: str
    integration: str
    sentiment: Dict[str, Any]


class RiskAssessment(TypedDict):
    """Оценка рисков."""

    score: int  # 0-100
    level: Literal["low", "medium", "high", "critical"]
    factors: List[str]  # Top risk factors
    categories: Dict[str, int]  # Detailed risk scores by category


class Finding(TypedDict):
    """Отдельная находка в ходе анализа."""

    category: str  # legal, court, finance, etc.
    severity: Literal["low", "medium", "high", "critical"]
    description: str
    source: str  # dadata, casebook, perplexity, tavily, infosphere


class ReportData(TypedDict):
    """Структура данных отчёта."""

    risk_assessment: RiskAssessment
    summary: str
    findings: List[Finding]
    recommendations: List[str]
    metadata: Dict[str, Any]
    source_data: Dict[str, Any]


class SourceData(TypedDict, total=False):
    """Агрегированные данные из всех источников."""

    dadata: Dict[str, Any]
    casebook: Dict[str, Any]
    infosphere: Dict[str, Any]
    perplexity: List[Dict[str, Any]]
    tavily: List[Dict[str, Any]]


__all__ = [
    "ClientAnalysisState",
    "SearchIntent",
    "SearchResult",
    "RiskAssessment",
    "Finding",
    "ReportData",
    "SourceData",
]
