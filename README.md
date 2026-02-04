# Система анализа контрагентов

Мультиагентная платформа для автоматизированной проверки и оценки рисков клиентов/контрагентов. Ориентирована на российский рынок (152-ФЗ compliance, российские источники данных, кириллический NLP).

## Возможности

- **Анализ компаний по ИНН** — сбор данных из DaData (ЕГРЮЛ), InfoSphere, Casebook (суды), Perplexity AI и Tavily
- **Мультиагентный workflow** на LangGraph (Orchestrator -> DataCollector -> ReportAnalyzer -> FileWriter)
- **Оценка рисков (0-100)** с нормализованным скором по 6 категориям + генерация PDF/JSON отчётов
- **PII-защита** — обязательное маскирование персональных данных перед отправкой в LLM (Microsoft Presidio + 7 кастомных RU-распознавателей)
- **LLM с fallback** — OpenRouter (Claude) -> HuggingFace -> GigaChat -> YandexGPT
- **REST API** — FastAPI с SSE-стримингом, планировщиком задач и версионированным API `/api/v1/`
- **RabbitMQ** — три очереди (analysis, cache, llm) с DLQ, как альтернативный вход к REST API
- **RAG** — обогащение контекста анализа из ChromaDB (семантический поиск похожих отчётов)
- **Кэширование** — Tarantool с TTL и in-memory fallback
- **Браузерный интерфейс** — Streamlit с 8 вкладками
- **MCP-сервер** для интеграции с IDE
- **Мониторинг** — Prometheus + Grafana + Alertmanager

## Технологии

| Технология | Назначение |
|------------|------------|
| Python 3.12 | Язык |
| FastAPI + Uvicorn | Backend API |
| Streamlit | Web UI |
| LangGraph | Оркестрация агентов |
| OpenRouter (Claude 3.5 Sonnet) | LLM с fallback на HuggingFace, GigaChat, YandexGPT |
| Microsoft Presidio + spaCy | PII-защита (152-ФЗ) |
| Tarantool | Кэширование с TTL |
| RabbitMQ (FastStream) | Очереди сообщений |
| ChromaDB | Векторная БД для RAG |
| Prometheus + Grafana | Мониторинг |
| Docker Compose | Контейнеризация (10 сервисов) |

## Быстрый старт

### Docker Compose (рекомендуется)

```bash
cp .env.example .env
# Отредактируйте .env и добавьте API ключи

docker-compose up -d
```

Приложение будет доступно:
- Web UI: http://localhost:5000
- API: http://localhost:8000
- API Docs: http://localhost:8000/docs
- Prometheus: http://localhost:9090
- Grafana: http://localhost:3000

### Локальный запуск

```bash
# Установка зависимостей через Poetry
poetry install --with dev

# Запуск (backend + Streamlit)
python run.py
```

## Переменные окружения

Создайте файл `.env` на основе `.env.example`:

```env
# Аутентификация
ADMIN_TOKEN=your_admin_token

# LLM
OPENROUTER_API_KEY=your_openrouter_api_key

# Поисковые сервисы
PERPLEXITY_API_KEY=your_perplexity_api_key
TAVILY_API_KEY=your_tavily_api_key

# Источники данных по ИНН
DADATA_API_KEY=your_dadata_api_key
INFOSPHERE_LOGIN=your_login
INFOSPHERE_PASSWORD=your_password
CASEBOOK_API_KEY=your_casebook_api_key

# Кэш (опционально)
TARANTOOL_HOST=localhost
TARANTOOL_PORT=3302

# RabbitMQ (опционально)
RABBITMQ_HOST=localhost
RABBITMQ_PORT=5672

# Email (опционально)
SMTP_HOST=smtp.example.com
SMTP_PORT=587
SMTP_USER=your_email
SMTP_PASSWORD=your_password
```

## API Endpoints

### Версионированный API (`/api/v1/`)

```bash
# Анализ клиента
curl -X POST http://localhost:8000/api/v1/agent/analyze-client \
  -H "Content-Type: application/json" \
  -d '{"client_name": "Газпром", "inn": "7736050003"}'

# С SSE streaming
curl -X POST "http://localhost:8000/api/v1/agent/analyze-client?stream=true" \
  -H "Content-Type: application/json" \
  -d '{"client_name": "Сбербанк"}'

# Отчёты
curl http://localhost:8000/api/v1/reports

# Данные из внешних источников
curl -X POST http://localhost:8000/api/v1/data/perplexity/search \
  -H "Content-Type: application/json" \
  -d '{"query": "судебные дела Газпром"}'

# Асинхронный LLM запрос
curl -X POST http://localhost:8000/api/v1/llm/async \
  -H "Content-Type: application/json" \
  -d '{"prompt": "Анализ рисков компании", "callback_url": "http://..."}'

# Тестирование PII-маскирования
curl -X POST http://localhost:8000/api/v1/llm/mask-text \
  -H "Content-Type: application/json" \
  -d '{"text": "ИНН 7707083893, директор Иванов Иван"}'
```

### Мониторинг и администрирование

```bash
# Healthcheck
curl http://localhost:8000/api/v1/health

# Метрики
curl http://localhost:8000/api/v1/metrics

# Статус circuit breakers
curl http://localhost:8000/api/v1/circuit-breakers

# Административные (требуют X-Auth-Token)
curl -X POST http://localhost:8000/api/v1/cache/clear \
  -H "X-Auth-Token: your_admin_token"
```

> **Примечание:** Legacy endpoints `/agent/...`, `/data/...` deprecated (sunset: 2026-12-31). Используйте `/api/v1/...`.

## Структура проекта

```
app/
├── main.py                     # FastAPI приложение, middleware, lifespan
├── run.py                      # Точка входа (backend + Streamlit)
├── config/                     # Конфигурация (YAML + env + hot-reload)
│   ├── settings.py             # Facade настроек
│   ├── base.py                 # AppBaseSettings, SchedulerSettings
│   ├── database.py             # Tarantool, Mongo, PostgreSQL
│   ├── external_api.py         # Все внешние API
│   ├── security.py             # CORS, HSTS, CSP, IP-filter
│   └── services.py             # Queue, Mail, Chroma, MCP
├── agents/                     # LangGraph агенты
│   ├── orchestrator.py         # Оркестратор: валидация, DaData, LLM search intents
│   ├── client_workflow.py      # StateGraph workflow
│   ├── data_collector/         # Параллельный сбор данных
│   ├── collectors/             # Registry-паттерн коллекторов
│   ├── report_analyzer.py      # LLM-анализ с Chain-of-Thought
│   ├── risk_calculator.py      # Нормализованный риск-скор (0-100)
│   ├── file_writer.py          # Генерация PDF/JSON
│   ├── llm_manager.py          # LLM: fallback chain, PII masking, audit, cache
│   ├── rag_context.py          # RAG: обогащение из ChromaDB
│   └── web_scraper.py          # Web scraping
├── api/                        # REST API
│   ├── v1.py                   # Versioned API (/api/v1)
│   ├── routes/                 # agent, data, reports, analytics, llm, scheduler...
│   ├── error_handlers.py       # Обработка ошибок
│   └── rate_limit.py           # Rate limiting
├── services/                   # Клиенты внешних сервисов
│   ├── http_client.py          # AsyncHttpClient с circuit breaker
│   ├── openrouter_client.py    # OpenRouter API
│   ├── perplexity_client.py    # Perplexity AI
│   ├── tavily_client.py        # Tavily Search
│   ├── chroma_service.py       # ChromaDB
│   ├── email_client.py         # SMTP
│   └── scheduler_service.py    # APScheduler
├── storage/                    # Хранилище данных
│   ├── tarantool.py            # TarantoolClient: singleton, LRU cache
│   ├── repositories/           # Repository pattern (cache, reports, threads)
│   └── init.lua                # Tarantool schema
├── schemas/                    # Pydantic-схемы
│   ├── report.py               # ClientAnalysisReport
│   ├── requests.py             # Request models
│   └── llm.py                  # LLM API schemas
├── shared/                     # Shared utilities
│   ├── pii_protection.py       # Presidio PII masking (7 RU recognizers)
│   ├── llm_audit.py            # LLM audit logging (152-ФЗ)
│   ├── security.py             # INN validation, sanitization
│   ├── prometheus_metrics.py   # Prometheus metrics
│   └── toolkit/                # Logging, circuit breaker, auth, helpers...
├── messaging/                  # RabbitMQ
│   ├── broker.py               # FastStream (analysis, cache, llm queues + DLQ)
│   ├── publisher.py            # Message publisher
│   └── worker.py               # Background worker
├── prompts/                    # Prompt management
│   ├── manager.py              # PromptManager с версионированием
│   └── adaptive_prompt_engine.py  # Адаптация промптов по фидбекам
├── mcp_server/                 # MCP Server для IDE-интеграции
│   ├── main.py                 # FastMCP server
│   ├── tools/                  # MCP tools
│   ├── resources/              # API specs, reference data
│   └── prompts/                # System prompts (typed, versioned)
└── frontend/                   # Streamlit UI
    ├── app.py                  # 8 вкладок
    ├── api_client.py           # HTTP client for API
    └── tabs/                   # UI tabs
```

## Workflow анализа

```
Пользователь (REST API / Streamlit / RabbitMQ)
                 ↓
Orchestrator (валидация ИНН, DaData, LLM search intents)
                 ↓
    ┌────────────┼────────────┐
    ↓            ↓            ↓
InfoSphere   Casebook   Perplexity + Tavily
 (параллельно)           (web search, scraping)
    └────────────┼────────────┘
                 ↓
Data Collector (агрегация)
                 ↓
Report Analyzer (PII mask -> LLM + CoT + RAG -> PII unmask -> Risk score)
                 ↓
File Writer (PDF + JSON отчёт)
```

## Уровни риска

| Уровень | Баллы | Рекомендация |
|---------|-------|--------------|
| low | 0-24 | Стандартная процедура |
| medium | 25-49 | Дополнительная проверка |
| high | 50-74 | Глубокое расследование |
| critical | 75-100 | Рекомендуется отказ |

## Resilience

- **Circuit Breaker** для всех внешних сервисов (per-service + app-level)
- **Retry с exponential backoff** (до 3 попыток, включая 429 rate limit retry)
- **LLM fallback chain** — автоматический переход между провайдерами
- **Таймауты** — DaData: 30s, InfoSphere/Casebook: 360s, Perplexity/Tavily: 60s
- **Dead Letter Queue** — failed RabbitMQ messages сохраняются в DLQ
- **In-memory fallback** при недоступности Tarantool
- **Graceful degradation** — RAG работает без ChromaDB, analysis без RabbitMQ
- **PII fail-safe** — при ошибке маскирования LLM-вызов блокируется полностью

## Разработка

```bash
# Линтинг
make lint                # ruff + pyright + vulture + bandit + pip-audit
make format              # black + ruff format

# Тесты
pytest tests/ -q
pytest tests/ -q --cov=app

# Безопасность
make audit               # security-check + deps-check + secrets-check
```

## Лицензия

Проект разработан для внутреннего использования.

---

Разработчик: Korch Ivan
Обновлено: Февраль 2026
