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


class AsyncLLMQueueMessage(BaseModel):
    """Message for async LLM queue processing."""

    request_id: str = Field(..., description="Unique request ID")
    prompt: str = Field(..., description="User prompt")
    system_prompt: Optional[str] = Field(None, description="System prompt")
    provider: str = Field(..., description="LLM provider name")
    callback_url: str = Field(..., description="Callback URL for result delivery")
    callback_headers: Optional[Dict[str, str]] = Field(None, description="Callback headers")
    temperature: float = Field(default=0.7, description="LLM temperature")
    max_tokens: int = Field(default=4096, description="Max tokens to generate")
    request_metadata: Optional[Dict[str, Any]] = Field(None, description="Custom metadata")
    created_at: float = Field(..., description="Request creation timestamp")
