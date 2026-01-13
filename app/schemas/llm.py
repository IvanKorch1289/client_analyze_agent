"""
LLM request/response schemas for async processing.

Supports multiple LLM providers with webhook callback delivery.
"""

from enum import Enum
from typing import Any, Dict, Optional

from pydantic import BaseModel, Field, HttpUrl


class LLMProviderEnum(str, Enum):
    """Supported LLM providers."""

    OPENROUTER = "openrouter"
    HUGGINGFACE = "huggingface"
    GIGACHAT = "gigachat"
    YANDEXGPT = "yandexgpt"
    OPENLLAMA = "openllama"  # Internal LLM via local deployment


class AsyncLLMRequest(BaseModel):
    """
    Request for async LLM processing.

    The request is queued immediately and the result is delivered
    via webhook callback to the specified URL.
    """

    prompt: str = Field(..., min_length=1, max_length=50000, description="User prompt")
    system_prompt: Optional[str] = Field(
        None, max_length=10000, description="System prompt (optional)"
    )
    provider: LLMProviderEnum = Field(
        default=LLMProviderEnum.OPENROUTER, description="LLM provider to use"
    )
    callback_url: HttpUrl = Field(..., description="URL to POST results to")
    callback_headers: Optional[Dict[str, str]] = Field(
        default=None, description="Headers to include in callback request"
    )

    # LLM parameters
    temperature: float = Field(default=0.7, ge=0.0, le=2.0, description="Sampling temperature")
    max_tokens: int = Field(default=4096, ge=1, le=32000, description="Maximum tokens to generate")

    # Metadata for tracking
    request_metadata: Optional[Dict[str, Any]] = Field(
        default=None, description="Custom metadata returned with callback"
    )


class AsyncLLMAccepted(BaseModel):
    """Response when async LLM request is accepted."""

    status: str = "accepted"
    request_id: str = Field(..., description="Unique request ID for tracking")
    message: str = "Request queued for processing"
    estimated_time_seconds: Optional[int] = Field(
        None, description="Estimated processing time"
    )


class LLMCallbackPayload(BaseModel):
    """Payload sent to callback URL after LLM processing."""

    request_id: str = Field(..., description="Original request ID")
    status: str = Field(..., description="Processing status: success or error")
    provider_used: str = Field(..., description="Provider that processed the request")
    response: Optional[str] = Field(None, description="LLM response text")
    error: Optional[str] = Field(None, description="Error message if failed")
    usage: Optional[Dict[str, int]] = Field(None, description="Token usage statistics")
    processing_time_ms: float = Field(..., description="Processing time in milliseconds")
    request_metadata: Optional[Dict[str, Any]] = Field(
        None, description="Original request metadata"
    )


class LLMProviderStatus(BaseModel):
    """Status of an LLM provider."""

    provider: str
    available: bool
    model: Optional[str] = None
    error: Optional[str] = None


class LLMProvidersResponse(BaseModel):
    """Response listing available LLM providers."""

    providers: list[str] = Field(..., description="List of provider names")
    status: Dict[str, bool] = Field(..., description="Provider availability status")


__all__ = [
    "LLMProviderEnum",
    "AsyncLLMRequest",
    "AsyncLLMAccepted",
    "LLMCallbackPayload",
    "LLMProviderStatus",
    "LLMProvidersResponse",
]
