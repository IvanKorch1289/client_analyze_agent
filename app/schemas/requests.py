"""
Request schemas for API endpoints.

Centralized Pydantic models for all API request payloads.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field, field_validator


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
    search_query: Optional[str] = Field(None, description="Поисковый запрос (обязателен для perplexity/tavily)")

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
    """
    Request for client analysis.

    Canonical schema used by API, messaging, and MCP server.
    Includes validation for security-sensitive fields.
    """

    client_name: str = Field(..., max_length=200, description="Client/company name")
    inn: str = Field(default="", description="Company INN (10 or 12 digits, optional)")
    additional_notes: str = Field(
        default="",
        max_length=5000,
        description="Additional notes from user",
    )
    session_id: Optional[str] = Field(default=None, description="Session ID for tracking")
    save_report: bool = Field(default=True, description="Save report to database")

    @field_validator("client_name")
    @classmethod
    def validate_client_name(cls, v: str) -> str:
        """Validate and sanitize client name."""
        from app.shared.security import sanitize_for_llm

        return sanitize_for_llm(v, max_length=200, strict=False)

    @field_validator("inn")
    @classmethod
    def validate_inn_field(cls, v: str) -> str:
        """Validate INN format."""
        if v:
            from app.shared.security import validate_inn

            is_valid, error = validate_inn(v)
            if not is_valid:
                raise ValueError(error)
        return v.strip()

    @field_validator("additional_notes")
    @classmethod
    def validate_notes(cls, v: str) -> str:
        """Validate and sanitize additional notes."""
        if v:
            from app.shared.security import sanitize_for_llm

            return sanitize_for_llm(v, max_length=5000, strict=False)
        return ""


class BatchAnalysisRequest(BaseModel):
    """Request for batch client analysis (multiple INNs)."""

    clients: List[Dict[str, Any]] = Field(
        ...,
        min_length=1,
        max_length=100,
        description="List of clients to analyze. Each must have 'client_name' and optionally 'inn', 'additional_notes'.",
    )
    save_reports: bool = Field(default=True, description="Save reports to database")
    webhook_url: Optional[str] = Field(None, description="URL to notify when batch completes")

    @field_validator("clients")
    @classmethod
    def validate_clients(cls, v: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Validate each client entry has required fields."""
        for i, client in enumerate(v):
            if "client_name" not in client:
                raise ValueError(f"Client at index {i} missing 'client_name'")
            if len(client["client_name"]) > 200:
                raise ValueError(f"Client at index {i}: client_name exceeds 200 chars")
        return v


class WebhookRegisterRequest(BaseModel):
    """Request to register a webhook endpoint."""

    url: str = Field(..., description="URL to receive POST notifications")
    events: List[str] = Field(
        ...,
        min_length=1,
        description="Event types to subscribe to (e.g., 'analysis.completed', 'batch.completed')",
    )
    secret: Optional[str] = Field(None, description="HMAC secret for signature verification")
    description: str = Field(default="", description="Human-readable description")


class PromptRequest(BaseModel):
    """Back-compat endpoint payload for Streamlit UI."""

    prompt: str


class FeedbackRequest(BaseModel):
    """Запрос на отправку фидбека по отчёту с перезапуском анализа."""

    report_id: str = Field(..., description="ID отчёта для фидбека")
    rating: str = Field(
        ...,
        description="Оценка: accurate, partially_accurate, inaccurate",
        pattern="^(accurate|partially_accurate|inaccurate)$",
    )
    comment: Optional[str] = Field(None, description="Комментарий пользователя")
    rerun_analysis: bool = Field(
        default=True,
        description="Перезапустить анализ с учётом фидбека",
    )
    focus_areas: Optional[List[str]] = Field(
        None,
        description="Области для дополнительного внимания при переанализе",
    )
