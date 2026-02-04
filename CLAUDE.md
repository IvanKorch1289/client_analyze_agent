# CLAUDE.md — Руководство для AI-ассистента по проекту

## Описание проекта

**Система анализа контрагентов** (counterparty-analyzer) — платформа для автоматизированной проверки и оценки рисков клиентов/контрагентов. Проект ориентирован на российский рынок (152-ФЗ compliance, российские источники данных, кириллический NLP).

### Ключевой функционал (6 модулей)

1. **Агент анализа клиента** — мультиагентный workflow на LangGraph (Orchestrator → DataCollector → ReportAnalyzer → FileWriter), собирающий данные из внешних источников (DaData, Casebook, InfoSphere, Perplexity, Tavily), выполняющий LLM-анализ с Chain-of-Thought, рассчитывающий нормализованный риск-скор (0-100) и генерирующий отчёт (PDF/JSON).

2. **REST API для запуска агента** — FastAPI-эндпоинты (`/api/v1/agent/analyze-client`, `/api/v1/reports`, `/api/v1/data/*`, `/api/v1/analytics/*`) для запуска анализа, получения отчётов, доступа к внешним данным и аналитике. Поддержка SSE-стриминга прогресса, планирование отложенных задач через Scheduler.

3. **API для запросов к LLM** — асинхронный LLM API (`/api/v1/llm/async`) с webhook callback. Поддержка 4 провайдеров (OpenRouter/Claude, HuggingFace/Llama, GigaChat, YandexGPT) с автоматическим fallback. Эндпоинт `/api/v1/llm/mask-text` для тестирования PII-маскирования. Эндпоинт `/api/v1/llm/providers` для проверки статуса провайдеров.

4. **RabbitMQ интеграция** — три очереди через FastStream: `analysis` (запуск анализа клиента), `cache` (инвалидация кэша), `llm` (асинхронные LLM запросы). Dead Letter Queue (DLQ) с DLX для failed-сообщений. Correlation ID для отслеживания запросов. REST API работает как альтернативный вход — при включённом RabbitMQ запросы маршрутизируются через очередь, при отключённом — обрабатываются напрямую через background tasks.

5. **Система RAG** — обогащение контекста LLM-анализа через ChromaDB. Семантический поиск похожих прошлых отчётов (embedding similarity), поиск по загруженным документам. RAG-контекст автоматически добавляется в промпт анализатора. Graceful degradation: при недоступности ChromaDB анализ продолжается без RAG.

6. **Браузерный интерфейс** — Streamlit single-page приложение с вкладками: анализ клиента, сравнение отчётов, внешние данные, LLM-запросы, мониторинг, RAG-управление, утилиты, документация. Админ-режим через `X-Auth-Token`. Все запросы идут через HTTP-клиент к FastAPI backend.

## КРИТИЧЕСКИ ВАЖНО: Безопасность PII данных

### Принцип: никакие персональные данные клиента не должны попадать во внешние LLM

Система обеспечивает **обязательное маскирование PII** перед каждым обращением к внешней LLM. Это требование 152-ФЗ «О персональных данных».

### Как работает PII-защита

```
Пользователь вводит текст с PII
        ↓
mask_pii() — Presidio + 7 кастомных RU-распознавателей
        ↓
"ИНН 7707083893, директор Иванов Иван" → "ИНН [INN_1], директор [CLIENT_NAME_1]"
        ↓
Замаскированный текст отправляется в LLM
        ↓
LLM отвечает с псевдонимами: "[CLIENT_NAME_1] имеет риски..."
        ↓
unmask_pii() — обратная замена по маппингу
        ↓
"Иванов Иван имеет риски..." — пользователь получает читаемый ответ
```

### 7 кастомных распознавателей для РФ (`app/shared/pii_protection.py`)

| Тип | Entity | Пример | Score |
|-----|--------|--------|-------|
| ИНН | `RU_INN` | 7707083893 → `[INN_1]` | 0.85 |
| ОГРН | `RU_OGRN` | 1027739019901 → `[OGRN_1]` | 0.80 |
| СНИЛС | `RU_SNILS` | 123-456-789 01 → `[SNILS_1]` | 0.90 |
| ФИО | `RU_PERSON` | Иванов Иван Иванович → `[CLIENT_NAME_1]` | 0.35-0.85 |
| Адрес | `RU_ADDRESS` | г. Москва, ул. Ленина, д. 1 → `[ADDRESS_1]` | 0.70-0.75 |
| Паспорт | `RU_PASSPORT` | 4510 123456 → `[PASSPORT_1]` | 0.50-0.90 |
| Телефон | `RU_PHONE` | +7(499)123-45-67 → `[PHONE_1]` | 0.85 |

### 3 уровня маскирования

- **low** — только финансовые идентификаторы (ИНН, ОГРН, карты, IBAN)
- **medium** — финансовые + контакты (телефон, email)
- **high** (по умолчанию) — все PII включая ФИО, адреса, паспорта

### Правила безопасности PII при разработке

1. **Маскирование включено ВСЕГДА** — не зависит от `llm_audit_enabled`, управляется `pii_masking_enabled` (default: `true`)
2. **При ошибке маскирования — БЛОКИРОВКА** — если `mask_pii()` упал, LLM-вызов блокируется полностью (`PIIMaskingError`), данные НЕ отправляются
3. **Нет исключений для DEBUG** — PII защита работает одинаково в dev и prod
4. **Reversible Pseudonymization** — нумерованные псевдонимы (`[CLIENT_NAME_1]`, `[INN_2]`) позволяют точно восстановить оригинал в ответе LLM
5. **Двойной уровень** — PII маскируется как в `LLMManager.ainvoke()` (основной путь), так и в `_process_llm_request_background()` (LLM API путь)
6. **Аудит** — все LLM-вызовы логируются с флагами `pii_detected`, `pii_types` для compliance

### Где применяется маскирование

| Точка входа | Файл | Механизм |
|-------------|-------|----------|
| Агент анализа (workflow) | `app/agents/llm_manager.py:_mask_prompt_pii()` | Автоматически в `ainvoke()` |
| LLM API (async) | `app/api/routes/llm.py:_process_llm_request_background()` | Перед `ainvoke_with_provider()` |
| LLM API (queue) | `app/messaging/broker.py:handle_async_llm_request()` | Через `LLMManager` |
| Тестирование маскирования | `app/api/routes/llm.py:mask_text()` | Прямой вызов `mask_pii()` |

### При добавлении новых LLM-вызовов

**ОБЯЗАТЕЛЬНО** используйте один из двух путей:
- `LLMManager.ainvoke()` — автоматическое маскирование + fallback + cache + audit
- Явный вызов `mask_pii()` → вызов LLM → `unmask_pii()` — если нужен прямой контроль

**ЗАПРЕЩЕНО** вызывать LLM-провайдеры напрямую без маскирования PII.

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
- **PII-защита:** Microsoft Presidio (7 кастомных распознавателей для РФ) + spaCy (ru_core_news_lg/sm)
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
│   ├── routes/                 # Роуты: agent, data, reports, export, analytics, scheduler, llm...
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
│   ├── embedding_service.py    # Embedding service для RAG
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
│   ├── llm.py                  # LLM API schemas (AsyncLLMRequest, MaskTextRequest...)
│   └── api.py                  # API schemas
├── shared/                     # Shared utilities
│   ├── pii_protection.py       # Presidio PII masking (7 RU recognizers) — КРИТИЧЕСКИ ВАЖНЫЙ МОДУЛЬ
│   ├── llm_audit.py            # LLM audit logging (152-ФЗ compliance)
│   ├── llm_cache.py            # LLM response caching
│   ├── security.py             # INN validation, sanitization
│   ├── prometheus_metrics.py   # Custom application metrics
│   ├── memory_monitor.py       # Memory leak protection
│   ├── exceptions.py           # Custom exceptions (PIIMaskingError)
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
│   ├── broker.py               # FastStream broker (analysis, cache, llm queues + DLQ)
│   ├── publisher.py            # Message publisher
│   ├── worker.py               # Background worker
│   └── models.py               # Message models (ClientAnalysisRequest, AsyncLLMQueueMessage...)
├── mcp_server/                 # MCP Server для IDE-интеграции
│   ├── main.py                 # FastMCP server
│   ├── tools/                  # MCP tools (analysis, validation, api, file)
│   ├── resources/              # MCP resources (api specs, best practices, reference data)
│   └── prompts/                # System prompts и adaptive prompt engine
├── prompts/                    # Adaptive prompt engine
│   └── adaptive_prompt_engine.py
└── frontend/                   # Streamlit UI
    ├── app.py                  # Main Streamlit app (8 вкладок)
    ├── router.py               # Page routing + access control
    ├── api_client.py           # HTTP client for API
    ├── tabs/                   # UI tabs (analysis, comparison, data, llm, monitor, rag, utilities, docs)
    ├── lib/                    # UI components (validators, charts, formatters)
    └── assets/                 # CSS, logos
```

## Workflow анализа клиента

```
                    Пользователь (REST API / Streamlit / RabbitMQ)
                               ↓
                    Orchestrator (валидация ИНН, DaData, LLM search intents)
                               ↓
              ┌────────────────┼────────────────┐
              ↓                ↓                ↓
         InfoSphere        Casebook      Perplexity + Tavily
         (параллельно)   (параллельно)   (web search, scraping)
              └────────────────┼────────────────┘
                               ↓
                    Data Collector (агрегация всех источников)
                               ↓
                    Report Analyzer (LLM + CoT + RAG context)
                    ├── PII masking ПЕРЕД LLM
                    ├── LLM анализ (с fallback chain)
                    ├── PII unmasking ПОСЛЕ LLM
                    └── Risk score (0-100)
                               ↓
                    File Writer (PDF + JSON отчёт)
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
1. **PII Protection FIRST** — обязательное маскирование PII перед ЛЮБОЙ отправкой в LLM (152-ФЗ). При ошибке маскирования — блокировка вызова, НЕ degradation
2. **Singleton pattern** — для TarantoolClient, LLMManager, AsyncHttpClient (через `get_instance()`)
3. **Hot-reload** — конфигурация через Settings facade с @property, watchdog для YAML/.env
4. **Graceful degradation** — fallback на in-memory при недоступности Tarantool, fallback LLM chain, RAG без ChromaDB
5. **Circuit Breaker** — для всех внешних сервисов (per-service + app-level)
6. **Dual entry point** — REST API и RabbitMQ как два равноправных входа; RabbitMQ с автоматическим fallback на background tasks

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
- PII-тесты: `tests/test_pii_protection.py` — обязательная проверка маскирования всех типов PII
- Тестовые файлы: `test_*.py`

### API
- Версионированный API: `/api/v1/...` (основной)
- Legacy endpoints: `/agent/...`, `/data/...` (deprecated, sunset 2026-12-31)
- Стандартизированный формат ответа: `{"status": "success/error", "data": {...}, "error": {...}}`
- Rate limiting: SlowAPI per IP
- Auth: `X-Auth-Token` header для admin endpoints

### RabbitMQ
- 3 очереди: `analysis_queue`, `cache_queue`, `llm_queue`
- DLQ через Dead Letter Exchange (`dlx`) — failed сообщения сохраняются в Tarantool
- `correlation_id` для связи запрос-ответ
- Настройка: `settings.queue.enabled` — при `false` используются background tasks
- TTL: analysis — 1 час, llm — 5 мин
- Max delivery attempts: 3 (настраивается через `MAX_DELIVERY_ATTEMPTS`)

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
5. **README устарел** — структура проекта в README не соответствует фактической
6. **`asyncio.get_event_loop()`** используется вместо `asyncio.get_running_loop()` — deprecation warning на Python 3.12+
7. **Единая точка отказа** — если Tarantool и in-memory одновременно заполнены, данные теряются
8. **`_run_coroutine_sync()`** в LLMManager создаёт потоки для sync-async bridge — потенциальный deadlock

### Средние
9. **Дублирование fallback логики** — risk_calculator.py и report_analyzer._calculate_risk_fallback() пересекаются
10. **Hardcoded thinking messages** — в `client_workflow.py` thinking_messages захардкожены
11. **Search cache в двух местах** — `_search_cache` dict в TarantoolClient + основной кэш
12. **gRPC заявлен, но не реализован** — настройки есть, кода нет
13. **Redis заявлен, но не используется** — настройки есть, подключения нет
