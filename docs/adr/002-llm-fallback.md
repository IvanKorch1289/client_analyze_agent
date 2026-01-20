# ADR-002: Стратегия LLM Fallback

**Статус:** Принято
**Дата:** 2026-01-14
**Авторы:** Development Team

## Контекст

Система критически зависит от LLM для:
- Генерации поисковых запросов (orchestrator)
- Анализа рисков и создания отчётов (report_analyzer)
- Форматирования выводов

Облачные LLM API могут быть:
- Временно недоступны
- Перегружены (rate limits)
- Медленны в пиковые часы

## Рассмотренные альтернативы

### 1. Единый провайдер (OpenAI/Anthropic)
**Плюсы:**
- Простота интеграции
- Консистентное качество

**Минусы:**
- Single point of failure
- Зависимость от одного вендора

### 2. Локальные LLM (Ollama, llama.cpp)
**Плюсы:**
- Нет зависимости от облака
- Приватность данных

**Минусы:**
- Требуют мощного GPU
- Качество ниже облачных моделей
- Сложность развертывания

### 3. Multi-provider Fallback
**Плюсы:**
- Высокая доступность
- Выбор оптимального провайдера
- Разные ценовые категории

**Минусы:**
- Сложность интеграции
- Разное качество ответов
- Необходимость унификации API

## Решение

Выбрана **Multi-provider Fallback стратегия** с приоритизацией.

### Порядок провайдеров:

```
1. OpenRouter (Primary)
   ├─ Model: anthropic/claude-3.5-sonnet
   ├─ Качество: ⭐⭐⭐⭐⭐
   └─ Timeout: 60s

2. HuggingFace (Fallback #1)
   ├─ Model: Meta-Llama-3.1-70B-Instruct
   ├─ Качество: ⭐⭐⭐⭐
   └─ Timeout: 90s

3. GigaChat (Fallback #2)
   ├─ Model: GigaChat-Pro
   ├─ Качество: ⭐⭐⭐
   └─ Timeout: 120s

4. YandexGPT (Fallback #3)
   ├─ Model: YandexGPT-Lite
   ├─ Качество: ⭐⭐⭐
   └─ Timeout: 120s
```

### Логика переключения:

```python
for provider in fallback_order:
    if not provider_status[provider]:
        continue  # Пропускаем недоступные

    try:
        response = await provider.ainvoke(prompt)
        provider_status[provider] = True
        return response
    except Exception:
        provider_status[provider] = False
        continue

raise AllProvidersFailedError()
```

### PII Protection:

Перед отправкой в любой LLM выполняется маскирование PII:
- ИНН → `[INN_MASKED_1]`
- ФИО → `[PERSON_MASKED_1]`
- Адреса → `[ADDRESS_MASKED_1]`

После получения ответа PII восстанавливается.

## Последствия

### Позитивные:
- 99.9% availability (при независимых сбоях провайдеров)
- Автоматическое переключение без участия пользователя
- Соответствие 152-ФЗ (PII не уходит в облако)
- Prometheus метрики для мониторинга fallbacks

### Негативные:
- Разное качество ответов от разных провайдеров
- Необходимость поддержки нескольких API ключей
- Сложность тестирования всех путей

## Метрики

Мониторинг через Prometheus:
- `client_llm_requests_total{provider, status}`
- `client_llm_latency_seconds{provider}`
- `client_llm_fallbacks_total{from_provider, to_provider}`

## Связанные документы
- `app/agents/llm_manager.py` - Реализация
- `app/shared/pii_protection.py` - PII маскирование
- `docs/adr/001-tarantool-cache.md` - Кэширование LLM ответов
