# Система анализа контрагентов

Мультиагентная система для анализа потенциальных клиентов и контрагентов с использованием LLM, LangGraph и внешних источников данных.

## Возможности

- **Анализ компаний по ИНН** через DaData, InfoSphere, Casebook
- **Веб-поиск** через Perplexity AI и Tavily
- **Мультиагентный workflow** с оркестратором, поисковыми агентами и анализатором
- **Оценка рисков** с автоматическим формированием отчётов
- **Кэширование** через Tarantool (с in-memory fallback)
- **TCP-клиент** для интеграции с внешними системами
- **MCP-сервер** для интеграции с IDE

## Технологии

| Технология | Назначение |
|------------|------------|
| OpenRouter | LLM (Claude 3.5 Sonnet по умолчанию) |
| LangGraph | Оркестрация агентов |
| FastAPI | Backend API |
| Streamlit | Web UI |
| Tarantool | Кэширование с TTL |
| Perplexity | Веб-поиск |
| Tavily | Расширенный поиск |
| DaData | Данные о компаниях |
| Casebook | Судебные дела |
| InfoSphere | Дополнительная аналитика |

## Быстрый старт

### Docker Compose (рекомендуется)

```bash
cp .env.example .env

docker-compose up -d
```

Приложение будет доступно:
- Web UI: http://localhost:5000
- API: http://localhost:8000
- API Docs: http://localhost:8000/docs

### Локальный запуск

```bash
pip install uv
uv pip install -e .

python run.py
```

## Переменные окружения

Создайте файл `.env`:

```env
OPENROUTER_API_KEY=your_openrouter_api_key

PERPLEXITY_API_KEY=your_perplexity_api_key
TAVILY_API_KEY=your_tavily_api_key

DADATA_API_KEY=your_dadata_api_key
INFOSPHERE_LOGIN=your_login
INFOSPHERE_PASSWORD=your_password
CASEBOOK_API_KEY=your_casebook_api_key

TARANTOOL_HOST=localhost
TARANTOOL_PORT=3302
```

## API Endpoints

### Анализ клиента

```bash
curl -X POST http://localhost:8000/agent/analyze-client \
  -H "Content-Type: application/json" \
  -d '{
    "client_name": "Газпром",
    "inn": "7736050003"
  }'
```

С SSE streaming:
```bash
curl -X POST "http://localhost:8000/agent/analyze-client?stream=true" \
  -H "Content-Type: application/json" \
  -d '{"client_name": "Сбербанк"}'
```

### Внешние источники

```bash
curl -X POST http://localhost:8000/utility/perplexity/search \
  -H "Content-Type: application/json" \
  -d '{"query": "судебные дела Газпром"}'

curl -X POST http://localhost:8000/utility/tavily/search \
  -H "Content-Type: application/json" \
  -d '{"query": "финансовые новости Сбербанк"}'
```

### Мониторинг

```bash
curl http://localhost:8000/utility/health
curl http://localhost:8000/utility/metrics
curl http://localhost:8000/utility/circuit-breakers
```

## Структура проекта

```
app/
├── main.py              # FastAPI приложение
├── settings.py          # Конфигурация
├── frontend/            # Web-интерфейс
│   └── app.py           # Streamlit UI
├── utility/             # Утилиты
│   ├── logging_client.py  # Логирование
│   ├── cache.py         # Декоратор кэширования
│   ├── helpers.py       # Вспомогательные функции
│   └── tcp_client.py    # TCP-клиент
├── agents/              # LangGraph агенты
│   ├── orchestrator.py  # Оркестратор
│   ├── search.py        # Поисковый агент
│   ├── report_analyzer.py  # Анализатор
│   └── workflow.py      # Граф workflow
├── api/routes/          # API роуты
├── mcp_server/          # MCP сервер
│   ├── server.py        # MCP ядро
│   └── tools.py         # Инструменты MCP
├── services/            # Клиенты внешних сервисов
│   ├── http_client.py   # HTTP с circuit breaker
│   ├── openrouter_client.py
│   ├── perplexity_client.py
│   └── tavily_client.py
└── storage/             # Кэширование
    └── tarantool.py
```

## Уровни риска

| Уровень | Баллы | Рекомендация |
|---------|-------|--------------|
| low | 0-24 | Стандартная процедура |
| medium | 25-49 | Дополнительная проверка |
| high | 50-74 | Глубокое расследование |
| critical | 75-100 | Рекомендуется отказ |

## Resilience

- **Circuit Breaker** для защиты от каскадных сбоев
- **Retry с exponential backoff** (до 3 попыток)
- **Таймауты** для каждого сервиса
- **Метрики** запросов и ошибок
- **In-memory fallback** при недоступности Tarantool

## Разработка

```bash
ruff check app/
black app/
pyright app/
```

## Лицензия

Проект разработан для внутреннего использования.

---

Разработчик: Korch Ivan  
Обновлено: Декабрь 2025
