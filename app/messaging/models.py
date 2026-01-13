"""
Pydantic-модели сообщений для RabbitMQ (FastStream).
"""

from __future__ import annotations

from typing import Any, Dict, Optional

from pydantic import BaseModel, Field

# Import canonical schema (avoid duplication)
from app.schemas.requests import ClientAnalysisRequest


class ClientAnalysisResult(BaseModel):
    """Результат анализа (упакованный для очереди)."""

    status: str = Field(..., description="Статус выполнения (completed/failed/...)")
    session_id: Optional[str] = Field(default=None, description="ID сессии workflow")
    summary: Optional[str] = Field(default=None, description="Короткое резюме")
    raw_result: Dict[str, Any] = Field(default_factory=dict, description="Полный результат workflow")


class CacheInvalidateRequest(BaseModel):
    """Инвалидация кэша (по префиксу или полностью)."""

    prefix: Optional[str] = Field(default=None, description="Префикс ключей")
    invalidate_all: bool = Field(default=False, description="Инвалидировать всё")
