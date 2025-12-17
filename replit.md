# GigaChat MCP AI-Agent with Tools and Caching

## Overview
A multi-agent system built with GigaChat (Russian LLM), LangGraph, LangChain, FastAPI, and Streamlit. The system supports tool calling for company analysis via Russian data providers (DaData, InfoSphere, Casebook).

## Project Structure
```
app/
├── main.py            # FastAPI app entry point
├── settings.py        # Configuration settings
├── streamlit_app.py   # Streamlit frontend
├── advanced_funcs/    # Logging utilities
├── agents/            # LangGraph workflow agents
│   ├── workflow.py    # Main agent graph
│   ├── planner.py     # Planning agent
│   ├── executor.py    # Tool execution
│   └── analyzer.py    # Analysis agent
├── api/routes/        # FastAPI API routes
├── server/            # MCP server
├── services/          # HTTP client, data fetching
├── storage/           # Tarantool/in-memory cache
└── templates/         # HTML templates
```

## Architecture
- **Frontend**: Streamlit on port 5000 (0.0.0.0)
- **Backend**: FastAPI on port 8000 (localhost)
- **Cache**: In-memory fallback (Tarantool not available in Replit)

## Running the Application
```bash
python run.py
```

This starts both:
1. Streamlit frontend on port 5000
2. FastAPI backend on port 8000

## Environment Variables (Optional)
The app works without external API keys using mock/fallback behavior:
- `PERPLEXITY_API_KEY` - Perplexity AI for web search
- `INFOSPHERE_LOGIN`, `INFOSPHERE_PASSWORD` - InfoSphere API
- `DADATA_API_KEY` - DaData API
- `CASEBOOK_API_KEY` - Casebook API
- `HUGGING_FACE_TOKEN` - HuggingFace model access
- `GIGACHAT_TOKEN` - GigaChat API

## Perplexity Integration
The app includes Perplexity AI integration for web search capabilities:
- MCP tools: `perplexity_search`, `perplexity_analyze`, `tavily_search`, `tavily_advanced_search`, `tavily_status`
- API endpoints: `POST /utility/perplexity/search`, `GET /utility/perplexity/status`
- Client: `app/services/perplexity_client.py`

## Client Analysis Workflow (NEW)
Multi-agent LangGraph workflow for analyzing potential clients/companies:

### Architecture
```
Orchestrator -> Search Agent (parallel) -> Report Analyzer
```

### Agents
1. **Orchestrator** (`app/agents/orchestrator.py`): Validates input and creates 5 search intents
2. **Search Agent** (`app/agents/search.py`): Parallel Perplexity searches with sentiment analysis
3. **Report Analyzer** (`app/agents/report_analyzer.py`): Creates risk assessment (0-100 score)

### API Endpoints
```
POST /agent/analyze-client
{
  "client_name": "Company Name",
  "inn": "1234567890",  // optional
  "additional_notes": "..."  // optional
}
Query params: stream=true для SSE streaming
```

### Response (batch mode)
- `session_id`: Unique analysis ID
- `status`: "completed" | "failed"
- `report`: Risk assessment with findings, recommendations, citations
- `summary`: Markdown summary

### Streaming Mode (stream=true)
SSE events с прогрессом выполнения:
- `start` - начало анализа
- `progress` - текущий этап (orchestrating, searching, analyzing)
- `orchestrator` - результат формирования поисковых запросов
- `search_result` - результат каждого поиска
- `report` - итоговый отчёт с риск-оценкой
- `result` - полный результат анализа
- `complete` - завершение
- `error` - ошибка

### Risk Levels
- **low** (0-24): Standard procedure
- **medium** (25-49): Additional verification
- **high** (50-74): Deep investigation required
- **critical** (75-100): Consider rejection

## Resilience & Monitoring

### HTTP Client (`app/services/http_client.py`)
Enhanced HTTP client with production-ready resilience patterns:
- **Circuit Breaker**: Prevents cascading failures with configurable thresholds
- **Retry Logic**: Exponential backoff using tenacity library
- **Timeouts**: Service-specific timeout configurations
- **Metrics**: Request tracking (success rate, latency, retry counts)

### Service-Specific Configurations
| Service    | Read Timeout | Max Retries | CB Failure Threshold |
|------------|--------------|-------------|---------------------|
| Tavily     | 60s          | 3           | 5                   |
| Perplexity | 90s          | 3           | 5                   |
| DaData     | 30s          | 2           | 3                   |
| Casebook   | 30s          | 2           | 3                   |

### Monitoring Endpoints
- `GET /utility/health` - Health check with component status and issues
- `GET /utility/circuit-breakers` - Circuit breaker states
- `GET /utility/metrics` - Request metrics per service
- `POST /utility/circuit-breakers/{service}/reset` - Reset circuit breaker
- `POST /utility/metrics/reset` - Reset metrics

### Circuit Breaker States
- **CLOSED**: Normal operation, requests pass through
- **OPEN**: Too many failures, requests rejected immediately
- **HALF_OPEN**: Testing recovery with limited requests

### TarantoolClient (`app/storage/tarantool.py`)
Optimized cache client with batch operations and compression:
- **Batch Operations**: `get_many()`, `set_many()`, `delete_many()` for efficient bulk operations
- **Data Compression**: gzip compression for objects > 1KB
- **Search Caching**: `cache_search_result()`, `get_cached_search()` with TTL
- **Metrics Tracking**: hits, misses, hit rate, compression stats, latency
- **Prefix Deletion**: `delete_by_prefix()` for bulk cleanup

### Cache API Endpoints
- `GET /utility/cache/metrics` - Cache statistics and configuration
- `POST /utility/cache/metrics/reset` - Reset cache metrics
- `DELETE /utility/cache/prefix/{prefix}` - Delete keys by prefix

## Recent Changes
- 2025-12-17: External Data Tab Split & TCP Client
  - Split "Внешние данные" into two tabs: "По ИНН" and "Поисковые запросы"
  - INN validation (10 or 12 digits) for DaData/Casebook/InfoSphere
  - Search queries for Perplexity/Tavily (text search)
  - Added TCPMessageClient for async message sending with TCP server
  - TCP endpoints: /utility/tcp/status, /utility/tcp/connect, /utility/tcp/send
  - Added retry logic with increasing timeouts (60s -> 120s -> 240s, max 600s)
  - Up to 3 retry attempts for timeout errors
- 2025-12-17: Streamlit UI Reorganization & Timeout Improvements
  - Merged "Внешние запросы" into "Внешние данные" tab
  - Sources now include: DaData, Casebook, InfoSphere, Perplexity, Tavily
  - "Все источники" queries all 5 sources (INN + search providers)
  - Simplified "Утилиты" tab: aligned service dashboard, Tarantool cache only
  - All Streamlit UI text translated to Russian
  - Increased Perplexity timeout: read=150s (was 90s)
  - Increased Tavily timeout: read=120s (was 60s)
  - Settings loads .env via pydantic-settings (model_config env_file)
- 2025-12-17: LLM Provider & Dashboard Upgrade
  - Replaced HuggingFace LLM with OpenRouter (Claude 3.5 Sonnet default)
  - Created OpenRouterClient (app/services/openrouter_client.py) with httpx
  - OpenRouterLLM class extends LangChain LLM for compatibility
  - New endpoint: GET /utility/openrouter/status
  - Updated /utility/health to include OpenRouter status
  - Refactored Streamlit Utilities page to Service Dashboard
    - Status cards for LLM, Perplexity, Tavily, Cache
    - Search Tools Test section (Perplexity/Tavily tabs)
    - Cache Management buttons
    - System Health display
- 2025-12-16: Fixed ChatPromptTemplate missing variables error
  - Escaped curly braces in JSON examples in planner.py: `{"plan"...}` -> `{{"plan"...}}`
  - Escaped placeholder text in analyzer.py: `{текст}` -> `{{текст}}`
  - Added hasattr check for response.content for better type safety
- 2025-12-16: Multi-Source Parallel Data Collection
  - New data_collector agent: parallel API calls to Casebook, InfoSphere, DaData, Perplexity, Tavily
  - Updated workflow: orchestrator -> data_collector -> analyzer -> file_writer
  - file_writer agent: saves reports to Markdown and JSON files in `reports/` directory
  - Enhanced report_analyzer: integrates data from all 5 sources
- 2025-12-16: LangGraph Workflow Optimization
  - Rate limiting with semaphore (max 3 concurrent API calls)
  - Staggered delays between search requests (0.5s)
  - Structured logging for search operations
  - Per-search duration tracking
- 2025-12-16: Enhanced Error Handling & Structured Logging
  - Request ID tracking middleware (X-Request-ID header)
  - Structured JSON logging (`logger.structured()`)
  - Exception logging with full context (`logger.log_exception()`)
  - Timed operation context manager (`logger.timed()`)
  - Slow request warnings (>1s)
- 2025-12-16: MCP Server Expansion
  - Tavily search tools: `tavily_search`, `tavily_advanced_search`, `tavily_status`
  - Fixed cache key to include all search parameters
- 2025-12-16: Streaming API для анализа клиентов
  - Добавлен SSE streaming endpoint (stream=true query param)
  - События прогресса: start, progress, orchestrator, search_result, report, result, complete
  - Обработка отключения клиента с очисткой ресурсов
- 2025-12-16: TarantoolClient Optimizations
  - Added batch operations (get_many, set_many, delete_many)
  - Implemented gzip compression for large objects
  - Added search result caching with TTL
  - Added cache metrics (hits, misses, compression stats)
  - Added prefix-based deletion
  - Added cache monitoring endpoints
- 2025-12-16: HTTP Client Resilience Improvements
  - Added Circuit Breaker pattern with configurable thresholds
  - Implemented retry logic with tenacity (exponential backoff)
  - Added service-specific timeout configurations
  - Added request metrics tracking
  - Updated Tavily/Perplexity clients to use resilient HTTP client
  - Added monitoring API endpoints (health, circuit-breakers, metrics)
- 2025-12-15: Added Tavily Search Integration
  - Created TavilyClient service
  - Added REST API endpoints: POST /utility/tavily/search, GET /utility/tavily/status
- 2025-12-15: Added Streamlit startup to app/main.py lifespan
- 2025-12-15: Added Client Analysis Multi-Agent Workflow
  - Created Orchestrator, Search, and Report Analyzer agents
  - LangGraph workflow with parallel Perplexity searches
  - Risk assessment with sentiment analysis
  - API endpoint: POST /agent/analyze-client
- 2025-12-15: Added Perplexity AI agent integration
  - Created PerplexityClient service
  - Added MCP tools for search and analysis
  - Added REST API endpoints
- 2025-12-15: Initial Replit setup
  - Made Tarantool optional with in-memory fallback
  - Configured Streamlit to run on port 5000
  - Configured FastAPI backend on port 8000
  - Made all API keys optional with defaults
