# 📚 ПОЛНОЕ ОПИСАНИЕ КОДА ПРОЕКТА

**Дата:** 2025-12-18  
**Версия:** 1.0 (после рефакторинга)  
**Всего файлов:** 41 Python файлов

---

## 📂 СТРУКТУРА ПРОЕКТА

```
/workspace/
├── app/
│   ├── agents/           # Агенты LangGraph workflow
│   ├── api/              # FastAPI роуты
│   ├── config/           # Система конфигурации
│   ├── frontend/         # Streamlit UI
│   ├── schemas/          # Pydantic модели
│   ├── services/         # Внешние API клиенты
│   ├── storage/          # Tarantool + кеширование
│   ├── utility/          # Вспомогательные функции
│   └── main.py           # Точка входа FastAPI
├── reports/              # Сгенерированные отчеты
├── logs/                 # Логи приложения
├── tests/                # Тесты
├── docker-compose.yml    # Orchestration
├── Dockerfile            # Docker образ
└── pyproject.toml        # Poetry зависимости
```

---

## 🤖 AGENTS (LangGraph Workflow)

### `agents/client_workflow.py` (318 строк)
**Назначение:** Главный LangGraph workflow для анализа клиентов

**Архитектура:**
```
Orchestrator → Data Collector → Report Analyzer → File Writer
```

**Ключевые компоненты:**
- `ClientAnalysisState` (TypedDict) - состояние workflow
- `build_client_analysis_graph()` - создает граф
- `run_client_analysis_streaming()` - streaming или batch режим
- `_run_streaming_analysis()` - возвращает AsyncGenerator с событиями прогресса
- `_run_batch_analysis()` - обычный режим, возвращает Dict

**Streaming события:**
- `{"type": "progress", "data": {...}}` - прогресс выполнения
- `{"type": "orchestrator", "data": {...}}` - результат оркестратора
- `{"type": "data_collected", "data": {...}}` - данные собраны
- `{"type": "report", "data": {...}}` - отчет готов
- `{"type": "result", "data": {...}}` - финальный результат
- `{"type": "error", "data": {...}}` - ошибка

**Зависимости:**
- `orchestrator_agent` - формирует поисковые запросы
- `data_collector_agent` - собирает данные параллельно
- `report_analyzer_agent` - анализирует и создает отчет
- `file_writer_agent` - сохраняет в файлы
- `save_thread_to_tarantool` - сохраняет историю

---

### `agents/orchestrator.py` (106 строк)
**Назначение:** Координирует workflow, формирует план поиска

**Функционал:**
- Валидация входных данных (client_name обязателен)
- Формирование 5 базовых поисковых запросов:
  1. `reputation` - репутация компании
  2. `lawsuits` - судебные дела
  3. `news` - актуальные новости
  4. `negative` - негативная информация
  5. `financial` - финансовое состояние
- Добавление custom запроса из `additional_notes`

**Входные данные:** 
- `client_name` (обязательно)
- `inn` (опционально)
- `additional_notes` (опционально)

**Выходные данные:**
- `search_intents` - список запросов для поиска
- `orchestrator_result` - метаданные

**Шаблоны запросов:**
```python
"репутация компании {client_name} отзывы клиентов"
"{client_name} ИНН {inn} судебные дела арбитраж"
"{client_name} новости последние события"
"{client_name} проблемы скандалы жалобы"
"{client_name} ИНН {inn} финансовое состояние банкротство"
```

---

### `agents/data_collector.py` (555 строк)
**Назначение:** Параллельный сбор данных из всех источников

**Источники данных:**
1. **Структурированные API:**
   - DaData (информация о компании)
   - InfoSphere (проверка по базам)
   - Casebook (арбитражные дела)

2. **Веб-поиск:**
   - Perplexity AI (поиск с LLM)
   - Tavily (веб-поиск)

**Ключевые константы (из config):**
- `MAX_CONCURRENT_SEARCHES` = 5 - максимум параллельных запросов
- `SEARCH_TIMEOUT_SECONDS` = 60 - таймаут на запрос
- `MAX_CONTENT_LENGTH` = 2500 - максимум символов в контенте

**Функции:**
- `data_collector_agent(state)` - главная функция агента
- `_fetch_perplexity()` - запрос к Perplexity
- `_fetch_tavily()` - запрос к Tavily
- `_analyze_sentiment()` - простой sentiment analysis (positive/negative/neutral)
- `_bounded()` - wrapper для ограничения параллелизма через Semaphore

**Алгоритм:**
1. Сбор данных из структурированных API (параллельно)
2. Выполнение веб-поиска по каждому intent (через semaphore)
3. Анализ sentiment для каждого результата
4. Сбор статистики (успешные/неудачные источники, timing)

**Выходные данные:**
- `source_data` - данные от API (DaData, InfoSphere, Casebook)
- `search_results` - результаты поиска с sentiment
- `collection_stats` - статистика сбора

---

### `agents/report_analyzer.py` (309 строк)
**Назначение:** Анализирует результаты и создает итоговый отчет

**Ключевые функции:**

**1. `calculate_risk_score(search_results)`**
- Рассчитывает оценку риска 0-100
- Определяет уровень: low / medium / high / critical
- Факторы риска на основе sentiment и категорий

**Логика подсчета:**
- Базовый риск: 50 points
- Судебные дела (negative): +15
- Негативные СМИ: +20
- Финансовые проблемы: +25
- Плохая репутация: +10
- Положительная репутация: -10
- Стабильные финансы: -15
- Sentiment влияет: `-10 * avg_sentiment`

**Уровни риска:**
- `< 25` = low
- `25-49` = medium
- `50-74` = high
- `>= 75` = critical

**2. `generate_summary(search_results, client_name)`**
- Генерирует текстовое резюме в Markdown
- Группирует по категориям
- Добавляет иконки sentiment: `+` / `-` / `~`
- Обрезает контент до 500 символов

**3. `analyze_source_data(source_data)`**
- Парсит данные от DaData, InfoSphere, Casebook
- Извлекает company_info (название, статус, адрес, руководство)
- Подсчитывает судебные дела
- Определяет risk_signals (например, "Компания ликвидирована")

**4. `generate_recommendations(risk)`**
- Генерирует рекомендации на основе уровня риска
- `low`: льготные условия, стандартная проверка
- `medium`: запросить документы, проверить лицензии
- `high`: углубленная проверка, обеспечение сделки
- `critical`: отказ или 100% предоплата

**Выходные данные:**
- `report` (Dict) - соответствует схеме `ClientAnalysisReport`
- `analysis_result` (str) - текстовое резюме
- `current_step` = "completed"

**Валидация:** Использует `ClientAnalysisReport.model_validate()` для проверки структуры

---

### `agents/file_writer.py` (194 строки)
**Назначение:** Сохраняет отчет в файлы

**Функционал:**
- Создает директорию `reports/` если не существует
- Генерирует имена файлов: `{timestamp}_{client_name}_{inn}.{ext}`
- Сохраняет два формата:
  1. **Markdown** (.md) - читабельный отчет
  2. **JSON** (.json) - структурированные данные

**Структура Markdown:**
```markdown
# Отчёт по анализу клиента: {name}
**Дата:** ...
**ИНН:** ...

## Оценка риска
**Уровень риска:** 🟢 LOW (20/100)
### Факторы риска:
- Фактор 1
- Фактор 2

## Резюме
{summary}

## Рекомендации
- Рекомендация 1
- Рекомендация 2

## Детальные находки
### ✅ Категория 1
Key points...

## Источники
1. URL 1
2. URL 2
```

**Иконки уровней риска:**
- 🟢 low
- 🟡 medium  
- 🟠 high
- 🔴 critical

**Выходные данные:**
- `saved_files` - пути к сохраненным файлам
  ```python
  {
    "markdown": "reports/20251218_120000_Company_1234567890.md",
    "json": "reports/20251218_120000_Company_1234567890.json"
  }
  ```

---

### `agents/llm_init.py` (97 строк)
**Назначение:** Инициализация LLM для агентов

**Компоненты:**

**1. `_OpenRouterProvider`**
- Единственный активный провайдер (после рефакторинга)
- Использует OpenRouter API
- Конфигурация из `settings.openrouter.*`
- Default модель: `anthropic/claude-3.5-sonnet`

**2. `FallbackLLM(LLM)`**
- LangChain-compatible класс
- Реализует метод `_call()` для синхронных вызовов
- Fallback механизм (сейчас только OpenRouter)
- Логирование через `logger.structured()`

**Удалено после рефакторинга:**
- ❌ `_HuggingFaceProvider` (не использовался)
- ❌ `_GigaChatProvider` (не использовался)

**Экспорты:**
- `llm` - синглтон FallbackLLM
- `openrouter_client` - async клиент OpenRouter

**Миграция на новую config:**
```python
# Старое
settings.openrouter_api_key

# Новое
settings.openrouter.api_key
settings.openrouter.model
settings.openrouter.temperature
settings.openrouter.max_tokens
```

---

## 🌐 API (FastAPI Routes)

### `api/routes/agent.py` (228 строк после рефакторинга)
**Назначение:** API endpoints для работы с агентами

**Endpoints:**

**1. `POST /agent/analyze-client`** (streaming)
- Rate limit: 5/minute
- Входные данные:
  ```python
  class ClientAnalysisRequest(BaseModel):
      client_name: str
      inn: Optional[str] = ""
      additional_notes: Optional[str] = ""
  ```
- Выходные данные: Server-Sent Events (SSE) stream
- События:
  - `progress` - прогресс выполнения (10%, 25%, 60%, 70%, 85%, 90%)
  - `orchestrator` - поисковые запросы сформированы
  - `data_collected` - данные собраны
  - `report` - отчет готов
  - `result` - финальный результат
  - `error` - ошибка

**2. `GET /agent/thread_history/{thread_id}`**
- Rate limit: 30/minute
- Получить историю диалога из Tarantool
- Возвращает: thread_data или `{"error": "Thread not found"}`

**3. `GET /agent/threads`**
- Rate limit: 20/minute
- Список всех сохраненных диалогов
- Query params: `limit` (default 50)
- Возвращает: список thread_id + metadata

**Удалено после рефакторинга:**
- ❌ `POST /agent/prompt` - не работал, использовал старый workflow

**Rate Limiting:**
- Использует `slowapi.Limiter`
- Константы из `app.config.constants`
- Глобальный лимит: 100/minute, 2000/hour

---

### `api/routes/data.py` (132 строки)
**Назначение:** API для работы с внешними источниками данных

**Endpoints:**

**1. `GET /data/client/infosphere/{inn}`**
- Получить данные из InfoSphere по ИНН
- Проверка по базам: ФССП, ФНС, банкротство, терроризм, и т.д.
- Кешируется: TTL 3600 секунд

**2. `GET /data/client/dadata/{inn}`**
- Получить данные из DaData по ИНН
- Информация о компании: название, адрес, статус, руководство
- Кешируется: TTL 7200 секунд

**3. `GET /data/client/casebook/{inn}`**
- Получить арбитражные дела из Casebook
- Судебные дела компании
- Кешируется: TTL 9600 секунд

**4. `GET /data/client/info/{inn}`**
- Параллельный запрос ко всем 3 источникам
- Возвращает объединенные данные
- Кешируется: TTL 9600 секунд

**5. `POST /data/search/perplexity`**
- Поиск через Perplexity AI
- Входные данные:
  ```python
  class PerplexityRequest(BaseModel):
      inn: str
      search_query: str
      search_recency: str = "month"  # day/week/month/year
  ```
- Валидация ИНН с контрольной суммой

**6. `POST /data/search/tavily`**
- Поиск через Tavily
- Входные данные:
  ```python
  class TavilyRequest(BaseModel):
      inn: str
      search_query: str
      search_depth: str = "basic"  # basic/advanced
      max_results: int = 5
      include_answer: bool = True
      include_domains: Optional[List[str]] = None
      exclude_domains: Optional[List[str]] = None
  ```

**Валидация ИНН:**
- Использует `validate_inn()` из `app.utility.helpers`
- Проверка контрольных сумм для 10-ти и 12-тизначных ИНН
- Возвращает кортеж: `(is_valid: bool, error_message: str)`

---

### `api/routes/utility.py` (545 строк)
**Назначение:** Системные утилиты, мониторинг, управление

**Endpoints:**

**1. `GET /utility/health`**
- Query param: `deep=false` (быстрая) или `deep=true` (глубокая)
- Быстрая проверка: только конфигурация
- Глубокая проверка: реальные запросы к внешним API
- Возвращает:
  ```python
  {
    "status": "healthy" | "degraded",
    "issues": [...],  # если есть проблемы
    "components": {
      "http_client": "healthy",
      "tarantool": "healthy",
      "openrouter": {...},
      "perplexity": {...},
      "tavily": {...},
      "email": {...}
    }
  }
  ```

**2. `GET /utility/metrics`**
- Метрики системы:
  - HTTP клиент: circuit breakers, retry stats
  - Tarantool: кеш hit rate, сохраненные данные
  - External APIs: статусы, latency
- Требует admin права

**3. `GET /utility/circuit-breakers`**
- Статус circuit breakers
- Для каждого бреакера: state (closed/open/half-open), failures, last_failure
- Требует admin права

**4. `POST /utility/circuit-breakers/{service_name}/reset`**
- Сброс circuit breaker для сервиса
- Требует admin права

**5. `POST /utility/cache/clear`**
- Очистка всех кешей (Tarantool + in-memory в клиентах)
- Требует admin права

**6. `GET /utility/cache/stats`**
- Статистика кеширования
- Hit rate, miss rate, размер кеша
- Требует admin права

**7. `GET /utility/logs`**
- Последние логи приложения
- Query params: `lines=100`, `level=info|warning|error`
- Возвращает массив лог-записей
- Требует admin права

**8. `POST /utility/pdf`**
- Генерация PDF отчета
- Входные данные: `{"report_data": {...}, "client_name": str, "inn": str}`
- Возвращает: `FileResponse` с PDF файлом
- Использует `fpdf` библиотеку

**9. `GET /utility/reports`**
- Список всех сохраненных отчетов
- Сканирует директорию `reports/`
- Возвращает: список файлов с метаданными

**10. `GET /utility/reports/{filename}`**
- Скачать отчет
- Возвращает: `FileResponse` (MD или JSON)

**11. `GET /utility/auth/role`**
- Проверить роль текущего пользователя
- Header: `X-Auth-Token`
- Возвращает: `{"role": "admin" | "user", "is_admin": bool}`

**12. `GET /utility/telemetry/spans`**
- OpenTelemetry spans для трейсинга
- Требует admin права

**Авторизация:**
- Использует `app.utility.auth`
- Header: `X-Auth-Token` = ADMIN_TOKEN
- Роли: `admin`, `user`
- Большинство endpoints требуют admin

---

## ⚙️ CONFIG (Централизованная конфигурация)

### `config/config_loader.py` (164 строки)
**Назначение:** Загрузка конфигурации из Vault/Env/YAML

**Класс `ConfigLoader`:**

**Методы:**
1. `load_from_vault(path, mount_point="secret")` - загрузка из HashiCorp Vault
2. `load_from_yaml(file_path)` - загрузка из YAML
3. `clear_cache()` - очистка кеша

**Класс `BaseSettingsWithLoader(BaseSettings)`:**
- Расширяет Pydantic `BaseSettings`
- Добавляет загрузку из Vault/YAML
- Приоритет: Vault > Env > YAML > kwargs > defaults
- Singleton через `get_instance()`

**Cascade Loading:**
```python
# 1. Пытается загрузить из Vault (если VAULT_ENABLED=true)
# 2. Загружает из environment variables
# 3. Загружает из YAML (если указан yaml_group)
# 4. Использует defaults из модели
```

**Пример использования:**
```python
class MySettings(BaseSettingsWithLoader):
    yaml_group = "database"
    vault_path = "secret/app/database"
    
    host: str = "localhost"
    port: int = 5432

settings = MySettings.get_instance()
```

---

### `config/constants.py` (213 строк)
**Назначение:** Все константы приложения в одном месте

**Категории констант:**

**1. Workflow:**
- `WORKFLOW_TIMEOUT_SECONDS = 300`
- `MAX_RETRY_ATTEMPTS = 3`
- `RETRY_DELAY_SECONDS = 2`

**2. HTTP Client:**
- `HTTP_TIMEOUT_SECONDS = 30`
- `HTTP_CONNECT_TIMEOUT_SECONDS = 10`
- `HTTP_MAX_RETRIES = 3`
- `CIRCUIT_BREAKER_FAILURE_THRESHOLD = 5`
- `CIRCUIT_BREAKER_TIMEOUT_SECONDS = 60`

**3. Cache & Storage:**
- `CACHE_DEFAULT_TTL_SECONDS = 3600`
- `CACHE_MAX_SIZE_MB = 500`
- `TARANTOOL_RECONNECT_DELAY_SECONDS = 5`

**4. Pagination:**
- `DEFAULT_PAGE_SIZE = 50`
- `MAX_PAGE_SIZE = 1000`

**5. Content Limits:**
- `MAX_CONTENT_LENGTH = 2500`
- `MAX_SEARCH_RESULTS_PER_INTENT = 10`
- `MAX_CONCURRENT_SEARCHES = 5`

**6. Rate Limiting:**
- `RATE_LIMIT_GLOBAL_PER_MINUTE = 100`
- `RATE_LIMIT_GLOBAL_PER_HOUR = 2000`
- `RATE_LIMIT_ANALYZE_CLIENT_PER_MINUTE = 5`
- `RATE_LIMIT_SEARCH_PER_MINUTE = 30`

**7. Timeouts по сервисам:**
- `DADATA_TIMEOUT_SECONDS = 15`
- `INFOSPHERE_TIMEOUT_SECONDS = 30`
- `CASEBOOK_TIMEOUT_SECONDS = 20`
- `PERPLEXITY_TIMEOUT_SECONDS = 60`
- `TAVILY_TIMEOUT_SECONDS = 45`
- `OPENROUTER_TIMEOUT_SECONDS = 60`
- `SEARCH_TIMEOUT_SECONDS = 60`

**8. Risk Assessment:**
- `RISK_LEVEL_LOW = "low"`
- `RISK_LEVEL_MEDIUM = "medium"`
- `RISK_LEVEL_HIGH = "high"`
- `RISK_LEVEL_CRITICAL = "critical"`
- `RISK_THRESHOLD_LOW = 25`
- `RISK_THRESHOLD_MEDIUM = 50`
- `RISK_THRESHOLD_HIGH = 75`

**9. Tarantool Spaces:**
- `TARANTOOL_SPACE_CACHE = "cache"`
- `TARANTOOL_SPACE_THREADS = "threads"`
- `TARANTOOL_SPACE_PERSISTENT = "persistent"`

**10. File Paths:**
- `REPORTS_DIR = "reports"`
- `LOGS_DIR = "logs"`
- `TEMP_DIR = "temp"`
- `ENV_FILE = ".env"`

**11. Validation Patterns:**
- `INN_PATTERN_10 = r"^\d{10}$"`
- `INN_PATTERN_12 = r"^\d{12}$"`

**12. Logging:**
- `LOG_ROTATION_SIZE_MB = 10`
- `LOG_ROTATION_COUNT = 5`
- `LOG_FORMAT = "%(asctime)s - %(name)s - %(levelname)s - %(message)s"`

**13. Feature Flags:**
- `ENABLE_TELEMETRY = True`
- `ENABLE_COMPRESSION = True`
- `ENABLE_CIRCUIT_BREAKER = True`

**Экспорт:**
```python
from app.config import MAX_CONCURRENT_SEARCHES, SEARCH_TIMEOUT_SECONDS
```

---

### `config/base.py`, `database.py`, `external_api.py`, `security.py`, `services.py`
**Назначение:** Модульные настройки приложения

**Структура:**
- Каждый файл содержит `Pydantic BaseSettings` модели
- Наследуются от `BaseSettingsWithLoader`
- Singleton instances для прямого использования

**`base.py`:**
- `AppBaseSettings` - порты, debug, log level, CORS
- `SchedulerSettings` - фоновые задачи, очистка

**`database.py`:**
- `TarantoolConnectionSettings` - host, port, user, password, pool size
- `MongoConnectionSettings` - MongoDB (для будущего использования)

**`external_api.py`:**
- `HttpBaseSettings` - общие настройки HTTP клиента
- `DadataAPISettings` - API key, URL, cache TTL
- `CasebookAPISettings` - API key, URL
- `InfoSphereAPISettings` - login, password, URL
- `PerplexityAPISettings` - API key, model, cache TTL
- `TavilyAPISettings` - API key, cache TTL
- `OpenRouterAPISettings` - API key, model, temperature, max_tokens

**`security.py`:**
- `SecureSettings` - admin_token, secret_key, JWT, rate limiting, IP whitelist/blacklist

**`services.py`:**
- `QueueSettings` - RabbitMQ host, port, credentials, queues
- `RedisSettings` - Redis connection (для будущего)
- `MailSettings` - SMTP настройки
- `FileStorageSettings` - local/S3
- `LogStorageSettings` - file/external logging
- `GRPCSettings` - gRPC (для будущего)

---

### `config/settings.py` (94 строки)
**Назначение:** Корневая конфигурация, объединяет все модули

**Класс `Settings(BaseSettings)`:**
```python
class Settings(BaseSettings):
    # Общие настройки
    app: AppBaseSettings
    scheduler: SchedulerSettings
    secure: SecureSettings
    http_base: HttpBaseSettings
    
    # Хранилища
    tarantool: TarantoolConnectionSettings
    mongo: MongoConnectionSettings
    redis: RedisSettings
    
    # External APIs
    dadata: DadataAPISettings
    casebook: CasebookAPISettings
    infosphere: InfoSphereAPISettings
    perplexity: PerplexityAPISettings
    tavily: TavilyAPISettings
    openrouter: OpenRouterAPISettings
    
    # Services
    queue: QueueSettings
    mail: MailSettings
    tasks: TasksSettings
    storage: FileStorageSettings
    logging: LogStorageSettings
    grpc: GRPCSettings
```

**Singleton:**
```python
settings = Settings()
```

**Использование:**
```python
from app.config import settings

# Доступ к настройкам
api_key = settings.perplexity.api_key
host = settings.tarantool.host
timeout = settings.http_base.timeout
```

---

### `config/__init__.py`
**Назначение:** Экспорт settings и констант

**Экспорты:**
```python
from app.config.settings import settings
from app.config.constants import *

__all__ = ["settings", "MAX_CONCURRENT_SEARCHES", ...]
```

**Использование:**
```python
# Импорт settings
from app.config import settings

# Импорт констант
from app.config import MAX_CONCURRENT_SEARCHES, SEARCH_TIMEOUT_SECONDS
```

---

## 🎨 FRONTEND (Streamlit UI)

### `frontend/app.py` (1079 строк)
**Назначение:** Веб-интерфейс для работы с системой

**Технологии:**
- Streamlit 1.29+
- Requests для API вызовов
- SSE (Server-Sent Events) для streaming

**Страницы:**
1. **"Запрос агенту"** - анализ клиента
2. **"История"** - список прошлых анализов
3. **"Внешние данные"** - запрос к API напрямую
4. **"Утилиты"** (admin) - системные функции
5. **"Метрики"** (admin) - мониторинг
6. **"Логи"** (admin) - просмотр логов

**Ключевые функции:**

**1. Авторизация:**
- Sidebar: ввод admin token
- Проверка через `/utility/auth/role`
- Хранение в `st.session_state`

**2. Страница "Запрос агенту":**
- Форма:
  - Название клиента (обязательно)
  - ИНН (с валидацией контрольной суммы)
  - Дополнительные заметки
- Streaming анализ:
  - Progress bar
  - Real-time обновления статуса
  - Отображение результатов по мере получения
- События SSE:
  - `progress` → progress bar
  - `orchestrator` → список запросов
  - `data_collected` → успешные источники
  - `report` → risk score, findings
  - `result` → финальный результат
- Отображение отчета:
  - Risk level с цветовой индикацией
  - Findings по категориям
  - Recommendations
  - Citations
  - Сохраненные файлы (ссылки на скачивание)

**3. Страница "История":**
- Список threads из Tarantool
- Для каждого: client_name, inn, created_at
- Клик → детали thread
- Лимит: 50 последних

**4. Страница "Внешние данные":**
- Вкладки: DaData, InfoSphere, Casebook, Perplexity, Tavily
- Прямые запросы к API
- JSON вывод результатов

**5. Админские страницы:**
- **Утилиты:**
  - Health check (quick/deep)
  - Circuit breakers reset
  - Cache clear
  - Generate PDF
- **Метрики:**
  - HTTP client stats
  - Tarantool cache stats
  - Circuit breakers status
- **Логи:**
  - Последние N строк
  - Фильтр по level (info/warning/error)

**CSS Customization:**
- Sidebar всегда видим (исправлено)
- Кастомные цвета для risk levels
- Responsive дизайн

**Валидация ИНН:**
- Использует `validate_inn_frontend()` 
- Fallback: пытается импортировать из `app.utility.helpers`
- Если нет - простая проверка длины

**Request Helper:**
```python
def request_with_retry(url, method="GET", max_retries=3, timeout=30):
    # Retry logic с exponential backoff
    # Обработка ошибок
    # Возвращает Response или None
```

**API Base URL:**
```python
API_BASE_URL = os.getenv("API_BASE_URL", "http://localhost:8000")
```

---

## 📦 SERVICES (Внешние API клиенты)

### `services/http_client.py` (489 строк)
**Назначение:** Универсальный HTTP клиент с resilience patterns

**Класс `AsyncHttpClient` (Singleton):**

**Функционал:**
- **httpx.AsyncClient** - async HTTP клиент
- **Circuit Breaker** - защита от каскадных сбоев
- **Retry с exponential backoff** - повторные попытки
- **Connection pooling** - переиспользование соединений
- **HTTP/2 support** - современный протокол
- **Timeouts** - глобальные и per-request
- **Compression** - gzip/deflate

**Circuit Breaker:**
- Failure threshold: 5 failures
- Timeout: 60 секунд
- States: closed → open → half-open → closed
- Per-service tracking

**Методы:**

**1. `get_instance()` (classmethod)**
- Thread-safe singleton с double-checked locking
- Использует `asyncio.Lock`
- Инициализация один раз

**2. `request(method, url, **kwargs)`**
- Главный метод для HTTP запросов
- Retry logic: max 3 попытки
- Circuit breaker проверка
- Логирование всех запросов

**3. `fetch_all_pages(url, params, max_pages=100)`**
- Автоматическая пагинация
- Параметр `page` в query
- Останавливается при пустом ответе

**4. `get_circuit_breaker_status()`**
- Статус всех circuit breakers
- Для каждого: state, failures, last_failure

**5. `reset_circuit_breaker(service_name)`**
- Принудительный reset

**6. `aclose()` / `close_global()`**
- Graceful shutdown
- Закрывает все соединения

**Конфигурация:**
```python
timeout = httpx.Timeout(
    connect=10.0,
    read=30.0,
    write=10.0,
    pool=5.0
)

limits = httpx.Limits(
    max_connections=50,
    max_keepalive_connections=10,
    keepalive_expiry=30.0
)
```

**Использование:**
```python
client = await AsyncHttpClient.get_instance()
response = await client.request("GET", "https://api.example.com/data")
```

---

### `services/perplexity_client.py` (269 строк)
**Назначение:** Клиент для Perplexity AI API

**Класс `PerplexityClient` (Singleton):**

**Функционал:**
- LangChain OpenAI-compatible интеграция
- In-memory кеширование (TTL 300s)
- Поддержка search_recency_filter
- Citation extraction

**Методы:**

**1. `ask(question, search_recency_filter="month")`**
- Главный метод для поиска
- Recency: day / week / month / year
- Возвращает:
  ```python
  {
    "success": True,
    "content": "...",
    "citations": [...],
    "model": "sonar-pro",
    "cached": False
  }
  ```

**2. `is_configured()`**
- Проверка API key

**3. `healthcheck(timeout_s=8.0)`**
- Проверка доступности
- Тестовый запрос
- Возвращает status + latency

**4. `clear_cache()` / `get_cache_stats()`**
- Управление кешем

**Кеширование:**
- Key: hash(messages + model + temperature + recency)
- TTL: из `settings.perplexity.cache_ttl`
- In-memory dict

**Конфигурация:**
```python
model = settings.perplexity.model  # "sonar-pro"
api_key = settings.perplexity.api_key
cache_ttl = settings.perplexity.cache_ttl
```

**LangChain интеграция:**
```python
from langchain_openai import ChatOpenAI

llm = ChatOpenAI(
    model=self.model,
    api_key=self.api_key,
    base_url=self.BASE_URL,
    temperature=0.1
)
```

---

### `services/tavily_client.py` (278 строк)
**Назначение:** Клиент для Tavily веб-поиска

**Класс `TavilyClient` (Singleton):**

**Функционал:**
- LangChain TavilySearchResults интеграция
- In-memory кеширование (TTL 300s)
- Поддержка search_depth: basic / advanced
- Domain filtering

**Методы:**

**1. `search(query, search_depth="basic", max_results=5, ...)`**
- Главный метод поиска
- Параметры:
  - `search_depth`: basic / advanced / fast / ultra-fast
  - `max_results`: кол-во результатов
  - `include_answer`: bool - включить AI answer
  - `include_raw_content`: bool - полный контент
  - `include_domains`: List[str] - фильтр доменов
  - `exclude_domains`: List[str] - исключить домены
  - `use_cache`: bool - использовать кеш
- Возвращает:
  ```python
  {
    "success": True,
    "answer": "...",
    "results": [
      {
        "title": "...",
        "url": "...",
        "content": "...",
        "snippet": "...",
        "score": 0.95
      }
    ],
    "cached": False
  }
  ```

**2. `search_with_fallback(query, fallback_handler)`**
- Поиск с fallback функцией
- Если Tavily не работает → вызов fallback

**3. `healthcheck(timeout_s=8.0)`**
- Проверка доступности
- Тестовый запрос на "site:example.com"

**Кеширование:**
- Key: hash(query + depth + max_results + domains + ...)
- TTL: из `settings.tavily.cache_ttl`

**Конфигурация:**
```python
api_key = settings.tavily.api_key
cache_ttl = settings.tavily.cache_ttl
```

**LangChain интеграция:**
```python
from langchain_community.tools.tavily_search import TavilySearchResults

tool = TavilySearchResults(
    max_results=max_results,
    include_answer=True,
    include_raw_content=False
)
results = tool.invoke({"query": query})
```

---

### `services/openrouter_client.py` (180 строк)
**Назначение:** Клиент для OpenRouter API (мультимодельный LLM)

**Класс `OpenRouterClient`:**

**Функционал:**
- Доступ к множеству LLM моделей
- Async методы через httpx
- Health check с реальным запросом

**Методы:**

**1. `chat(messages, model=None, temperature=None, max_tokens=None)`**
- Главный метод для chat completion
- Входные данные:
  ```python
  messages = [
    {"role": "system", "content": "You are..."},
    {"role": "user", "content": "Question?"}
  ]
  ```
- Возвращает:
  ```python
  {
    "success": True,
    "content": "Assistant reply...",
    "model": "anthropic/claude-3.5-sonnet",
    "usage": {
      "prompt_tokens": 100,
      "completion_tokens": 200,
      "total_tokens": 300
    }
  }
  ```

**2. `check_status()`**
- Health check
- Тестовый запрос: "Hi"
- Возвращает: available (bool), latency, error

**Конфигурация:**
```python
api_key = settings.openrouter.api_key
model = settings.openrouter.model  # "anthropic/claude-3.5-sonnet"
temperature = settings.openrouter.temperature  # 0.1
max_tokens = settings.openrouter.max_tokens  # 4096
```

**Headers:**
```python
{
  "Authorization": f"Bearer {api_key}",
  "HTTP-Referer": "https://replit.com",
  "X-Title": "Client Analysis Agent"
}
```

**Singleton:**
```python
def get_openrouter_client() -> OpenRouterClient:
    return OpenRouterClient()
```

---

### `services/email_client.py` (189 строк)
**Назначение:** SMTP клиент для отправки email

**Класс `EmailClient` (Singleton):**

**Функционал:**
- Отправка email через SMTP
- TLS шифрование
- Health check (проверка подключения к SMTP)

**Методы:**

**1. `send_email(to, subject, body, html=False)`**
- Отправка email
- Поддержка plain text / HTML
- Возвращает: `{"success": True/False, "message": "..."}`

**2. `check_health(timeout=10)`**
- Проверка SMTP соединения
- Попытка подключения и login
- Возвращает: status, latency, error

**3. `is_configured()`**
- Проверка наличия всех настроек

**Конфигурация:**
```python
smtp_host = settings.mail.smtp_host
smtp_port = settings.mail.smtp_port
smtp_user = settings.mail.smtp_user
smtp_password = settings.mail.smtp_password
use_tls = settings.mail.use_tls
default_from = settings.mail.default_from
```

**Использование:**
```python
client = EmailClient.get_instance()
result = client.send_email(
    to="user@example.com",
    subject="Report Ready",
    body="Your report is ready!"
)
```

---

### `services/fetch_data.py` (128 строк)
**Назначение:** Сбор данных из структурированных API

**Функции (все async):**

**1. `fetch_from_dadata(inn)`**
- Получение данных о компании из DaData
- Cache TTL: 7200 секунд
- Возвращает:
  ```python
  {
    "status": "success",
    "data": {
      "name": {"full_with_opf": "..."},
      "inn": "...",
      "kpp": "...",
      "ogrn": "...",
      "address": {"value": "..."},
      "state": {"status": "ACTIVE"},
      "management": {"name": "..."}
    }
  }
  ```

**2. `fetch_from_infosphere(inn)`**
- Проверка по базам InfoSphere
- Cache TTL: 3600 секунд
- XML запрос/ответ
- Sources: fssp, bankrot, cbr, egrul, fns, fsin, terrorist, etc.
- Возвращает parsed XML as dict

**3. `fetch_from_casebook(inn)`**
- Арбитражные дела из Casebook
- Cache TTL: 9600 секунд
- Автоматическая пагинация (до 100 результатов)
- Возвращает:
  ```python
  {
    "status": "success",
    "data": [
      {
        "caseNumber": "...",
        "courtName": "...",
        "plaintiffName": "...",
        "defendantName": "...",
        "caseDate": "..."
      }
    ]
  }
  ```

**4. `fetch_company_info(inn)`**
- Параллельный сбор из всех 3 источников
- Cache TTL: 9600 секунд
- Использует `asyncio.gather()`
- Валидация ИНН (10 или 12 цифр)
- Возвращает:
  ```python
  {
    "inn": "...",
    "dadata": {...},
    "infosphere": {...},
    "casebook": {...}
  }
  ```

**Кеширование:**
- Использует декоратор `@cache_response(ttl=...)`
- Ключ кеша: hash(function_name + args)
- Хранение в Tarantool

**Конфигурация:**
```python
# DaData
url = settings.dadata.api_url
api_key = settings.dadata.api_key

# InfoSphere
url = settings.infosphere.api_url
login = settings.infosphere.login
password = settings.infosphere.password

# Casebook
url = settings.casebook.api_url
api_key = settings.casebook.api_key
```

---

## 💾 STORAGE

### `storage/tarantool.py` (806 строк)
**Назначение:** Tarantool клиент для кеширования и персистентности

**Класс `TarantoolClient` (Singleton):**

**Функционал:**
- Thread-safe singleton с двойной блокировкой
- In-memory fallback если Tarantool недоступен
- Compression (gzip) для больших данных
- Метрики кеширования
- Batch operations

**Spaces:**
- `cache` - кеш с TTL
- `persistent` - долгосрочное хранение (threads, etc.)

**Ключевые методы:**

**1. Cache operations:**
- `get(key, default=None)` - получить из кеша
- `set(key, value, ttl=3600)` - сохранить с TTL
- `delete(key)` - удалить
- `exists(key)` - проверка существования
- `clear_cache()` - очистка всего кеша

**2. Persistent operations:**
- `get_persistent(key)` - получить persistent данные
- `set_persistent(key, value)` - сохранить persistent
- `delete_persistent(key)` - удалить persistent

**3. Batch operations:**
- `set_many(items: List[Tuple[key, value, ttl]])` - массовое сохранение
- `get_many(keys: List[str])` - массовое чтение

**4. Utility:**
- `get_cache_stats()` - статистика кеша
- `get_persistent_stats()` - статистика persistent
- `flush_all()` - очистка всех spaces
- `is_connected()` - проверка подключения

**5. Special:**
- `save_thread_to_tarantool(thread_id, data)` - async функция для сохранения threads
- `list_threads(limit=50)` - список сохраненных threads

**Compression:**
- Автоматически для данных > 1KB
- Использует gzip level 6
- Сохраняет статистику (bytes_saved_by_compression)

**Метрики (`CacheMetrics`):**
```python
{
  "hits": 1000,
  "misses": 100,
  "hit_rate_percent": 90.91,
  "sets": 150,
  "deletes": 50,
  "compressed_saves": 75,
  "bytes_saved_by_compression": 12345,
  "avg_get_time_ms": 1.5,
  "avg_set_time_ms": 2.3
}
```

**In-memory fallback:**
- Если Tarantool не доступен
- Используется Python dict
- Логируется warning

**Конфигурация:**
```python
host = settings.tarantool.host
port = settings.tarantool.port
user = settings.tarantool.user
password = settings.tarantool.password
```

**Thread Safety:**
- Использует `asyncio.Lock` для синхронизации
- Double-checked locking для инициализации
- ThreadPoolExecutor для sync operations

---

### `storage/init.lua` (42 строки)
**Назначение:** Инициализация Tarantool spaces

**Создаваемые spaces:**

**1. `cache` space:**
```lua
box.schema.space.create('cache', {
    if_not_exists = true
})
box.space.cache:format({
    {name = 'key', type = 'string'},
    {name = 'value', type = 'any'},
    {name = 'ttl', type = 'number'}
})
box.space.cache:create_index('primary', {
    parts = {'key'},
    if_not_exists = true
})
```

**2. `persistent` space:**
```lua
box.schema.space.create('persistent', {
    if_not_exists = true
})
box.space.persistent:format({
    {name = 'key', type = 'string'},
    {name = 'value', type = 'any'}
})
box.space.persistent:create_index('primary', {
    parts = {'key'},
    if_not_exists = true
})
```

**Cleanup функция:**
```lua
function cleanup_expired_cache()
    local now = os.time()
    for _, tuple in box.space.cache:pairs() do
        if tuple.ttl < now then
            box.space.cache:delete(tuple.key)
        end
    end
end
```

**Фоновая задача:**
- Запускается каждые 60 секунд
- Удаляет просроченные записи из cache

---

## 🛠️ UTILITY

### `utility/helpers.py` (119 строк)
**Назначение:** Вспомогательные функции

**Функции:**

**1. `validate_inn(inn: str) -> Tuple[bool, str]`**
- Валидация ИНН с проверкой контрольных сумм
- Поддержка 10-значных (юрлица) и 12-значных (ИП/физлица)
- Возвращает: `(is_valid, error_message)`

**Алгоритм для 10-значного ИНН:**
```python
weights = [2, 4, 10, 3, 5, 9, 4, 6, 8]
check_digit = (sum(int(inn[i]) * weights[i] for i in range(9)) % 11) % 10
```

**Алгоритм для 12-значного ИНН:**
```python
weights1 = [7, 2, 4, 10, 3, 5, 9, 4, 6, 8]
weights2 = [3, 7, 2, 4, 10, 3, 5, 9, 4, 6, 8]
# Проверка двух контрольных цифр
```

**2. `format_inn(inn: str) -> str`**
- Форматирование ИНН для отображения
- Удаляет лишние символы
- Добавляет пробелы для читаемости

**3. `clean_xml_dict(data: Dict) -> Dict`**
- Очистка XML dict от мусора
- Удаление None, пустых строк
- Рекурсивная обработка вложенных структур

---

### `utility/logging_client.py` (344 строки)
**Назначение:** Централизованная система логирования

**Класс `CustomLogger`:**

**Функционал:**
- Rich console output (цветной)
- File logging с ротацией
- Structured logging (JSON)
- Context managers для трейсинга
- Async/sync поддержка

**Методы:**

**1. Базовые:**
- `info(message, **kwargs)`
- `warning(message, **kwargs)`
- `error(message, **kwargs)`
- `debug(message, **kwargs)`
- `critical(message, **kwargs)`

**2. Structured:**
- `structured(level, event_name, **context)` - структурированное логирование
  ```python
  logger.structured("info", "user_login", user_id=123, ip="1.2.3.4")
  ```

**3. Context:**
- `set_context(**kwargs)` - установить контекст
- `clear_context()` - очистить контекст
- `get_context()` - получить текущий контекст

**4. Request context:**
- `set_request_id(request_id)` - для трейсинга запросов
- `get_request_id()` - получить request_id

**5. Context managers:**
- `@logger.trace_operation(operation_name)` - декоратор для трейсинга
- `with logger.operation_context(name):` - контекстный менеджер

**Форматирование:**
```python
"[%(asctime)s] [%(levelname)s] [%(name)s] [%(component)s] %(message)s"
```

**Ротация файлов:**
- Размер: 10 MB
- Количество: 5 файлов
- Имена: `app.log`, `app.log.1`, `app.log.2`, etc.
- Путь: `logs/` директория

**Rich Console:**
- Цветной вывод
- Timestamps
- Thread/Process info
- Exception tracebacks

**Singleton:**
```python
logger = CustomLogger.get_instance()
```

**Использование:**
```python
logger.info("Starting analysis", component="workflow", client_name="ABC")

with logger.operation_context("data_collection"):
    # код
    pass

@logger.trace_operation("process_data")
async def process():
    # код
    pass
```

---

### `utility/cache.py` (96 строк)
**Назначение:** Декоратор для кеширования функций

**Функция `cache_response(ttl=3600)`:**
- Декоратор для кеширования результатов функций
- Работает с async функциями
- Использует TarantoolClient для хранения
- Генерирует ключ: hash(function_name + args + kwargs)

**Использование:**
```python
@cache_response(ttl=7200)
async def fetch_data(inn: str):
    # Дорогая операция
    return data
```

**Логика:**
1. Генерируется cache_key из function_name + аргументов
2. Проверка в кеше
3. Если есть → возврат из кеша
4. Если нет → выполнение функции → сохранение в кеш (TTL)
5. Логирование cache hits/misses

**Cache key:**
```python
key = f"cache:{func.__name__}:{hash_str}"
```

---

### `utility/auth.py` (85 строк)
**Назначение:** Авторизация и роли

**Enum `Role`:**
```python
class Role(str, Enum):
    ADMIN = "admin"
    USER = "user"
```

**Функции:**

**1. `get_current_role(token: Optional[str])`**
- Определяет роль по токену
- Сравнение с ADMIN_TOKEN из env
- Возвращает: `Role.ADMIN` или `Role.USER`

**2. `require_admin(role: Role = Depends(get_current_role))`**
- Dependency для FastAPI
- Требует admin роль
- Raises HTTPException(403) если не admin

**3. `get_admin_token()`**
- Получить ADMIN_TOKEN из settings
- Используется для проверки

**Использование:**
```python
@router.get("/admin")
async def admin_endpoint(role: Role = Depends(require_admin)):
    # Только для админов
    pass
```

**Header:**
```
X-Auth-Token: {ADMIN_TOKEN}
```

---

### `utility/pdf_generator.py` (339 строк)
**Назначение:** Генерация PDF отчетов

**Класс `UTF8PDF(FPDF)`:**
- Расширяет FPDF для поддержки UTF-8
- Добавляет шрифт DejaVu для кириллицы
- Кастомные header/footer

**Функции:**

**1. `normalize_report_for_pdf(report_data)`**
- Нормализует разные форматы отчета
- Поддержка старого и нового формата
- Возвращает единый dict:
  ```python
  {
    "risk_score": 0-100,
    "risk_level": "low"|"medium"|"high"|"critical",
    "summary": "...",
    "findings": [...],
    "recommendations": [...],
    "citations": [...]
  }
  ```

**2. `generate_pdf_report(report_data, client_name, inn, output_path=None)`**
- Генерирует PDF файл
- Разделы:
  - Заголовок (client_name, inn, дата)
  - Risk Assessment (цветной блок)
  - Summary
  - Findings (по категориям)
  - Recommendations
  - Citations
- Цвета для risk levels:
  - low: зеленый (0, 200, 0)
  - medium: желтый (255, 200, 0)
  - high: оранжевый (255, 100, 0)
  - critical: красный (255, 0, 0)
- Возвращает: путь к файлу

**3. `save_pdf_report(report_data, client_name, inn)`**
- Wrapper для generate_pdf_report
- Автоматическое имя файла
- Сохранение в `reports/` директорию

**Шрифт:**
- DejaVuSans.ttf для кириллицы
- Regular + Bold версии
- Fallback на стандартные шрифты если нет

**Размеры:**
- Заголовки: 16pt, Bold
- Подзаголовки: 14pt, Bold
- Текст: 10pt, Regular
- Отступы: 10mm

---

### `utility/telemetry.py` (145 строк)
**Назначение:** OpenTelemetry трейсинг

**Функции:**

**1. `init_telemetry()`**
- Инициализация OpenTelemetry
- Настройка span exporter
- Настройка trace provider

**2. `get_span_exporter()`**
- Получить текущий span exporter
- Для экспорта в мониторинг системы

**3. `get_log_store()`**
- Получить in-memory лог хранилище
- Для endpoint `/utility/logs`

**Трейсинг:**
- Автоматический для FastAPI requests
- Manual spans для важных операций
- Attributes: request_id, component, operation

**Экспорт:**
- ConsoleSpanExporter (по умолчанию)
- Можно заменить на Jaeger/Zipkin

---

## 📋 SCHEMAS

### `schemas/report.py` (52 строки)
**Назначение:** Pydantic модели для отчетов

**Models:**

**1. `ReportMetadata`**
```python
class ReportMetadata(BaseModel):
    client_name: str
    inn: str = ""
    analysis_date: datetime
    data_sources_count: int = 0
    successful_sources: int = 0
```

**2. `RiskAssessment`**
```python
class RiskAssessment(BaseModel):
    score: int = Field(ge=0, le=100)  # 0-100
    level: RiskLevel  # low/medium/high/critical
    factors: List[str] = []
```

**3. `Finding`**
```python
class Finding(BaseModel):
    category: str
    sentiment: SentimentLabel  # positive/neutral/negative
    key_points: str = ""
```

**4. `ClientAnalysisReport` (главная)**
```python
class ClientAnalysisReport(BaseModel):
    metadata: ReportMetadata
    company_info: Dict[str, Any] = {}
    legal_cases_count: int = 0
    risk_assessment: RiskAssessment
    findings: List[Finding] = []
    summary: str = ""
    citations: List[str] = []
    recommendations: List[str] = []
```

**Type Aliases:**
```python
RiskLevel = Literal["low", "medium", "high", "critical", "unknown"]
SentimentLabel = Literal["positive", "neutral", "negative", "unknown"]
```

**Использование:**
```python
# Валидация
report_obj = ClientAnalysisReport.model_validate(report_dict)

# Экспорт в JSON
report_json = report_obj.model_dump(mode="json")
```

---

## 🚀 MAIN

### `main.py` (192 строки)
**Назначение:** Точка входа FastAPI приложения

**Компоненты:**

**1. Lifespan manager:**
```python
@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    - Инициализация Tarantool
    - Инициализация HTTP client
    - Инициализация LLM
    - Инициализация telemetry
    
    yield
    
    # Shutdown
    - Закрытие всех клиентов
```

**2. FastAPI app:**
```python
app = FastAPI(
    title="Multi-Agent Client Analysis System",
    description="...",
    lifespan=lifespan
)
```

**3. Middleware:**
- `RequestIdMiddleware` - генерирует уникальный ID для каждого запроса
- OpenTelemetry instrumentation
- Rate limiting

**4. Rate Limiter:**
```python
limiter = Limiter(
    key_func=get_remote_address,
    default_limits=[
        f"{RATE_LIMIT_GLOBAL_PER_MINUTE}/minute",
        f"{RATE_LIMIT_GLOBAL_PER_HOUR}/hour"
    ],
    storage_uri="memory://"
)
```

**5. Routers:**
- `agent_router` - `/agent/*`
- `data_router` - `/data/*`
- `utility_router` - `/utility/*`

**6. CORS:**
- Настраивается через env: `CORS_ORIGINS`
- По умолчанию: `["*"]`

**7. Main функция:**
```python
async def main():
    config = uvicorn.Config(
        app,
        host="0.0.0.0",
        port=BACKEND_PORT,
        log_level="info"
    )
    server = uvicorn.Server(config)
    await server.serve()

if __name__ == "__main__":
    asyncio.run(main())
```

**Environment Variables:**
- `BACKEND_PORT` (default: 8000)
- `CORS_ORIGINS`
- `ADMIN_TOKEN`
- Все из config (Tarantool, API keys, etc.)

---

## 📦 DEPENDENCIES (pyproject.toml)

**Основные:**
- `python = "^3.11"`
- `fastapi = "^0.109.0"`
- `uvicorn[standard] = "^0.27.0"`
- `httpx = "^0.26.0"`
- `pydantic = "^2.5.0"`
- `pydantic-settings = "^2.1.0"`
- `langgraph = "^0.0.20"`
- `langchain-core = "^0.1.16"`
- `langchain-openai = "^0.0.2"`
- `langchain-community = "^0.0.13"`
- `tarantool = "^1.1.0"`
- `streamlit = "^1.29.0"`
- `requests = "^2.31.0"`
- `xmltodict = "^0.13.0"`
- `msgpack = "^1.0.7"`
- `fpdf2 = "^2.7.0"`
- `opentelemetry-api = "^1.22.0"`
- `opentelemetry-sdk = "^1.22.0"`
- `opentelemetry-instrumentation-fastapi = "^0.43b0"`
- `rich = "^13.7.0"`
- `slowapi = "^0.1.9"`
- `hvac = "^2.1.0"` (HashiCorp Vault)
- `pyyaml = "^6.0.1"`

**Dev:**
- `pytest = "^7.4.3"`
- `pytest-asyncio = "^0.21.1"`
- `ruff = "^0.1.9"`
- `pyright = "^1.1.344"`
- `detect-secrets = "^1.4.0"`
- `black = "^23.12.1"`

---

## 🐳 DOCKER & DEPLOYMENT

### `docker-compose.yml`
**Сервисы:**

**1. `app` (FastAPI)**
- Image: собирается из Dockerfile
- Ports: 8000:8000
- Environment: все API keys + Tarantool/RabbitMQ settings
- Depends on: tarantool, rabbitmq
- Health check: `/utility/health`
- Volumes: `./reports`, `./logs`

**2. `tarantool`**
- Image: `tarantool/tarantool:2.11`
- Ports: 3301:3301 (admin), 3302:3302 (client)
- Init script: `./app/storage/init.lua`
- Health check: `tarantoolctl connect`

**3. `rabbitmq`**
- Image: `rabbitmq:3.13-management-alpine`
- Ports: 5672:5672 (AMQP), 15672:15672 (Management UI)
- Environment: RABBITMQ_DEFAULT_USER, RABBITMQ_DEFAULT_PASS
- Health check: `rabbitmq-diagnostics ping`
- Volume: `rabbitmq_data`

**Volumes:**
- `tarantool_data` - persistent Tarantool data
- `rabbitmq_data` - persistent RabbitMQ data

---

## 📝 ИТОГО

**Архитектура:** Микросервисная, event-driven (LangGraph)  
**Паттерны:** Singleton, Repository (частично), Circuit Breaker, Retry, Cache-Aside  
**Асинхронность:** Полная (asyncio, httpx)  
**Типизация:** Pydantic models + type hints  
**Логирование:** Централизованное, structured  
**Конфигурация:** Модульная, Vault/Env/YAML  
**Кеширование:** Tarantool + in-memory  
**Resilience:** Circuit Breaker, Retry, Timeouts  
**Monitoring:** OpenTelemetry, health checks  
**UI:** Streamlit с SSE streaming  

**Сильные стороны:**
- ✅ Хорошая архитектура (LangGraph workflow)
- ✅ Resilience patterns (Circuit Breaker, Retry)
- ✅ Централизованная конфигурация
- ✅ Структурированное логирование
- ✅ Кеширование с Tarantool
- ✅ Streaming результатов

**Области для улучшения:**
- 🟡 Tarantool spaces не разделены (cache, reports, threads в одном)
- 🟡 RabbitMQ не интегрирован (есть в docker, но не используется)
- 🟡 In-memory кеши в клиентах (дублируют Tarantool)
- 🟡 Streamlit UI базовый (нет компонентов, real-time updates)
- 🟡 Тесты неполные
- 🟡 Нет Repository pattern для Tarantool

**Следующие шаги:** См. `/workspace/DEVELOPMENT_PLAN.md`
