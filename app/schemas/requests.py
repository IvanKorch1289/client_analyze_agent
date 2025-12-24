"""
Request schemas for API endpoints.

Centralized Pydantic models for all API request payloads.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


class BulkDeleteRequest(BaseModel):
    """Request for bulk delete operation."""

    report_ids: List[str] = Field(..., min_length=1, max_length=100)


class ScheduleClientAnalysisRequest(BaseModel):
    """Запрос на планирование анализа клиента."""

    client_name: str = Field(..., description="Название клиента")
    inn: str = Field(..., description="ИНН клиента", min_length=10, max_length=12)
    additional_notes: str = Field(default="", description="Дополнительные заметки")

    delay_minutes: Optional[int] = Field(None, description="Задержка в минутах", ge=1)
    delay_seconds: Optional[int] = Field(None, description="Задержка в секундах", ge=1)
    run_date: Optional[datetime] = Field(None, description="Конкретное время выполнения (ISO 8601)")

    task_id: Optional[str] = Field(None, description="Пользовательский ID задачи (опционально)")


class ScheduleDataFetchRequest(BaseModel):
    """Запрос на планирование сбора данных из внешних источников."""

    inn: str = Field(..., description="ИНН компании", min_length=10, max_length=12)
    sources: List[str] = Field(
        ...,
        description="Источники данных: dadata, casebook, infosphere, perplexity, tavily",
    )
    search_query: Optional[str] = Field(
        None, description="Поисковый запрос (обязателен для perplexity/tavily)"
    )

    perplexity_recency: str = Field(default="month", description="Perplexity: фильтр актуальности (day/week/month)")
    tavily_depth: str = Field(default="basic", description="Tavily: глубина поиска (basic/advanced)")
    tavily_max_results: int = Field(default=5, description="Tavily: максимум результатов", ge=1, le=10)
    tavily_include_answer: bool = Field(default=True, description="Tavily: включить краткий ответ")

    delay_minutes: Optional[int] = Field(None, description="Задержка в минутах", ge=1)
    delay_seconds: Optional[int] = Field(None, description="Задержка в секундах", ge=1)
    run_date: Optional[datetime] = Field(None, description="Конкретное время выполнения (ISO 8601)")

    task_id: Optional[str] = Field(None, description="Пользовательский ID задачи (опционально)")


class PDFReportRequest(BaseModel):
    """Request body for PDF report generation."""

    client_name: str
    inn: Optional[str] = None
    session_id: Optional[str] = None
    report_data: Dict[str, Any]


class PerplexityRequest(BaseModel):
    """Request for Perplexity search."""

    inn: str
    search_query: str
    search_recency: str = "month"

    @property
    def query(self) -> str:
        return f"ИНН {self.inn}: {self.search_query}. Ответь только фактами без предположений."


class TavilyRequest(BaseModel):
    """Request for Tavily search."""

    inn: str
    search_query: str
    search_depth: str = "basic"
    max_results: int = 5
    include_answer: bool = True
    include_domains: Optional[List[str]] = None
    exclude_domains: Optional[List[str]] = None

    @property
    def query(self) -> str:
        return f"ИНН {self.inn} {self.search_query}"


class ComparisonRequest(BaseModel):
    """Request for reports comparison."""

    report_ids: List[str] = Field(..., min_length=2, max_length=10)


class ClientAnalysisRequest(BaseModel):
    """Request for client analysis."""

    client_name: str
    inn: Optional[str] = ""
    additional_notes: Optional[str] = ""


class PromptRequest(BaseModel):
    """Back-compat endpoint payload for Streamlit UI."""

    prompt: str
