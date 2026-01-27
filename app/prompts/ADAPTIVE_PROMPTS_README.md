# Система адаптивных промптов на основе фидбеков

## Обзор

Система автоматически дорабатывает промпты для агентов на основе анализа последних 10 фидбеков пользователя. Это позволяет избежать повторения одних и тех же ошибок в новых анализах.

## Архитектура

```
┌─────────────────┐
│ Пользователь    │
│ отправляет      │
│ фидбек          │
└────────┬────────┘
         │
         ▼
┌─────────────────────┐
│ FeedbackRepository  │ ◄── Сохранение в Tarantool
│ (хранилище)         │
└─────────┬───────────┘
          │
          │ Последние 10 фидбеков
          ▼
┌──────────────────────────┐
│ AdaptivePromptEngine     │
│                          │
│ 1. Анализ паттернов      │
│ 2. Генерация инструкций  │ ◄── Использует LLM
│ 3. Доработка промпта     │
└──────────┬───────────────┘
           │
           │ Адаптированный промпт
           ▼
┌──────────────────────┐
│ Orchestrator/Analyzer│ ◄── Агенты используют
│ Agent                │     улучшенный промпт
└──────────────────────┘
```

## Компоненты

### 1. FeedbackRepository (`app/storage/feedback_repository.py`)

**Назначение:** Хранение и получение фидбеков из Tarantool

**Методы:**
- `save(feedback)` - сохранить фидбек
- `get_recent_feedbacks(limit, rating_filter)` - получить последние N фидбеков
- `analyze_feedback_patterns(limit)` - анализ паттернов ошибок

**Схема данных Tarantool:**
```
space: feedbacks
fields:
  1. feedback_id: string (primary key)
  2. report_id: string (indexed)
  3. rating: string (accurate/partially_accurate/inaccurate)
  4. comment: string
  5. focus_areas: string (JSON array)
  6. client_name: string
  7. inn: string
  8. timestamp: number (indexed)
```

### 2. AdaptivePromptEngine (`app/prompts/adaptive_prompt_engine.py`)

**Назначение:** Генерация адаптированных промптов на основе истории фидбеков

**Методы:**
- `get_adaptive_prompt(template_name, params, session_id)` - получить адаптированный промпт
- `_generate_adaptive_instructions(...)` - использует LLM для генерации инструкций
- `clear_cache(session_id)` - очистить кэш

**Алгоритм работы:**
1. Получить базовый промпт из PromptManager
2. Загрузить последние 10 фидбеков с негативными/частично точными оценками
3. Проанализировать паттерны (частые проблемы, области внимания)
4. Использовать LLM для генерации конкретных инструкций
5. Добавить инструкции к базовому промпту
6. Кэшировать результат для сессии

## Интеграция

### Шаг 1: Обновить Tarantool Client

```python
# app/storage/tarantool.py

from app.storage.feedback_repository import FeedbackRepository

class TarantoolClient:
    async def init(self):
        # ... существующий код ...

        # Инициализировать репозиторий фидбеков
        self.feedback_repo = FeedbackRepository(self.conn)
        await self.feedback_repo.init_space()

    def get_feedback_repository(self) -> FeedbackRepository:
        """Получить репозиторий фидбеков."""
        return self.feedback_repo
```

### Шаг 2: Обновить API endpoint для фидбеков

```python
# app/api/routes/agent.py

@agent_router.post("/feedback")
async def submit_feedback(request: Request, data: FeedbackRequest):
    """Отправить фидбек и сохранить в БД."""

    # ... существующий код получения original_report ...

    # НОВОЕ: Сохранить фидбек в БД
    tarantool = await TarantoolClient.get_instance()
    feedback_repo = tarantool.get_feedback_repository()

    feedback_record = {
        "feedback_id": f"fb_{int(time.time() * 1000)}",
        "report_id": data.report_id,
        "rating": data.rating,
        "comment": data.comment,
        "focus_areas": data.focus_areas or [],
        "client_name": original_report.get("client_name", ""),
        "inn": original_report.get("inn", ""),
        "timestamp": time.time(),
    }

    await feedback_repo.save(feedback_record)

    # ... остальной код переанализа ...
```

### Шаг 3: Использовать в агентах

```python
# app/agents/orchestrator.py

from app.prompts.adaptive_prompt_engine import AdaptivePromptEngine
from app.storage.tarantool import TarantoolClient

async def orchestrator_agent(state: Dict[str, Any]) -> Dict[str, Any]:
    client_name = state.get("client_name", "")
    additional_notes = state.get("additional_notes", "")
    session_id = state.get("session_id", "")

    # НОВОЕ: Получить адаптированный промпт
    tarantool = await TarantoolClient.get_instance()
    feedback_repo = tarantool.get_feedback_repository()

    adaptive_engine = AdaptivePromptEngine.get_instance()
    adaptive_engine.feedback_repo = feedback_repo

    prompt = await adaptive_engine.get_adaptive_prompt(
        template_name="orchestrator",
        params={
            "client_name": client_name,
            "additional_notes": additional_notes or "Нет дополнительных указаний"
        },
        session_id=session_id,
        feedback_lookback=10  # Последние 10 фидбеков
    )

    # Использовать адаптированный промпт для LLM
    llm_manager = LLMManager.get_instance()
    response = await llm_manager.ainvoke(
        prompt=prompt,
        provider=LLMProvider.OPENROUTER,
    )

    # ... обработка ответа ...
```

### Шаг 4: Аналогично для analyzer

```python
# app/agents/report_analyzer.py

async def report_analyzer_agent(state: Dict[str, Any]) -> Dict[str, Any]:
    session_id = state.get("session_id", "")

    # Получить адаптированный промпт
    tarantool = await TarantoolClient.get_instance()
    feedback_repo = tarantool.get_feedback_repository()

    adaptive_engine = AdaptivePromptEngine.get_instance()
    adaptive_engine.feedback_repo = feedback_repo

    prompt = await adaptive_engine.get_adaptive_prompt(
        template_name="analyzer",
        params={
            "client_name": state.get("client_name", ""),
            "search_results": state.get("search_results", []),
            # ... другие параметры ...
        },
        session_id=session_id,
        feedback_lookback=10
    )

    # ... использовать промпт ...
```

## Примеры использования

### Пример 1: Базовое использование

```python
from app.prompts.adaptive_prompt_engine import AdaptivePromptEngine
from app.storage.tarantool import TarantoolClient

async def analyze_with_adaptive_prompts():
    # Получить экземпляры
    tarantool = await TarantoolClient.get_instance()
    feedback_repo = tarantool.get_feedback_repository()

    adaptive_engine = AdaptivePromptEngine()
    adaptive_engine.feedback_repo = feedback_repo

    # Получить адаптированный промпт
    prompt = await adaptive_engine.get_adaptive_prompt(
        template_name="orchestrator",
        params={"client_name": "Газпром"},
        session_id="session_123"
    )

    print("Адаптированный промпт:", prompt)
```

### Пример 2: Анализ паттернов фидбеков

```python
async def analyze_feedback_patterns():
    tarantool = await TarantoolClient.get_instance()
    feedback_repo = tarantool.get_feedback_repository()

    # Получить анализ последних 10 фидбеков
    patterns = await feedback_repo.analyze_feedback_patterns(limit=10)

    print("Частые проблемы:", patterns["common_issues"])
    print("Распределение оценок:", patterns["rating_distribution"])
    print("Примеры комментариев:", patterns["sample_comments"])
```

### Пример 3: Сохранение фидбека

```python
async def save_user_feedback():
    tarantool = await TarantoolClient.get_instance()
    feedback_repo = tarantool.get_feedback_repository()

    feedback = {
        "feedback_id": "fb_1234567890",
        "report_id": "report_123",
        "rating": "inaccurate",
        "comment": "Не учтены судебные дела за 2024 год",
        "focus_areas": ["court_cases", "legal_issues"],
        "client_name": "ООО Ромашка",
        "inn": "7707083893",
        "timestamp": time.time()
    }

    feedback_id = await feedback_repo.save(feedback)
    print(f"Фидбек сохранен: {feedback_id}")
```

## Как работает адаптация промптов

### Пример адаптированного промпта

**Базовый промпт (orchestrator v2.0):**
```
Ты - эксперт по анализу бизнеса и поиску информации о компаниях.

Компания для анализа: Газпром
Дополнительные указания: Нет дополнительных указаний

Сгенерируй 3-5 специфичных поисковых запроса...
```

**Адаптированный промпт (с учетом фидбеков):**
```
Ты - эксперт по анализу бизнеса и поиску информации о компаниях.

Компания для анализа: Газпром
Дополнительные указания: Нет дополнительных указаний

Сгенерируй 3-5 специфичных поисковых запроса...

================================================================================
🔄 АДАПТИВНЫЕ ИНСТРУКЦИИ (на основе анализа последних фидбеков):
================================================================================

На основе анализа последних 10 фидбеков выявлены следующие проблемы:

1. КРИТИЧЕСКИ ВАЖНО: Всегда включай поиск судебных дел за последние 2 года,
   даже если пользователь не указал это явно. В 7 из 10 случаев пользователи
   жаловались на отсутствие информации о судебных делах.

2. Уделяй особое внимание финансовым показателям: в 5 случаях пользователи
   отмечали недостаточную глубину анализа финансового состояния.

3. При поиске информации о репутации компании ищи КОНКРЕТНЫЕ факты и цифры,
   а не общие фразы. Пользователи жалуются на абстрактность.

4. Всегда проверяй наличие связей с государственными контрактами и их объемы.

5. Обращай внимание на негативные упоминания в СМИ за последний год,
   особенно связанные с невыполнением обязательств.

================================================================================
⚠️ КРИТИЧЕСКИ ВАЖНО: Эти инструкции основаны на реальных ошибках в предыдущих
анализах. Следуй им СТРОГО, чтобы избежать повторения тех же проблем.
================================================================================
```

## Преимущества системы

1. **Автоматическое обучение**: Система учится на ошибках без ручного программирования
2. **Персонализация**: Адаптация под паттерны ошибок конкретного пользователя
3. **Непрерывное улучшение**: Каждый новый фидбек улучшает качество будущих анализов
4. **Прозрачность**: Пользователь видит, какие инструкции добавлены на основе фидбеков
5. **Масштабируемость**: Работает для любых агентов (orchestrator, analyzer, и т.д.)

## Мониторинг и отладка

### Логи

Система логирует:
- Сохранение фидбеков: `feedback_saved`
- Генерацию адаптивных промптов: `adaptive_prompt_generated`
- Анализ паттернов: количество учтенных фидбеков, частые проблемы

### Метрики

Рекомендуется отслеживать:
- Количество фидбеков в БД
- Распределение рейтингов (accurate/partially_accurate/inaccurate)
- Частоту использования адаптивных промптов
- Улучшение качества после внедрения адаптивных инструкций

## Настройка

### Параметры AdaptivePromptEngine

```python
adaptive_engine = AdaptivePromptEngine()

# Количество фидбеков для анализа (по умолчанию: 10)
prompt = await adaptive_engine.get_adaptive_prompt(
    ...,
    feedback_lookback=10  # Изменить на 5, 15, 20 и т.д.
)
```

### Фильтрация фидбеков

```python
# Получить только фидбеки с оценкой "inaccurate"
feedbacks = await feedback_repo.get_recent_feedbacks(
    limit=10,
    rating_filter="inaccurate"  # или "partially_accurate"
)
```

## Будущие улучшения

1. **Персональные профили**: Отдельные адаптации для разных пользователей
2. **A/B тестирование**: Сравнение эффективности разных версий инструкций
3. **Метрики качества**: Автоматическая оценка улучшения после адаптации
4. **UI для просмотра истории**: Интерфейс для просмотра адаптаций промптов
5. **Экспорт лучших практик**: Автоматическое создание новых версий базовых промптов

## Заключение

Система адаптивных промптов на основе фидбеков - это мощный инструмент
для непрерывного улучшения качества анализов. Она превращает каждую
ошибку в урок и автоматически предотвращает её повторение в будущем.
