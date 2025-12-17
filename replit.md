# Система анализа контрагентов

## Overview

This is a multi-agent system for analyzing potential clients and counterparties (контрагентов). The system uses LLM orchestration via LangGraph to coordinate multiple AI agents that gather data from various Russian business intelligence sources, perform web searches, and generate risk assessment reports.

The core workflow:
1. **Orchestrator Agent** receives client data (company name, INN) and plans search strategy
2. **Data Collector Agent** fetches data in parallel from multiple sources (DaData, InfoSphere, Casebook, Perplexity, Tavily)
3. **Report Analyzer Agent** processes collected data and calculates risk scores
4. **File Writer Agent** saves structured reports to disk

## User Preferences

Preferred communication style: Simple, everyday language.

## System Architecture

### Application Structure
- **Backend**: FastAPI application serving REST API on port 8000
- **Frontend**: Streamlit web UI on port 5000
- **Entry Point**: `run.py` starts both services; `app/main.py` contains FastAPI app with Streamlit launcher

### Agent Architecture (LangGraph-based)
The system uses a state machine pattern with TypedDict states flowing through agent nodes:

| Agent | Purpose |
|-------|---------|
| `orchestrator` | Validates input, creates search intents |
| `data_collector` | Parallel data fetching with semaphore-based rate limiting |
| `report_analyzer` | Risk scoring (0-100 scale with low/medium/high/critical levels) |
| `file_writer` | Saves JSON reports to `reports/` directory |
| `planner` | (Generic workflow) LLM-based tool sequence planning |
| `executor` | Executes MCP tools based on plan |
| `analyzer` | Summarizes tool execution results |

### LLM Integration
- **Primary**: OpenRouter API (default model: Claude 3.5 Sonnet)
- **Wrapper**: Custom `OpenRouterLLM` class implements LangChain's `LLM` interface for compatibility
- **Configuration**: Temperature 0.1, max 4096 tokens

### MCP Server
FastMCP-based tool server (`app/mcp_server/`) exposes tools that agents can invoke:
- File system operations
- Company data fetching
- Search integrations

### HTTP Client
Robust async HTTP client (`app/services/http_client.py`) featuring:
- Circuit breaker pattern (failure threshold: 5, timeout: 30s)
- Retry logic with exponential backoff via tenacity
- Configurable timeouts (connect: 5s, read: 30s)

### Caching Strategy
- **Primary**: Tarantool key-value store with TTL
- **Fallback**: In-memory dict when Tarantool unavailable
- **Decorator**: `@cache_response(ttl=seconds)` for automatic caching
- **Features**: Compression for large values, batch operations

### API Routes
- `/agent/*` - Agent workflow endpoints (prompt processing, client analysis)
- `/data/*` - Direct data source access (InfoSphere, DaData, Casebook by INN)
- `/utility/*` - Health checks, cache management, PDF generation

### Authentication
Simple token-based RBAC via `X-Auth-Token` header:
- Admin role: Full access including cache clearing
- Viewer role: Read-only access
- Guest role: Limited access

## External Dependencies

### Data Sources (Russian Business Intelligence)
| Service | Purpose | Config Key |
|---------|---------|------------|
| DaData | Company registration data by INN | `dadata_api_key` |
| InfoSphere | Extended analytics (FSSP, bankruptcy, etc.) | `infosphere_login`, `infosphere_password` |
| Casebook | Arbitration court cases | `casebook_api_key` |

### AI/Search Services
| Service | Purpose | Config Key |
|---------|---------|------------|
| OpenRouter | LLM access (Claude, etc.) | `openrouter_api_key` |
| Perplexity | AI-powered web search | `perplexity_api_key` |
| Tavily | Extended web search | `tavily_token` |

### Infrastructure
| Service | Purpose | Config |
|---------|---------|--------|
| Tarantool | Caching with TTL | `tarantool_host:3302` |

### Configuration
All settings managed via `app/settings.py` using pydantic-settings, loaded from `.env` file.