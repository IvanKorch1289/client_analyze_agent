# CLAUDE.md — Руководство для AI-ассистента по проекту

## Описание проекта

**Система анализа контрагентов** (counterparty-analyzer) — мультиагентная платформа для автоматизированной проверки и оценки рисков контрагентов/клиентов с использованием LLM и внешних источников данных. Проект ориентирован на российский рынок (152-ФЗ compliance, российские источники данных, кириллический NLP).

## Технологический стек

- **Язык:** Python 3.12
- **Backend:** FastAPI + Uvicorn/Gunicorn
- **Frontend:** Streamlit (single-page)
- **Оркестрация агентов:** LangGraph (StateGraph)
- **LLM:** OpenRouter (Claude 3.5 Sonnet) с fallback на HuggingFace, GigaChat, YandexGPT
- **Кэширование:** Tarantool (с in-memory fallback)
- **Очередь сообщений:** RabbitMQ (FastStream)
- **Векторная БД:** ChromaDB (RAG)
- **Мониторинг:** Prometheus + Grafana + Alertmanager
- **PII-защита:** Microsoft Presidio (7 кастомных распознавателей для РФ)
- **Контейнеризация:** Docker Compose (10 сервисов)
- **CI/CD:** GitHub Actions (lint, test, security, build, container scan)

## Архитектура проекта

```
app/
├── main.py                     # FastAPI-приложение, middleware, lifespan
├── run.py                      # Точка входа (backend + Streamlit)
├── config/                     # Конфигурация (YAML + env + hot-reload)
│   ├── settings.py             # Facade над singleton-группами настроек
│   ├── base.py                 # AppBaseSettings, SchedulerSettings
│   ├── database.py             # Tarantool, Mongo, PostgreSQL
│   ├── external_api.py         # Все внешние API (DaData, Casebook, LLM...)
│   ├── security.py             # Security settings (CORS, HSTS, CSP, IP-filter)
│   ├── services.py             # Queue, Mail, Chroma, MCP, Frontend
│   ├── constants.py            # Rate limits, pagination limits
│   ├── config_loader.py        # YAML loader
│   ├── watchdog.py             # Hot-reload конфигов
│   └── reload.py               # Reload logic
├── agents/                     # LangGraph агенты
│   ├── orchestrator.py         # Оркестратор: валидация, DaData, LLM-генерация search intents
│   ├── client_workflow.py      # StateGraph workflow (orchestrator->collector->analyzer->writer)
│   ├── data_collector/         # Параллельный сбор данных из всех источников
│   ├── report_analyzer.py      # LLM-анализ с Chain-of-Thought, fallback на ручной расчёт
│   ├── risk_calculator.py      # Нормализованный расчёт риск-скора (0-100)
│   ├── file_writer.py          # Генерация PDF/JSON отчётов
│   ├── llm_manager.py          # LLMManager: fallback chain, PII masking, audit, cache
│   ├── llm_init.py             # Lazy init LLM
│   ├── rag_context.py          # RAG: обогащение контекста из ChromaDB
│   ├── web_scraper.py          # Web scraping для Tavily full texts
│   └── collectors/             # Registry паттерн для коллекторов данных
├── api/                        # REST API
│   ├── v1.py                   # Versioned API (/api/v1)
│   ├── routes/                 # Роуты: agent, data, reports, export, analytics, scheduler...
│   ├── error_handlers.py       # Централизованная обработка ошибок
│   ├── rate_limit.py           # Rate limiting per-route
│   └── response.py             # Стандартизированные ответы
├── services/                   # Клиенты внешних сервисов
│   ├── http_client.py          # AsyncHttpClient с circuit breaker, retry, metrics
│   ├── openrouter_client.py    # OpenRouter API
│   ├── perplexity_client.py    # Perplexity AI
│   ├── tavily_client.py        # Tavily Search
│   ├── llm_provider.py         # llm_generate_json/text wrapper
│   ├── chroma_service.py       # ChromaDB service
│   ├── email_client.py         # SMTP
│   ├── scheduler_service.py    # APScheduler
│   ├── analysis_executor.py    # Executor для анализа
│   └── shutdown_manager.py     # Graceful shutdown
├── storage/                    # Хранилище данных
│   ├── tarantool.py            # TarantoolClient: singleton, compression, LRU eviction
│   ├── repositories/           # Repository pattern (cache, reports, threads)
│   ├── connection.py           # Connection management
│   ├── compression.py          # gzip compression handler
│   └── init.lua                # Tarantool schema (spaces, indexes)
├── schemas/                    # Pydantic-схемы
│   ├── report.py               # ClientAnalysisReport
│   ├── requests.py             # Request models
│   ├── responses.py            # Response models
│   └── api.py                  # API schemas
├── shared/                     # Shared utilities
│   ├── pii_protection.py       # Presidio PII masking (7 RU recognizers)
│   ├── llm_audit.py            # LLM audit logging (152-ФЗ compliance)
│   ├── llm_cache.py            # LLM response caching
│   ├── security.py             # INN validation, sanitization
│   ├── prometheus_metrics.py   # Custom application metrics
│   ├── memory_monitor.py       # Memory leak protection
│   ├── exceptions.py           # Custom exceptions
│   └── toolkit/                # Reusable toolkit
│       ├── logging.py          # Structured logging (loguru)
│       ├── circuit_breaker.py  # Circuit breaker implementation
│       ├── auth.py             # Admin token auth
│       ├── decorators.py       # Caching, retry decorators
│       ├── telemetry.py        # OpenTelemetry init
│       ├── metrics.py          # App-level metrics
│       ├── helpers.py          # Utility functions
│       ├── formatters.py       # Text formatting
│       ├── parsers.py          # Data parsers
│       ├── pagination.py       # Pagination utilities
│       ├── export.py           # Export utilities
│       └── pdf.py              # PDF generation
├── messaging/                  # RabbitMQ messaging
│   ├── broker.py               # FastStream broker
│   ├── publisher.py            # Message publisher
│   ├── worker.py               # Background worker
│   └── models.py               # Message models
├── mcp_server/                 # MCP Server для IDE-интеграции
│   ├── main.py                 # FastMCP server
│   ├── tools/                  # MCP tools (analysis, validation, api, file)
│   ├── resources/              # MCP resources (api specs, best practices, reference data)
│   └── prompts/                # System prompts и adaptive prompt engine
├── prompts/                    # Adaptive prompt engine
│   └── adaptive_prompt_engine.py
└── frontend/                   # Streamlit UI
    ├── app.py                  # Main Streamlit app
    ├── router.py               # Page routing
    ├── api_client.py           # HTTP client for API
    ├── tabs/                   # UI tabs (analysis, data, monitor, rag, comparison...)
    ├── lib/                    # UI components (validators, charts, formatters)
    └── assets/                 # CSS, logos
```

## Workflow анализа клиента

```
Orchestrator (LLM + DaData) ──┐   ┌── InfoSphere (параллельно)
                               ├───┤
                               │   └── Casebook (параллельно)
                               ↓
                    Data Collector (Perplexity + Tavily + web scraping)
                               ↓
                    Report Analyzer (LLM + CoT + RAG + PII masking)
                               ↓
                    File Writer (PDF + JSON)
```

## Ключевые команды

```bash
# Установка
poetry install --with dev

# Запуск (dev)
python run.py

# Docker
docker-compose up -d

# Линтинг
make lint                # ruff + pyright + vulture + bandit + pip-audit
make format              # black + ruff format

# Тесты
pytest tests/ -q
pytest tests/ -q --cov=app

# Безопасность
make audit               # security-check + deps-check + secrets-check
make complexity           # Анализ сложности кода
```

## Правила разработки

### Архитектурные принципы
1. **Singleton pattern** — для TarantoolClient, LLMManager, AsyncHttpClient (через `get_instance()`)
2. **Hot-reload** — конфигурация через Settings facade с @property, watchdog для YAML/.env
3. **Graceful degradation** — fallback на in-memory при недоступности Tarantool, fallback LLM chain
4. **Circuit Breaker** — для всех внешних сервисов (per-service + app-level)
5. **PII Protection** — обязательное маскирование PII перед отправкой в LLM (152-ФЗ)

### Стиль кода
- **Formatter:** Black (line-length 88) + Ruff
- **Type checker:** Pyright (basic mode)
- **Linter:** Ruff (pyflakes, pycodestyle, isort, flake8-bugbear, flake8-comprehensions)
- **Security:** Bandit + pip-audit
- **Imports:** isort-совместимый порядок (stdlib → third-party → local)
- **Docstrings:** На русском или английском, обязательны для публичных функций
- **Logging:** Через `app.shared.toolkit.logging.logger` (structured logging)
- **Ignore:** E501 (длина строки не ограничена жёстко)

### Конфигурация
- Секреты **только** через `.env` или HashiCorp Vault (никогда в YAML)
- URL, порты, таймауты — в `config/app.dev.yaml` / `config/app.prod.yaml`
- Доступ к настройкам: `from app.config.settings import settings` → `settings.openrouter.model`

### Тестирование
- Тесты в `tests/` (pytest + pytest-asyncio)
- Conftest: `tests/conftest.py` (TarantoolClient mock, fixtures)
- Нагрузочные тесты: Locust (`tests/locustfile.py`)
- Benchmark: pytest-benchmark
- Тестовые файлы: `test_*.py`

### API
- Версионированный API: `/api/v1/...` (основной)
- Legacy endpoints: `/agent/...`, `/data/...` (deprecated, sunset 2026-12-31)
- Стандартизированный формат ответа: `{"status": "success/error", "data": {...}, "error": {...}}`
- Rate limiting: SlowAPI per IP
- Auth: `X-Auth-Token` header для admin endpoints

### Docker
- Multi-stage build (builder → runtime, ~350MB)
- Non-root user `appuser`
- Healthchecks для всех сервисов
- Resource limits для каждого контейнера
- 10 сервисов: app, worker, mcp, chroma, tarantool, rabbitmq, jayguard, prometheus, alertmanager, grafana

## Известные ограничения и зоны для улучшения

### Критичные
1. **Нет PostgreSQL** — данные хранятся только в Tarantool (KV) и in-memory; нет реляционной БД для аналитики
2. **Нет миграций** — schema Tarantool задаётся в Lua (`init.lua`), нет версионирования схемы
3. **Тесты без реальных интеграций** — все внешние сервисы замоканы; нет staging-окружения
4. **Smoke tests заглушены** — CI/CD pipeline содержит placeholder для smoke tests

### Важные
5. **README устарел** — структура проекта в README не соответствует фактической (`app/settings.py` → `app/config/settings.py`, `app/utility/` → `app/shared/toolkit/`)
6. **Нет database migrations** — при изменении схемы Tarantool нужно ручное вмешательство
7. **Отсутствует PostgreSQL** (заявлен в README, но не используется) — нет реляционного хранения
8. **`asyncio.get_event_loop()`** используется вместо `asyncio.get_running_loop()` — deprecation warning на Python 3.12+
9. **Единая точка отказа** — если Tarantool и in-memory одновременно заполнены, данные теряются

### Средние
10. **Дублирование fallback логики** — risk_calculator.py и report_analyzer._calculate_risk_fallback() пересекаются
11. **Hardcoded thinking messages** — в `client_workflow.py` thinking_messages захардкожены
12. **Search cache в двух местах** — `_search_cache` dict в TarantoolClient + основной кэш
13. **gRPC заявлен, но не реализован** — настройки есть, кода нет
14. **Redis заявлен, но не используется** — настройки есть, подключения нет
