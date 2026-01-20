# ADR-003: Multi-Agent Архитектура (LangGraph)

**Статус:** Принято
**Дата:** 2026-01-14
**Авторы:** Development Team

## Контекст

Анализ контрагента включает несколько этапов:
1. Формирование поисковых запросов
2. Сбор данных из 7+ источников
3. Анализ и нормализация рисков
4. Генерация отчёта

Каждый этап имеет свою специфику и может выполняться независимо.

## Рассмотренные альтернативы

### 1. Монолитный сервис
**Плюсы:**
- Простота разработки
- Меньше overhead

**Минусы:**
- Сложность масштабирования
- Тяжело тестировать отдельные части
- Нет параллелизма

### 2. Микросервисы
**Плюсы:**
- Независимое масштабирование
- Изоляция сбоев

**Минусы:**
- Сетевой overhead
- Сложность orchestration
- Distributed transactions

### 3. Multi-Agent (LangGraph)
**Плюсы:**
- Чёткое разделение ответственности
- Встроенный state management
- Параллельное выполнение
- Поддержка streaming

**Минусы:**
- Зависимость от LangGraph
- Кривая обучения

## Решение

Выбрана **Multi-Agent архитектура на базе LangGraph**.

### Агенты:

```
┌─────────────────────┐
│ Orchestrator Agent  │
│ (LLM + DaData)      │
└─────────────────────┘
         │
         ▼
┌─────────────────────┐
│ Data Collector Agent│
│ ┌─────┬─────┬─────┐ │
│ │DaDa │Info │Case │ │  ← INN-based (parallel)
│ │ta   │Sph. │book │ │
│ └─────┴─────┴─────┘ │
│ ┌─────────┬───────┐ │
│ │Perplexity│Tavily│ │  ← Web search (parallel)
│ └─────────┴───────┘ │
└─────────────────────┘
         │
         ▼
┌─────────────────────┐
│ Report Analyzer     │
│ (LLM + CoT)         │
└─────────────────────┘
         │
         ▼
┌─────────────────────┐
│ File Writer Agent   │
│ (PDF + JSON)        │
└─────────────────────┘
```

### State Management:

```python
class ClientAnalysisState(TypedDict):
    session_id: str
    client_name: str
    inn: str

    # Orchestrator output
    search_intents: List[Dict]

    # Data Collector output
    source_data: Dict[str, Any]
    search_results: List[Dict]

    # Analyzer output
    report: Dict[str, Any]

    # File Writer output
    saved_files: Dict[str, str]

    # Control
    current_step: Literal["orchestrating", "collecting", "analyzing", "saving", "completed", "failed"]
    error: str
```

### Оптимизация (Sprint 8.1):

```python
# Параллельный запуск orchestrator + INN sources
early_inn_tasks = {
    "infosphere": asyncio.create_task(fetch_infosphere(inn)),
    "casebook": asyncio.create_task(fetch_casebook(inn)),
}
orchestrator_result = await orchestrator_agent(state)

# Data collector использует уже запущенные tasks
state["_early_inn_tasks"] = early_inn_tasks
await data_collector_agent(state)
```

## Последствия

### Позитивные:
- Чёткое разделение ответственности (SRP)
- Параллельный сбор данных (~6 минут вместо ~12)
- Легко добавить новые агенты
- Streaming поддержка для UI

### Негативные:
- Зависимость от LangGraph библиотеки
- State passing между агентами
- Сложность отладки distributed flow

## Метрики

- `client_analysis_duration_seconds{stage}` - время каждого этапа
- `client_analysis_active` - количество активных анализов
- `client_analysis_requests_total{status}` - общее количество запросов

## Связанные документы
- `app/agents/client_workflow.py` - Workflow граф
- `app/agents/orchestrator.py` - Orchestrator agent
- `app/agents/data_collector.py` - Data collector
- `app/agents/report_analyzer.py` - Report analyzer
