"""
HTTP API schemas for OpenAPI (v1).

These models are intentionally lightweight: they document the response shape
without over-constraining internal dynamic fields.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


class HealthServiceInfo(BaseModel):
    configured: bool
    status: str
    model: Optional[str] = None


class HealthComponentPerplexity(BaseModel):
    configured: bool
    status: str


class HealthComponentTavily(BaseModel):
    configured: bool
    status: str


class HealthComponents(BaseModel):
    http_client: str
    tarantool: str
    openrouter: HealthServiceInfo
    perplexity: HealthComponentPerplexity
    tavily: HealthComponentTavily


class HealthResponse(BaseModel):
    status: str = Field(description="Overall status: healthy|degraded")
    issues: Optional[List[str]] = None
    components: HealthComponents


class PerplexitySearchResponse(BaseModel):
    status: str
    inn: str
    content: str
    citations: List[str] = []
    model: Optional[str] = None
    integration: Optional[str] = None


class TavilySearchResultItem(BaseModel):
    url: str
    content: Optional[str] = None
    title: Optional[str] = None


class TavilySearchResponse(BaseModel):
    status: str
    inn: str
    answer: str
    results: List[Dict[str, Any]] = []
    query: str
    cached: bool = False
    integration: Optional[str] = None


class AppMetricsResponse(BaseModel):
    status: str
    metrics: Dict[str, Any]
