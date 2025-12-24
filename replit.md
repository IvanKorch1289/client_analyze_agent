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

## User Preferences

Preferred communication style: Simple, everyday language.

## System Architecture

### Application Stack
| Layer | Technology | Purpose |
|-------|------------|---------|
| Frontend | Streamlit | Web UI on port 5000 |
| Backend | FastAPI | REST API on port 8000 |
| Orchestration | LangGraph (StateGraph) | Agent workflow coordination |
| LLM Integration | LangChain + OpenRouter | Claude 3.5 Sonnet default |
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