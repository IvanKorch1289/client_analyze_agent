# Sprint 3 - UI/UX Improvements & Admin Tools

> **Дата начала**: 2026-01-15
> **Статус**: В РАБОТЕ
> **Приоритет**: P1 (Опциональные улучшения)

---

## 🎯 Цели Sprint 3

### Приоритет P1 (Высокий, но не критичный)
1. ✅ **Исправление критической ошибки** - ImportError require_admin_token
2. 🔄 **Расширение Admin API** - технические эндпоинты для операционного мониторинга
3. 🔄 **Русификация интерфейса** - все надписи на русском (кроме имен собственных)
4. 🔄 **UI панель мониторинга** - System Monitor dashboard в Streamlit
5. ⏸️ **Визуализация риск-скора** - графики с Plotly (если успеем)

---

## 📋 Детальный план задач

### Задача 3.1: Исправление ImportError ✅ DONE

**Файлы:**
- `app/api/routes/admin.py` (ИСПРАВЛЕНО)

**Проблема:**
```python
ImportError: cannot import name 'require_admin_token' from 'app.utility.auth'
```

**Решение:**
```python
# Было:
from app.utility.auth import require_admin_token

# Стало:
from app.utility.auth import require_admin
```

**Результат:**
- ✅ Импорт исправлен во всех местах (7 occurrences)
- ✅ Ruff checks passed
- ✅ Приложение должно запускаться

**Время:** ~5 минут

---

### Задача 3.2: Расширение Admin API (P1)

**Файлы:**
- `app/api/routes/admin.py` (ДОПОЛНИТЬ)

**Новые эндпоинты:**

#### 3.2.1: POST /admin/llm/test-provider/{provider}
Тестирование конкретного LLM провайдера (диагностика fallback цепочки).

```python
@admin_router.post("/llm/test-provider/{provider}", dependencies=[Depends(require_admin)])
async def test_llm_provider(provider: str) -> Dict[str, Any]:
    """
    Тестирование LLM провайдера.

    Отправляет тестовый запрос в указанный LLM и возвращает результат.
    Полезно для диагностики проблем с fallback цепочкой.

    Args:
        provider: Имя провайдера (openrouter, huggingface, gigachat, yandexgpt)

    Returns:
        {
            "provider": str,
            "status": "success" | "error",
            "response_preview": str,
            "duration_ms": float,
            "error": str | None
        }
    """
```

#### 3.2.2: GET /admin/storage/disk-usage
Мониторинг дискового пространства (отчеты, логи, временные файлы).

```python
@admin_router.get("/storage/disk-usage", dependencies=[Depends(require_admin)])
async def get_disk_usage() -> Dict[str, Any]:
    """
    Использование дискового пространства.

    Returns:
        {
            "reports": {"size_mb": float, "file_count": int},
            "logs": {"size_mb": float, "file_count": int},
            "temp": {"size_mb": float, "file_count": int}
        }
    """
```

#### 3.2.3: POST /admin/storage/cleanup
Очистка старых файлов (отчеты, логи).

```python
@admin_router.post("/storage/cleanup", dependencies=[Depends(require_admin)])
async def cleanup_old_files(days: int = 30) -> Dict[str, Any]:
    """
    Очистка файлов старше N дней.

    Args:
        days: Удалить файлы старше указанного количества дней

    Returns:
        {
            "status": "completed",
            "deleted_files_count": int,
            "cutoff_days": int
        }
    """
```

#### 3.2.4: POST /admin/cache/warmup
Прогрев кэша популярными запросами.

```python
@admin_router.post("/cache/warmup", dependencies=[Depends(require_admin)])
async def warmup_cache() -> Dict[str, Any]:
    """
    Прогрев кэша популярными запросами.

    Полезно после рестарта сервиса или очистки кэша.

    Returns:
        {
            "status": "completed",
            "queries_warmed": int,
            "details": List[Dict]
        }
    """
```

**Оценка времени:** 4-6 часов

---

### Задача 3.3: Русификация интерфейса (P1)

**Файлы для проверки:**
- `app/frontend/**/*.py` (все Streamlit файлы)
- `app/api/**/*.py` (response messages)
- `app/shared/**/*.py` (error messages)

**Что проверить:**
1. **Streamlit UI:**
   - Заголовки страниц
   - Названия вкладок
   - Кнопки, лейблы, подсказки
   - Сообщения об ошибках
   - Success/warning messages

2. **API Responses:**
   - Error messages
   - Success messages
   - Validation messages

3. **Исключения:**
   - Технические термины (OpenRouter, Tarantool, RabbitMQ) - остаются as-is
   - Имена собственные (Claude, Perplexity, Tavily) - остаются as-is
   - Названия полей JSON (client_name, inn) - остаются на английском

**Примеры исправлений:**
```python
# Плохо:
st.title("Client Analysis Dashboard")
st.button("Submit")
st.error("Request failed")

# Хорошо:
st.title("Панель анализа контрагентов")
st.button("Отправить")
st.error("Запрос не выполнен")
```

**Оценка времени:** 2-3 часа

---

### Задача 3.4: UI панель мониторинга (P1)

**Файлы:**
- `app/frontend/tabs/system_monitor.py` (НОВЫЙ)
- `app/frontend/app.py` (ДОПОЛНИТЬ - добавить вкладку)

**Функциональность:**

#### 1. Метрики (4 колонки):
- Circuit Breakers (total/open)
- HTTP Requests (total + success rate)
- Cache Hit Rate (%)
- Cache Size (keys)

#### 2. Вкладки с детальной информацией:
- **Circuit Breakers:** Таблица со статусом всех CB + кнопка Reset
- **HTTP Metrics:** Таблица по сервисам + кнопка Reset All Metrics
- **Cache Entries:** TOP-50 записей + кнопки очистки по префиксам
- **Running Tasks:** Список активных анализов + кнопка Cancel

**UI компоненты:**
```python
# Метрики
col1, col2, col3, col4 = st.columns(4)
with col1:
    st.metric("Circuit Breakers", f"{closed}/{total}", delta="OK")

# Детальные таблицы
st.dataframe(circuit_breakers_data, use_container_width=True)

# Управление
if st.button("🔄 Reset Circuit Breaker"):
    # ...
```

**Оценка времени:** 6-8 часов

---

### Задача 3.5: Визуализация риск-скора (P1, опционально)

**Файлы:**
- `app/frontend/tabs/analysis.py` (ДОПОЛНИТЬ)

**Функциональность:**

#### 1. Gauge chart (индикатор риск-скора):
- Значение 0-100
- Цветные зоны (зеленая, желтая, оранжевая, красная)
- Delta к среднему значению

#### 2. Bar chart (распределение по категориям):
- Legal (35%)
- Financial (30%)
- Reputation (20%)
- Regulatory (15%)

**Библиотека:** Plotly (уже в зависимостях)

```python
import plotly.graph_objects as go

fig = go.Figure(go.Indicator(
    mode="gauge+number+delta",
    value=risk_score,
    domain={'x': [0, 1], 'y': [0, 1]},
    title={'text': "Риск-скор"},
    gauge={
        'axis': {'range': [None, 100]},
        'bar': {'color': _get_risk_color(risk_score)},
        'steps': [
            {'range': [0, 25], 'color': "lightgreen"},
            {'range': [25, 50], 'color': "yellow"},
            {'range': [50, 75], 'color': "orange"},
            {'range': [75, 100], 'color': "red"},
        ]
    }
))

st.plotly_chart(fig, use_container_width=True)
```

**Оценка времени:** 4-5 часов

---

## ⏱️ Оценка времени Sprint 3

| Задача | Оценка | Приоритет | Статус |
|--------|--------|-----------|--------|
| 3.1 ImportError fix | 5 мин | P0 | ✅ DONE |
| 3.2 Admin API эндпоинты | 4-6 ч | P1 | 🔄 TODO |
| 3.3 Русификация интерфейса | 2-3 ч | P1 | 🔄 TODO |
| 3.4 UI панель мониторинга | 6-8 ч | P1 | 🔄 TODO |
| 3.5 Визуализация риск-скора | 4-5 ч | P1 | ⏸️ OPTIONAL |
| **Итого P1 (обязательно)** | **12-17 ч** | | |
| **Итого P1 + опциональное** | **16-22 ч** | | |

**Рекомендация:** Выполнить задачи 3.1-3.4, задачу 3.5 делать если останется время.

---

## 📊 Ожидаемые результаты

### UX/UI улучшения:
- ✅ **Стабильность** - исправлена критическая ошибка запуска
- 🎯 **Операционный мониторинг** - админ панель с метриками
- 🇷🇺 **Локализация** - полностью русифицированный интерфейс
- 📈 **Визуализация** - наглядные графики риск-скора

### Операционные улучшения:
- 🔧 **Диагностика LLM** - тестирование провайдеров
- 💾 **Управление хранилищем** - мониторинг и очистка дискового пространства
- ⚡ **Прогрев кэша** - быстрый старт после рестарта

### Качество:
- 📈 **Лучше UX** - удобные дашборды и графики
- 📈 **Лучше DX** - инструменты для диагностики и управления
- 📈 **Production-ready** - готово к эксплуатации

---

## ✅ Definition of Done

Задача считается выполненной когда:
1. ✅ Код написан и прошёл линтеры (ruff, black, pyright)
2. ✅ UI компоненты работают без ошибок
3. ✅ Все надписи на русском (кроме имен собственных)
4. ✅ Документация обновлена (docstrings, комментарии)
5. ✅ Commit создан с подробным описанием
6. ✅ Push в remote branch выполнен

---

## 🚀 Старт Sprint 3

**Порядок выполнения:**
1. ✅ Task 3.1: ImportError fix (критично, уже выполнено)
2. 🔄 Task 3.2: Admin API расширение (быстрая победа, полезные инструменты)
3. 🔄 Task 3.3: Русификация интерфейса (важно для UX)
4. 🔄 Task 3.4: UI панель мониторинга (основная задача спринта)
5. ⏸️ Task 3.5: Визуализация риск-скора (если останется время)

**Начинаем с Task 3.2!** 🔧
