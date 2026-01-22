# ADR-003: LLM provider fallback chain strategy

## Status
Accepted

## Context

The Client Analysis Agent relies heavily on LLM capabilities for:
- Generating search queries from company names
- Analyzing collected data for risk factors
- Producing human-readable risk assessments

LLM providers can experience:
- Rate limiting during peak usage
- Service outages
- Network connectivity issues
- API changes or deprecations

We needed a resilient strategy to ensure analysis completion even when primary LLM is unavailable.

## Decision

We implemented a **multi-provider fallback chain** with automatic failover:

1. **OpenRouter** (Primary) - Claude 3.5 Sonnet
2. **HuggingFace** (Fallback #1) - Llama 3.1 70B
3. **GigaChat** (Fallback #2) - GigaChat-Pro (Sber)
4. **YandexGPT** (Fallback #3) - YandexGPT-Lite

### Key design principles:

1. **Lazy Initialization**: Providers are initialized only when needed, reducing startup time and memory usage.

2. **Graceful Degradation**: Each fallback provides acceptable (if reduced) quality rather than complete failure.

3. **Transparent Failover**: Application code doesn't need to handle provider-specific logic.

4. **Configurable Priority**: Provider order can be changed via configuration without code changes.

## Consequences

### Positive:
- High availability (4 independent providers)
- Graceful degradation under partial failures
- Cost optimization (can prioritize cheaper providers)
- Geographic redundancy (US + Russia providers)

### Negative:
- Inconsistent output quality across providers
- Need to maintain API keys for 4 services
- Prompt compatibility issues (different models interpret prompts differently)
- Increased complexity in LLM manager

### Mitigations:
- Standardized prompt templates that work across all providers
- Output validation to catch provider-specific quirks
- Metrics tracking per provider for quality monitoring
- PII masking before any LLM call (compliance requirement)

## Implementation Details

```python
class LLMManager:
    """Multi-provider LLM manager with automatic fallback."""

    PROVIDERS = [
        ("openrouter", "claude-3.5-sonnet"),
        ("huggingface", "meta-llama/Llama-3.1-70B-Instruct"),
        ("gigachat", "GigaChat-Pro"),
        ("yandexgpt", "yandexgpt-lite"),
    ]

    async def ainvoke(self, prompt: str) -> str:
        # PII masking (152-FZ compliance)
        masked = mask_pii(prompt)

        for provider_name, model in self.PROVIDERS:
            try:
                provider = self._get_provider(provider_name)
                result = await provider.ainvoke(masked.text)

                # Unmask PII in response
                return unmask_pii(result, masked.replacements)
            except Exception as e:
                logger.warning(f"Provider {provider_name} failed: {e}")
                continue

        raise AllProvidersFailedError("All LLM providers exhausted")
```

## Alternatives Considered

### Single Provider with Retry
- **Pros**: Simplest implementation
- **Cons**: Single point of failure, no resilience
- **Rejected because**: Unacceptable for production use

### Load Balancer Across Providers
- **Pros**: Better resource utilization, automatic health checks
- **Cons**: Complex setup, all providers must be equally capable
- **Rejected because**: Providers have different capabilities and pricing

### Queue-Based with Dead Letter
- **Pros**: Guaranteed eventual processing
- **Cons**: Higher latency, complexity
- **Rejected because**: Real-time response required for good UX

### Self-Hosted LLM (Ollama/vLLM)
- **Pros**: No external dependencies, full control
- **Cons**: High infrastructure cost, limited model quality
- **Rejected because**: Quality of self-hosted models doesn't meet our requirements yet
