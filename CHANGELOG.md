# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added
- Multi-stage Dockerfile for optimized image size (~350MB vs ~800MB)
- AlertManager integration for Prometheus alerts
- Comprehensive CI/CD pipeline with security scanning (bandit, pip-audit, Trivy)
- Docker resource limits and logging configuration
- Container vulnerability scanning with Trivy
- **OpenRouter model availability check with automatic fallback** (2026-01-22)
  - Real-time model availability verification via OpenRouter API
  - Configurable fallback model list (Claude, GPT-4, Gemini, Llama)
  - Model availability caching (5 min TTL) to reduce API overhead
  - Smart model switching on failures with zero downtime
  - Configuration options:
    - `OPENROUTER_CHECK_AVAILABILITY` (default: true)
    - `OPENROUTER_FALLBACK_MODELS` (6 models by default)
    - `OPENROUTER_AVAILABILITY_CACHE_TTL` (default: 300s)
- **Real-time streaming progress UI** (2026-01-22)
  - Server-Sent Events (SSE) based progress indicator
  - Live display of current execution step with emoji indicators
  - Model information for each analysis stage:
    - Orchestrating: Claude 3.5 Sonnet (OpenRouter)
    - Collecting: Perplexity + Tavily (API)
    - Analyzing: Claude 3.5 Sonnet (OpenRouter)
  - Real-time statistics: execution time, data sources, risk score
  - Session ID tracking for debugging

### Changed
- Improved Docker Compose configuration with environment variable secrets
- Enhanced Prometheus configuration with AlertManager target
- **Streamlit UI analysis tab refactored** to use streaming API instead of threading
  - Replaced polling-based progress with SSE streaming
  - Added httpx client for HTTP/2 and streaming support
  - Improved error handling with detailed context
  - Better user feedback with step-by-step progress updates

### Fixed
- **Missing `validate_inn` function import error** in Streamlit frontend (2026-01-22)
  - Added `validate_inn()` wrapper function in `app/frontend/lib/validators.py`
  - Function returns tuple `(is_valid, error_message)` for compatibility
  - Maintains backward compatibility with existing code

## [0.1.0] - 2026-01-22

### Added

#### Core Features
- Multi-agent workflow orchestration with LangGraph
- 7 data sources integration:
  - DaData (EGRUL registry data)
  - Casebook (arbitration court cases)
  - InfoSphere (12+ databases: FSSP, bankruptcy, Central Bank, FNS)
  - Perplexity AI (web search with LLM analysis)
  - Tavily (extended search + web scraping)
- Normalized risk scoring system (0-100 scale)
- PDF and JSON report generation
- Streamlit UI for interactive analysis
- MCP Server for IDE integration

#### Security & Compliance (Sprint 2)
- PII protection with 7 custom Russian recognizers:
  - RU_INN (tax identification numbers)
  - RU_OGRN (registration numbers)
  - RU_SNILS (social security numbers)
  - RU_PERSON (Russian names in Cyrillic)
  - RU_ADDRESS (Russian addresses)
  - RU_PASSPORT (passport numbers)
  - RU_PHONE (Russian phone numbers)
- LLM Audit Trail with hash-only mode for compliance
- 152-FZ compliance (Russian personal data law)
- Presidio NLP engine configured for Russian language

#### Resilience & Performance
- Circuit breakers with per-service configuration
- Retry with exponential backoff (max 3 attempts)
- Configurable timeouts per data source:
  - DaData: 30s
  - InfoSphere/Casebook: 360s (6 minutes)
  - LLM: 60-120s
- Rate limiting with Retry-After header support
- Connection pooling with HTTP/2 support

#### LLM Integration
- Multi-provider fallback chain:
  1. OpenRouter (Claude 3.5 Sonnet)
  2. HuggingFace (Llama 3.1 70B)
  3. GigaChat (Sber)
  4. YandexGPT
- Jay Guard proxy support (optional)
- Lazy provider initialization

#### Caching (Tarantool)
- In-memory cache with TTL and msgpack+gzip compression
- Batch operations (set_many, get_many)
- Search result caching with MD5 hash
- In-memory fallback when Tarantool unavailable
- Lua procedures for fast operations
- Smart cache invalidation on negative feedback

#### Infrastructure
- Docker Compose with health checks for all services
- RabbitMQ message broker for async tasks
- Prometheus metrics instrumentation
- OpenTelemetry tracing
- Structured logging with Rich + JSON

#### Testing (Sprints 13-14)
- E2E workflow tests
- Integration tests (Tarantool, RabbitMQ)
- API tests (20+ test cases)
- Performance tests (timeout validation)
- Load/performance tests
- Security tests

#### Documentation
- API Reference documentation
- User Guide with step-by-step instructions
- Troubleshooting guide
- Deployment Runbook
- AsyncAPI specification for RabbitMQ

### Changed
- Optimized Tavily web scraping with parallel execution
- Increased cache TTL for Perplexity/Tavily from 5 minutes to 1 hour
- Improved code quality with P1/P2 fixes

### Security
- Fixed CVE-2025-68664 (langchain >= 1.2.3)
- Fixed CVE-2025-69223 through CVE-2025-69230 (aiohttp >= 3.13.3)
- Fixed CVE-2026-21441 (urllib3 >= 2.6.3)
- Admin endpoints protected with ADMIN_TOKEN
- Security headers (CSP, HSTS, X-Frame-Options)
- Rate limiting with SlowAPI
- Input validation with Pydantic schemas
- HashiCorp Vault support for secrets (optional)

## Version History

### Sprint Timeline

| Sprint | Focus | Status |
|--------|-------|--------|
| Sprint 0 | MVP Core | Completed |
| Sprint 1 | Data Sources | Completed |
| Sprint 2 | Security (PII, Audit) | Completed |
| Sprint 3 | Performance Optimization | Completed |
| Sprint 4 | Code Quality | Completed |
| Sprint 5 | Advanced Features | Completed |
| Sprint 6-9 | UI, Observability, Enterprise | Completed |
| Sprint 10-11 | Refactoring, Exception Handling | Completed |
| Sprint 13 | API Tests | Completed |
| Sprint 14 | Load/Security Tests | Completed |

---

[Unreleased]: https://github.com/IvanKorch1289/client_analyze_agent/compare/v0.1.0...HEAD
[0.1.0]: https://github.com/IvanKorch1289/client_analyze_agent/releases/tag/v0.1.0
