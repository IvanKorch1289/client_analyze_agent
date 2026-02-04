"""
Prometheus metrics for Client Analysis Agent.

Provides metrics for monitoring:
- Analysis requests and duration
- LLM API calls and latency
- Cache performance
- Data source health
- System resources
"""

from typing import Optional

try:
    from prometheus_client import (
        Counter,
        Gauge,
        Histogram,
        Info,
        CollectorRegistry,
        generate_latest,
        CONTENT_TYPE_LATEST,
    )

    PROMETHEUS_AVAILABLE = True
except ImportError:
    PROMETHEUS_AVAILABLE = False


# Default registry
REGISTRY = CollectorRegistry() if PROMETHEUS_AVAILABLE else None


def create_counter(name: str, description: str, labels: list = None) -> Optional["Counter"]:
    """Create a Prometheus counter."""
    if not PROMETHEUS_AVAILABLE:
        return None
    return Counter(name, description, labels or [], registry=REGISTRY)


def create_histogram(
    name: str,
    description: str,
    labels: list = None,
    buckets: tuple = None,
) -> Optional["Histogram"]:
    """Create a Prometheus histogram."""
    if not PROMETHEUS_AVAILABLE:
        return None
    return Histogram(
        name,
        description,
        labels or [],
        buckets=buckets or (0.1, 0.5, 1.0, 2.5, 5.0, 10.0, 30.0, 60.0, 120.0, 300.0),
        registry=REGISTRY,
    )


def create_gauge(name: str, description: str, labels: list = None) -> Optional["Gauge"]:
    """Create a Prometheus gauge."""
    if not PROMETHEUS_AVAILABLE:
        return None
    return Gauge(name, description, labels or [], registry=REGISTRY)


# ========== Analysis Metrics ==========

ANALYSIS_REQUESTS = create_counter(
    "client_analysis_requests_total",
    "Total number of analysis requests",
    ["status", "source"],
)

ANALYSIS_DURATION = create_histogram(
    "client_analysis_duration_seconds",
    "Analysis duration in seconds",
    ["stage"],
    buckets=(5.0, 10.0, 30.0, 60.0, 120.0, 300.0, 600.0),
)

ACTIVE_ANALYSES = create_gauge(
    "client_analysis_active",
    "Number of currently running analyses",
)


# ========== LLM Metrics ==========

LLM_REQUESTS = create_counter(
    "client_llm_requests_total",
    "Total LLM API requests",
    ["provider", "status"],
)

LLM_LATENCY = create_histogram(
    "client_llm_latency_seconds",
    "LLM API latency in seconds",
    ["provider"],
    buckets=(1.0, 5.0, 10.0, 30.0, 60.0, 120.0),
)

LLM_TOKENS = create_counter(
    "client_llm_tokens_total",
    "Total tokens used",
    ["provider", "type"],  # type: input/output
)

LLM_FALLBACKS = create_counter(
    "client_llm_fallbacks_total",
    "Number of LLM provider fallbacks",
    ["from_provider", "to_provider"],
)


# ========== Cache Metrics ==========

CACHE_OPERATIONS = create_counter(
    "client_cache_operations_total",
    "Cache operations",
    ["operation", "status"],  # operation: get/set/delete, status: hit/miss/success
)

CACHE_HIT_RATE = create_gauge(
    "client_cache_hit_rate",
    "Cache hit rate percentage",
    ["cache_type"],
)

CACHE_SIZE = create_gauge(
    "client_cache_size_bytes",
    "Cache size in bytes",
    ["cache_type"],
)


# ========== Data Source Metrics ==========

SOURCE_REQUESTS = create_counter(
    "client_source_requests_total",
    "Data source requests",
    ["source", "status"],
)

SOURCE_LATENCY = create_histogram(
    "client_source_latency_seconds",
    "Data source latency in seconds",
    ["source"],
    buckets=(1.0, 5.0, 10.0, 30.0, 60.0, 180.0, 360.0),
)

SOURCE_AVAILABLE = create_gauge(
    "client_source_available",
    "Data source availability (1=available, 0=unavailable)",
    ["source"],
)


# ========== Risk Score Metrics ==========

RISK_SCORE = create_histogram(
    "client_risk_score",
    "Distribution of risk scores",
    ["category"],
    buckets=(10, 25, 50, 75, 90, 100),
)

HIGH_RISK_ALERTS = create_counter(
    "client_high_risk_alerts_total",
    "Number of high risk alerts triggered",
    ["risk_level"],
)


# ========== PII Protection Metrics ==========

PII_MASKING_CALLS = create_counter(
    "client_pii_masking_calls_total",
    "Total PII masking calls",
    ["status"],  # status: detected/clean/error
)

PII_ENTITIES_DETECTED = create_counter(
    "client_pii_entities_detected_total",
    "PII entities detected by type",
    ["entity_type"],  # RU_INN, RU_PERSON, RU_PHONE, etc.
)

PII_MASKING_LATENCY = create_histogram(
    "client_pii_masking_latency_seconds",
    "PII masking latency in seconds",
    [],
    buckets=(0.01, 0.05, 0.1, 0.25, 0.5, 1.0, 2.0, 5.0),
)

PII_MASKING_ERRORS = create_counter(
    "client_pii_masking_errors_total",
    "PII masking errors (LLM calls blocked)",
    ["error_type"],  # masking_failure, analyzer_init
)


# ========== System Metrics ==========

QUEUE_SIZE = create_gauge(
    "client_queue_size",
    "Message queue size",
    ["queue_name"],
)

ERRORS = create_counter(
    "client_errors_total",
    "Total errors by type",
    ["error_type", "component"],
)


# ========== Application Info ==========

APP_INFO = None
if PROMETHEUS_AVAILABLE:
    APP_INFO = Info("client_analysis_agent", "Application info", registry=REGISTRY)


class MetricsCollector:
    """
    Facade for collecting metrics throughout the application.

    Usage:
        metrics = MetricsCollector()
        metrics.record_analysis_start()
        # ... do analysis ...
        metrics.record_analysis_complete(duration=45.0, success=True)
    """

    def __init__(self):
        self._enabled = PROMETHEUS_AVAILABLE

    @property
    def enabled(self) -> bool:
        return self._enabled

    def set_app_info(self, version: str, environment: str) -> None:
        """Set application info."""
        if APP_INFO:
            APP_INFO.info(
                {
                    "version": version,
                    "environment": environment,
                }
            )

    # ===== Analysis =====

    def record_analysis_start(self) -> None:
        """Record start of analysis."""
        if ACTIVE_ANALYSES:
            ACTIVE_ANALYSES.inc()

    def record_analysis_complete(
        self,
        duration: float,
        success: bool,
        source: str = "api",
    ) -> None:
        """Record completion of analysis."""
        if ACTIVE_ANALYSES:
            ACTIVE_ANALYSES.dec()
        if ANALYSIS_REQUESTS:
            ANALYSIS_REQUESTS.labels(
                status="success" if success else "failure",
                source=source,
            ).inc()
        if ANALYSIS_DURATION:
            ANALYSIS_DURATION.labels(stage="total").observe(duration)

    def record_analysis_stage(self, stage: str, duration: float) -> None:
        """Record duration of analysis stage."""
        if ANALYSIS_DURATION:
            ANALYSIS_DURATION.labels(stage=stage).observe(duration)

    # ===== LLM =====

    def record_llm_request(
        self,
        provider: str,
        success: bool,
        latency: float,
        input_tokens: int = 0,
        output_tokens: int = 0,
    ) -> None:
        """Record LLM API request."""
        if LLM_REQUESTS:
            LLM_REQUESTS.labels(
                provider=provider,
                status="success" if success else "failure",
            ).inc()
        if LLM_LATENCY:
            LLM_LATENCY.labels(provider=provider).observe(latency)
        if LLM_TOKENS:
            if input_tokens:
                LLM_TOKENS.labels(provider=provider, type="input").inc(input_tokens)
            if output_tokens:
                LLM_TOKENS.labels(provider=provider, type="output").inc(output_tokens)

    def record_llm_fallback(self, from_provider: str, to_provider: str) -> None:
        """Record LLM provider fallback."""
        if LLM_FALLBACKS:
            LLM_FALLBACKS.labels(
                from_provider=from_provider,
                to_provider=to_provider,
            ).inc()

    # ===== Cache =====

    def record_cache_hit(self, cache_type: str = "default") -> None:
        """Record cache hit."""
        if CACHE_OPERATIONS:
            CACHE_OPERATIONS.labels(operation="get", status="hit").inc()

    def record_cache_miss(self, cache_type: str = "default") -> None:
        """Record cache miss."""
        if CACHE_OPERATIONS:
            CACHE_OPERATIONS.labels(operation="get", status="miss").inc()

    def record_cache_set(self, success: bool = True) -> None:
        """Record cache set."""
        if CACHE_OPERATIONS:
            CACHE_OPERATIONS.labels(
                operation="set",
                status="success" if success else "failure",
            ).inc()

    def update_cache_stats(
        self,
        cache_type: str,
        hit_rate: float,
        size_bytes: int,
    ) -> None:
        """Update cache statistics."""
        if CACHE_HIT_RATE:
            CACHE_HIT_RATE.labels(cache_type=cache_type).set(hit_rate)
        if CACHE_SIZE:
            CACHE_SIZE.labels(cache_type=cache_type).set(size_bytes)

    # ===== Data Sources =====

    def record_source_request(
        self,
        source: str,
        success: bool,
        latency: float,
    ) -> None:
        """Record data source request."""
        if SOURCE_REQUESTS:
            SOURCE_REQUESTS.labels(
                source=source,
                status="success" if success else "failure",
            ).inc()
        if SOURCE_LATENCY:
            SOURCE_LATENCY.labels(source=source).observe(latency)

    def set_source_availability(self, source: str, available: bool) -> None:
        """Set data source availability."""
        if SOURCE_AVAILABLE:
            SOURCE_AVAILABLE.labels(source=source).set(1 if available else 0)

    # ===== Risk =====

    def record_risk_score(self, score: float, category: str = "total") -> None:
        """Record risk score."""
        if RISK_SCORE:
            RISK_SCORE.labels(category=category).observe(score)

    def record_high_risk_alert(self, risk_level: str) -> None:
        """Record high risk alert."""
        if HIGH_RISK_ALERTS:
            HIGH_RISK_ALERTS.labels(risk_level=risk_level).inc()

    # ===== PII =====

    def record_pii_masking(
        self,
        pii_detected: bool,
        entity_types: list = None,
        latency: float = 0.0,
    ) -> None:
        """Record PII masking call result."""
        if PII_MASKING_CALLS:
            status = "detected" if pii_detected else "clean"
            PII_MASKING_CALLS.labels(status=status).inc()
        if PII_MASKING_LATENCY and latency > 0:
            PII_MASKING_LATENCY.observe(latency)
        if PII_ENTITIES_DETECTED and entity_types:
            for entity_type in entity_types:
                PII_ENTITIES_DETECTED.labels(entity_type=entity_type).inc()

    def record_pii_error(self, error_type: str = "masking_failure") -> None:
        """Record PII masking error (LLM call blocked)."""
        if PII_MASKING_CALLS:
            PII_MASKING_CALLS.labels(status="error").inc()
        if PII_MASKING_ERRORS:
            PII_MASKING_ERRORS.labels(error_type=error_type).inc()

    # ===== Errors =====

    def record_error(self, error_type: str, component: str) -> None:
        """Record error."""
        if ERRORS:
            ERRORS.labels(error_type=error_type, component=component).inc()

    # ===== Export =====

    def get_metrics(self) -> bytes:
        """Get metrics in Prometheus format."""
        if not PROMETHEUS_AVAILABLE or not REGISTRY:
            return b""
        return generate_latest(REGISTRY)

    def get_content_type(self) -> str:
        """Get content type for metrics response."""
        if not PROMETHEUS_AVAILABLE:
            return "text/plain"
        return CONTENT_TYPE_LATEST


# Global metrics collector instance
metrics = MetricsCollector()
