# Implementation Plan: Client Analyze Agent Improvements

## Executive Summary

This plan addresses four key areas:
1. **Dependency Vulnerabilities** - Security patches for critical CVEs
2. **Code Refactoring** - Remove duplications, improve patterns
3. **Async LLM API Endpoint** - Webhook-based async LLM access
4. **Streamlit Frontend** - UI for direct LLM interaction

---

## Phase 1: Dependency Vulnerabilities (CRITICAL)

### Critical CVEs Identified

| Package | Current | Vulnerability | Severity | Action |
|---------|---------|---------------|----------|--------|
| `langchain` | ^0.3.27 | CVE-2025-68664 (Serialization Injection) | CVSS 9.3 | Upgrade to >=0.3.29 |
| `langchain-core` | implicit | Same CVE - Secret extraction | HIGH | Upgrade with langchain |

### Implementation Steps

```bash
# Step 1: Audit current vulnerabilities
pip-audit --format=json > audit_report.json

# Step 2: Update pyproject.toml
# langchain = "^0.3.29"  # or latest patched
# langchain-community = "^0.3.30"

# Step 3: Update dependencies
poetry update langchain langchain-core langchain-community

# Step 4: Verify
poetry run pytest
```

### Files to Modify
- `pyproject.toml` - Update package versions
- `poetry.lock` - Regenerate

---

## Phase 2: Code Refactoring

### 2.1 Duplicate Code to Consolidate

#### A. Duplicate `get_llm_manager()` Functions

| Location | Action |
|----------|--------|
| `app/agents/llm_manager.py:504` | KEEP (canonical) |
| `app/services/llm_provider.py:16` | REMOVE, re-export from llm_manager |

#### B. Duplicate `ClientAnalysisRequest` Schema (3 copies!)

| Location | Action |
|----------|--------|
| `app/schemas/requests.py:100` | KEEP (canonical) |
| `app/messaging/models.py:12` | REMOVE, import from schemas |
| `app/mcp_server/tools/analysis_tools.py:20` | REMOVE, import from schemas |

#### C. Duplicate Caching Patterns

Both `PerplexityClient` and `TavilyClient` implement identical L1+L2 caching.

**Create:** `app/services/base_cached_client.py`

```python
from abc import ABC, abstractmethod
from typing import Any, Dict, Optional
import asyncio

class CachedServiceClient(ABC):
    """Base class for service clients with L1+L2 caching."""

    def __init__(self, cache_ttl: int = 3600):
        self._cache: Dict[str, Dict[str, Any]] = {}
        self._cache_ttl = cache_ttl
        self._inflight: Dict[str, asyncio.Future] = {}

    @abstractmethod
    def _get_cache_key(self, **kwargs) -> str: ...

    @abstractmethod
    async def _execute_request(self, **kwargs) -> Dict[str, Any]: ...

    async def request_with_cache(self, use_cache: bool = True, **kwargs):
        """Common L1 -> L2 -> Coalesce -> Execute pattern."""
        cache_key = self._get_cache_key(**kwargs)

        # L1 check
        if use_cache and cache_key in self._cache:
            cached = self._cache[cache_key]
            if not self._is_expired(cached):
                return cached["data"]

        # Request coalescing
        if cache_key in self._inflight:
            return await self._inflight[cache_key]

        # Execute
        future = asyncio.create_task(self._execute_request(**kwargs))
        self._inflight[cache_key] = future

        try:
            result = await future
            self._cache[cache_key] = {"data": result, "timestamp": time.time()}
            return result
        finally:
            self._inflight.pop(cache_key, None)
```

### 2.2 Anti-Patterns to Fix

#### A. Print Statements to Replace

| File | Line | Replace With |
|------|------|--------------|
| `app/main.py` | 630 | `logger.info()` |
| `app/shared/config.py` | 139-141 | `logger.error()` |
| `app/config/__init__.py` | 13-19 | Remove (docstring) |

#### B. Singleton Pattern Standardization

**Current:** 11 different `global _variable` patterns

**Standard pattern to adopt:**

```python
class Service:
    _instance: Optional["Service"] = None
    _lock: Optional[asyncio.Lock] = None

    @classmethod
    async def get_instance(cls) -> "Service":
        if cls._lock is None:
            cls._lock = asyncio.Lock()
        async with cls._lock:
            if cls._instance is None:
                cls._instance = cls()
            return cls._instance
```

### 2.3 Files to Refactor

| File | Changes |
|------|---------|
| `app/services/llm_provider.py` | Remove duplicate, re-export |
| `app/messaging/models.py` | Import schema instead of defining |
| `app/mcp_server/tools/analysis_tools.py` | Import schema |
| `app/services/perplexity_client.py` | Inherit from CachedServiceClient |
| `app/services/tavily_client.py` | Inherit from CachedServiceClient |

---

## Phase 3: Async LLM API Endpoint

### 3.1 Architecture

```
┌──────────┐      ┌───────────────┐      ┌───────────┐
│  Client  │─(1)─▶│ POST /llm/async│─(2)─▶│ RabbitMQ  │
│  System  │      │ 202 Accepted  │      │ llm_queue │
└──────────┘      └───────────────┘      └─────┬─────┘
      ▲                                        │
      │                                        ▼
      │           ┌───────────────┐      ┌───────────┐
      └───(4)─────│   Callback    │◀─(3)─│  Worker   │
                  │   Webhook     │      │ (consume) │
                  └───────────────┘      └─────┬─────┘
                                               │
                                         ┌─────▼─────┐
                                         │ LLMManager│
                                         │ (fallback)│
                                         └───────────┘
```

### 3.2 New Files to Create

#### A. `app/schemas/llm.py` - Request/Response Models

```python
from enum import Enum
from typing import Any, Dict, Optional
from pydantic import BaseModel, Field, HttpUrl

class LLMProviderEnum(str, Enum):
    OPENROUTER = "openrouter"
    HUGGINGFACE = "huggingface"
    GIGACHAT = "gigachat"
    YANDEXGPT = "yandexgpt"
    OPENLLAMA = "openllama"

class AsyncLLMRequest(BaseModel):
    prompt: str = Field(..., min_length=1, max_length=50000)
    system_prompt: Optional[str] = Field(None, max_length=10000)
    provider: LLMProviderEnum = Field(default=LLMProviderEnum.OPENROUTER)
    callback_url: HttpUrl
    callback_headers: Optional[Dict[str, str]] = None
    temperature: float = Field(default=0.7, ge=0.0, le=2.0)
    max_tokens: int = Field(default=4096, ge=1, le=32000)
    request_metadata: Optional[Dict[str, Any]] = None

class AsyncLLMAccepted(BaseModel):
    status: str = "accepted"
    request_id: str
    message: str = "Request queued for processing"
    estimated_time_seconds: Optional[int] = None

class LLMCallbackPayload(BaseModel):
    request_id: str
    status: str  # "success" | "error"
    provider_used: str
    response: Optional[str] = None
    error: Optional[str] = None
    usage: Optional[Dict[str, int]] = None
    processing_time_ms: float
    request_metadata: Optional[Dict[str, Any]] = None
```

#### B. `app/api/routes/llm.py` - API Endpoint

```python
import time
import uuid
from fastapi import APIRouter, HTTPException, Request

from app.schemas.llm import AsyncLLMRequest, AsyncLLMAccepted, LLMProviderEnum
from app.messaging.publisher import get_rabbit_publisher
from app.config import settings

llm_router = APIRouter(prefix="/llm", tags=["LLM"])

@llm_router.post("/async", response_model=AsyncLLMAccepted, status_code=202)
async def submit_async_llm_request(request: Request, data: AsyncLLMRequest):
    """Submit async LLM request. Returns 202 immediately, delivers via callback."""
    request_id = f"llm_{uuid.uuid4().hex[:16]}_{int(time.time())}"

    if settings.queue.enabled:
        publisher = get_rabbit_publisher()
        await publisher.publish_async_llm_request(
            request_id=request_id,
            prompt=data.prompt,
            system_prompt=data.system_prompt,
            provider=data.provider.value,
            callback_url=str(data.callback_url),
            callback_headers=data.callback_headers,
            temperature=data.temperature,
            max_tokens=data.max_tokens,
            request_metadata=data.request_metadata,
        )
    else:
        # Fallback: background task
        import asyncio
        asyncio.create_task(_process_llm_background(request_id, data))

    return AsyncLLMAccepted(request_id=request_id, estimated_time_seconds=30)

@llm_router.get("/providers")
async def list_llm_providers():
    """List available LLM providers."""
    from app.agents.llm_manager import get_llm_manager
    manager = get_llm_manager()
    return {
        "providers": [p.value for p in LLMProviderEnum],
        "status": manager.get_provider_status(),
    }
```

#### C. `app/messaging/broker.py` - Queue Handler (additions)

```python
@broker.subscriber("llm_async_queue")
async def handle_async_llm_request(msg: AsyncLLMQueueMessage):
    """Process async LLM request and send callback."""
    import httpx
    start_time = time.perf_counter()

    try:
        from app.agents.llm_manager import get_llm_manager, LLMProvider
        manager = get_llm_manager()

        response = await manager.ainvoke_with_provider(
            prompt=msg.prompt,
            provider=LLMProvider(msg.provider),
            temperature=msg.temperature,
            max_tokens=msg.max_tokens,
        )

        callback_payload = {
            "request_id": msg.request_id,
            "status": "success",
            "response": response,
            "processing_time_ms": (time.perf_counter() - start_time) * 1000,
        }
    except Exception as e:
        callback_payload = {
            "request_id": msg.request_id,
            "status": "error",
            "error": str(e),
        }

    # Send callback
    async with httpx.AsyncClient() as client:
        await client.post(msg.callback_url, json=callback_payload, timeout=30)
```

### 3.3 Integration Points

**Update `app/api/v1.py`:**
```python
from app.api.routes.llm import llm_router
# In create_v1_app():
app.include_router(llm_router)
```

---

## Phase 4: Streamlit Frontend

### 4.1 New Tab: `app/frontend/tabs/llm.py`

**Features:**
- Provider selection dropdown (OpenRouter, HuggingFace, GigaChat, YandexGPT, OpenLlama)
- System prompt + User prompt text areas
- Callback URL configuration with optional auth header
- Temperature and max_tokens sliders
- Request metadata (JSON)
- Request history in session

### 4.2 Router Update

**Update `app/frontend/router.py`:**
```python
TAB_DEFS: List[TabDef] = [
    TabDef(key="analysis", label="Analizis klienta", admin_only=False),
    TabDef(key="data", label="Vneshnie dannye", admin_only=False),
    TabDef(key="llm", label="LLM Access", admin_only=False),  # NEW
    TabDef(key="utilities", label="Utilityi", admin_only=True),
    TabDef(key="docs", label="Dokumentaciya", admin_only=True),
]
```

### 4.3 Main App Update

**Update `app/frontend/app.py`:**
```python
from app.frontend.tabs import llm as tab_llm

# In tab routing:
elif tab == "llm":
    tab_llm.render(api)
```

---

## Implementation Sequence

| Phase | Priority | Estimated Effort | Dependencies |
|-------|----------|------------------|--------------|
| 1. Dependency Vulnerabilities | CRITICAL | 2-4 hours | None |
| 2. Code Refactoring | HIGH | 8-12 hours | Phase 1 |
| 3. Async LLM Endpoint | HIGH | 12-16 hours | Phase 2 |
| 4. Streamlit Frontend | MEDIUM | 6-8 hours | Phase 3 |

---

## Testing Strategy

### Unit Tests
- [ ] `test_llm_schema_validation.py` - Request/response validation
- [ ] `test_llm_queue_message.py` - Queue serialization
- [ ] `test_cached_client_base.py` - Base class behavior

### Integration Tests
- [ ] `test_async_llm_flow.py` - API -> Queue -> Worker -> Callback
- [ ] `test_provider_fallback_async.py` - Provider switching
- [ ] `test_callback_failure_handling.py` - Retry logic

### E2E Tests
- [ ] `test_streamlit_llm_tab.py` - Form submission
- [ ] `test_callback_delivery.py` - Mock endpoint verification

---

## File Summary

### New Files to Create
| File | Purpose |
|------|---------|
| `app/schemas/llm.py` | LLM request/response schemas |
| `app/api/routes/llm.py` | Async LLM API endpoint |
| `app/services/base_cached_client.py` | Base class for cached clients |
| `app/frontend/tabs/llm.py` | Streamlit LLM tab |

### Files to Modify
| File | Changes |
|------|---------|
| `pyproject.toml` | Update vulnerable dependencies |
| `app/api/v1.py` | Include llm_router |
| `app/messaging/broker.py` | Add llm_async_queue handler |
| `app/messaging/publisher.py` | Add publish_async_llm_request |
| `app/messaging/models.py` | Add AsyncLLMQueueMessage |
| `app/services/llm_provider.py` | Remove duplicate, re-export |
| `app/frontend/router.py` | Add LLM tab definition |
| `app/frontend/app.py` | Add LLM tab routing |

---

## Security Checklist

- [ ] All LangChain packages updated to patched versions
- [ ] `secrets_from_env=False` set in serialization calls
- [ ] Callback URL validation (no internal IPs)
- [ ] Rate limiting on `/llm/async` endpoint
- [ ] Input sanitization on prompts
- [ ] Callback payload does not leak secrets
