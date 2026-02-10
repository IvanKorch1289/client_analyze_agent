# Система анализа контрагентов

Мультиагентная платформа для автоматизированной проверки и оценки рисков клиентов/контрагентов. Ориентирована на российский рынок (152-ФЗ compliance, российские источники данных, кириллический NLP).

## Возможности

### Основные функции
- **Анализ компаний по ИНН** — сбор данных из DaData (ЕГРЮЛ), InfoSphere (12+ баз), Casebook (суды), Perplexity AI и Tavily
- **Мультиагентный workflow** на LangGraph (Orchestrator → DataCollector → ReportAnalyzer → FileWriter)
- **Оценка рисков (0-100)** с нормализованным скором по 6 категориям + генерация PDF/JSON отчётов
- **PII-защита** — обязательное маскирование персональных данных перед отправкой в LLM (Microsoft Presidio + 7 кастомных RU-распознавателей)

### Enterprise-функции (Phase 6)
- **RBAC** — 4 роли (admin, analyst, viewer, guest) с гранулярными правами доступа
- **Batch API** — пакетный анализ до 100 клиентов в одном запросе
- **Webhooks** — подписка на события системы (analysis.completed, batch.completed)
- **Audit Trail** — журнал всех действий для compliance-мониторинга

### Инфраструктура
- **LLM с fallback** — OpenRouter (Claude) → HuggingFace → GigaChat → YandexGPT
- **REST API** — FastAPI с SSE-стримингом, планировщиком задач и версионированным API `/api/v1/`
- **RabbitMQ** — три очереди (analysis, cache, llm) с DLQ, как альтернативный вход к REST API
- **RAG** — обогащение контекста анализа из ChromaDB (семантический поиск похожих отчётов)
- **Кэширование** — Tarantool с TTL и in-memory fallback
- **Браузерный интерфейс** — Streamlit с 8 вкладками
- **MCP-сервер** — интеграция с IDE (Cursor, VS Code)
- **Мониторинг** — Prometheus + Grafana + Alertmanager

## Быстрый старт

### Docker Compose (рекомендуется)

```bash
# 1. Клонируйте репозиторий
git clone https://github.com/IvanKorch1289/client_analyze_agent.git
cd client_analyze_agent

# 2. Создайте файл .env
cp .env.example .env

# 3. Добавьте API-ключи в .env (см. раздел "Переменные окружения")
nano .env

# 4. Запустите
docker-compose up -d
```

**Доступные адреса:**
| Сервис | URL | Описание |
|--------|-----|----------|
| Web UI | http://localhost:5000 | Streamlit интерфейс |
| API | http://localhost:8000 | REST API |
| API Docs | http://localhost:8000/docs | Swagger документация |
| Prometheus | http://localhost:9090 | Метрики |
| Grafana | http://localhost:3000 | Дашборды (admin/admin) |

### Локальный запуск (для разработки)

```bash
# Установка зависимостей
poetry install --with dev

# Запуск (backend + Streamlit)
python run.py

# Или отдельно backend
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000

# Или отдельно Streamlit
streamlit run app/frontend/app.py --server.port 5000
```

## Переменные окружения

Создайте `.env` на основе `.env.example`:

```env
# ===== ОБЯЗАТЕЛЬНЫЕ =====

# Аутентификация (32+ символов для production)
ADMIN_TOKEN=your_strong_admin_token_here_32chars

# LLM API (минимум один из провайдеров)
OPENROUTER_API_KEY=sk-or-v1-...

# ===== РЕКОМЕНДУЕМЫЕ =====

# Поисковые сервисы
PERPLEXITY_API_KEY=pplx-...
TAVILY_API_KEY=tvly-...

# Источники данных по ИНН
DADATA_API_KEY=...
INFOSPHERE_LOGIN=...
INFOSPHERE_PASSWORD=...
CASEBOOK_API_KEY=...

# ===== ОПЦИОНАЛЬНЫЕ =====

# Дополнительные LLM (fallback)
HUGGINGFACE_API_KEY=hf_...
GIGACHAT_CREDENTIALS=...
YANDEX_API_KEY=...

# RBAC токены для разных ролей
ANALYST_TOKEN=...
VIEWER_TOKEN=...

# Кэш (если не указано — in-memory fallback)
TARANTOOL_HOST=localhost
TARANTOOL_PORT=3302

# RabbitMQ (если не указано — background tasks)
RABBITMQ_HOST=localhost
RABBITMQ_PORT=5672

# Email-уведомления
SMTP_HOST=smtp.example.com
SMTP_PORT=587
SMTP_USER=...
SMTP_PASSWORD=...
```

## Использование API

### Анализ клиента (основной сценарий)

```bash
# Простой анализ
curl -X POST http://localhost:8000/api/v1/agent/analyze-client \
  -H "Content-Type: application/json" \
  -H "X-Auth-Token: your_admin_token" \
  -d '{"client_name": "Газпром", "inn": "7736050003"}'

# С SSE streaming (для отображения прогресса)
curl -X POST "http://localhost:8000/api/v1/agent/analyze-client?stream=true" \
  -H "Content-Type: application/json" \
  -H "X-Auth-Token: your_admin_token" \
  -d '{"client_name": "Сбербанк"}'
```

### Пакетный анализ (Batch API)

```bash
# Анализ нескольких клиентов за один запрос
curl -X POST http://localhost:8000/api/v1/batch/analyze \
  -H "Content-Type: application/json" \
  -H "X-Auth-Token: your_admin_token" \
  -d '{
    "clients": [
      {"client_name": "Газпром", "inn": "7736050003"},
      {"client_name": "Сбербанк", "inn": "7707083893"},
      {"client_name": "Яндекс", "inn": "7736207543"}
    ],
    "save_reports": true,
    "webhook_url": "https://your-server.com/webhook"
  }'
```

### Работа с отчётами

```bash
# Список отчётов
curl http://localhost:8000/api/v1/reports \
  -H "X-Auth-Token: your_token"

# Получить отчёт по ID
curl http://localhost:8000/api/v1/reports/{report_id}

# Экспорт в PDF
curl http://localhost:8000/api/v1/export/pdf/{report_id} \
  -o report.pdf
```

### Webhooks (подписка на события)

```bash
# Зарегистрировать webhook
curl -X POST http://localhost:8000/api/v1/webhooks \
  -H "Content-Type: application/json" \
  -H "X-Auth-Token: your_admin_token" \
  -d '{
    "url": "https://your-server.com/webhook",
    "events": ["analysis.completed", "batch.completed"],
    "secret": "optional_hmac_secret"
  }'

# Список webhooks
curl http://localhost:8000/api/v1/webhooks \
  -H "X-Auth-Token: your_admin_token"

# История доставки
curl http://localhost:8000/api/v1/webhooks/deliveries \
  -H "X-Auth-Token: your_admin_token"
```

### Audit Trail (журнал аудита)

```bash
# Получить записи аудита
curl "http://localhost:8000/api/v1/audit/entries?action=analysis&limit=100" \
  -H "X-Auth-Token: your_admin_token"

# Статистика аудита
curl http://localhost:8000/api/v1/audit/stats \
  -H "X-Auth-Token: your_admin_token"
```

### Внешние источники данных

```bash
# Поиск через Perplexity AI
curl -X POST http://localhost:8000/api/v1/data/perplexity/search \
  -H "Content-Type: application/json" \
  -H "X-Auth-Token: your_token" \
  -d '{"query": "судебные дела Газпром"}'

# Данные из DaData
curl -X POST http://localhost:8000/api/v1/data/dadata/suggest \
  -H "Content-Type: application/json" \
  -H "X-Auth-Token: your_token" \
  -d '{"inn": "7736050003"}'
```

### Асинхронный LLM API

```bash
# Асинхронный запрос с webhook callback
curl -X POST http://localhost:8000/api/v1/llm/async \
  -H "Content-Type: application/json" \
  -H "X-Auth-Token: your_token" \
  -d '{
    "prompt": "Проанализируй риски компании...",
    "callback_url": "https://your-server.com/llm-callback"
  }'

# Тестирование PII-маскирования
curl -X POST http://localhost:8000/api/v1/llm/mask-text \
  -H "Content-Type: application/json" \
  -d '{"text": "ИНН 7707083893, директор Иванов Иван"}'
```

### Мониторинг и администрирование

```bash
# Healthcheck
curl http://localhost:8000/api/v1/health

# Метрики Prometheus
curl http://localhost:8000/api/v1/metrics

# Статус circuit breakers
curl http://localhost:8000/api/v1/circuit-breakers

# Очистка кэша (admin)
curl -X POST http://localhost:8000/api/v1/admin/cache/clear \
  -H "X-Auth-Token: your_admin_token"

# Статистика LLM (admin)
curl http://localhost:8000/api/v1/admin/llm/stats \
  -H "X-Auth-Token: your_admin_token"
```

## Роли и права доступа (RBAC)

| Роль | Токен | Права |
|------|-------|-------|
| **admin** | `ADMIN_TOKEN` | Полный доступ: анализ, отчёты, webhooks, audit, кэш, конфигурация |
| **analyst** | `ANALYST_TOKEN` | Анализ, batch, отчёты, данные, LLM, audit (чтение) |
| **viewer** | `VIEWER_TOKEN` | Только чтение: отчёты, результаты анализа |
| **guest** | (без токена) | Минимальный доступ: просмотр публичных отчётов |

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
Report Analyzer (PII mask → LLM + CoT + RAG → PII unmask → Risk score)
                 ↓
File Writer (PDF + JSON отчёт)
```

## Уровни риска

| Уровень | Баллы | Цвет | Рекомендация |
|---------|-------|------|--------------|
| low | 0-24 | Зелёный | Стандартная процедура |
| medium | 25-49 | Жёлтый | Дополнительная проверка |
| high | 50-74 | Оранжевый | Глубокое расследование |
| critical | 75-100 | Красный | Рекомендуется отказ |

## Resilience

- **Circuit Breaker** для всех внешних сервисов (per-service + app-level)
- **Retry с exponential backoff** (до 3 попыток, включая 429 rate limit)
- **LLM fallback chain** — автоматический переход между провайдерами
- **Таймауты** — DaData: 30s, InfoSphere/Casebook: 360s, Perplexity/Tavily: 60s
- **Dead Letter Queue** — failed RabbitMQ messages сохраняются в DLQ
- **In-memory fallback** при недоступности Tarantool
- **Graceful degradation** — RAG работает без ChromaDB, analysis без RabbitMQ
- **PII fail-safe** — при ошибке маскирования LLM-вызов блокируется полностью

## Структура проекта

```
app/
├── main.py                     # FastAPI приложение, middleware, lifespan
├── run.py                      # Точка входа (backend + Streamlit)
├── config/                     # Конфигурация (YAML + env + hot-reload)
├── agents/                     # LangGraph агенты
│   ├── orchestrator.py         # Оркестратор: валидация, DaData, LLM search intents
│   ├── client_workflow.py      # StateGraph workflow
│   ├── data_collector/         # Параллельный сбор данных
│   ├── report_analyzer.py      # LLM-анализ с Chain-of-Thought
│   ├── risk_calculator.py      # Нормализованный риск-скор (0-100)
│   ├── file_writer.py          # Генерация PDF/JSON
│   ├── llm_manager.py          # LLM: fallback chain, PII masking, audit, cache
│   └── rag_context.py          # RAG: обогащение из ChromaDB
├── api/                        # REST API
│   ├── v1.py                   # Versioned API (/api/v1)
│   └── routes/                 # agent, data, reports, batch, webhooks, audit...
├── services/                   # Клиенты внешних сервисов
│   ├── http_client.py          # AsyncHttpClient с circuit breaker
│   └── ...                     # openrouter, perplexity, tavily, chroma...
├── storage/                    # Tarantool + repositories
├── schemas/                    # Pydantic-схемы
├── shared/                     # Shared utilities
│   ├── pii_protection.py       # Presidio PII masking (7 RU recognizers)
│   ├── audit_trail.py          # Audit logging
│   ├── webhooks.py             # Webhook manager
│   └── toolkit/                # Logging, auth, circuit breaker...
├── messaging/                  # RabbitMQ (FastStream)
├── mcp_server/                 # MCP Server для IDE
└── frontend/                   # Streamlit UI (8 вкладок)
```

## Разработка

```bash
# Линтинг и форматирование
make lint                # ruff + pyright + vulture + bandit + pip-audit
make format              # black + ruff format

# Тесты
pytest tests/ -q
pytest tests/ -q --cov=app

# Безопасность
make audit               # security-check + deps-check + secrets-check
```

## Технологии

| Технология | Назначение |
|------------|------------|
| Python 3.12 | Язык |
| FastAPI + Uvicorn | Backend API |
| Streamlit | Web UI |
| LangGraph | Оркестрация агентов |
| OpenRouter (Claude 3.5 Sonnet) | LLM с fallback |
| Microsoft Presidio + spaCy | PII-защита (152-ФЗ) |
| Tarantool | Кэширование с TTL |
| RabbitMQ (FastStream) | Очереди сообщений |
| ChromaDB | Векторная БД для RAG |
| Prometheus + Grafana | Мониторинг |
| Docker Compose | Контейнеризация (10 сервисов) |

## Лицензия

Проект разработан для внутреннего использования.

---

Разработчик: Korch Ivan
Обновлено: Февраль 2026
