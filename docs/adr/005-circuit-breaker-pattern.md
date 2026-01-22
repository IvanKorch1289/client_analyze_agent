# ADR-005: Circuit breaker pattern for external services

## Status
Accepted

## Context

The Client Analysis Agent depends on multiple external services:
- **DaData API**: Company registry data
- **InfoSphere API**: Multi-database checks (FSSP, bankruptcy, etc.)
- **Casebook API**: Court case data
- **Perplexity AI**: Web search with LLM
- **Tavily**: Web scraping
- **LLM Providers**: OpenRouter, HuggingFace, GigaChat, YandexGPT

These services can experience:
- Temporary outages
- Rate limiting
- Network timeouts
- Cascading failures

Without protection, a single failing service can:
- Block the entire analysis workflow
- Exhaust connection pools
- Accumulate timeouts (up to 6 minutes per request)
- Degrade user experience significantly

## Decision

We implemented a **three-level circuit breaker pattern**:

### Level 1: Per-Service Circuit Breakers
Each external service has its own circuit breaker with configurable thresholds.

```python
CIRCUIT_BREAKER_CONFIGS = {
    "dadata": {"failure_threshold": 5, "recovery_timeout": 30},
    "infosphere": {"failure_threshold": 3, "recovery_timeout": 60},
    "casebook": {"failure_threshold": 3, "recovery_timeout": 60},
    "perplexity": {"failure_threshold": 5, "recovery_timeout": 30},
    "tavily": {"failure_threshold": 5, "recovery_timeout": 30},
}
```

### Level 2: HTTP Client Circuit Breaker
Global circuit breaker for the HTTP client layer, protecting against widespread network issues.

### Level 3: Application Circuit Breaker
Top-level circuit breaker that triggers when error rate across all services exceeds threshold.

## Consequences

### Positive:
- **Fail Fast**: Requests fail immediately when service is known to be down
- **Resource Protection**: No connection pool exhaustion during outages
- **Automatic Recovery**: Half-open state allows gradual recovery testing
- **Isolation**: One failing service doesn't affect others
- **Metrics**: Circuit state provides health visibility

### Negative:
- **Complexity**: Three levels of circuit breakers to configure and monitor
- **False Triggers**: Temporary spikes can open circuit unnecessarily
- **Recovery Delay**: Service may be available before circuit closes
- **State Management**: Circuit state needs to be consistent across instances

### Mitigations:
- Tuned thresholds based on observed service behavior
- Half-open state with gradual traffic increase
- Prometheus metrics for circuit state monitoring
- In-memory state (acceptable for single-instance deployment)

## Implementation Details

### Circuit Breaker States

```
CLOSED ──[failures >= threshold]──> OPEN
   ^                                  │
   │                                  │
   └──[success]── HALF_OPEN <──[timeout]──┘
```

### Per-Service Configuration

```python
class CircuitBreakerConfig:
    failure_threshold: int = 5      # Failures before opening
    success_threshold: int = 2      # Successes to close from half-open
    recovery_timeout: int = 30      # Seconds before trying half-open
    timeout: int = 30               # Request timeout in seconds

# Service-specific overrides
INFOSPHERE_CONFIG = CircuitBreakerConfig(
    failure_threshold=3,
    recovery_timeout=60,
    timeout=360,  # 6 minutes for multi-page processing
)
```

### Retry with Exponential Backoff

```python
@retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=0.5, min=0.5, max=4),
    retry=retry_if_exception_type((TimeoutError, ConnectionError)),
)
async def fetch_with_retry(url: str) -> Response:
    # Circuit breaker check happens here
    if circuit_breaker.is_open:
        raise CircuitBreakerOpenError()
    ...
```

## Alternatives Considered

### No Circuit Breaker (Timeout Only)
- **Pros**: Simpler implementation
- **Cons**: Resources wasted on known-failing services
- **Rejected because**: 6-minute timeouts are unacceptable UX

### External Circuit Breaker (Envoy/Istio)
- **Pros**: Infrastructure-level, language-agnostic
- **Cons**: Additional infrastructure complexity
- **Rejected because**: Overkill for our deployment model

### Queue-Based Decoupling
- **Pros**: Complete isolation, guaranteed delivery
- **Cons**: Higher latency, complexity
- **Rejected because**: Real-time analysis requires synchronous responses

### Bulkhead Pattern Only
- **Pros**: Resource isolation without state management
- **Cons**: Doesn't provide fail-fast behavior
- **Rejected because**: We need both isolation AND fast failure detection
