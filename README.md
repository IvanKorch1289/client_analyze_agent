# Система анализа контрагентов

Мультиагентная система для анализа потенциальных клиентов и контрагентов с использованием LLM, LangGraph и внешних источников данных.

## Возможности

- **Анализ компаний по ИНН** через DaData, InfoSphere, Casebook
- **Веб-поиск** через Perplexity AI и Tavily
- **Мультиагентный workflow** с оркестратором, поисковыми агентами и анализатором
- **Оценка рисков** с автоматическим формированием отчётов
- **Генерация PDF-отчётов** с оценкой рисков и рекомендациями
- **Кэширование** через Tarantool (с in-memory fallback)
- **TCP-клиент** для интеграции с внешними системами
- **Email-уведомления** через SMTP
- **MCP-сервер** для интеграции с IDE
- **Ролевой доступ** (admin/viewer/guest) для защиты административных функций

## Технологии

| Технология | Назначение |
|------------|------------|
| OpenRouter | LLM (Claude 3.5 Sonnet по умолчанию) |
| LangGraph | Оркестрация агентов |
| FastAPI | Backend API |
| Streamlit | Web UI |
| Tarantool | Кэширование с TTL |
| PostgreSQL | Хранение данных |
| Perplexity | Веб-поиск |
| Tavily | Расширенный поиск |
| DaData | Данные о компаниях |
| Casebook | Судебные дела |
| InfoSphere | Дополнительная аналитика |

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

### Локальный запуск

```bash
# Установка зависимостей через Poetry
poetry install

# Или через pip
pip install -e .

# Запуск
python run.py
```

## Переменные окружения

Создайте файл `.env` на основе `.env.example`:

```env
# Аутентификация
ADMIN_TOKEN=your_admin_token
VIEWER_TOKEN=your_viewer_token

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

# Email (опционально)
SMTP_HOST=smtp.example.com
SMTP_PORT=587
SMTP_USER=your_email
SMTP_PASSWORD=your_password

# TCP сервер (опционально)
TCP_HOST=localhost
TCP_PORT=9000
```

## API Endpoints

### Анализ клиента

```bash
# Базовый анализ
curl -X POST http://localhost:8000/agent/analyze-client \
  -H "Content-Type: application/json" \
  -d '{
    "client_name": "Газпром",
    "inn": "7736050003"
  }'

# С SSE streaming
curl -X POST "http://localhost:8000/agent/analyze-client?stream=true" \
  -H "Content-Type: application/json" \
  -d '{"client_name": "Сбербанк"}'
```

### Внешние источники

```bash
# Поиск через Perplexity
curl -X POST http://localhost:8000/utility/perplexity/search \
  -H "Content-Type: application/json" \
  -d '{"query": "судебные дела Газпром"}'

# Поиск через Tavily
curl -X POST http://localhost:8000/utility/tavily/search \
  -H "Content-Type: application/json" \
  -d '{"query": "финансовые новости Сбербанк"}'
```

### Мониторинг

```bash
# Общий статус
curl http://localhost:8000/utility/health

# Метрики HTTP клиентов
curl http://localhost:8000/utility/metrics

# Статус circuit breakers
curl http://localhost:8000/utility/circuit-breakers

# Статус email
curl http://localhost:8000/utility/email/status

# Статус TCP
curl http://localhost:8000/utility/tcp/healthcheck
```

### Административные операции (требуют ADMIN_TOKEN)

```bash
# Сброс метрик
curl -X POST http://localhost:8000/utility/metrics/reset \
  -H "X-Auth-Token: your_admin_token"

# Очистка кэша по префиксу
curl -X DELETE http://localhost:8000/utility/cache/prefix/search: \
  -H "X-Auth-Token: your_admin_token"

# Сброс circuit breaker
curl -X POST http://localhost:8000/utility/circuit-breakers/perplexity/reset \
  -H "X-Auth-Token: your_admin_token"
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
│   ├── auth.py          # Авторизация
│   ├── pdf_generator.py # Генерация PDF
│   └── tcp_client.py    # TCP-клиент
├── agents/              # LangGraph агенты
│   ├── orchestrator.py  # Оркестратор
│   ├── search.py        # Поисковый агент
│   ├── report_analyzer.py  # Анализатор
│   └── workflow.py      # Граф workflow
├── api/routes/          # API роуты
│   ├── agent.py         # Агентские эндпоинты
│   ├── data.py          # Данные по ИНН
│   └── utility.py       # Утилиты и мониторинг
├── mcp_server/          # MCP сервер
│   ├── server.py        # MCP ядро
│   └── tools.py         # Инструменты MCP
├── services/            # Клиенты внешних сервисов
│   ├── http_client.py   # HTTP с circuit breaker
│   ├── openrouter_client.py
│   ├── perplexity_client.py
│   ├── tavily_client.py
│   └── email_client.py  # SMTP клиент
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

## Дашборд сервисов

Streamlit UI включает панель мониторинга сервисов:
- **LLM (OpenRouter)** - статус и модель
- **Perplexity** - конфигурация и circuit breaker
- **Tavily** - конфигурация и метрики
- **Tarantool** - режим и количество записей
- **Email (SMTP)** - доступность почтового сервера
- **TCP Server** - статус подключения

## Разработка

```bash
# Проверка кода
ruff check app/
black app/
pyright app/
```

## Лицензия

Проект разработан для внутреннего использования.

---

Разработчик: Korch Ivan  
Обновлено: Декабрь 2025
