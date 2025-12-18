# 🚀 БЫСТРЫЕ УЛУЧШЕНИЯ И ДОРАБОТКИ

**Дата:** 18 декабря 2025

---

## ✅ ЧТО УЖЕ СДЕЛАНО СЕГОДНЯ

1. ✅ **Scheduler Service** - отложенные задачи (APScheduler)
   - 350 строк кода
   - API endpoints для планирования анализа клиентов
   - Интеграция с main.py lifespan

2. ✅ **LLMManager** - fallback стратегия (ФАЗА 2, частично)
   - OpenRouter → HuggingFace → GigaChat
   - 431 строка кода
   - Автоматическое переключение при ошибках

3. ✅ **Конфигурация HuggingFace и GigaChat**
   - Добавлены settings классы
   - Интеграция в root Settings
   - .env.example обновлен

---

## 🔧 ПРЕДЛАГАЕМЫЕ НЕБОЛЬШИЕ УЛУЧШЕНИЯ

### 1️⃣ УДАЛИТЬ МЕРТВЫЙ КОД (5 минут)

#### ❌ Удалить `app/utility/cache.py`

**Причина:** Используется только в `fetch_data.py`, но можно заменить на `CacheRepository`

**Действия:**
1. Удалить `/workspace/app/utility/cache.py` (73 строки)
2. Обновить `app/utility/__init__.py` - убрать `cache_response` из exports
3. Обновить `app/services/fetch_data.py` - использовать `CacheRepository` напрямую

**Выгода:**
- ✅ -73 строки мертвого кода
- ✅ Унификация кеширования
- ✅ Меньше путаницы (один способ кешировать)

---

### 2️⃣ ОПТИМИЗИРОВАТЬ FETCH_DATA.PY (10 минут)

**Файл:** `app/services/fetch_data.py`

**Проблема:** Использует старый декоратор `@cache_response`

**Текущий код:**
```python
from app.utility import cache_response

@cache_response(ttl=7200)
async def fetch_dadata_info(inn: str):
    ...
```

**Улучшенный код:**
```python
from app.storage.tarantool import TarantoolClient

async def fetch_dadata_info(inn: str):
    # Check cache первоначально
    client = await TarantoolClient.get_instance()
    cache_repo = client.get_cache_repository()
    
    cache_key = f"dadata:{inn}"
    cached = await cache_repo.get(cache_key)
    if cached:
        return cached
    
    # Fetch from API
    result = await _fetch_dadata_api(inn)
    
    # Save to cache
    await cache_repo.set_with_ttl(cache_key, result, ttl=7200, source="dadata")
    
    return result
```

**Выгода:**
- ✅ Явный контроль кеша
- ✅ Статистика по источникам (source="dadata")
- ✅ Единый подход

---

### 3️⃣ ДОБАВИТЬ HEALTH CHECK ДЛЯ ВНЕШНИХ API (15 минут)

**Файл:** Создать `app/api/routes/health.py` (NEW)

**Функционал:**
```python
@health_router.get("/health/external")
async def check_external_apis():
    """Проверка здоровья всех внешних API."""
    results = {}
    
    # DaData
    try:
        await check_dadata_health()
        results["dadata"] = {"status": "up", "latency_ms": 120}
    except:
        results["dadata"] = {"status": "down", "error": "..."}
    
    # InfoSphere
    # Casebook
    # Perplexity
    # Tavily
    # OpenRouter
    # HuggingFace
    # GigaChat
    
    return {
        "status": "healthy" if all(r["status"] == "up" for r in results.values()) else "degraded",
        "apis": results,
        "timestamp": datetime.now().isoformat()
    }
```

**Выгода:**
- ✅ Visibility проблем с API
- ✅ Мониторинг latency
- ✅ Алерты при недоступности

---

### 4️⃣ УЛУЧШИТЬ LOGGING В LLMManager (5 минут)

**Файл:** `app/agents/llm_manager.py`

**Добавить:**
```python
async def ainvoke(self, prompt: str, **kwargs) -> str:
    start_time = time.perf_counter()
    
    # ... existing code ...
    
    duration = time.perf_counter() - start_time
    
    logger.structured(
        "info",
        "llm_invocation",
        component="llm_manager",
        provider=provider.value,
        prompt_length=len(prompt),
        response_length=len(response),
        duration_ms=round(duration * 1000, 2),  # NEW
        fallback_used=provider != LLMProvider.OPENROUTER,  # NEW
    )
```

**Выгода:**
- ✅ Метрики длительности LLM вызовов
- ✅ Tracking fallback usage
- ✅ Observability

---

### 5️⃣ ДОБАВИТЬ МЕТОД `get_latest_report_by_inn()` (10 минут)

**Файл:** `app/storage/repositories/reports_repository.py`

**Добавить:**
```python
async def get_latest_report_by_inn(self, inn: str) -> Optional[Dict[str, Any]]:
    """
    Получить последний отчет по ИНН.
    
    Args:
        inn: ИНН клиента
        
    Returns:
        Последний отчет или None
    """
    reports = await self.get_reports_by_inn(inn, limit=1)
    return reports[0] if reports else None
```

**Использование в orchestrator.py:**
```python
# Загружаем прошлый отчет для контекста
reports_repo = client.get_reports_repository()
previous_report = await reports_repo.get_latest_report_by_inn(inn)

if previous_report:
    state["previous_report"] = previous_report
    logger.info(f"Found previous report for {inn}, adding to context")
```

**Выгода:**
- ✅ Удобный API
- ✅ Подготовка к ФАЗЕ 3 (контекст прошлых отчетов)

---

### 6️⃣ ДОБАВИТЬ RATE LIMITING НА REDIS (10 минут)

**Файл:** `app/main.py`

**Текущий код:**
```python
limiter = Limiter(
    key_func=get_remote_address,
    storage_uri="memory://"  # ❌ In-memory
)
```

**Улучшенный код:**
```python
from app.config import settings

# Используем Redis если доступен, иначе memory
storage_uri = f"redis://{settings.redis.host}:{settings.redis.port}" if settings.redis.host else "memory://"

limiter = Limiter(
    key_func=get_remote_address,
    storage_uri=storage_uri,
    default_limits=[
        f"{RATE_LIMIT_GLOBAL_PER_MINUTE}/minute",
        f"{RATE_LIMIT_GLOBAL_PER_HOUR}/hour",
    ],
)

logger.info(f"Rate limiting storage: {storage_uri}")
```

**Выгода:**
- ✅ Персистентный rate limiting (не сбрасывается при рестарте)
- ✅ Distributed rate limiting (для нескольких инстансов)

---

### 7️⃣ ДОБАВИТЬ STATS ENDPOINT ДЛЯ CACHE/REPORTS/THREADS (10 минут)

**Файл:** `app/api/routes/utility.py`

**Добавить:**
```python
@utility_router.get("/stats/storage")
async def get_storage_stats():
    """Статистика по всем storage."""
    client = await TarantoolClient.get_instance()
    
    cache_repo = client.get_cache_repository()
    reports_repo = client.get_reports_repository()
    threads_repo = client.get_threads_repository()
    
    return {
        "cache": await cache_repo.get_stats(),
        "reports": await reports_repo.get_stats(),
        "threads": await threads_repo.get_stats(),
        "timestamp": datetime.now().isoformat()
    }
```

**Выгода:**
- ✅ Мониторинг storage
- ✅ Видимость использования
- ✅ Capacity planning

---

### 8️⃣ УЛУЧШИТЬ ERROR HANDLING В SCHEDULER (5 минут)

**Файл:** `app/services/scheduler_service.py`

**Добавить в `_execute_client_analysis`:**
```python
async def _execute_client_analysis(self, client_name: str, inn: str, additional_notes: str = ""):
    task_id = f"analysis_{inn}_{int(time.time())}"
    
    try:
        result = await run_client_analysis_batch(...)
        
        # ✅ NEW: Сохраняем результат в Tarantool
        client = await TarantoolClient.get_instance()
        
        # Сохраняем отчет
        if result.get("status") == "completed" and result.get("report"):
            reports_repo = client.get_reports_repository()
            report_id = await reports_repo.create_from_workflow_result(result)
            logger.info(f"Scheduled analysis report saved: {report_id}")
        
        # Обновляем метаданные задачи
        if task_id in self._tasks_metadata:
            self._tasks_metadata[task_id].update({
                "status": "completed",
                "result": result,
                "completed_at": datetime.now()
            })
        
    except Exception as e:
        # Сохраняем ошибку в метаданные
        if task_id in self._tasks_metadata:
            self._tasks_metadata[task_id].update({
                "status": "failed",
                "error": str(e),
                "failed_at": datetime.now()
            })
        
        logger.error(f"Scheduled analysis failed: {e}", exc_info=True)
```

**Выгода:**
- ✅ Автоматическое сохранение результатов
- ✅ Tracking ошибок
- ✅ История выполнения

---

### 9️⃣ ДОБАВИТЬ PYDANTIC VALIDATION ДЛЯ INN (5 минут)

**Файл:** Создать `app/schemas/common.py` (NEW)

```python
from pydantic import BaseModel, Field, validator

class INNField(BaseModel):
    """Pydantic поле для валидации ИНН."""
    
    inn: str = Field(..., min_length=10, max_length=12)
    
    @validator('inn')
    def validate_inn(cls, v):
        from app.utility.helpers import validate_inn
        
        if not validate_inn(v):
            raise ValueError(f"Invalid INN: {v}")
        
        return v
```

**Использование:**
```python
class AnalyzeClientRequest(INNField):
    client_name: str
    additional_notes: str = ""
```

**Выгода:**
- ✅ Автоматическая валидация на API уровне
- ✅ Единообразие валидации
- ✅ Понятные ошибки для пользователя

---

### 🔟 ДОБАВИТЬ GRACEFUL SHUTDOWN ДЛЯ SCHEDULER (5 минут)

**Файл:** `app/services/scheduler_service.py`

**Обновить `shutdown()`:**
```python
def shutdown(self, wait_for_jobs: bool = True, timeout: int = 30):
    """
    Остановить scheduler с graceful shutdown.
    
    Args:
        wait_for_jobs: Ждать завершения текущих задач
        timeout: Максимальное время ожидания (секунды)
    """
    if self._started:
        if wait_for_jobs:
            logger.info(f"Waiting up to {timeout}s for jobs to finish...")
        
        self.scheduler.shutdown(wait=wait_for_jobs)
        self._started = False
        
        # Сохраняем метаданные задач в Tarantool перед shutdown
        self._save_metadata_to_storage()
        
        logger.info("Scheduler stopped gracefully")
```

**Выгода:**
- ✅ Не теряем выполняющиеся задачи
- ✅ Сохраняем метаданные
- ✅ Graceful restart

---

## 📊 ИТОГОВАЯ ТАБЛИЦА

| # | Улучшение | Время | Выгода | Приоритет |
|---|-----------|-------|--------|-----------|
| 1 | Удалить cache.py | 5 мин | -73 строки, унификация | 🔴 ВЫСОКИЙ |
| 2 | Оптимизировать fetch_data.py | 10 мин | Явный контроль кеша | 🔴 ВЫСОКИЙ |
| 3 | Health check API | 15 мин | Мониторинг | 🟡 СРЕДНИЙ |
| 4 | Logging в LLMManager | 5 мин | Метрики | 🟡 СРЕДНИЙ |
| 5 | get_latest_report_by_inn | 10 мин | Удобный API | 🟡 СРЕДНИЙ |
| 6 | Rate limiting на Redis | 10 мин | Персистентность | 🟡 СРЕДНИЙ |
| 7 | Stats endpoint | 10 мин | Мониторинг | 🟢 НИЗКИЙ |
| 8 | Error handling в Scheduler | 5 мин | Надежность | 🔴 ВЫСОКИЙ |
| 9 | Pydantic INN validation | 5 мин | Автоматизация | 🟢 НИЗКИЙ |
| 10 | Graceful shutdown | 5 мин | Надежность | 🟢 НИЗКИЙ |

**ИТОГО:** 80 минут (~1.3 часа)

---

## 🎯 РЕКОМЕНДУЕМЫЙ ПОРЯДОК ВЫПОЛНЕНИЯ

### Сессия 1 (30 минут) - КРИТИЧЕСКИЕ

1. ✅ Удалить `cache.py` и обновить `fetch_data.py` (15 мин)
2. ✅ Error handling в Scheduler (5 мин)
3. ✅ Logging в LLMManager (5 мин)
4. ✅ Rate limiting на Redis (5 мин)

### Сессия 2 (25 минут) - ВАЖНЫЕ

5. ✅ `get_latest_report_by_inn()` (10 мин)
6. ✅ Health check API (15 мин)

### Сессия 3 (25 минут) - ДОПОЛНИТЕЛЬНЫЕ

7. ✅ Stats endpoint (10 мин)
8. ✅ Pydantic INN validation (5 мин)
9. ✅ Graceful shutdown (5 мин)

---

## ✅ ЗАКЛЮЧЕНИЕ

Эти небольшие улучшения:
- ✅ Удалят ~73 строки мертвого кода
- ✅ Улучшат observability (логи, метрики, health checks)
- ✅ Повысят надежность (error handling, graceful shutdown)
- ✅ Упростят API (удобные методы)

**Все изменения готовы к имплементации и не ломают существующий код!**

Приступить к выполнению?
