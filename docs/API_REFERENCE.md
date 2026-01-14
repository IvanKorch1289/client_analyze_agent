# API Reference — Client Analyze Agent

> Документация REST API системы мультиагентного анализа контрагентов

## Содержание

- [Обзор](#обзор)
- [Базовый URL](#базовый-url)
- [Аутентификация](#аутентификация)
- [Rate Limiting](#rate-limiting)
- [Коды ошибок](#коды-ошибок)
- [Группы эндпоинтов](#группы-эндпоинтов)
- [Swagger UI](#swagger-ui)

---

## Обзор

API построено на FastAPI и предоставляет эндпоинты для:

- **Агент** — запуск и управление анализом клиентов
- **Отчёты** — просмотр, фильтрация, экспорт результатов анализа
- **Внешние данные** — получение данных из DaData, Casebook, Инфосферы, Perplexity, Tavily
- **Scheduler** — планирование отложенных задач анализа и сбора данных
- **Аналитика** — dashboard, тренды, сравнение отчётов
- **Утилиты** — health checks, метрики, управление кэшем, логи

---

## Базовый URL

```
http://localhost:8000/api/v1
```

В production замените `localhost:8000` на ваш домен.

---

## Аутентификация

### X-Auth-Token Header

Для административных эндпоинтов требуется заголовок `X-Auth-Token`:

```http
GET /api/v1/utility/config
X-Auth-Token: your_admin_token
```

Токен настраивается через переменную окружения `ADMIN_TOKEN`.

### Режим доступа

Система использует простую модель аутентификации на основе `ADMIN_TOKEN`:

- **Без токена**: Доступ только к публичным эндпоинтам (health check, базовые GET-запросы)
- **С токеном**: Полный доступ ко всем эндпоинтам, включая административные операции

Если токен не установлен в переменных окружения, административные эндпоинты возвращают `401 Unauthorized`.

---

## Rate Limiting

API использует rate limiting на основе IP-адреса клиента.

| Группа эндпоинтов | Лимит |
|-------------------|-------|
| Анализ клиента (`/agent/analyze-client`) | 5 запросов/минута |
| Поиск и отчёты (`/data/*`, `/analytics/*`) | 30 запросов/минута |
| Административные (`/utility/config`, `/cache/*`) | 60 запросов/минута |
| Общие (`/scheduler/*`) | 60 запросов/минута |
| Глобальный лимит | 100 запросов/минута, 2000/час |

При превышении лимита возвращается `429 Too Many Requests`:

```json
{
  "detail": "Rate limit exceeded. Try again in 60 seconds."
}
```

---

## Коды ошибок

### HTTP статусы

| Код | Описание | Когда возникает |
|-----|----------|-----------------|
| `200` | OK | Успешный запрос |
| `400` | Bad Request | Невалидные параметры (неверный ИНН, отсутствующие поля) |
| `401` | Unauthorized | Отсутствует или неверный X-Auth-Token |
| `403` | Forbidden | Недостаточно прав (требуется admin) |
| `404` | Not Found | Ресурс не найден (отчёт, задача) |
| `429` | Too Many Requests | Превышен rate limit |
| `500` | Internal Server Error | Внутренняя ошибка сервера |
| `502` | Bad Gateway | Ошибка внешнего сервиса (Perplexity, Tavily) |
| `503` | Service Unavailable | Сервис недоступен (API key не настроен) |

### Формат ошибки

```json
{
  "detail": "Описание ошибки",
  "code": "error_code"
}
```

---

## Группы эндпоинтов

### 1. Агент (`/agent`)

#### POST /agent/analyze-client

Запуск анализа клиента. Основной эндпоинт системы.

**Request Body:**
```json
{
  "client_name": "ООО Ромашка",
  "inn": "7707083893",
  "additional_notes": "Проверить судебные дела за 2024 год"
}
```

| Параметр | Тип | Обязательный | Описание |
|----------|-----|--------------|----------|
| `client_name` | string | Да | Название компании |
| `inn` | string | Нет | ИНН (10 или 12 цифр) |
| `additional_notes` | string | Нет | Дополнительные инструкции для анализа |

**Query Parameters:**

| Параметр | Тип | Описание |
|----------|-----|----------|
| `stream` | boolean | Если `true`, возвращает SSE-поток с прогрессом |

**Response (200):**
```json
{
  "status": "success",
  "session_id": "analysis_abc123_1703520000",
  "summary": "Краткое резюме анализа...",
  "report": {
    "risk_assessment": {
      "score": 45,
      "level": "medium",
      "factors": ["Судебные иски", "Негативные упоминания"]
    }
  }
}
```

#### GET /agent/threads

Получить список тредов анализа.

**Response:**
```json
{
  "total": 10,
  "threads": [
    {
      "thread_id": "abc123",
      "user_prompt": "Анализ ООО Ромашка...",
      "created_at": "2025-12-25T10:00:00",
      "message_count": 5,
      "client_name": "ООО Ромашка",
      "inn": "7707083893"
    }
  ]
}
```

#### DELETE /agent/analyze/{session_id}

Отменить запущенный анализ.

**Response:**
```json
{
  "status": "cancelled",
  "session_id": "analysis_abc123",
  "message": "Анализ успешно отменён"
}
```

#### POST /agent/feedback

Отправить фидбек по отчёту и перезапустить анализ.

**Request Body:**
```json
{
  "report_id": "rpt_123",
  "rating": "partially_accurate",
  "comment": "Не учтены данные о банкротстве",
  "focus_areas": ["судебные дела", "банкротство"],
  "rerun_analysis": true
}
```

| Параметр | Описание |
|----------|----------|
| `rating` | `accurate`, `partially_accurate`, `inaccurate` |
| `rerun_analysis` | Перезапустить анализ с учётом фидбека |

---

### 2. Отчёты (`/reports`)

#### GET /reports

Список отчётов с фильтрацией и пагинацией.

**Query Parameters:**

| Параметр | Тип | Описание |
|----------|-----|----------|
| `limit` | int | Количество записей (1-500, default: 50) |
| `offset` | int | Смещение (default: 0) |
| `inn` | string | Фильтр по ИНН (точное совпадение) |
| `risk_level` | string | Фильтр по уровню риска: `low`, `medium`, `high`, `critical` |
| `client_name` | string | Поиск по названию компании |
| `date_from` | datetime | Фильтр: дата от (ISO 8601) |
| `date_to` | datetime | Фильтр: дата до (ISO 8601) |
| `min_risk_score` | int | Минимальный балл риска (0-100) |
| `max_risk_score` | int | Максимальный балл риска (0-100) |

**Response:**
```json
{
  "status": "success",
  "reports": [...],
  "total": 150,
  "limit": 50,
  "offset": 0,
  "has_more": true
}
```

#### GET /reports/{report_id}

Получить полный отчёт по ID.

#### GET /reports/{report_id}/export

Экспортировать отчёт в JSON или CSV.

| Параметр | Описание |
|----------|----------|
| `format` | `json` или `csv` |

#### GET /reports/stats/summary

Статистика по отчётам: общее количество, распределение по риску, средний балл.

#### DELETE /reports/{report_id}

Удалить отчёт (требуется admin).

---

### 3. Внешние данные (`/data`)

#### GET /data/client/dadata/{inn}

Получить данные компании из DaData.

#### GET /data/client/casebook/{inn}

Получить судебные дела из Casebook.

#### GET /data/client/infosphere/{inn}

Получить данные из Инфосферы.

#### GET /data/client/info/{inn}

Получить данные из всех источников одновременно.

#### POST /data/search/perplexity

Веб-поиск через Perplexity AI.

**Request Body:**
```json
{
  "inn": "7707083893",
  "query": "судебные дела банкротство",
  "search_recency": "month"
}
```

| Параметр | Описание |
|----------|----------|
| `search_recency` | `day`, `week`, `month` |

#### POST /data/search/tavily

Веб-поиск через Tavily.

**Request Body:**
```json
{
  "inn": "7707083893",
  "query": "судебные дела",
  "search_depth": "advanced",
  "max_results": 10,
  "include_answer": true
}
```

---

### 4. Scheduler (`/scheduler`)

#### POST /scheduler/schedule-analysis

Запланировать анализ клиента на будущее.

**Request Body:**
```json
{
  "client_name": "ООО Ромашка",
  "inn": "7707083893",
  "delay_minutes": 30
}
```

Или с конкретной датой:
```json
{
  "client_name": "ООО Ромашка",
  "inn": "7707083893",
  "run_date": "2025-12-25T15:30:00"
}
```

#### POST /scheduler/schedule-data-fetch

Запланировать сбор данных из внешних источников.

**Request Body:**
```json
{
  "inn": "7707083893",
  "sources": ["dadata", "casebook", "perplexity"],
  "search_query": "судебные дела",
  "delay_minutes": 5
}
```

#### GET /scheduler/tasks

Список запланированных задач.

#### GET /scheduler/task/{task_id}

Информация о конкретной задаче.

#### DELETE /scheduler/task/{task_id}

Отменить запланированную задачу.

---

### 5. Аналитика (`/analytics`)

#### GET /analytics/dashboard

Данные для главного dashboard: метрики, графики, статус сервисов.

#### GET /analytics/trends

Тренды рисков за N дней (7-90).

| Параметр | Описание |
|----------|----------|
| `days` | Количество дней для анализа |

#### POST /analytics/comparison

Сравнение нескольких отчётов.

**Request Body:**
```json
{
  "report_ids": ["rpt_1", "rpt_2", "rpt_3"]
}
```

#### GET /analytics/top-companies

Топ наиболее часто анализируемых компаний.

---

### 6. Утилиты (`/utility`)

#### GET /utility/health

Health check системы.

| Параметр | Описание |
|----------|----------|
| `deep` | `true` — реальные проверки внешних сервисов |

**Response:**
```json
{
  "status": "healthy",
  "issues": null,
  "components": {
    "http_client": "healthy",
    "tarantool": "healthy",
    "openrouter": {"configured": true, "status": "ready"},
    "perplexity": {"configured": true, "status": "ready"},
    "tavily": {"configured": true, "status": "ready"}
  }
}
```

#### GET /utility/config

Снимок текущей конфигурации (admin only).

#### POST /utility/config/reload

Перезагрузить конфигурацию (admin only).

#### GET /utility/metrics

Метрики HTTP клиента.

#### GET /utility/app-metrics

Метрики приложения (admin only).

#### GET /utility/circuit-breakers

Статус circuit breakers для внешних сервисов.

#### GET /utility/tarantool/status

Статус Tarantool/кэша.

#### GET /utility/logs

Получить логи приложения.

| Параметр | Описание |
|----------|----------|
| `limit` | Количество записей |
| `since_minutes` | За последние N минут |
| `level` | DEBUG, INFO, WARNING, ERROR |

#### POST /utility/reports/pdf

Сгенерировать PDF отчёт.

---

## Swagger UI

Интерактивная документация API доступна по адресам:

| URL | Описание |
|-----|----------|
| `/docs` | Swagger UI (основной) |
| `/api/v1/docs` | Swagger UI (версионированный API) |
| `/openapi.json` | OpenAPI спецификация в JSON |
| `/redoc` | ReDoc (альтернативный UI) |

---

## Примеры использования

### cURL: Запуск анализа

```bash
curl -X POST "http://localhost:8000/api/v1/agent/analyze-client" \
  -H "Content-Type: application/json" \
  -d '{"client_name": "ООО Ромашка", "inn": "7707083893"}'
```

### cURL: Получить отчёты с фильтром

```bash
curl -X GET "http://localhost:8000/api/v1/reports?risk_level=high&limit=10" \
  -H "X-Auth-Token: your_admin_token"
```

### Python: Запуск анализа

```python
import requests

response = requests.post(
    "http://localhost:8000/api/v1/agent/analyze-client",
    json={
        "client_name": "ООО Ромашка",
        "inn": "7707083893",
        "additional_notes": "Проверить банкротство"
    },
    headers={"X-Auth-Token": "your_token"}
)

result = response.json()
print(f"Риск-скор: {result['report']['risk_assessment']['score']}")
```

---

## Поддержка

При возникновении вопросов по API:

1. Проверьте `/utility/health` для диагностики
2. Изучите логи через `/utility/logs`
3. Проверьте статус circuit breakers: `/utility/circuit-breakers`
