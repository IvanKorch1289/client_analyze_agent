# Sprint 3: План оптимизации и новые фичи

> **Дата создания**: 2026-01-16
> **Автор**: Claude (AI Analyst)
> **Статус**: Планирование

---

## Анализ текущего состояния

### Что выполнено (Sprint 1-2)
- ✅ PII Protection (7 custom Presidio recognizers)
- ✅ LLM Audit Trail с hash-only режимом
- ✅ Tavily параллелизация (3→5 concurrent)
- ✅ Cache TTL увеличен (Perplexity/Tavily: 300s→3600s)
- ✅ Умный сброс кэша при негативном feedback

### Выявленные проблемы

#### 1. Неполная локализация интерфейса
**Файлы с смешанным русским/английским:**

| Файл | Проблема |
|------|----------|
| `router.py:16-25` | Смешанные лейблы: "Анализ клиента", "LLM Access", "System Monitor" |
| `app.py:166` | "Система анализа контрагентов" - OK |
| `llm.py` | Полностью на русском - OK |
| `ui.py:219-222` | Русские сообщения об ошибках - OK |

**Конкретные строки требующие изменения:**
```python
# router.py:18-25
TabDef(key="llm", label="LLM Access", admin_only=False),        # → "Доступ к LLM"
TabDef(key="monitor", label="System Monitor", admin_only=True), # → "Мониторинг"
```

#### 2. Крупные модули требующие рефакторинга
| Модуль | Строк | Проблема |
|--------|-------|----------|
| `tarantool.py` | 1,069 | Монолитный, много ответственностей |
| `utility.py` | 990 | Смешанные admin endpoints |
| `llm_manager.py` | 745 | PII логика внутри LLM manager |
| `data_collector.py` | 720 | Сложная логика объединения результатов |

---

## Sprint 3: План задач

### P0: Локализация UI (1-2 часа)

#### Задача 3.1.1: Исправить смешанные лейблы в router.py
```python
# БЫЛО:
TabDef(key="llm", label="LLM Access", admin_only=False),
TabDef(key="monitor", label="System Monitor", admin_only=True),

# СТАЛО:
TabDef(key="llm", label="Доступ к LLM", admin_only=False),
TabDef(key="monitor", label="Мониторинг", admin_only=True),
```

#### Задача 3.1.2: Добавить систему i18n (опционально)
```python
# app/frontend/i18n/translations.py (НОВОЕ)
from typing import Dict

TRANSLATIONS: Dict[str, Dict[str, str]] = {
    "ru": {
        "nav.analysis": "Анализ клиента",
        "nav.data": "Внешние данные",
        "nav.llm": "Доступ к LLM",
        "nav.monitor": "Мониторинг",
        "nav.utilities": "Утилиты",
        "nav.docs": "Документация",

        "error.timeout": "Превышено время ожидания",
        "error.connection": "Ошибка соединения",
        "error.validation": "Некорректные данные",

        "button.apply": "Применить",
        "button.logout": "Выйти",
        "button.send": "Отправить",
        "button.refresh": "Обновить",
    },
    "en": {
        "nav.analysis": "Client Analysis",
        "nav.data": "External Data",
        "nav.llm": "LLM Access",
        "nav.monitor": "Monitoring",
        "nav.utilities": "Utilities",
        "nav.docs": "Documentation",

        "error.timeout": "Request timeout",
        "error.connection": "Connection error",
        "error.validation": "Validation error",

        "button.apply": "Apply",
        "button.logout": "Logout",
        "button.send": "Send",
        "button.refresh": "Refresh",
    }
}

def get_text(key: str, lang: str = "ru") -> str:
    """Get translated text by key."""
    return TRANSLATIONS.get(lang, {}).get(key, key)
```

---

### P1: Новые фичи для UI/UX

#### Задача 3.2.1: Переключатель языка в sidebar
```python
# app/frontend/app.py - добавить в _render_sidebar()

def _render_sidebar() -> None:
    with st.sidebar:
        # Переключатель языка
        st.selectbox(
            "🌐 Язык / Language",
            options=["Русский", "English"],
            key="ui_language",
            index=0,
        )

        st.divider()
        st.title(_t("nav.title"))  # "Навигация" / "Navigation"
        # ... остальной код
```

#### Задача 3.2.2: Dashboard метрик в реальном времени
```python
# app/frontend/tabs/monitor.py - новая секция

def _render_realtime_metrics(api: ApiClient) -> None:
    """Отрисовка метрик в реальном времени."""
    section_header("Метрики системы", emoji="📊")

    # Auto-refresh каждые 30 секунд
    if st.checkbox("Автообновление", key="auto_refresh"):
        st_autorefresh(interval=30000, key="metrics_refresh")

    col1, col2, col3, col4 = st.columns(4)

    with col1:
        st.metric(
            "Анализов сегодня",
            value=metrics.get("analyses_today", 0),
            delta=metrics.get("analyses_delta", 0),
        )

    with col2:
        st.metric(
            "Cache Hit Rate",
            value=f"{metrics.get('cache_hit_rate', 0):.1f}%",
            delta=f"{metrics.get('cache_delta', 0):.1f}%",
        )

    with col3:
        st.metric(
            "Среднее время анализа",
            value=f"{metrics.get('avg_analysis_time', 0):.1f}s",
        )

    with col4:
        st.metric(
            "LLM Провайдер",
            value=metrics.get("current_provider", "N/A"),
        )
```

#### Задача 3.2.3: Визуализация риск-скора
```python
# app/frontend/lib/components.py - новый компонент

def render_risk_gauge(score: int, category: str) -> None:
    """Отрисовка gauge диаграммы для риск-скора."""
    import plotly.graph_objects as go

    # Определение цвета по уровню риска
    if score <= 25:
        color = "#00C853"  # Зелёный - низкий риск
        risk_level = "Низкий"
    elif score <= 50:
        color = "#FFD600"  # Жёлтый - средний
        risk_level = "Средний"
    elif score <= 75:
        color = "#FF9100"  # Оранжевый - повышенный
        risk_level = "Повышенный"
    else:
        color = "#FF1744"  # Красный - высокий
        risk_level = "Высокий"

    fig = go.Figure(go.Indicator(
        mode="gauge+number",
        value=score,
        domain={"x": [0, 1], "y": [0, 1]},
        title={"text": f"{category}<br><span style='font-size:0.8em'>{risk_level} риск</span>"},
        gauge={
            "axis": {"range": [0, 100]},
            "bar": {"color": color},
            "steps": [
                {"range": [0, 25], "color": "#E8F5E9"},
                {"range": [25, 50], "color": "#FFF9C4"},
                {"range": [50, 75], "color": "#FFE0B2"},
                {"range": [75, 100], "color": "#FFCDD2"},
            ],
        },
    ))

    fig.update_layout(height=200, margin=dict(t=50, b=0, l=20, r=20))
    st.plotly_chart(fig, use_container_width=True)
```

#### Задача 3.2.4: История анализов с фильтрацией
```python
# app/frontend/tabs/analysis.py - новая секция

def _render_analysis_history(api: ApiClient) -> None:
    """История выполненных анализов с фильтрацией."""
    section_header("История анализов", emoji="📜")

    col1, col2, col3 = st.columns(3)
    with col1:
        date_from = st.date_input("С даты", key="history_from")
    with col2:
        date_to = st.date_input("По дату", key="history_to")
    with col3:
        risk_filter = st.selectbox(
            "Уровень риска",
            options=["Все", "Низкий", "Средний", "Высокий"],
            key="risk_filter",
        )

    if st.button("Загрузить историю", key="btn_load_history"):
        with st.spinner("Загрузка..."):
            history = api.get(
                "/reports/history",
                params={
                    "from": date_from.isoformat(),
                    "to": date_to.isoformat(),
                    "risk_level": risk_filter if risk_filter != "Все" else None,
                }
            )

        if history:
            df = pd.DataFrame(history.get("reports", []))
            st.dataframe(
                df[["company_name", "inn", "risk_score", "created_at"]],
                use_container_width=True,
            )
```

---

### P1: Технические эндпоинты (API)

#### Задача 3.3.1: Эндпоинт сравнения компаний
```python
# app/api/routes/analysis.py

@router.post("/compare", response_model=ComparisonReport)
async def compare_companies(
    request: CompareRequest,
    background_tasks: BackgroundTasks,
) -> ComparisonReport:
    """
    Сравнить несколько компаний по риск-профилю.

    Request:
        {"companies": [{"name": "Компания А", "inn": "1234567890"}, ...]}

    Response:
        {
            "comparison_id": "uuid",
            "companies": [...],
            "ranking": [{"inn": "...", "risk_score": 45, "rank": 1}],
            "summary": "Компания А имеет наименьший риск-скор..."
        }
    """
    pass
```

#### Задача 3.3.2: Эндпоинт экспорта в Excel
```python
# app/api/routes/reports.py

@router.get("/export/{report_id}")
async def export_report(
    report_id: str,
    format: ExportFormat = Query(ExportFormat.PDF),
) -> FileResponse:
    """
    Экспорт отчёта в различных форматах.

    Formats:
        - pdf (default)
        - xlsx (Excel)
        - docx (Word)
        - json (raw data)
    """
    pass
```

#### Задача 3.3.3: Webhook для уведомлений о завершении
```python
# app/api/routes/webhooks.py (НОВОЕ)

@router.post("/subscribe")
async def subscribe_webhook(
    request: WebhookSubscription,
) -> WebhookResponse:
    """
    Подписаться на уведомления о событиях.

    Events:
        - analysis_complete
        - analysis_failed
        - high_risk_detected (score > 75)
        - cache_invalidated
    """
    pass
```

---

### P2: Рефакторинг модулей

#### Задача 3.4.1: Разбиение tarantool.py
```
ТЕКУЩЕЕ: app/storage/tarantool.py (1,069 строк)

НОВОЕ:
app/storage/
├── __init__.py
├── client.py           # TarantoolClient class (300 строк)
├── connection.py       # ConnectionManager, pooling (200 строк)
├── compression.py      # Сжатие/распаковка данных (150 строк)
├── metrics.py          # Метрики производительности (100 строк)
├── cache_layer.py      # CacheLayer с TTL логикой (200 строк)
└── repositories/
    ├── __init__.py
    ├── cache.py        # CacheRepository
    ├── reports.py      # ReportsRepository
    └── threads.py      # ThreadsRepository
```

#### Задача 3.4.2: Разбиение data_collector.py
```
ТЕКУЩЕЕ: app/agents/data_collector.py (720 строк)

НОВОЕ:
app/agents/
├── data_collector.py         # Оркестратор (200 строк)
├── collectors/
│   ├── __init__.py
│   ├── base.py               # AbstractCollector
│   ├── dadata.py             # DaDataCollector
│   ├── casebook.py           # CasebookCollector
│   ├── infosphere.py         # InfoSphereCollector
│   ├── perplexity.py         # PerplexityCollector
│   └── tavily.py             # TavilyCollector
└── result_merger.py          # Логика объединения результатов
```

---

### P2: Мониторинг и Observability

#### Задача 3.5.1: Prometheus метрики
```python
# app/shared/metrics.py (НОВОЕ)

from prometheus_client import Counter, Histogram, Gauge

# Счётчики
ANALYSIS_REQUESTS = Counter(
    "analysis_requests_total",
    "Total analysis requests",
    ["status", "source"],
)

LLM_REQUESTS = Counter(
    "llm_requests_total",
    "Total LLM API requests",
    ["provider", "status"],
)

# Гистограммы
ANALYSIS_DURATION = Histogram(
    "analysis_duration_seconds",
    "Analysis duration in seconds",
    buckets=[10, 30, 60, 120, 300, 600],
)

LLM_LATENCY = Histogram(
    "llm_latency_seconds",
    "LLM API latency",
    ["provider"],
    buckets=[1, 5, 10, 30, 60, 120],
)

# Gauges
CACHE_HIT_RATE = Gauge(
    "cache_hit_rate",
    "Cache hit rate percentage",
    ["cache_type"],
)

ACTIVE_ANALYSES = Gauge(
    "active_analyses",
    "Currently running analyses",
)
```

#### Задача 3.5.2: Grafana dashboard JSON
```json
// config/grafana/dashboards/main.json
{
  "title": "Client Analysis Agent",
  "panels": [
    {
      "title": "Analyses per Hour",
      "type": "graph",
      "targets": [{"expr": "rate(analysis_requests_total[1h])"}]
    },
    {
      "title": "LLM Provider Status",
      "type": "stat",
      "targets": [{"expr": "llm_provider_available"}]
    },
    {
      "title": "Average Analysis Time",
      "type": "gauge",
      "targets": [{"expr": "histogram_quantile(0.95, analysis_duration_seconds_bucket)"}]
    },
    {
      "title": "Cache Hit Rate",
      "type": "gauge",
      "targets": [{"expr": "cache_hit_rate"}]
    }
  ]
}
```

---

## Предложенные новые фичи

### Фича 1: Batch Analysis (Пакетный анализ)
**Описание:** Загрузка CSV/Excel файла со списком компаний для массового анализа.

```python
# UI: Загрузка файла
uploaded_file = st.file_uploader("Загрузить список компаний", type=["csv", "xlsx"])

# API: POST /analysis/batch
{
    "companies": [
        {"name": "Компания 1", "inn": "1234567890"},
        {"name": "Компания 2", "inn": "0987654321"},
    ],
    "callback_url": "https://...",  # Уведомление по завершении
    "priority": "normal"
}
```

**Выгода:** Экономия времени для compliance офицеров, проверяющих 50+ контрагентов.

---

### Фича 2: Risk Alerts (Оповещения о рисках)
**Описание:** Автоматические уведомления при обнаружении высокого риска.

```python
# Конфигурация в UI
alert_config = {
    "channels": ["email", "telegram", "webhook"],
    "thresholds": {
        "high_risk": 75,  # Notify if score > 75
        "bankruptcy_risk": True,  # Notify on bankruptcy indicators
        "court_cases": 10,  # Notify if > 10 active cases
    },
    "recipients": ["compliance@company.com", "@telegram_bot"]
}
```

**Выгода:** Проактивный мониторинг рисков контрагентов.

---

### Фича 3: Periodic Re-analysis (Периодический переанализ)
**Описание:** Автоматический переанализ важных контрагентов по расписанию.

```python
# UI: Настройка расписания
schedule = st.selectbox(
    "Частота переанализа",
    options=["Еженедельно", "Ежемесячно", "Ежеквартально"],
)

# API: POST /analysis/schedule
{
    "inn": "1234567890",
    "frequency": "weekly",
    "notify_on_change": True,  # Уведомлять только при изменении риск-скора
    "change_threshold": 10,    # Минимальное изменение для уведомления
}
```

**Выгода:** Отслеживание изменений в риск-профиле контрагентов.

---

### Фича 4: Comparison Mode (Режим сравнения)
**Описание:** Сравнение 2-5 компаний бок о бок.

```
┌─────────────────┬─────────────────┬─────────────────┐
│  Компания А     │  Компания Б     │  Компания В     │
├─────────────────┼─────────────────┼─────────────────┤
│ Risk: 45 🟡     │ Risk: 23 🟢     │ Risk: 78 🔴     │
│ Legal: 3 cases  │ Legal: 0 cases  │ Legal: 12 cases │
│ Finance: OK     │ Finance: OK     │ Finance: ⚠️     │
│ Age: 5 years    │ Age: 12 years   │ Age: 2 years    │
└─────────────────┴─────────────────┴─────────────────┘
```

**Выгода:** Быстрый выбор между несколькими поставщиками/партнёрами.

---

### Фича 5: Custom Risk Weights (Кастомные веса рисков)
**Описание:** Настройка весов категорий риска под специфику бизнеса.

```python
# UI: Настройка весов
st.subheader("Настройка весов риск-категорий")

weights = {
    "legal": st.slider("Юридические риски", 0, 100, 35),
    "financial": st.slider("Финансовые риски", 0, 100, 30),
    "reputation": st.slider("Репутационные риски", 0, 100, 20),
    "regulatory": st.slider("Регуляторные риски", 0, 100, 15),
}

# Валидация: сумма должна быть 100
total = sum(weights.values())
if total != 100:
    st.warning(f"Сумма весов: {total}% (должна быть 100%)")
```

**Выгода:** Адаптация под специфику отрасли (банки vs производство vs IT).

---

### Фича 6: API Rate Limiting Dashboard
**Описание:** Визуализация использования API квот внешних сервисов.

```
┌─────────────────────────────────────────────────────┐
│                API Usage Today                       │
├──────────────┬─────────────┬────────────┬──────────┤
│ Provider     │ Used        │ Limit      │ Status   │
├──────────────┼─────────────┼────────────┼──────────┤
│ DaData       │ 450/500     │ 90%        │ 🟡       │
│ OpenRouter   │ 120/1000    │ 12%        │ 🟢       │
│ Perplexity   │ 80/100      │ 80%        │ 🟡       │
│ Tavily       │ 45/200      │ 22%        │ 🟢       │
└──────────────┴─────────────┴────────────┴──────────┘
```

**Выгода:** Предотвращение превышения лимитов и неожиданных счетов.

---

## Приоритизация

### Рекомендуемый порядок выполнения

| # | Задача | Приоритет | Сложность | Время |
|---|--------|-----------|-----------|-------|
| 1 | Локализация router.py | P0 | Низкая | 15 мин |
| 2 | Risk gauge визуализация | P1 | Средняя | 2-3 ч |
| 3 | История анализов | P1 | Средняя | 2-3 ч |
| 4 | Dashboard метрик | P1 | Средняя | 3-4 ч |
| 5 | Batch analysis API | P1 | Высокая | 4-6 ч |
| 6 | Prometheus метрики | P2 | Средняя | 3-4 ч |
| 7 | Рефакторинг tarantool | P2 | Высокая | 6-8 ч |
| 8 | Comparison mode | P2 | Высокая | 4-6 ч |

---

## Быстрые победы (Quick Wins)

### 1. Исправление локализации (15 минут)
Изменить `router.py:18-25`:
- "LLM Access" → "Доступ к LLM"
- "System Monitor" → "Мониторинг"

### 2. Добавить favicon (5 минут)
Добавить `app/frontend/assets/favicon.ico` и обновить `app.py:165`:
```python
st.set_page_config(
    page_title="Система анализа контрагентов",
    page_icon="🔍",  # или путь к favicon
    layout="wide",
)
```

### 3. Улучшить сообщения об ошибках (30 минут)
Добавить более информативные сообщения при ошибках API в `ui.py`.

---

## Заключение

Проект **Client Analysis Agent** находится в отличном состоянии после Sprint 2. Основные рекомендации:

1. **Немедленно:** Исправить локализацию (смешанные RU/EN лейблы)
2. **Краткосрочно:** Добавить визуализации (risk gauge, метрики)
3. **Среднесрочно:** Рефакторинг крупных модулей
4. **Долгосрочно:** Новые фичи (batch analysis, alerts, comparison)

**Готовность к production:** ✅ 100% (все критичные задачи выполнены)
**Потенциал улучшений:** ⭐⭐⭐⭐⭐ (много возможностей для развития)
