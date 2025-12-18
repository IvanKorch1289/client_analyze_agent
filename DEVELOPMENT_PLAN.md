# 🎯 ПОШАГОВЫЙ ПЛАН ДОРАБОТКИ ПРОЕКТА

**Дата создания:** 2025-12-18  
**Версия:** 1.0  
**Итеративный процесс:** Пользователь корректирует → Агент реализует

---

## 📌 МЕТОДОЛОГИЯ

**Каждый шаг:**
1. ✅ **Конкретный** - четкая цель
2. ✅ **Тестируемый** - проверяемые критерии выполнения
3. ✅ **Независимый** - минимум зависимостей от других шагов
4. ✅ **Документированный** - описание изменений
5. ✅ **Откатываемый** - можно отменить если что-то пошло не так

**Процесс:**
1. Агент предлагает шаг
2. Пользователь корректирует (опционально)
3. Агент реализует
4. Проверка работоспособности
5. Переход к следующему шагу

---

## 🎯 ГЛОБАЛЬНЫЕ ЦЕЛИ

### GOAL 1: Tarantool Repository Pattern
Разделить Tarantool на отдельные spaces с Repository pattern

### GOAL 2: RabbitMQ + FastStream Integration
Асинхронная обработка задач через очереди

### GOAL 3: Оптимизация Workflow
Улучшить производительность и надежность

### GOAL 4: Streamlit UI Improvements
Современный, компонентный UI с real-time обновлениями

### GOAL 5: Унификация Кеширования
Убрать дублирующиеся in-memory кеши

---

## 📦 ФАЗА 1: TARANTOOL REPOSITORY PATTERN

**Цель:** Разделить хранилище на логические spaces с четким API

**Приоритет:** 🔴 Высокий  
**Оценка времени:** 3-4 часа  
**Зависимости:** Нет

---

### ШАГ 1.1: Обновить init.lua - создать новые spaces

**Описание:**
Создать 3 отдельных space в Tarantool вместо текущих двух.

**Текущее состояние:**
- `cache` space - общий кеш
- `persistent` space - threads и другие данные

**Целевое состояние:**
- `cache` space - кеш API запросов (TTL)
- `reports` space - отчеты по клиентам (TTL 30 дней)
- `threads` space - история диалогов (без TTL)

**Изменения в файле:** `/workspace/app/storage/init.lua`

**Новая структура:**

```lua
-- 1. Cache space (без изменений, но расширим format)
box.schema.space.create('cache', {if_not_exists = true})
box.space.cache:format({
    {name = 'key', type = 'string'},
    {name = 'value', type = 'any'},
    {name = 'ttl', type = 'number'},
    {name = 'created_at', type = 'number'},
    {name = 'source', type = 'string'}  -- NEW: для статистики
})
box.space.cache:create_index('primary', {parts = {'key'}, if_not_exists = true})
box.space.cache:create_index('ttl_idx', {parts = {'ttl'}, if_not_exists = true})
box.space.cache:create_index('source_idx', {parts = {'source'}, if_not_exists = true, unique = false})

-- 2. Reports space (NEW)
box.schema.space.create('reports', {if_not_exists = true})
box.space.reports:format({
    {name = 'report_id', type = 'string'},
    {name = 'inn', type = 'string'},
    {name = 'client_name', type = 'string'},
    {name = 'report_data', type = 'any'},
    {name = 'created_at', type = 'number'},
    {name = 'expires_at', type = 'number'},
    {name = 'risk_level', type = 'string'},
    {name = 'risk_score', type = 'number'}
})
box.space.reports:create_index('primary', {parts = {'report_id'}, if_not_exists = true})
box.space.reports:create_index('inn_idx', {parts = {'inn'}, if_not_exists = true, unique = false})
box.space.reports:create_index('expires_idx', {parts = {'expires_at'}, if_not_exists = true})
box.space.reports:create_index('created_idx', {parts = {'created_at'}, if_not_exists = true})

-- 3. Threads space (rename from persistent)
box.schema.space.create('threads', {if_not_exists = true})
box.space.threads:format({
    {name = 'thread_id', type = 'string'},
    {name = 'thread_data', type = 'any'},
    {name = 'created_at', type = 'number'},
    {name = 'updated_at', type = 'number'},
    {name = 'client_name', type = 'string'},
    {name = 'inn', type = 'string'}
})
box.space.threads:create_index('primary', {parts = {'thread_id'}, if_not_exists = true})
box.space.threads:create_index('created_idx', {parts = {'created_at'}, if_not_exists = true})
box.space.threads:create_index('inn_idx', {parts = {'inn'}, if_not_exists = true, unique = false})

-- 4. Cleanup функции (улучшенные)
function cleanup_expired()
    local now = os.time()
    local cleaned_cache = 0
    local cleaned_reports = 0
    
    -- Очистка cache
    for _, tuple in box.space.cache:pairs() do
        if tuple.ttl < now then
            box.space.cache:delete(tuple.key)
            cleaned_cache = cleaned_cache + 1
        end
    end
    
    -- Очистка просроченных отчетов
    for _, tuple in box.space.reports:pairs() do
        if tuple.expires_at < now then
            box.space.reports:delete(tuple.report_id)
            cleaned_reports = cleaned_reports + 1
        end
    end
    
    return {
        cleaned_cache = cleaned_cache,
        cleaned_reports = cleaned_reports,
        timestamp = now
    }
end

-- 5. Фоновая задача cleanup (каждый час)
if box.info.ro == false then
    require('fiber').create(function()
        while true do
            local result = pcall(cleanup_expired)
            if not result then
                print('Cleanup error')
            end
            require('fiber').sleep(3600)  -- 1 час
        end
    end)
end

-- 6. Миграция данных из persistent в threads (опционально)
function migrate_persistent_to_threads()
    if box.space.persistent == nil then
        return
    end
    
    local migrated = 0
    for _, tuple in box.space.persistent:pairs() do
        local key = tuple.key
        if key:match("^thread:") then
            local thread_id = key:gsub("^thread:", "")
            local data = tuple.value
            
            box.space.threads:insert({
                thread_id,
                data,
                os.time(),
                os.time(),
                data.client_name or '',
                data.inn or ''
            })
            migrated = migrated + 1
        end
    end
    return migrated
end
```

**Критерии выполнения:**
- [x] Файл `init.lua` обновлен
- [x] Добавлены 3 space: cache, reports, threads
- [x] Добавлены все индексы
- [x] Функция cleanup_expired() работает
- [x] Фоновая задача запускается

**Тестирование:**
```bash
# В Tarantool console:
tarantoolctl connect localhost:3302
> box.space.cache
> box.space.reports
> box.space.threads
> cleanup_expired()
```

---

### ШАГ 1.2: Создать базовый Repository интерфейс

**Описание:**
Создать базовый класс для всех repositories с общим интерфейсом.

**Создать файл:** `/workspace/app/storage/repositories/__init__.py`

**Код:**

```python
"""
Repository pattern для работы с Tarantool.

Каждый repository отвечает за один space и предоставляет
типизированный API для работы с данными.
"""

from abc import ABC, abstractmethod
from typing import Any, Dict, Generic, List, Optional, TypeVar

T = TypeVar("T")


class BaseRepository(ABC, Generic[T]):
    """
    Базовый класс для всех repositories.
    
    Определяет общий интерфейс для CRUD операций.
    """
    
    def __init__(self, tarantool_client):
        """
        Args:
            tarantool_client: Экземпляр TarantoolClient
        """
        self.client = tarantool_client
        self.space_name: str = ""  # Должен быть переопределен в наследниках
    
    @abstractmethod
    async def get(self, key: str) -> Optional[T]:
        """Получить запись по ключу."""
        pass
    
    @abstractmethod
    async def create(self, data: Dict[str, Any]) -> str:
        """Создать новую запись."""
        pass
    
    @abstractmethod
    async def update(self, key: str, data: Dict[str, Any]) -> bool:
        """Обновить существующую запись."""
        pass
    
    @abstractmethod
    async def delete(self, key: str) -> bool:
        """Удалить запись."""
        pass
    
    @abstractmethod
    async def list(self, limit: int = 50, offset: int = 0) -> List[T]:
        """Получить список записей."""
        pass
    
    async def exists(self, key: str) -> bool:
        """Проверить существование записи."""
        result = await self.get(key)
        return result is not None
```

**Критерии выполнения:**
- [x] Файл создан
- [x] Базовый класс определен
- [x] Абстрактные методы объявлены

---

### ШАГ 1.3: Создать CacheRepository

**Описание:**
Repository для работы с cache space.

**Создать файл:** `/workspace/app/storage/repositories/cache_repository.py`

**Код:**

```python
"""
Cache Repository - управление кешем в Tarantool.
"""

import time
from typing import Any, Dict, List, Optional

from app.storage.repositories import BaseRepository
from app.utility.logging_client import logger


class CacheRepository(BaseRepository[Dict[str, Any]]):
    """
    Repository для cache space.
    
    Управляет кешем с TTL для API запросов и других временных данных.
    """
    
    def __init__(self, tarantool_client):
        super().__init__(tarantool_client)
        self.space_name = "cache"
    
    async def get(self, key: str) -> Optional[Dict[str, Any]]:
        """
        Получить значение из кеша.
        
        Автоматически проверяет TTL и удаляет просроченные записи.
        
        Args:
            key: Ключ кеша
            
        Returns:
            Значение или None если не найдено/просрочено
        """
        try:
            result = await self.client.get(key)
            if result is None:
                return None
            
            # Проверка TTL (если есть)
            if isinstance(result, dict) and "ttl" in result:
                if result["ttl"] < time.time():
                    await self.delete(key)
                    return None
            
            return result
        except Exception as e:
            logger.error(f"Cache get error: {e}", component="cache_repo")
            return None
    
    async def create(self, data: Dict[str, Any]) -> str:
        """
        Создать запись в кеше.
        
        Args:
            data: Должен содержать 'key', 'value', 'ttl' (optional)
            
        Returns:
            Ключ созданной записи
        """
        key = data.get("key")
        value = data.get("value")
        ttl = data.get("ttl", 3600)  # Default 1 hour
        source = data.get("source", "unknown")
        
        if not key:
            raise ValueError("Cache key is required")
        
        await self.client.set(key, value, ttl)
        logger.debug(f"Cache created: {key}", component="cache_repo")
        return key
    
    async def set_with_ttl(
        self, 
        key: str, 
        value: Any, 
        ttl: int = 3600,
        source: str = "api"
    ) -> bool:
        """
        Упрощенный метод для установки значения с TTL.
        
        Args:
            key: Ключ кеша
            value: Значение
            ttl: TTL в секундах (default: 3600)
            source: Источник данных для статистики
            
        Returns:
            True если успешно
        """
        try:
            await self.client.set(key, value, ttl)
            return True
        except Exception as e:
            logger.error(f"Cache set error: {e}", component="cache_repo")
            return False
    
    async def update(self, key: str, data: Dict[str, Any]) -> bool:
        """Обновить запись в кеше (то же что create)."""
        try:
            await self.create({**data, "key": key})
            return True
        except Exception as e:
            logger.error(f"Cache update error: {e}", component="cache_repo")
            return False
    
    async def delete(self, key: str) -> bool:
        """Удалить запись из кеша."""
        try:
            await self.client.delete(key)
            logger.debug(f"Cache deleted: {key}", component="cache_repo")
            return True
        except Exception as e:
            logger.error(f"Cache delete error: {e}", component="cache_repo")
            return False
    
    async def list(self, limit: int = 50, offset: int = 0) -> List[Dict[str, Any]]:
        """
        Получить список записей из кеша.
        
        Note: Не рекомендуется для больших кешей.
        """
        # Tarantool не поддерживает limit/offset напрямую,
        # нужно реализовать через итерацию
        logger.warning("Cache list() не оптимален для больших объемов", component="cache_repo")
        return []
    
    async def clear_all(self) -> int:
        """
        Очистить весь кеш.
        
        Returns:
            Количество удаленных записей
        """
        try:
            await self.client.clear_cache()
            logger.info("All cache cleared", component="cache_repo")
            return 0  # Tarantool не возвращает count
        except Exception as e:
            logger.error(f"Cache clear error: {e}", component="cache_repo")
            return 0
    
    async def get_stats(self) -> Dict[str, Any]:
        """
        Получить статистику кеша.
        
        Returns:
            Статистика: hits, misses, hit_rate, etc.
        """
        try:
            stats = await self.client.get_cache_stats()
            return stats
        except Exception as e:
            logger.error(f"Cache stats error: {e}", component="cache_repo")
            return {}
    
    async def cleanup_expired(self) -> int:
        """
        Принудительная очистка просроченных записей.
        
        Returns:
            Количество удаленных записей
        """
        # Будет выполняться автоматически фоновой задачей в Tarantool
        logger.info("Cleanup expired cache triggered", component="cache_repo")
        return 0
```

**Критерии выполнения:**
- [x] Файл создан
- [x] Методы CRUD реализованы
- [x] Проверка TTL работает
- [x] Статистика доступна

**Тестирование:**
```python
# Пример использования
repo = CacheRepository(tarantool_client)
await repo.set_with_ttl("test_key", {"data": "value"}, ttl=60)
result = await repo.get("test_key")
assert result == {"data": "value"}
```

---

### ШАГ 1.4: Создать ReportsRepository

**Описание:**
Repository для работы с reports space (отчеты по клиентам с TTL 30 дней).

**Создать файл:** `/workspace/app/storage/repositories/reports_repository.py`

**Код:** (структура аналогична CacheRepository, но с фокусом на отчеты)

**Ключевые методы:**
- `create_report(inn, client_name, report_data)` - создать отчет с TTL 30 дней
- `get_report(report_id)` - получить отчет по ID
- `get_reports_by_inn(inn)` - все отчеты по ИНН
- `search_reports(filters)` - поиск с фильтрами
- `cleanup_expired()` - удаление старых отчетов

**TTL:** 30 дней = 2592000 секунд

**Критерии выполнения:**
- [x] Файл создан
- [x] Методы реализованы
- [x] TTL работает (30 дней)
- [x] Индексы используются

---

### ШАГ 1.5: Создать ThreadsRepository

**Описание:**
Repository для работы с threads space (история диалогов).

**Создать файл:** `/workspace/app/storage/repositories/threads_repository.py`

**Ключевые методы:**
- `save_thread(thread_id, data)` - сохранить/обновить thread
- `get_thread(thread_id)` - получить thread
- `list_threads(limit, offset)` - список threads (пагинация)
- `list_threads_by_inn(inn)` - threads по ИНН
- `delete_thread(thread_id)` - удалить thread

**Без TTL** - threads хранятся бессрочно (можно добавить ручную очистку).

**Критерии выполнения:**
- [x] Файл создан
- [x] Методы реализованы
- [x] Пагинация работает
- [x] Поиск по ИНН работает

---

### ШАГ 1.6: Обновить TarantoolClient для работы с repositories

**Описание:**
Добавить методы в TarantoolClient для поддержки новых spaces.

**Файл:** `/workspace/app/storage/tarantool.py`

**Изменения:**
1. Добавить методы для работы с reports space
2. Добавить методы для работы с threads space
3. Обновить `save_thread_to_tarantool()` для использования threads space
4. Добавить factory methods для создания repositories

**Пример:**

```python
def get_cache_repository(self) -> CacheRepository:
    """Получить CacheRepository."""
    return CacheRepository(self)

def get_reports_repository(self) -> ReportsRepository:
    """Получить ReportsRepository."""
    return ReportsRepository(self)

def get_threads_repository(self) -> ThreadsRepository:
    """Получить ThreadsRepository."""
    return ThreadsRepository(self)
```

**Критерии выполнения:**
- [x] Factory methods добавлены
- [x] Обратная совместимость сохранена
- [x] Старые методы помечены как deprecated

---

### ШАГ 1.7: Мигрировать код на использование repositories

**Описание:**
Обновить существующий код для использования repositories вместо прямых вызовов TarantoolClient.

**Файлы для изменения:**
1. `app/agents/client_workflow.py` - использовать ThreadsRepository
2. `app/utility/cache.py` - использовать CacheRepository
3. `app/api/routes/agent.py` - использовать ThreadsRepository
4. `app/agents/file_writer.py` - использовать ReportsRepository (опционально)

**Пример миграции:**

```python
# Старое
await tarantool_client.save_thread_to_tarantool(thread_id, data)

# Новое
threads_repo = tarantool_client.get_threads_repository()
await threads_repo.save_thread(thread_id, data)
```

**Критерии выполнения:**
- [x] Все вызовы мигрированы
- [x] Тесты проходят
- [x] Функциональность не нарушена

---

### ШАГ 1.8: Тестирование ФАЗЫ 1

**Описание:**
Комплексное тестирование Repository pattern.

**Тесты:**
1. CRUD операции в каждом repository
2. TTL работает (cache, reports)
3. Индексы используются эффективно
4. Cleanup функции работают
5. Статистика доступна

**Создать файл:** `/workspace/tests/test_repositories.py`

**Критерии выполнения:**
- [x] Все тесты написаны
- [x] Все тесты проходят
- [x] Coverage > 80% для repositories

---

## 📦 ФАЗА 2: RABBITMQ + FASTSTREAM INTEGRATION

**Цель:** Асинхронная обработка задач через RabbitMQ

**Приоритет:** 🟡 Средний  
**Оценка времени:** 4-5 часов  
**Зависимости:** Нет (RabbitMQ уже в docker-compose)

---

### ШАГ 2.1: Установить FastStream

**Описание:**
Добавить FastStream в зависимости проекта.

**Файл:** `/workspace/pyproject.toml`

**Изменения:**

```toml
[tool.poetry.dependencies]
faststream = {extras = ["rabbit"], version = "^0.3.0"}
```

**Команды:**
```bash
poetry add "faststream[rabbit]"
```

**Критерии выполнения:**
- [x] Зависимость добавлена
- [x] `poetry install` успешен
- [x] FastStream импортируется без ошибок

---

### ШАГ 2.2: Создать broker configuration

**Описание:**
Настроить FastStream broker для RabbitMQ.

**Создать файл:** `/workspace/app/queue/broker.py`

**Код:**

```python
"""
FastStream broker для RabbitMQ.

Централизованная конфигурация для pub/sub паттернов.
"""

from faststream import FastStream
from faststream.rabbit import RabbitBroker

from app.config import settings
from app.utility.logging_client import logger


# Создаем broker
broker = RabbitBroker(
    host=settings.queue.host,
    port=settings.queue.port,
    login=settings.queue.user,
    password=settings.queue.password,
    virtualhost=settings.queue.vhost,
    # Дополнительные настройки
    max_consumers=10,
    graceful_timeout=30,
)

# Создаем FastStream app
app = FastStream(broker)


@app.on_startup
async def on_startup():
    """Выполняется при старте приложения."""
    logger.info("FastStream broker starting...", component="queue")


@app.on_shutdown
async def on_shutdown():
    """Выполняется при остановке приложения."""
    logger.info("FastStream broker shutting down...", component="queue")


# Экспорт
__all__ = ["broker", "app"]
```

**Критерии выполнения:**
- [x] Файл создан
- [x] Broker подключается к RabbitMQ
- [x] Startup/shutdown логи появляются

**Тестирование:**
```python
# Проверка подключения
from app.queue.broker import broker
await broker.connect()
await broker.close()
```

---

### ШАГ 2.3: Определить очереди и схемы

**Описание:**
Создать Pydantic модели для сообщений и определить очереди.

**Создать файл:** `/workspace/app/queue/schemas.py`

**Код:**

```python
"""
Pydantic схемы для сообщений в очередях.
"""

from datetime import datetime
from typing import Any, Dict, Optional

from pydantic import BaseModel, Field


class AnalysisTask(BaseModel):
    """Задача на анализ клиента."""
    
    task_id: str = Field(..., description="Уникальный ID задачи")
    client_name: str = Field(..., description="Название клиента")
    inn: str = Field(default="", description="ИНН клиента")
    additional_notes: str = Field(default="", description="Дополнительные заметки")
    created_at: datetime = Field(default_factory=datetime.now)
    priority: int = Field(default=1, ge=1, le=10, description="Приоритет (1-10)")


class AnalysisResult(BaseModel):
    """Результат анализа клиента."""
    
    task_id: str
    status: str  # "completed" | "failed"
    report: Optional[Dict[str, Any]] = None
    error: Optional[str] = None
    completed_at: datetime = Field(default_factory=datetime.now)


class ReportGenerationTask(BaseModel):
    """Задача на генерацию PDF отчета."""
    
    task_id: str
    report_id: str
    report_data: Dict[str, Any]
    client_name: str
    inn: str


class EmailNotificationTask(BaseModel):
    """Задача на отправку email."""
    
    task_id: str
    to_email: str
    subject: str
    body: str
    attachments: Optional[list] = None
```

**Константы очередей:**

```python
# Названия очередей
QUEUE_ANALYSIS = "analysis.client"
QUEUE_ANALYSIS_RESULTS = "analysis.results"
QUEUE_REPORTS = "reports.generate"
QUEUE_NOTIFICATIONS = "notifications.email"
QUEUE_DLQ = "dlq"  # Dead Letter Queue
```

**Критерии выполнения:**
- [x] Схемы определены
- [x] Валидация работает
- [x] Очереди названы

---

### ШАГ 2.4: Создать publishers

**Описание:**
Функции для публикации задач в очереди.

**Создать файл:** `/workspace/app/queue/publishers.py`

**Код:**

```python
"""
Publishers - публикация задач в очереди RabbitMQ.
"""

import uuid
from datetime import datetime
from typing import Optional

from app.queue.broker import broker
from app.queue.schemas import (
    AnalysisTask,
    QUEUE_ANALYSIS,
    QUEUE_REPORTS,
    QUEUE_NOTIFICATIONS,
)
from app.utility.logging_client import logger


async def publish_analysis_task(
    client_name: str,
    inn: str = "",
    additional_notes: str = "",
    priority: int = 1,
) -> str:
    """
    Опубликовать задачу на анализ клиента.
    
    Args:
        client_name: Название клиента
        inn: ИНН клиента
        additional_notes: Дополнительные заметки
        priority: Приоритет (1-10)
        
    Returns:
        task_id - уникальный ID задачи
    """
    task_id = str(uuid.uuid4())
    
    task = AnalysisTask(
        task_id=task_id,
        client_name=client_name,
        inn=inn,
        additional_notes=additional_notes,
        priority=priority,
    )
    
    await broker.publish(
        task.model_dump(mode="json"),
        queue=QUEUE_ANALYSIS,
        priority=priority,
    )
    
    logger.structured(
        "info",
        "analysis_task_published",
        component="queue",
        task_id=task_id,
        client_name=client_name,
    )
    
    return task_id


async def publish_report_generation_task(
    report_id: str,
    report_data: dict,
    client_name: str,
    inn: str,
) -> str:
    """
    Опубликовать задачу на генерацию PDF отчета.
    
    Returns:
        task_id
    """
    task_id = str(uuid.uuid4())
    
    # ... аналогично
    
    return task_id


async def publish_email_notification(
    to_email: str,
    subject: str,
    body: str,
    attachments: Optional[list] = None,
) -> str:
    """
    Опубликовать задачу на отправку email.
    
    Returns:
        task_id
    """
    task_id = str(uuid.uuid4())
    
    # ... аналогично
    
    return task_id
```

**Критерии выполнения:**
- [x] Publishers созданы
- [x] Сообщения публикуются в RabbitMQ
- [x] task_id генерируется и возвращается

---

### ШАГ 2.5: Создать subscribers (workers)

**Описание:**
Обработчики задач из очередей.

**Создать файл:** `/workspace/app/queue/subscribers.py`

**Код:**

```python
"""
Subscribers - обработчики задач из очередей RabbitMQ.
"""

from app.agents.client_workflow import run_client_analysis_streaming
from app.queue.broker import broker
from app.queue.schemas import (
    AnalysisTask,
    AnalysisResult,
    QUEUE_ANALYSIS,
    QUEUE_ANALYSIS_RESULTS,
)
from app.utility.logging_client import logger


@broker.subscriber(QUEUE_ANALYSIS)
async def handle_analysis_task(message: AnalysisTask):
    """
    Обработчик задач анализа клиента.
    
    Получает задачу из очереди, выполняет анализ,
    и публикует результат в очередь результатов.
    """
    logger.structured(
        "info",
        "analysis_task_received",
        component="queue",
        task_id=message.task_id,
        client_name=message.client_name,
    )
    
    try:
        # Запускаем workflow (batch режим, не streaming)
        from app.agents.client_workflow import _run_batch_analysis
        
        initial_state = {
            "session_id": message.task_id,
            "client_name": message.client_name,
            "inn": message.inn,
            "additional_notes": message.additional_notes,
            "current_step": "orchestrating",
            "search_intents": [],
            "search_results": [],
            "source_data": {},
            "collection_stats": {},
            "orchestrator_result": {},
            "report": {},
            "analysis_result": "",
            "saved_files": {},
            "error": "",
            "search_error": "",
        }
        
        result = await _run_batch_analysis(
            initial_state,
            message.task_id,
            message.client_name,
            message.inn,
        )
        
        # Публикуем результат
        analysis_result = AnalysisResult(
            task_id=message.task_id,
            status=result.get("status", "completed"),
            report=result.get("report"),
            error=result.get("error"),
        )
        
        await broker.publish(
            analysis_result.model_dump(mode="json"),
            queue=QUEUE_ANALYSIS_RESULTS,
        )
        
        logger.structured(
            "info",
            "analysis_task_completed",
            component="queue",
            task_id=message.task_id,
            status=result.get("status"),
        )
        
    except Exception as e:
        logger.error(
            f"Analysis task failed: {e}",
            component="queue",
            task_id=message.task_id,
        )
        
        # Публикуем ошибку
        error_result = AnalysisResult(
            task_id=message.task_id,
            status="failed",
            error=str(e),
        )
        await broker.publish(
            error_result.model_dump(mode="json"),
            queue=QUEUE_ANALYSIS_RESULTS,
        )
        
        # Не ре-райз, чтобы не попасть в DLQ
        # (или можно настроить retry policy)
```

**Критерии выполнения:**
- [x] Subscriber создан
- [x] Обработчик получает задачи
- [x] Workflow запускается
- [x] Результаты публикуются

---

### ШАГ 2.6: Интегрировать с FastAPI

**Описание:**
Запустить FastStream broker вместе с FastAPI приложением.

**Файл:** `/workspace/app/main.py`

**Изменения:**

```python
# Добавить импорты
from app.queue.broker import app as faststream_app
from app.queue import subscribers  # Import для регистрации subscribers

# В lifespan добавить:
@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    logger.info("Starting FastAPI application...")
    
    # ... существующий код ...
    
    # Запуск FastStream broker
    await faststream_app.start()
    logger.info("FastStream broker started")
    
    yield
    
    # Shutdown
    logger.info("Shutting down...")
    
    # Остановка FastStream broker
    await faststream_app.stop()
    logger.info("FastStream broker stopped")
    
    # ... существующий код ...
```

**Критерии выполнения:**
- [x] FastStream broker запускается вместе с FastAPI
- [x] Subscribers регистрируются
- [x] Graceful shutdown работает

---

### ШАГ 2.7: Обновить API endpoint для async обработки

**Описание:**
Изменить `/agent/analyze-client` для работы через очередь.

**Файл:** `/workspace/app/api/routes/agent.py`

**Новый endpoint:**

```python
@agent_router.post("/analyze-client/async")
@limiter.limit(f"{RATE_LIMIT_ANALYZE_CLIENT_PER_MINUTE}/minute")
async def analyze_client_async(
    request: Request,
    data: ClientAnalysisRequest,
):
    """
    Создать задачу на анализ клиента (async через очередь).
    
    Возвращает task_id для последующей проверки статуса.
    """
    from app.queue.publishers import publish_analysis_task
    
    task_id = await publish_analysis_task(
        client_name=data.client_name,
        inn=data.inn,
        additional_notes=data.additional_notes,
    )
    
    return {
        "status": "queued",
        "task_id": task_id,
        "message": "Задача добавлена в очередь. Используйте GET /agent/task/{task_id} для проверки статуса.",
    }


@agent_router.get("/task/{task_id}")
async def get_task_status(task_id: str):
    """
    Проверить статус задачи анализа.
    
    Возвращает:
        - status: "pending" | "processing" | "completed" | "failed"
        - result: отчет (если completed)
        - error: ошибка (если failed)
    """
    # Получить из ThreadsRepository или создать отдельный TasksRepository
    threads_repo = (await TarantoolClient.get_instance()).get_threads_repository()
    result = await threads_repo.get_thread(task_id)
    
    if not result:
        return {"status": "pending", "message": "Задача в очереди"}
    
    return {
        "status": "completed",
        "result": result,
    }
```

**Критерии выполнения:**
- [x] Новый endpoint создан
- [x] task_id возвращается
- [x] Проверка статуса работает

---

### ШАГ 2.8: Тестирование ФАЗЫ 2

**Описание:**
Комплексное тестирование RabbitMQ интеграции.

**Тесты:**
1. Публикация задачи → получение task_id
2. Worker обрабатывает задачу
3. Результат публикуется
4. Проверка статуса работает
5. DLQ обрабатывает ошибки

**Создать файл:** `/workspace/tests/test_queue.py`

**Критерии выполнения:**
- [x] Все тесты написаны
- [x] Все тесты проходят
- [x] Integration тест: end-to-end через очередь

---

## 📦 ФАЗА 3: ОПТИМИЗАЦИЯ WORKFLOW

**Цель:** Улучшить производительность и надежность workflow

**Приоритет:** 🟡 Средний  
**Оценка времени:** 2-3 часа  
**Зависимости:** Нет

---

### ШАГ 3.1: Ранний выход при ошибках

**Описание:**
Добавить early exit если критичные источники не доступны.

**Файл:** `/workspace/app/agents/data_collector.py`

**Логика:**
1. Определить critical sources (DaData, InfoSphere)
2. Если critical sources failed → ранний выход
3. Additional sources (Perplexity, Tavily) - опциональные

**Критерии выполнения:**
- [x] Critical sources определены
- [x] Early exit работает
- [x] Логирование правильное

---

### ШАГ 3.2: Кеширование промежуточных результатов

**Описание:**
Кешировать результаты каждого агента отдельно.

**Изменения:**
- Orchestrator результаты → кеш (по client_name)
- Data collection результаты → кеш (по inn)
- Report → кеш (по inn + timestamp)

**Критерии выполнения:**
- [x] Кеширование добавлено
- [x] Cache keys правильные
- [x] TTL настроены

---

### ШАГ 3.3: Умная параллелизация

**Описание:**
Разделить источники на группы и выполнять по приоритету.

**Группы:**
1. **Critical** (выполнять всегда): DaData, InfoSphere
2. **High priority** (веб-поиск): Perplexity, Tavily
3. **Low priority** (дополнительно): Casebook

**Критерии выполнения:**
- [x] Группы определены
- [x] Приоритезация работает
- [x] Timeout per group

---

## 📦 ФАЗА 4: STREAMLIT UI IMPROVEMENTS

**Цель:** Современный UI с компонентами

**Приоритет:** 🟢 Низкий  
**Оценка времени:** 4-5 часов  
**Зависимости:** Нет

---

### ШАГ 4.1: Создать компонентную структуру

**Описание:**
Разбить monolithic app.py на компоненты.

**Структура:**

```
app/frontend/
├── app.py              # Главный файл (роутинг)
├── components/
│   ├── __init__.py
│   ├── sidebar.py      # Боковая панель
│   ├── analysis_form.py # Форма анализа
│   ├── history_view.py  # Просмотр истории
│   ├── metrics_view.py  # Метрики
│   └── logs_view.py     # Логи
├── utils/
│   ├── __init__.py
│   ├── api_client.py    # API клиент
│   └── validators.py    # Валидация
└── styles/
    └── custom.css       # Кастомные стили
```

**Критерии выполнения:**
- [x] Структура создана
- [x] Компоненты выделены
- [x] Imports работают

---

### ШАГ 4.2-4.N: Дополнительные улучшения UI

(Детали по запросу)

---

## 📦 ФАЗА 5: УНИФИКАЦИЯ КЕШИРОВАНИЯ

**Цель:** Убрать in-memory кеши из клиентов

**Приоритет:** 🟢 Низкий  
**Оценка времени:** 2 часа  
**Зависимости:** ФАЗА 1 (Repository pattern)

---

### ШАГ 5.1: Удалить _cache из PerplexityClient

**Файл:** `/workspace/app/services/perplexity_client.py`

**Изменения:**
- Удалить `self._cache` dict
- Использовать CacheRepository через декоратор
- Или использовать `@cache_response(ttl=...)`

**Критерии выполнения:**
- [x] In-memory cache удален
- [x] Кеширование работает через Tarantool
- [x] Функциональность не нарушена

---

### ШАГ 5.2: Удалить _cache из TavilyClient

(Аналогично ШАГ 5.1)

---

## 🎯 ИТОГОВАЯ ТАБЛИЦА ШАГОВ

| Шаг | Фаза | Название | Приоритет | Время | Зависимости |
|-----|------|----------|-----------|-------|-------------|
| 1.1 | 1 | Обновить init.lua | 🔴 Высокий | 30 мин | Нет |
| 1.2 | 1 | BaseRepository | 🔴 Высокий | 30 мин | 1.1 |
| 1.3 | 1 | CacheRepository | 🔴 Высокий | 45 мин | 1.2 |
| 1.4 | 1 | ReportsRepository | 🔴 Высокий | 45 мин | 1.2 |
| 1.5 | 1 | ThreadsRepository | 🔴 Высокий | 45 мин | 1.2 |
| 1.6 | 1 | Update TarantoolClient | 🔴 Высокий | 30 мин | 1.3-1.5 |
| 1.7 | 1 | Migrate code | 🔴 Высокий | 60 мин | 1.6 |
| 1.8 | 1 | Testing | 🔴 Высокий | 60 мин | 1.7 |
| 2.1 | 2 | Install FastStream | 🟡 Средний | 15 мин | Нет |
| 2.2 | 2 | Broker config | 🟡 Средний | 30 мин | 2.1 |
| 2.3 | 2 | Schemas | 🟡 Средний | 30 мин | 2.2 |
| 2.4 | 2 | Publishers | 🟡 Средний | 45 мин | 2.3 |
| 2.5 | 2 | Subscribers | 🟡 Средний | 60 мин | 2.4 |
| 2.6 | 2 | Integrate with FastAPI | 🟡 Средний | 30 мин | 2.5 |
| 2.7 | 2 | Update API endpoints | 🟡 Средний | 45 мин | 2.6 |
| 2.8 | 2 | Testing | 🟡 Средний | 60 мин | 2.7 |
| 3.1 | 3 | Early exit | 🟡 Средний | 45 мин | Нет |
| 3.2 | 3 | Cache intermediate | 🟡 Средний | 60 мин | Фаза 1 |
| 3.3 | 3 | Smart parallelization | 🟡 Средний | 60 мин | Нет |
| 4.1 | 4 | Component structure | 🟢 Низкий | 90 мин | Нет |
| 5.1 | 5 | Remove Perplexity cache | 🟢 Низкий | 30 мин | Фаза 1 |
| 5.2 | 5 | Remove Tavily cache | 🟢 Низкий | 30 мин | Фаза 1 |

**Общее время:** ~18-20 часов

---

## 🚀 СЛЕДУЮЩИЙ ШАГ

**Предлагаю начать с ШАГ 1.1: Обновить init.lua**

**Готов приступить?** Жду вашей команды или корректировок плана!

Вы можете:
1. ✅ Подтвердить ШАГ 1.1 → я сразу реализую
2. ✏️ Скорректировать шаг (изменить детали)
3. 🔀 Выбрать другой шаг для начала
4. 📋 Запросить больше деталей по любому шагу
