# 🎯 ПЛАН ПО ДОРАБОТКЕ / ИСПРАВЛЕНИЮ ФУНКЦИОНАЛА

**Дата создания:** 2025-12-18  
**Статус:** Рекомендации для дальнейшего развития

---

## ✅ УЖЕ ВЫПОЛНЕНО

### 1. Централизованная конфигурация ✅
- ✅ Реализована система загрузки из Vault/Env/YAML
- ✅ Модульная структура конфигурации
- ✅ Все компоненты мигрированы

### 2. Константы вынесены ✅
- ✅ Создан `app/config/constants.py`
- ✅ Все хардкоды заменены в критических местах

### 3. Streamlit sidebar ✅
- ✅ CSS исправлен, боковая панель отображается
- ✅ Улучшена валидация ИНН

### 4. Rate Limiting ✅
- ✅ Реализован глобальный rate limiting
- ✅ Добавлены лимиты на критичные endpoints

### 5. Удален мертвый код ✅
- ✅ ~900 строк удалено
- ✅ Код стал чище и понятнее

---

## 🔄 В ПРОЦЕССЕ РЕАЛИЗАЦИИ

### 1. Tarantool Storage (частично) ⏳

**Текущий статус:**
- ✅ Tarantool подключен и работает
- ✅ Используется один универсальный space
- ⏳ Нет разделения на cache/reports/threads
- ⏳ Нет TTL для отчетов (1 месяц)

**Что нужно доработать:**

#### Шаг 1: Обновить init.lua
Создать отдельные spaces в `/workspace/app/storage/init.lua`:

```lua
-- Cache space (общий кеш)
box.schema.space.create('cache', {
    if_not_exists = true,
    format = {
        {name = 'key', type = 'string'},
        {name = 'value', type = 'any'},
        {name = 'ttl', type = 'number'},
        {name = 'created_at', type = 'number'}
    }
})
box.space.cache:create_index('primary', {
    parts = {'key'},
    if_not_exists = true
})
box.space.cache:create_index('ttl_idx', {
    parts = {'ttl'},
    if_not_exists = true
})

-- Reports space (отчеты по клиентам)
box.schema.space.create('reports', {
    if_not_exists = true,
    format = {
        {name = 'report_id', type = 'string'},
        {name = 'inn', type = 'string'},
        {name = 'client_name', type = 'string'},
        {name = 'report_data', type = 'any'},
        {name = 'created_at', type = 'number'},
        {name = 'expires_at', type = 'number'}  -- TTL = created_at + 30 days
    }
})
box.space.reports:create_index('primary', {
    parts = {'report_id'},
    if_not_exists = true
})
box.space.reports:create_index('inn_idx', {
    parts = {'inn'},
    if_not_exists = true
})
box.space.reports:create_index('expires_idx', {
    parts = {'expires_at'},
    if_not_exists = true
})

-- Threads space (история диалогов)
box.schema.space.create('threads', {
    if_not_exists = true,
    format = {
        {name = 'thread_id', type = 'string'},
        {name = 'thread_data', type = 'any'},
        {name = 'created_at', type = 'number'},
        {name = 'updated_at', type = 'number'}
    }
})
box.space.threads:create_index('primary', {
    parts = {'thread_id'},
    if_not_exists = true
})

-- Функция очистки просроченных данных
function cleanup_expired()
    local now = os.time()
    
    -- Очистка просроченного кеша
    for _, tuple in box.space.cache:pairs() do
        if tuple.ttl < now then
            box.space.cache:delete(tuple.key)
        end
    end
    
    -- Очистка просроченных отчетов (старше 30 дней)
    for _, tuple in box.space.reports:pairs() do
        if tuple.expires_at < now then
            box.space.reports:delete(tuple.report_id)
        end
    end
    
    return true
end

-- Запуск очистки каждый час
if box.info.ro == false then
    require('fiber').create(function()
        while true do
            pcall(cleanup_expired)
            require('fiber').sleep(3600)  -- 1 час
        end
    end)
end
```

#### Шаг 2: Создать Repository pattern

**Файл:** `/workspace/app/storage/repositories/cache_repository.py`
```python
from typing import Any, Optional
from app.storage.tarantool import TarantoolClient

class CacheRepository:
    def __init__(self, client: TarantoolClient):
        self.client = client
        self.space = "cache"
    
    async def get(self, key: str) -> Optional[Any]:
        # Реализация get из cache space
        pass
    
    async def set(self, key: str, value: Any, ttl: int):
        # Реализация set в cache space
        pass
```

**Файл:** `/workspace/app/storage/repositories/reports_repository.py`
```python
import time
from typing import Any, Optional, List
from app.storage.tarantool import TarantoolClient

REPORT_TTL_DAYS = 30
REPORT_TTL_SECONDS = REPORT_TTL_DAYS * 24 * 60 * 60

class ReportsRepository:
    def __init__(self, client: TarantoolClient):
        self.client = client
        self.space = "reports"
    
    async def create_report(
        self, inn: str, client_name: str, report_data: dict
    ) -> str:
        """Создать новый отчет с TTL 30 дней"""
        import uuid
        report_id = str(uuid.uuid4())
        now = time.time()
        expires_at = now + REPORT_TTL_SECONDS
        
        # Сохранить в Tarantool
        # ...
        return report_id
    
    async def get_report_by_id(self, report_id: str) -> Optional[dict]:
        """Получить отчет по ID"""
        pass
    
    async def get_reports_by_inn(self, inn: str) -> List[dict]:
        """Получить все отчеты по ИНН"""
        pass
    
    async def delete_expired_reports(self):
        """Удалить просроченные отчеты"""
        pass
```

**Файл:** `/workspace/app/storage/repositories/threads_repository.py`
```python
from typing import Any, Optional, List
from app.storage.tarantool import TarantoolClient

class ThreadsRepository:
    def __init__(self, client: TarantoolClient):
        self.client = client
        self.space = "threads"
    
    async def save_thread(self, thread_id: str, thread_data: dict):
        """Сохранить или обновить диалог"""
        pass
    
    async def get_thread(self, thread_id: str) -> Optional[dict]:
        """Получить диалог по ID"""
        pass
    
    async def list_threads(self, limit: int = 50) -> List[dict]:
        """Получить список диалогов"""
        pass
```

---

### 2. Оптимизация workflow агента ⏳

**Текущие проблемы:**
- Все шаги выполняются последовательно
- Нет раннего выхода при ошибках
- Нет кеширования промежуточных результатов

**План оптимизации:**

#### Вариант 1: Разделить на подэтапы
```python
# Файл: app/agents/client_workflow.py

# Добавить стадии:
STAGE_QUICK_CHECK = "quick_check"  # Быстрая проверка ИНН (DaData)
STAGE_DEEP_CHECK = "deep_check"   # Глубокая проверка (InfoSphere, Casebook)
STAGE_WEB_SEARCH = "web_search"   # Веб-поиск (Perplexity, Tavily)

# Раннее прерывание:
if quick_check_failed:
    return early_result  # Не тратить время на остальное
```

#### Вариант 2: Кеширование промежуточных результатов
```python
# Кешировать результаты каждого источника
@cache_response(ttl=7200)
async def fetch_dadata(inn):
    ...

# При повторном запросе - брать из кеша
```

#### Вариант 3: Умная параллелизация
```python
# Группа 1: Критичные источники (выполнять всегда)
critical_sources = [fetch_dadata, fetch_infosphere]

# Группа 2: Дополнительные источники (выполнять только если критичные ок)
additional_sources = [fetch_casebook, fetch_perplexity, fetch_tavily]

# Выполнять группами
critical_results = await asyncio.gather(*critical_sources)
if all_ok(critical_results):
    additional_results = await asyncio.gather(*additional_sources)
```

---

### 3. Оптимизация внешних запросов ⏳

**Текущие проблемы:**
- Нет connection pooling для httpx
- Нет батчинга запросов
- Нет адаптивных таймаутов

**План оптимизации:**

#### Connection Pooling (уже частично реализовано)
```python
# app/services/http_client.py - улучшить конфигурацию

limits = httpx.Limits(
    max_connections=100,     # Увеличить
    max_keepalive_connections=20,
    keepalive_expiry=30.0
)
```

#### Batching для Casebook
```python
# Если нужно получить данные по нескольким ИНН:
async def fetch_multiple_inns(inns: List[str]):
    # Вместо N запросов - сделать 1 батчевый запрос
    # (если API поддерживает)
    pass
```

#### Request Coalescing
```python
# Если два запроса идут за одними данными одновременно:
_pending_requests = {}

async def fetch_with_coalescing(key, fetch_fn):
    if key in _pending_requests:
        return await _pending_requests[key]  # Ждем результата первого
    
    task = asyncio.create_task(fetch_fn())
    _pending_requests[key] = task
    try:
        return await task
    finally:
        del _pending_requests[key]
```

---

### 4. RabbitMQ + FastStream интеграция ⏳

**Текущий статус:**
- ✅ RabbitMQ добавлен в docker-compose
- ✅ QueueSettings созданы
- ⏳ FastStream не интегрирован
- ⏳ Очереди не используются

**План интеграции:**

#### Шаг 1: Установить FastStream
```bash
poetry add faststream[rabbit]
```

#### Шаг 2: Создать broker
**Файл:** `/workspace/app/queue/broker.py`
```python
from faststream import FastStream
from faststream.rabbit import RabbitBroker
from app.config import settings

broker = RabbitBroker(
    host=settings.queue.host,
    port=settings.queue.port,
    login=settings.queue.user,
    password=settings.queue.password,
    virtualhost=settings.queue.vhost,
)

app = FastStream(broker)
```

#### Шаг 3: Создать publishers
**Файл:** `/workspace/app/queue/publishers.py`
```python
from app.queue.broker import broker

async def publish_analysis_request(inn: str, client_name: str, notes: str):
    """Опубликовать задачу на анализ клиента"""
    await broker.publish(
        {
            "inn": inn,
            "client_name": client_name,
            "notes": notes,
            "timestamp": time.time(),
        },
        queue="analysis.client",
    )
```

#### Шаг 4: Создать subscribers
**Файл:** `/workspace/app/queue/subscribers.py`
```python
from app.queue.broker import broker, app
from app.agents.client_workflow import run_client_analysis_streaming

@broker.subscriber("analysis.client")
async def handle_client_analysis(data: dict):
    """Обработать задачу анализа клиента"""
    inn = data["inn"]
    client_name = data["client_name"]
    notes = data.get("notes", "")
    
    # Запустить анализ
    async for chunk in run_client_analysis_streaming(client_name, inn, notes):
        # Сохранить промежуточные результаты
        pass
    
    # Сохранить финальный результат в reports space
```

#### Шаг 5: Обновить API endpoint
```python
# app/api/routes/agent.py

@agent_router.post("/analyze-client")
async def analyze_client(request: ClientAnalysisRequest):
    """Создать задачу на анализ клиента (async через очередь)"""
    
    # Создать task_id
    task_id = str(uuid.uuid4())
    
    # Опубликовать в очередь
    await publish_analysis_request(
        inn=request.inn,
        client_name=request.client_name,
        notes=request.additional_notes,
    )
    
    return {
        "status": "queued",
        "task_id": task_id,
        "message": "Задача добавлена в очередь"
    }

@agent_router.get("/task/{task_id}")
async def get_task_status(task_id: str):
    """Проверить статус задачи"""
    # Получить из reports или из очереди статусов
    pass
```

---

## 🎨 УЛУЧШЕНИЯ STREAMLIT UI

### Приоритетные улучшения:

#### 1. Компонентная архитектура
**Создать:** `/workspace/app/frontend/components/`
```
components/
├── __init__.py
├── sidebar.py         # Боковая панель
├── analysis_form.py   # Форма анализа
├── history_view.py    # Просмотр истории
└── metrics_view.py    # Метрики и графики
```

#### 2. Real-time обновления
```python
# Использовать st.empty() для обновления в реальном времени
placeholder = st.empty()

async for chunk in analysis_stream:
    placeholder.markdown(chunk)  # Обновлять на лету
```

#### 3. История с фильтрами
```python
# Добавить фильтры:
- По дате
- По ИНН
- По клиенту
- По риску (высокий/средний/низкий)

# Пагинация:
page = st.number_input("Страница", min_value=1, value=1)
limit = 10
offset = (page - 1) * limit
```

#### 4. Просмотр сохраненных отчетов
```python
# Список отчетов
reports = get_reports_by_inn(inn)

for report in reports:
    with st.expander(f"Отчет от {report['created_at']}"):
        st.json(report['data'])
        st.download_button("Скачать PDF", data=report['pdf'])
```

#### 5. Сравнение компаний
```python
# Выбрать 2 компании
company1 = st.selectbox("Компания 1", companies)
company2 = st.selectbox("Компания 2", companies)

# Показать сравнение
col1, col2 = st.columns(2)
with col1:
    show_company_data(company1)
with col2:
    show_company_data(company2)
```

#### 6. UX улучшения
- ✨ Loading states (спиннеры)
- ⚠️ Error boundaries (обработка ошибок)
- 🔔 Toast notifications
- 🧭 Breadcrumbs (навигация)
- 🌙 Dark/Light theme toggle
- 📱 Responsive design

---

## 🔍 МОНИТОРИНГ И ЛОГИРОВАНИЕ

### Добавить (опционально):

#### 1. Prometheus метрики
```python
# app/utility/metrics.py
from prometheus_client import Counter, Histogram

api_requests = Counter('api_requests_total', 'Total API requests')
request_duration = Histogram('request_duration_seconds', 'Request duration')
```

#### 2. Grafana дашборды
- API requests per minute
- Response times
- Error rates
- Cache hit rates
- Queue lengths

#### 3. Structured logging
Уже реализовано через `logger.structured()`, можно добавить:
- JSON output для ELK stack
- Трейсинг через OpenTelemetry (уже частично)
- Алерты в Telegram/Slack

---

## 📊 ПРИОРИТЕТЫ

### 🔴 Высокий (сделать в первую очередь)
1. ✅ Завершить миграцию на новую config (СДЕЛАНО)
2. **Tarantool spaces + Repository pattern** (архитектура)
3. **RabbitMQ + FastStream** (async обработка)

### 🟡 Средний (можно отложить)
4. Оптимизация workflow агента
5. Streamlit компоненты и UX
6. Request coalescing и батчинг

### 🟢 Низкий (nice to have)
7. Prometheus + Grafana
8. API versioning
9. Сравнение компаний в UI

---

## 🧪 ТЕСТИРОВАНИЕ

### Что нужно протестировать:

#### Unit Tests
- [ ] Config loader (Vault/Env/YAML)
- [ ] Валидация ИНН (контрольные суммы)
- [ ] Repository pattern
- [ ] Кеширование

#### Integration Tests
- [ ] API endpoints
- [ ] RabbitMQ pub/sub
- [ ] Tarantool spaces
- [ ] External API clients

#### E2E Tests
- [ ] Полный workflow анализа клиента
- [ ] Streamlit UI (Playwright)

---

## 📝 ДОКУМЕНТАЦИЯ

### Что нужно документировать:

#### 1. Архитектура
- [ ] ADR (Architecture Decision Records)
- [ ] Диаграммы компонентов
- [ ] Схемы данных

#### 2. API
- [ ] OpenAPI спецификация
- [ ] Примеры запросов
- [ ] Rate limiting правила

#### 3. Deployment
- [ ] Docker Compose setup
- [ ] Environment variables
- [ ] Vault configuration

#### 4. Troubleshooting
- [ ] Частые ошибки
- [ ] Логи и мониторинг
- [ ] Контакты для поддержки

---

## 🚀 ROADMAP

### Q1 2025
- ✅ Централизованная конфигурация
- ✅ Удаление мертвого кода
- 🔄 Tarantool spaces (в процессе)
- 🔄 RabbitMQ интеграция (в процессе)

### Q2 2025
- Оптимизация workflow
- Streamlit улучшения
- Полное тестовое покрытие (>80%)

### Q3 2025
- Мониторинг (Prometheus + Grafana)
- API versioning
- Performance туning

---

**Следующий шаг:** Выбрать задачу из раздела "Высокий приоритет" и начать реализацию.
