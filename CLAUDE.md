# Client Analyze Agent - Project Context

## Project Overview

**Project Name:** Client Analyze Agent (Counterparty Analyzer)
**Version:** 0.1.0
**Language:** Python 3.12+
**Status:** Production-ready (95% completion)

A multi-agent system for analyzing business counterparties and clients using LLM orchestration, external data sources, and risk assessment algorithms. Built with FastAPI backend, Streamlit frontend, and LangGraph-based agent workflows.

### Core Capabilities
- Automated counterparty risk analysis
- Multi-source data aggregation (DaData, Perplexity, Tavily, Casebook)
- PDF report generation with risk scoring
- Streaming analysis with real-time progress
- Circuit breaker resilience patterns
- Role-based access control
- **Async LLM API with webhook callback** (NEW)

## Architecture

### Service Components
```
Docker Compose Services:
├── app          FastAPI backend + Streamlit frontend (ports 8000/5000)
├── worker       Background message consumer (RabbitMQ)
├── mcp          Model Context Protocol server (port 8011)
├── tarantool    In-memory cache database (port 3302)
└── rabbitmq     Message broker (ports 5672/15672)
```

### Agent Workflow (LangGraph)
```
Orchestrator → Data Collector → Report Analyzer → File Writer
    ↓              ↓                ↓               ↓
Validates     Gathers data    Calculates      Generates
input, INN    from external   risk scores     PDF reports
lookup        sources
```

### LLM Provider Chain (with fallbacks)
1. OpenRouter (Claude 3.5 Sonnet) - primary
2. HuggingFace (Meta Llama 3.1) - fallback 1
3. GigaChat (Sber) - fallback 2
4. YandexGPT - fallback 3

## Build/Run Commands

### Quick Start
```bash
# Install dependencies
poetry install

# Run both services (FastAPI + Streamlit)
python run.py

# Or run services separately
uvicorn app.main:app --host 0.0.0.0 --port 8000  # Backend
streamlit run app/frontend/app.py --server.port 5000  # Frontend
```

### Docker
```bash
docker-compose up -d          # Start all services
docker-compose logs -f app    # View logs
docker-compose down           # Stop services
```

### Development Commands (Makefile)
```bash
make format          # Format code (ruff + black)
make lint            # Run linters (ruff, pyright, pylint, vulture)
make test            # Run pytest
make audit           # Security audit (bandit)
make security-check  # Full security scan (pip-audit, detect-secrets)
make clean           # Clean build artifacts
```

### Testing
```bash
pytest                              # Run all tests
pytest -m "not integration"        # Skip integration tests
pytest tests/test_e2e_workflow.py  # Run specific test file
SKIP_INTEGRATION=true pytest       # CI mode
```

## Code Style Guidelines

### Formatting & Linting
- **Formatter:** Ruff + Black
- **Line length:** 88 characters
- **Type checking:** Pyright (strict mode recommended)
- **Import sorting:** Automatic via Ruff

### Conventions
- Use async/await for I/O operations
- Pydantic models for all request/response schemas
- Circuit breaker pattern for external service calls
- Structured logging with request ID tracking
- Type hints required for all function signatures

### Security Requirements
- No hardcoded credentials (use .env or Vault)
- Input sanitization via `app/shared/security.py`
- Rate limiting on all public endpoints
- Token authentication for admin operations

## File Structure Map

```
/home/user/client_analyze_agent/
├── app/
│   ├── main.py                    # FastAPI application entry
│   ├── agents/                    # LangGraph agent system
│   │   ├── orchestrator.py        # Main coordinator
│   │   ├── client_workflow.py     # Analysis workflow
│   │   ├── data_collector.py      # Data gathering
│   │   ├── report_analyzer.py     # Risk analysis
│   │   ├── risk_calculator.py     # Score computation
│   │   ├── file_writer.py         # PDF generation
│   │   ├── llm_init.py            # LLM setup
│   │   └── llm_manager.py         # Provider fallback chain
│   │
│   ├── api/                       # REST API layer
│   │   ├── v1.py                  # API v1 router
│   │   ├── routes/                # Endpoint handlers
│   │   │   ├── agent.py           # /agent/* endpoints
│   │   │   ├── data.py            # /data/* endpoints
│   │   │   ├── llm.py             # /llm/* endpoints (async LLM)
│   │   │   ├── reports.py         # /reports/* endpoints
│   │   │   ├── scheduler.py       # /scheduler/* endpoints
│   │   │   └── utility.py         # /health, /metrics
│   │   ├── error_handlers.py      # Global error handling
│   │   └── rate_limit.py          # Rate limiting
│   │
│   ├── frontend/                  # Streamlit web UI
│   │   ├── app.py                 # Main Streamlit app
│   │   ├── tabs/                  # Dashboard tabs
│   │   └── lib/                   # UI utilities
│   │
│   ├── services/                  # External integrations
│   │   ├── llm_provider.py        # LLM abstraction
│   │   ├── perplexity_client.py   # Perplexity AI
│   │   ├── tavily_client.py       # Tavily search
│   │   ├── http_client.py         # HTTP with circuit breaker
│   │   └── fetch_data.py          # Data orchestration
│   │
│   ├── storage/                   # Data persistence
│   │   ├── tarantool.py           # Cache client
│   │   └── repositories/          # Data access objects
│   │
│   ├── messaging/                 # RabbitMQ integration
│   │   ├── broker.py              # Message broker
│   │   └── worker.py              # Background processor
│   │
│   ├── config/                    # Configuration
│   │   ├── settings.py            # Settings facade
│   │   ├── config_loader.py       # YAML loader
│   │   └── *.py                   # Domain-specific settings
│   │
│   ├── schemas/                   # Pydantic models
│   ├── shared/                    # Shared utilities
│   ├── utility/                   # App utilities
│   └── mcp_server/                # MCP protocol server
│
├── tests/                         # Test suite (14 files)
├── config/                        # Configuration files
│   └── app.dev.yaml               # Development config
├── docs/                          # Documentation
│   ├── API_REFERENCE.md
│   ├── DEPLOYMENT_RUNBOOK.md
│   ├── TROUBLESHOOTING.md
│   └── USER_GUIDE.md
│
├── run.py                         # Main entry point
├── pyproject.toml                 # Poetry configuration
├── Dockerfile                     # Container image
├── docker-compose.yml             # Multi-service orchestration
├── Makefile                       # Development tasks
└── pytest.ini                     # Test configuration
```

## Key Dependencies

| Category | Package | Purpose |
|----------|---------|---------|
| Web | FastAPI 0.125, Streamlit 1.45 | Backend API, Frontend UI |
| Agents | LangChain 1.2.3, LangGraph 1.0.6 | LLM orchestration |
| Database | Tarantool 2.11 | In-memory caching |
| Queue | RabbitMQ 3.13, FastStream 0.6.5 | Async messaging |
| HTTP | HTTPX 0.28.1, Tenacity 9.1.2 | Resilient HTTP calls |
| PDF | FPDF2 2.8.5 | Report generation |
| Observability | OpenTelemetry 1.39.1 | Distributed tracing |

## Environment Variables

### Required
```bash
DADATA_API_KEY          # Company lookup by INN
OPENROUTER_API_KEY      # LLM provider
PERPLEXITY_API_KEY      # Web search
TAVILY_API_KEY          # Advanced search
ADMIN_TOKEN             # Admin authentication
SECRET_KEY              # App secret (min 32 chars)
```

### Optional
```bash
CASEBOOK_API_KEY        # Court cases database
INFOSPHERE_LOGIN/PASS   # Counterparty verification
TARANTOOL_HOST/PORT     # Cache (default: localhost:3302)
RABBITMQ_ENABLED        # Enable queue (default: false)
VAULT_ADDR/TOKEN        # HashiCorp Vault
```

## API Endpoints Summary

| Method | Endpoint | Purpose |
|--------|----------|---------|
| POST | `/api/v1/agent/analyze-client` | Start client analysis |
| GET | `/api/v1/agent/status/{task_id}` | Check analysis status |
| POST | `/api/v1/agent/feedback` | Submit analysis feedback |
| GET | `/api/v1/data/dadata/{inn}` | Lookup company by INN |
| GET | `/api/v1/reports` | List generated reports |
| GET | `/api/v1/reports/{id}/download` | Download PDF report |
| POST | `/api/v1/llm/async` | **Async LLM request with webhook** |
| GET | `/api/v1/llm/providers` | **List available LLM providers** |
| GET | `/health` | Health check |
| GET | `/metrics` | Prometheus metrics |
| GET | `/circuit-breakers` | Circuit breaker status |

## Testing Guidelines

- Unit tests: `tests/test_*.py`
- Integration tests: marked with `@pytest.mark.integration`
- P0 priority tests: `test_p0_*.py` (critical path testing)
- Use `SKIP_INTEGRATION=true` for CI runs
- Fixtures defined in `tests/conftest.py`

## Known Issues & TODOs

1. CORS configuration needs production/dev separation
2. MCP server lacks comprehensive documentation
3. Frontend has no automated tests
4. Some TODO comments remain in repository code

## Contact & Resources

- **README:** Russian documentation in `README.md`
- **API Docs:** `docs/API_REFERENCE.md`
- **Deployment:** `docs/DEPLOYMENT_RUNBOOK.md`
- **Troubleshooting:** `docs/TROUBLESHOOTING.md`
