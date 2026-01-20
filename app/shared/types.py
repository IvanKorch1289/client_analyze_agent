"""
Typed dictionaries for better type safety.

Replaces Dict[str, Any] with specific typed structures.
"""

from typing import Any, Dict, List, Literal, Optional, TypedDict


# ============================================================
# Analysis Types
# ============================================================


class CompanyInfo(TypedDict):
    """Company basic information."""

    name: str
    inn: str
    ogrn: Optional[str]
    kpp: Optional[str]
    address: Optional[str]
    status: Optional[str]


class RiskScore(TypedDict):
    """Risk score breakdown."""

    total: int
    legal: int
    financial: int
    reputation: int
    regulatory: int


class RiskLevel(TypedDict):
    """Risk level with label."""

    level: Literal["low", "medium", "high", "critical"]
    score: int
    description: str


class SearchResult(TypedDict):
    """Search result from web sources."""

    intent_id: str
    description: str
    query: str
    success: bool
    content: str
    citations: List[str]
    sentiment: "SentimentResult"


class SentimentResult(TypedDict):
    """Sentiment analysis result."""

    label: Literal["positive", "negative", "neutral"]
    score: float


# ============================================================
# Source Data Types
# ============================================================


class DaDataResult(TypedDict):
    """DaData API response structure."""

    source: Literal["dadata"]
    success: bool
    data: Optional[Dict[str, Any]]
    error: Optional[str]


class CasebookResult(TypedDict):
    """Casebook API response structure."""

    source: Literal["casebook"]
    success: bool
    data: Optional[List[Dict[str, Any]]]
    error: Optional[str]


class InfoSphereResult(TypedDict):
    """InfoSphere API response structure."""

    source: Literal["infosphere"]
    success: bool
    data: Optional[Dict[str, Any]]
    error: Optional[str]


class PerplexityResult(TypedDict):
    """Perplexity API response structure."""

    source: Literal["perplexity"]
    intent_id: str
    success: bool
    content: Optional[str]
    citations: List[str]
    error: Optional[str]


class TavilyResult(TypedDict):
    """Tavily API response structure."""

    source: Literal["tavily"]
    intent_id: str
    success: bool
    answer: Optional[str]
    results: List[Dict[str, Any]]
    error: Optional[str]


class SourceData(TypedDict):
    """Combined data from all sources."""

    dadata: Optional[DaDataResult]
    infosphere: Optional[InfoSphereResult]
    casebook: Optional[CasebookResult]
    perplexity: Dict[str, Any]
    tavily: Dict[str, Any]
    tavily_full_texts: List[Dict[str, Any]]
    cascade_perplexity: Optional[Dict[str, Any]]


# ============================================================
# Report Types
# ============================================================


class ReportMetadata(TypedDict):
    """Report metadata."""

    report_id: str
    created_at: float
    updated_at: Optional[float]
    version: int


class AnalysisReport(TypedDict):
    """Full analysis report structure."""

    metadata: ReportMetadata
    company: CompanyInfo
    risk_score: RiskScore
    risk_level: RiskLevel
    search_results: List[SearchResult]
    summary: str
    recommendations: List[str]
    sources_used: List[str]


# ============================================================
# Cache Types
# ============================================================


class CacheEntry(TypedDict):
    """Cache entry structure."""

    key: str
    value: Any
    expires_at: float
    created_at: float
    source: str


class CacheStats(TypedDict):
    """Cache statistics."""

    hits: int
    misses: int
    hit_rate_percent: float
    sets: int
    deletes: int
    avg_get_time_ms: float
    avg_set_time_ms: float


# ============================================================
# LLM Types
# ============================================================


class LLMRequest(TypedDict):
    """LLM request structure."""

    prompt: str
    provider: str
    temperature: float
    max_tokens: int


class LLMResponse(TypedDict):
    """LLM response structure."""

    content: str
    provider: str
    duration_ms: float
    tokens_used: Optional[int]
    from_cache: bool


class PIIResult(TypedDict):
    """PII detection result."""

    pii_detected: bool
    pii_count: int
    detected_pii_types: List[str]
    masked_text: str
    replacements: Dict[str, str]


# ============================================================
# API Types
# ============================================================


class APIResponse(TypedDict):
    """Standard API response."""

    status: Literal["success", "error"]
    data: Optional[Any]
    error: Optional[str]
    timestamp: float


class HealthStatus(TypedDict):
    """Health check response."""

    status: Literal["healthy", "unhealthy", "degraded"]
    components: Dict[str, bool]
    uptime_seconds: float
    version: str


class PaginatedResponse(TypedDict):
    """Paginated API response."""

    items: List[Any]
    total: int
    page: int
    page_size: int
    has_next: bool
    has_prev: bool


# ============================================================
# Feedback Types
# ============================================================


class FeedbackRequest(TypedDict):
    """User feedback request."""

    report_id: str
    rating: int
    comment: Optional[str]
    focus_areas: List[str]


class FeedbackResponse(TypedDict):
    """Feedback response."""

    feedback_id: str
    received_at: float
    reanalysis_triggered: bool


# ============================================================
# Monitoring Types
# ============================================================


class CircuitBreakerStatus(TypedDict):
    """Circuit breaker status."""

    state: Literal["closed", "open", "half_open"]
    failure_count: int
    last_failure_time: Optional[float]
    last_success_time: Optional[float]


class ProviderStatus(TypedDict):
    """LLM provider status."""

    provider: str
    available: bool
    last_check: float
    latency_ms: Optional[float]
    error: Optional[str]


class SystemMetrics(TypedDict):
    """System metrics."""

    cpu_percent: float
    memory_percent: float
    disk_percent: float
    active_connections: int
    queue_size: int
