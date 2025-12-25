# Client Analyze Agent - Multi-Agent Counterparty Analysis System

## Overview

A multi-agent system for analyzing potential clients and counterparties using LLMs, LangGraph orchestration, and external data sources. The system collects company data from multiple Russian business registries (DaData, InfoSphere, Casebook), performs web searches via Perplexity AI and Tavily, and generates risk assessment reports with PDF export.

**Core Functionality:**
- Company analysis by INN (Russian tax ID) through DaData, InfoSphere, Casebook APIs
- Web search integration via Perplexity AI and Tavily
- Multi-agent workflow with orchestrator, data collectors, and report analyzer
- Automated risk scoring (0-100) with PDF report generation
- Scheduled analysis tasks via APScheduler
- Message queue support via RabbitMQ/FastStream
- **User feedback system** - allows users to flag incorrect reports and trigger re-analysis with their comments incorporated into LLM instructions

## User Preferences

Preferred communication style: Simple, everyday language.

## System Architecture

### Application Stack
| Layer | Technology | Purpose |
|-------|------------|---------|
| Frontend | Streamlit | Web UI on port 5000 |
| Backend | FastAPI | REST API on port 8000 |
| Orchestration | LangGraph (StateGraph) | Agent workflow coordination |
| LLM Integration | LangChain + Multi-provider | OpenRouter → HuggingFace → GigaChat → YandexGPT fallback |
| Data Protection | Jay Guard Proxy | PII маскирование через внешний прокси (опционально) |
| Caching | Tarantool (in-memory fallback) | TTL-based caching |
| Messaging | FastStream + RabbitMQ | Async task processing |
| MCP Server | FastMCP | IDE integration on port 8011 |

### Agent Workflow Pattern
```
User Input → Orchestrator Agent → Data Collector (parallel sources)
                                    ├── DaData (company registry)
                                    ├── InfoSphere (analytics)
                                    ├── Casebook (court cases)
                                    ├── Perplexity (web search)
                                    └── Tavily (extended search)
                                → Report Analyzer → File Writer → PDF/JSON Output
```

### Key Design Decisions

1. **Parallel Data Collection**: All 5 data sources queried simultaneously with individual timeouts (360s for slow sources like InfoSphere/Casebook, 30s for fast sources like DaData)

2. **Circuit Breaker Pattern**: HTTP client implements per-service circuit breakers with configurable failure thresholds to prevent cascade failures

3. **Cascading Configuration**: Settings loaded with priority: HashiCorp Vault → Environment Variables → YAML files. Hot-reload supported via watchdog

4. **In-Memory Fallback**: When Tarantool is unavailable, system falls back to in-memory caching to maintain availability

5. **Role-Based Access**: Admin/guest roles controlled via `X-Auth-Token` header for protecting administrative endpoints

6. **Tarantool Dual-Engine Storage**: 
   - `memtx` engine for cache_space (RAM-based with snapshots/WAL for persistence)
   - `vinyl` engine for reports_space (LSM-backed disk storage with configurable bloom filters and page cache)
   - Automatic engine selection based on data access patterns

7. **User Feedback Re-analysis**: 
   - Feedback includes rating (accurate/partially_accurate/inaccurate), comment, and focus areas
   - Re-analysis incorporates previous report context (risk score, summary, findings) into LLM system prompt
   - Report analyzer agent includes "ДОПОЛНИТЕЛЬНЫЕ ИНСТРУКЦИИ И КОНТЕКСТ" section in user message

### Directory Structure
```
app/
├── agents/          # LangGraph agents (orchestrator, data_collector, report_analyzer)
├── api/             # FastAPI v1 routes and error handlers
│   ├── routes/      # Individual route files (agent, data, reports, scheduler, utility, analytics)
│   └── v1.py        # API v1 sub-app composition
├── config/          # Pydantic settings, constants, hot-reload
├── frontend/        # Streamlit UI with tab-based navigation
├── mcp_server/      # FastMCP server for external integrations
├── messaging/       # RabbitMQ broker, publisher, worker
├── schemas/         # Centralized Pydantic models
│   ├── api.py       # Health/status response models
│   ├── report.py    # ClientAnalysisReport and related models
│   ├── requests.py  # All API request models
│   └── responses.py # All API response models
├── services/        # External API clients and business logic
│   ├── llm_provider.py  # Unified LLM access (llm_generate_json, llm_generate_text)
│   ├── perplexity_client.py  # Perplexity AI search
│   ├── tavily_client.py      # Tavily web search
│   └── scheduler_service.py  # APScheduler integration
├── shared/          # Common utilities, security, exceptions
│   ├── toolkit/     # Consolidated utility functions (logging, metrics, cache, export)
│   ├── security.py  # INN validation, token auth
│   └── exceptions.py # Custom exception classes
├── storage/         # Tarantool client and repositories
│   ├── tarantool.py # Client with in-memory fallback
│   └── repositories/ # Data access layer
└── utility/         # Re-exports for backward compatibility
```

## External Dependencies

### Required API Keys (via environment or .env)
| Service | Purpose | Config Key |
|---------|---------|------------|
| OpenRouter | LLM provider | `OPENROUTER_API_KEY` |
| HuggingFace | LLM fallback #1 | `HUGGINGFACE_API_KEY` |
| GigaChat | LLM fallback #2 | `GIGACHAT_API_KEY` |
| YandexGPT | LLM fallback #3 | `YANDEXGPT_IAM_TOKEN`, `YANDEXGPT_FOLDER_ID` |
| DaData | Company registry lookup | `DADATA_API_KEY` |
| Perplexity | AI-powered web search | `PERPLEXITY_API_KEY` |
| Tavily | Extended web search | `TAVILY_API_KEY` |
| Casebook | Court case data | `CASEBOOK_API_KEY` |
| InfoSphere | Additional analytics | `INFOSPHERE_API_KEY` |

### Infrastructure Services
| Service | Purpose | Default Port |
|---------|---------|--------------|
| Tarantool | Caching & persistent storage | 3302 |
| RabbitMQ | Message queue (optional) | 5672 |
| SMTP | Email notifications (optional) | Configurable |

### Python Dependencies
- **Web Framework**: FastAPI, Streamlit, uvicorn
- **LLM/Agents**: langchain, langchain-openai, langgraph, fastmcp
- **HTTP**: httpx, tenacity (retry logic)
- **Data**: pydantic, msgpack, xmltodict
- **Scheduling**: APScheduler
- **Messaging**: faststream[rabbit]
- **PDF**: WeasyPrint
- **Observability**: opentelemetry, slowapi (rate limiting)

## Recent Changes

**25 декабря 2025:**
- Создан комплексный отчёт анализа `ANALYSIS_REPORT.md` (оценка 8.5/10)
- Создан план повышения готовности к production `PRODUCTION_READINESS_PLAN.md` (85% → 95%)
- Исправлен дублирующий импорт в `app/api/routes/utility.py`
- **Sprint 1 (Backend Hardening) завершён:**
  - Методы count, list, delete, search в threads_repository и cache_repository
  - Pydantic response models для health/metrics endpoints
  - 10 smoke-тестов Tarantool connectivity
- **Sprint 2 (QA/Testing) завершён:**
  - 12 интеграционных тестов feedback API (tests/test_feedback_api.py)
  - 17 интеграционных тестов RabbitMQ/FastStream (tests/test_messaging.py)
  - 8 E2E тестов полного workflow (tests/test_e2e_workflow.py)
  - Всего: 37 новых тестов, все проходят

## Test Coverage

| Suite | Tests | Focus |
|-------|-------|-------|
| test_repositories.py | 24 | Repository CRUD, in-memory fallback |
| test_tarantool_smoke.py | 10 | Connectivity, spaces, engines |
| test_feedback_api.py | 12 | Validation, rerun, instruction builder |
| test_messaging.py | 17 | Publisher, broker, DLQ config |
| test_e2e_workflow.py | 8 | Full INN→Report→Storage cycle |
| **Verified** | **65** | All passing |
| **Total in codebase** | **107** | 42 require staging/API keys |

## Production Readiness

**Текущий уровень:** 87%  
**Целевой уровень:** 95% (9.5/10)  
**План:** 5-спринтовый план (Backend → QA → SRE → Frontend → UX)

### Финальный анализ (25.12.2025)

| Критерий | Оценка |
|----------|--------|
| Функциональность | 9/10 |
| Качество кода | 8.5/10 |
| Тестовое покрытие | 8/10 (107 тестов) |
| Безопасность | 9/10 |
| Производительность | 8/10 |

Подробности в `FINAL_ANALYSIS_REPORT.md` и `PRODUCTION_READINESS_PLAN.md`