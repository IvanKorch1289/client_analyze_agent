# 🏗️ АРХИТЕКТУРНЫЕ РЕШЕНИЯ И ПЛАН РЕАЛИЗАЦИИ

**Дата:** 18 декабря 2025  
**Команда архитекторов:** Senior Backend + Integration + Code Quality + Workflow Designer

---

## ✅ ЧТО УЖЕ СДЕЛАНО

### 1. **Декоратор кэширования** ✅
- **Файл:** `/workspace/app/utility/decorators.py` (250 строк)
- **Функционал:**
  - `@cache_with_tarantool(ttl, source)` - универсальное кэширование
  - `@async_retry(max_attempts, delay)` - retry логика
- **Применено в:** `fetch_data.py` (удалено ~80 строк дублирования)

### 2. **Удалены ненужные файлы** ✅
- Удалено 7 MD файлов (~91KB): PHASE_1_COMPLETE, PHASE_2_PROGRESS, PROJECT_AUDIT, etc.

### 3. **Config структура** ✅
- `/workspace/config/` - YAML конфигурации ✅ ПРАВИЛЬНО
- `/workspace/app/config/` - Python модуль ✅ ПРАВИЛЬНО
- **Решение:** Оставить как есть (separation of concerns)

---

## 🔧 ЧТО НУЖНО СДЕЛАТЬ (КРИТИЧНЫЕ ЗАДАЧИ)

### 🔴 ЗАДАЧА 1: Исправление Workflow Агента (КРИТИЧНО)

#### Текущий граф (НЕПРАВИЛЬНЫЙ):
```
orchestrator → data_collector → analyzer → file_writer
```

#### Требуемый граф (ПРАВИЛЬНЫЙ):
```
1. api_tool_agent (параллельно: DaData, Casebook, InfoSphere) → JSON
2. orchestrator_agent (извлекает client_name из JSON)
3. search_agent (параллельно: Perplexity, Tavily) → добавляет в JSON
4. report_analyzer_agent (создает отчет с указанием источников)
5. [user_feedback_check]:
   - if "отчет корректен" → file_writer + save_to_tarantool + generate_pdf
   - if "отчет некорректен" → report_analyzer_agent (с user_comment)
```

#### Архитектурное решение:

```python
# /workspace/app/agents/client_workflow_v2.py

class ClientAnalysisStateV2(TypedDict):
    # Existing fields
    session_id: str
    client_name: str
    inn: str
    additional_notes: str
    
    # API data
    api_data: Dict[str, Any]  # {dadata: {...}, infosphere: {...}, casebook: {...}}
    
    # Search data
    search_data: Dict[str, Any]  # {perplexity: [...], tavily: [...]}
    
    # Report & feedback
    report: Dict[str, Any]
    user_feedback: Optional[str]  # "correct" | "incorrect"
    user_comment: Optional[str]  # Комментарий если некорректен
    previous_report: Optional[Dict[str, Any]]  # Для повторного анализа
    retry_count: int  # Счетчик попыток
    
    # Status
    current_step: Literal[
        "fetching_api",
        "orchestrating",
        "searching",
        "analyzing",
        "awaiting_feedback",
        "saving",
        "completed",
        "failed"
    ]

def build_improved_workflow():
    """Улучшенный workflow согласно требованиям."""
    workflow = StateGraph(ClientAnalysisStateV2)
    
    # Nodes
    workflow.add_node("api_tool", api_tool_agent)
    workflow.add_node("orchestrator", orchestrator_agent_v2)
    workflow.add_node("search", search_agent)
    workflow.add_node("analyzer", report_analyzer_agent_v2)
    workflow.add_node("file_writer", file_writer_agent_v2)
    
    # Edges
    workflow.set_entry_point("api_tool")
    workflow.add_edge("api_tool", "orchestrator")
    workflow.add_edge("orchestrator", "search")
    workflow.add_edge("search", "analyzer")
    
    # Conditional после analyzer
    def route_after_analyzer(state):
        if state.get("user_feedback") == "incorrect":
            # Повторный анализ
            if state.get("retry_count", 0) < 3:
                return "analyzer"
            else:
                logger.error("Max retry count reached")
                return END
        elif state.get("user_feedback") == "correct":
            return "file_writer"
        else:
            # Ожидание feedback
            return "awaiting_feedback"
    
    workflow.add_conditional_edges(
        "analyzer",
        route_after_analyzer,
        {
            "analyzer": "analyzer",
            "file_writer": "file_writer",
            "awaiting_feedback": END,  # Wait for user input
            END: END
        }
    )
    
    workflow.add_edge("file_writer", END)
    
    return workflow.compile()


# Новые агенты:

async def api_tool_agent(state: ClientAnalysisStateV2) -> Dict:
    """
    Agent 1: Параллельный вызов всех API.
    
    Вызывает DaData, Casebook, InfoSphere параллельно.
    Возвращает агрегированный JSON.
    """
    inn = state["inn"]
    
    # Parallel API calls
    dadata_task = asyncio.create_task(fetch_from_dadata(inn))
    casebook_task = asyncio.create_task(fetch_from_casebook(inn))
    infosphere_task = asyncio.create_task(fetch_from_infosphere(inn))
    
    results = await asyncio.gather(
        dadata_task, casebook_task, infosphere_task,
        return_exceptions=True
    )
    
    api_data = {
        "dadata": results[0] if not isinstance(results[0], Exception) else {"error": str(results[0]), "status": "failed"},
        "casebook": results[1] if not isinstance(results[1], Exception) else {"error": str(results[1]), "status": "failed"},
        "infosphere": results[2] if not isinstance(results[2], Exception) else {"error": str(results[2]), "status": "failed"},
    }
    
    return {
        "api_data": api_data,
        "current_step": "orchestrating"
    }


async def orchestrator_agent_v2(state: ClientAnalysisStateV2) -> Dict:
    """
    Agent 2: Извлекает client_name из API data.
    
    Анализирует api_data, извлекает название компании.
    Формирует поисковые запросы для Perplexity/Tavily.
    """
    api_data = state["api_data"]
    
    # Извлекаем client_name из DaData (primary source)
    client_name = state.get("client_name")
    
    if not client_name and api_data.get("dadata", {}).get("status") == "success":
        dadata_info = api_data["dadata"]["data"]
        client_name = dadata_info.get("name", {}).get("short_with_opf", "")
    
    if not client_name:
        client_name = "Unknown Company"
    
    # Формируем поисковые запросы
    search_queries = {
        "positive": [
            f"{client_name} достижения награды",
            f"{client_name} успешные проекты",
            f"ИНН {state['inn']} положительные отзывы"
        ],
        "negative": [
            f"{client_name} судебные дела иски",
            f"{client_name} долги задолженности",
            f"ИНН {state['inn']} негативные отзывы скандалы"
        ]
    }
    
    return {
        "client_name": client_name,
        "search_intents": search_queries,
        "current_step": "searching"
    }


async def search_agent(state: ClientAnalysisStateV2) -> Dict:
    """
    Agent 3: Параллельный поиск через Perplexity и Tavily.
    
    Выполняет positive/negative поиск.
    Добавляет результаты в JSON.
    """
    client_name = state["client_name"]
    queries = state.get("search_intents", {})
    
    # Initialize clients
    from app.services.perplexity_client import PerplexityClient
    from app.services.tavily_client import TavilyClient
    
    perplexity = PerplexityClient.get_instance()
    tavily = TavilyClient.get_instance()
    
    # Parallel search
    positive_queries = queries.get("positive", [])
    negative_queries = queries.get("negative", [])
    
    # Perplexity searches
    perp_tasks = [perplexity.search(q) for q in positive_queries + negative_queries]
    
    # Tavily searches  
    tavily_tasks = [tavily.search(q, max_results=5) for q in positive_queries + negative_queries]
    
    perp_results = await asyncio.gather(*perp_tasks, return_exceptions=True)
    tavily_results = await asyncio.gather(*tavily_tasks, return_exceptions=True)
    
    search_data = {
        "perplexity": {
            "positive": perp_results[:len(positive_queries)],
            "negative": perp_results[len(positive_queries):],
            "status": "success" if not any(isinstance(r, Exception) for r in perp_results) else "partial"
        },
        "tavily": {
            "positive": tavily_results[:len(positive_queries)],
            "negative": tavily_results[len(positive_queries):],
            "status": "success" if not any(isinstance(r, Exception) for r in tavily_results) else "partial"
        }
    }
    
    return {
        "search_data": search_data,
        "current_step": "analyzing"
    }


async def report_analyzer_agent_v2(state: ClientAnalysisStateV2) -> Dict:
    """
    Agent 4: Создание отчета с указанием источников.
    
    Анализирует api_data + search_data.
    Создает отчет с явным указанием источников.
    Если данных нет - указывает "данные не получены".
    """
    from app.agents.llm_manager import get_llm_manager
    
    api_data = state["api_data"]
    search_data = state.get("search_data", {})
    user_comment = state.get("user_comment", "")
    previous_report = state.get("previous_report")
    
    # Формируем контекст для LLM
    sources_summary = []
    
    # API sources
    for source, data in api_data.items():
        if data.get("status") == "success":
            sources_summary.append(f"✅ {source.upper()}: данные получены")
        else:
            sources_summary.append(f"❌ {source.upper()}: данные не получены ({data.get('error', 'unknown error')})")
    
    # Search sources
    for source, data in search_data.items():
        status = data.get("status", "failed")
        sources_summary.append(f"{'✅' if status == 'success' else '⚠️'} {source.upper()}: {status}")
    
    prompt = f"""
Создай подробный отчет по анализу клиента: {state['client_name']} (ИНН: {state['inn']})

ИСТОЧНИКИ ДАННЫХ:
{chr(10).join(sources_summary)}

ДАННЫЕ API:
{api_data}

РЕЗУЛЬТАТЫ ПОИСКА:
{search_data}

{"ПРОШЛЫЙ ОТЧЕТ (для контекста):" + str(previous_report) if previous_report else ""}

{"КОММЕНТАРИЙ ПОЛЬЗОВАТЕЛЯ (что исправить):" + user_comment if user_comment else ""}

ТРЕБОВАНИЯ К ОТЧЕТУ:
1. В отчете ОБЯЗАТЕЛЬНО указать источники для каждого факта
2. Если данные от какого-то источника не получены - явно указать это
3. Оценить риски на основе доступных данных
4. Создать структурированный отчет в JSON формате

ФОРМАТ ОТЧЕТА:
{{
  "metadata": {{
    "client_name": "...",
    "inn": "...",
    "analysis_date": "...",
    "sources_used": ["dadata", "casebook", ...]
  }},
  "summary": "Краткое резюме...",
  "data_sources_status": {{
    "dadata": "success|failed",
    "casebook": "success|failed",
    ...
  }},
  "risk_assessment": {{
    "score": 0-100,
    "level": "low|medium|high|critical",
    "factors": ["..."]
  }},
  "findings": [
    {{
      "category": "company_info|court_cases|negative_info|positive_info",
      "source": "dadata|casebook|perplexity|tavily",
      "summary": "...",
      "details": "..."
    }}
  ],
  "recommendations": ["..."]
}}
"""
    
    llm_manager = get_llm_manager()
    report_text = await llm_manager.ainvoke(prompt)
    
    # Parse JSON from LLM response
    import json
    try:
        report = json.loads(report_text)
    except:
        # Fallback если LLM вернул не JSON
        report = {
            "metadata": {"client_name": state["client_name"], "inn": state["inn"]},
            "summary": report_text,
            "error": "Failed to parse JSON from LLM"
        }
    
    return {
        "report": report,
        "current_step": "awaiting_feedback",  # Ждем feedback от пользователя
        "retry_count": state.get("retry_count", 0) + 1
    }


async def file_writer_agent_v2(state: ClientAnalysisStateV2) -> Dict:
    """
    Agent 5: Сохранение отчета в Tarantool и генерация PDF.
    
    Вызывается только если user_feedback == "correct".
    """
    from app.storage.tarantool import TarantoolClient
    from app.utility.pdf_generator import generate_pdf_report
    
    report = state["report"]
    session_id = state["session_id"]
    
    # Сохраняем в Tarantool
    client = await TarantoolClient.get_instance()
    reports_repo = client.get_reports_repository()
    
    report_id = await reports_repo.create({
        "inn": state["inn"],
        "client_name": state["client_name"],
        "report_data": report
    })
    
    # Генерируем PDF
    pdf_path = f"reports/{session_id}.pdf"
    generate_pdf_report(report, pdf_path)
    
    logger.info(f"Report saved: {report_id}, PDF: {pdf_path}")
    
    return {
        "saved_files": {
            "report_id": report_id,
            "pdf_path": pdf_path
        },
        "current_step": "completed"
    }
```

#### Файлы для создания:
1. `/workspace/app/agents/client_workflow_v2.py` - новый workflow
2. `/workspace/app/agents/api_tool_agent.py` - agent для API calls
3. `/workspace/app/agents/search_agent.py` - agent для Perplexity/Tavily
4. Обновить: `orchestrator.py`, `report_analyzer.py`, `file_writer.py`

**Оценка времени:** 2-3 часа

---

### 🔴 ЗАДАЧА 2: MCP Server на FastMCP (КРИТИЧНО)

#### Архитектурное решение:

```python
# /workspace/app/mcp_server/server_fastmcp.py

from fastmcp import FastMCP

# Создаем MCP server
mcp = FastMCP("Client Analysis MCP Server")


@mcp.tool()
async def save_report_to_file(
    report_id: str,
    format: str = "pdf"
) -> str:
    """
    Сохранить отчет в файл.
    
    Args:
        report_id: ID отчета в Tarantool
        format: Формат файла (pdf, json, md)
        
    Returns:
        Путь к сохраненному файлу
    """
    from app.storage.tarantool import TarantoolClient
    from app.utility.pdf_generator import generate_pdf_report
    
    client = await TarantoolClient.get_instance()
    reports_repo = client.get_reports_repository()
    
    report = await reports_repo.get(report_id)
    if not report:
        return f"Error: Report {report_id} not found"
    
    file_path = f"reports/{report_id}.{format}"
    
    if format == "pdf":
        generate_pdf_report(report["report_data"], file_path)
    elif format == "json":
        import json
        with open(file_path, "w") as f:
            json.dump(report, f, indent=2, ensure_ascii=False)
    elif format == "md":
        # Generate markdown
        pass
    
    return file_path


@mcp.tool()
async def read_report_from_tarantool(report_id: str) -> dict:
    """Прочитать отчет из Tarantool."""
    from app.storage.tarantool import TarantoolClient
    
    client = await TarantoolClient.get_instance()
    reports_repo = client.get_reports_repository()
    
    report = await reports_repo.get(report_id)
    return report if report else {"error": "Report not found"}


@mcp.tool()
async def list_reports(limit: int = 50) -> list:
    """Список всех отчетов."""
    from app.storage.tarantool import TarantoolClient
    
    client = await TarantoolClient.get_instance()
    reports_repo = client.get_reports_repository()
    
    reports = await reports_repo.list(limit=limit)
    return reports


@mcp.tool()
async def search_reports(inn: str) -> list:
    """Поиск отчетов по ИНН."""
    from app.storage.tarantool import TarantoolClient
    
    client = await TarantoolClient.get_instance()
    reports_repo = client.get_reports_repository()
    
    reports = await reports_repo.get_reports_by_inn(inn)
    return reports


@mcp.tool()
async def get_cache_stats() -> dict:
    """Статистика кэша."""
    from app.storage.tarantool import TarantoolClient
    
    client = await TarantoolClient.get_instance()
    cache_repo = client.get_cache_repository()
    
    stats = await cache_repo.get_stats()
    return stats


@mcp.tool()
async def get_system_health() -> dict:
    """Здоровье системы."""
    from app.storage.tarantool import TarantoolClient
    from app.agents.llm_manager import get_llm_manager
    
    client = await TarantoolClient.get_instance()
    llm_manager = get_llm_manager()
    
    health = {
        "tarantool": "up",
        "llm_providers": llm_manager.get_provider_status(),
        "cache_stats": await client.get_cache_repository().get_stats()
    }
    
    return health


# Запуск MCP server
if __name__ == "__main__":
    mcp.run()
```

#### Интеграция в main.py:

```python
# В lifespan добавить:
from app.mcp_server.server_fastmcp import mcp

# Startup
mcp_task = asyncio.create_task(mcp.run_async())

# Shutdown
mcp_task.cancel()
```

**Оценка времени:** 1 час

---

### 🔴 ЗАДАЧА 3: RabbitMQ + Отложенные задания (КРИТИЧНО)

#### Архитектурное решение:

Уже есть:
- ✅ `SchedulerService` для отложенных заданий (APScheduler)
- ✅ RabbitMQ в `docker-compose.yml`
- ⏳ Нужна интеграция FastStream

#### Файлы для создания:

```python
# /workspace/app/queue/broker.py
from faststream import FastStream
from faststream.rabbit import RabbitBroker

from app.config import settings

broker = RabbitBroker(
    f"amqp://{settings.queue.rabbitmq_user}:{settings.queue.rabbitmq_password}"
    f"@{settings.queue.rabbitmq_host}:{settings.queue.rabbitmq_port}/"
)

app = FastStream(broker)


# /workspace/app/queue/handlers.py
from faststream.rabbit import RabbitRouter

router = RabbitRouter()

@router.subscriber("client.analyze")
async def handle_analyze_client(message: dict):
    """Handle client analysis requests from RabbitMQ."""
    from app.agents.client_workflow_v2 import run_client_analysis_batch
    
    result = await run_client_analysis_batch(
        client_name=message["client_name"],
        inn=message["inn"],
        additional_notes=message.get("additional_notes", "")
    )
    
    return result


@router.subscriber("report.generate_pdf")
async def handle_generate_pdf(message: dict):
    """Handle PDF generation requests."""
    from app.utility.pdf_generator import generate_pdf_report
    
    report_id = message["report_id"]
    # ... generate PDF ...


# /workspace/app/queue/publishers.py
async def publish_analyze_client(client_name: str, inn: str):
    """Publish analyze client task to RabbitMQ."""
    from app.queue.broker import broker
    
    await broker.publish(
        {
            "client_name": client_name,
            "inn": inn,
            "timestamp": time.time()
        },
        queue="client.analyze"
    )


# API endpoint для вызова через RabbitMQ
@agent_router.post("/analyze-client/async-queue")
async def analyze_client_via_queue(request: AnalyzeClientRequest):
    """Async analysis via RabbitMQ."""
    from app.queue.publishers import publish_analyze_client
    
    await publish_analyze_client(request.client_name, request.inn)
    
    return {
        "status": "queued",
        "message": "Analysis task queued in RabbitMQ"
    }
```

#### Отложенные задания через API:

```python
# Уже реализовано! ✅
POST /scheduler/schedule-analysis
{
  "client_name": "ООО Ромашка",
  "inn": "1234567890",
  "delay_minutes": 30
}
```

**Оценка времени:** 2 часа

---

## 📊 ИТОГОВАЯ ОЦЕНКА ВРЕМЕНИ

| Задача | Время | Приоритет |
|--------|-------|-----------|
| ✅ Декоратор кэширования | DONE | 🔴 |
| ✅ Удаление файлов | DONE | 🟢 |
| ⏳ Исправление Workflow | 2-3 часа | 🔴 КРИТИЧНО |
| ⏳ MCP Server | 1 час | 🔴 КРИТИЧНО |
| ⏳ RabbitMQ Integration | 2 часа | 🔴 КРИТИЧНО |
| **ИТОГО** | **5-6 часов** | |

---

## 🎯 РЕКОМЕНДАЦИИ ПО ВЫПОЛНЕНИЮ

### Вариант А: Поэтапная реализация (рекомендуется)
1. **День 1:** Исправление Workflow (3 часа)
2. **День 2:** MCP Server + RabbitMQ (3 часа)

### Вариант Б: Параллельная разработка (быстрее)
- **Backend Developer 1:** Workflow
- **Backend Developer 2:** MCP Server
- **Backend Developer 3:** RabbitMQ

---

## 📝 СЛЕДУЮЩИЕ ШАГИ

1. **Создать новые файлы агентов:**
   - `client_workflow_v2.py`
   - `api_tool_agent.py`
   - `search_agent.py`

2. **Обновить существующие агенты:**
   - `orchestrator.py` → `orchestrator_agent_v2()`
   - `report_analyzer.py` → `report_analyzer_agent_v2()`
   - `file_writer.py` → `file_writer_agent_v2()`

3. **Реализовать MCP Server:**
   - `mcp_server/server_fastmcp.py`
   - Интеграция в `main.py`

4. **Реализовать RabbitMQ:**
   - `queue/broker.py`
   - `queue/handlers.py`
   - `queue/publishers.py`
   - Обновить `main.py` lifespan

5. **Обновить API endpoints:**
   - `POST /agent/analyze-client/async-queue`
   - Поддержка feedback (`POST /agent/feedback`)

6. **Тестирование:**
   - Unit tests для новых агентов
   - Integration tests для RabbitMQ
   - E2E tests для workflow

---

## ✅ ЧТО УЖЕ ГОТОВО К ИСПОЛЬЗОВАНИЮ

1. ✅ **Scheduler Service** - отложенные задания работают
2. ✅ **Декоратор кэширования** - применен в fetch_data.py
3. ✅ **LLMManager** - fallback стратегия готова
4. ✅ **Repository Pattern** - Tarantool repositories работают
5. ✅ **Централизованная конфигурация** - Vault/Env/YAML
6. ✅ **Структурное логирование** - метрики, трейсинг

---

## 🏁 СТАТУС

**Прогресс:** 60% готовности

**Готово:**
- ✅ Infrastructure (Config, Storage, Logging)
- ✅ Caching & Decorators
- ✅ Scheduler Service

**В работе:**
- ⏳ Workflow Refactoring (критично)
- ⏳ MCP Server (критично)
- ⏳ RabbitMQ Integration (критично)

**Ожидает:**
- ⏳ Streamlit UI improvements
- ⏳ PDF editing in browser
- ⏳ Monitoring (Prometheus/Grafana)

---

**Готов продолжить реализацию по вашему указанию!** 🚀
