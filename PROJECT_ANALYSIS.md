# Аналитический отчёт: Система анализа контрагентов

**Дата:** 2026-02-04
**Статус:** MVP готов, требуется доработка для production

---

## 1. Краткий обзор проекта

### Миссия
Автоматизированная проверка и оценка рисков контрагентов/клиентов с использованием LLM, внешних источников данных и обязательным маскированием персональных данных (152-ФЗ).

### 6 ключевых модулей

| # | Модуль | Описание | Статус |
|---|--------|----------|--------|
| 1 | **Агент анализа** | LangGraph workflow: Orchestrator → DataCollector → ReportAnalyzer → FileWriter. Сбор данных из 5+ источников, LLM-анализ с CoT, risk score 0-100, PDF/JSON отчёт | Реализован |
| 2 | **REST API агента** | FastAPI endpoints для запуска анализа, отчётов, данных, аналитики, scheduler | Реализован |
| 3 | **LLM API** | Async LLM запросы с webhook callback, 4 провайдера с fallback, маскирование PII, endpoint для тестирования маскирования | Реализован |
| 4 | **RabbitMQ** | 3 очереди (analysis, cache, llm) через FastStream, DLQ, correlation_id, fallback на background tasks | Реализован |
| 5 | **RAG система** | ChromaDB: семантический поиск похожих отчётов и документов, обогащение LLM-контекста, graceful degradation | Реализован |
| 6 | **Браузерный UI** | Streamlit single-page: 8 вкладок, админ-режим, HTTP-клиент к backend | Реализован |

### Безопасность PII (сквозная)
**Критическое требование:** персональные данные клиента маскируются ПЕРЕД отправкой в любую внешнюю LLM. Реализовано через Microsoft Presidio + 7 кастомных RU-распознавателей. При ошибке маскирования — блокировка LLM-вызова (`PIIMaskingError`).

---

## 2. Анализ текущего состояния по модулям

### 2.1. Агент анализа клиента (оценка: 8/10)

**Сильные стороны:**
- Чёткое разделение ответственности: 4 агента с single responsibility
- Registry pattern для коллекторов — легко добавить новый источник данных
- Параллельный сбор из InfoSphere, Casebook, Perplexity, Tavily
- Chain-of-Thought в Report Analyzer для прозрачности LLM-решений
- Fallback на ручной расчёт риска при недоступности LLM

**Проблемы:**
- Дублирование логики расчёта рисков: `risk_calculator.py` и `report_analyzer._calculate_risk_fallback()`
- Hardcoded thinking messages в `client_workflow.py`
- `_run_coroutine_sync()` в LLMManager создаёт daemon-потоки — потенциальный deadlock

### 2.2. REST API (оценка: 7/10)

**Сильные стороны:**
- Версионированный API (`/api/v1/...`)
- Rate limiting per-route через SlowAPI
- Стандартизированный формат ответов
- Centralized error handling
- SSE streaming для прогресса анализа

**Проблемы:**
- Legacy endpoints (`/agent/...`, `/data/...`) всё ещё существуют рядом с версионированными
- API_REFERENCE.md не автогенерируется — может рассинхрониться с кодом
- Нет OpenAPI-тегов для группировки в Swagger

### 2.3. LLM API (оценка: 8/10)

**Сильные стороны:**
- 4 провайдера с автоматическим fallback (OpenRouter → HuggingFace → GigaChat → YandexGPT)
- Автоматическое PII маскирование в ДВУХ местах: `LLMManager.ainvoke()` и `_process_llm_request_background()`
- Кэширование LLM-ответов (TTL 1 час)
- Audit logging всех LLM-вызовов для compliance
- Health check per-provider + сброс статуса
- Endpoint для тестирования PII маскирования (`/llm/mask-text`)
- Проверка доступности моделей OpenRouter с кэшем

**Проблемы:**
- Jay Guard proxy — отдельная точка отказа, не покрыта circuit breaker
- `invoke()` (синхронный) использует `_run_coroutine_sync()` — потенциальный deadlock при вызове из async context
- Нет retry с backoff при 429 (rate limit) от LLM провайдеров — сразу fallback

### 2.4. RabbitMQ интеграция (оценка: 7/10)

**Сильные стороны:**
- DLQ с Dead Letter Exchange — failed сообщения не теряются
- Correlation ID для отслеживания запрос-ответ
- Graceful fallback на background tasks при недоступности RabbitMQ
- TTL и delivery limits для защиты от зависших сообщений
- DLQ handlers сохраняют failed messages в Tarantool

**Проблемы:**
- PII маскирование в broker handler (`handle_async_llm_request`) идёт через LLMManager, но напрямую не вызывает `mask_pii()` — зависит от того, вызывается ли `ainvoke()` или `ainvoke_with_provider()`
- Нет retry policy с exponential backoff — только DLQ после N попыток
- `MAX_DELIVERY_ATTEMPTS` берётся из env var, но не из settings
- Callback URL в `handle_failed_llm` отправляется без retry — один POST и всё

### 2.5. RAG система (оценка: 6/10)

**Сильные стороны:**
- Graceful degradation — анализ работает без RAG
- Поиск похожих отчётов + документов из базы знаний
- Лимит RAG-контекста (6000 символов) — не перегружает промпт
- Прозрачное логирование количества найденных результатов

**Проблемы:**
- ChromaDB используется in-process — не масштабируется при нагрузке
- Embedding service — отдельный модуль, но его реализация не видна как отдельный сервис
- Нет метрик качества RAG (relevancy, precision)
- Нет UI для управления загруженными документами (кроме вкладки RAG в Streamlit)
- Нет chunk versioning — при обновлении документа старые чанки не удаляются

### 2.6. Браузерный интерфейс (оценка: 6/10)

**Сильные стороны:**
- 8 вкладок покрывают весь функционал
- Админ-режим с X-Auth-Token
- Single-page архитектура через router.py
- CSS кастомизация

**Проблемы:**
- Streamlit ограничен для продакшн-использования (нет мультитенантности, нет RBAC)
- `sys.path` manipulation в `app.py` — хрупкое решение
- Нет WebSocket — обновление статуса через polling
- Нет error boundaries — ошибка в одной вкладке может сломать всё приложение

### 2.7. Безопасность PII (оценка: 8/10)

**Сильные стороны:**
- 7 кастомных распознавателей для российских PII (ИНН, ОГРН, СНИЛС, ФИО, адрес, паспорт, телефон)
- Reversible Pseudonymization с нумерованными псевдонимами
- 3 уровня маскирования (low/medium/high)
- Fail-safe: при ошибке маскирования LLM-вызов блокируется
- Контекстные подсказки для повышения accuracy (слова-маркеры: «директор», «ИНН», «паспорт»)
- spaCy NLP для NER с fallback на меньшую модель

**Проблемы:**
- Score 0.35 для `full_name_pattern` (без отчества) — может пропускать ФИО без контекстных слов
- Regex `\b\d{10}\b` для ИНН ловит любые 10-значные числа — false positives (номера телефонов без кода, даты)
- Нет unit-тестов для edge cases: ФИО в родительном падеже, двойные фамилии, буква Ё
- `IGNORECASE` в Presidio — паттерн `[А-ЯЁ]` будет ловить и строчные буквы
- Нет мониторинга false positive/negative rate в production

---

## 3. Диагностика: сводная таблица рисков

### Технические риски

| Риск | Вероятность | Влияние | Модуль | Описание |
|------|-------------|---------|--------|----------|
| Утечка PII через прямой вызов LLM | Низкая | Критическое | LLM API | Если разработчик вызовет LLM-провайдер напрямую, минуя `LLMManager.ainvoke()` |
| False negative PII маскирования | Средняя | Критическое | PII | ФИО без контекста (score 0.35) или в нестандартном падеже может не распознаться |
| Потеря данных при рестарте | Высокая | Критическое | Storage | In-memory fallback теряет данные |
| Deadlock в sync-async bridge | Средняя | Высокое | LLM API | `_run_coroutine_sync()` создаёт потоки внутри async context |
| LLM rate limiting каскад | Средняя | Высокое | LLM API | При массовых запросах все 4 провайдера возвращают 429, нет backoff |
| Tarantool schema drift | Средняя | Высокое | Storage | Нет миграций — ручное обновление |
| RabbitMQ callback failure | Средняя | Среднее | RabbitMQ | Callback URL вызывается 1 раз без retry |
| RAG stale data | Средняя | Среднее | RAG | Старые чанки не удаляются при обновлении документа |

### Организационные риски

| Риск | Вероятность | Влияние | Описание |
|------|-------------|---------|----------|
| Bus factor = 1 | Высокая | Критическое | Проект ведётся одним разработчиком |
| Устаревание документации | Высокая | Среднее | README и API_REFERENCE могут рассинхрониться |
| Нет staging | Высокая | Высокое | Все тесты на моках, нет промежуточной среды |

---

## 4. План доведения до идеала

### Этап 1: PII-безопасность и Critical Fixes (Приоритет: ВЫСОКИЙ)

**Цель:** Устранить риски утечки PII и критические технические проблемы.

| # | Задача | Модуль | Ожидаемый результат | Метрика |
|---|--------|--------|---------------------|---------|
| 1.1 | Добавить edge-case тесты для PII: ФИО в падежах, двойные фамилии, буква Ё, смешанный RU/EN текст | PII | 0 пропущенных ФИО в типовых сценариях | >95% recall на тестовом dataset |
| 1.2 | Улучшить RU_INN regex — добавить контекстную валидацию (проверка контрольной суммы ИНН) | PII | Снижение false positives для 10-значных чисел | <5% false positive rate |
| 1.3 | Добавить linter-правило: запрет прямого импорта LLM-провайдеров вне `llm_manager.py` | PII/LLM | Невозможно случайно вызвать LLM без PII маскирования | 0 direct LLM imports в codebase |
| 1.4 | Добавить мониторинг PII false positive/negative в Prometheus | PII | Дашборд качества маскирования | Метрики доступны в Grafana |
| 1.5 | Исправить `_run_coroutine_sync()` — использовать `asyncio.run_coroutine_threadsafe()` | LLM API | Нет deadlocks | 0 deadlocks за 30 дней |
| 1.6 | Подключить PostgreSQL для персистентного хранения отчётов | Storage | Нет потерь данных при рестарте | 0 потерь |
| 1.7 | Заменить `asyncio.get_event_loop()` на `asyncio.get_running_loop()` | Код | Нет deprecation warnings | 0 warnings |

**Рекомендации:** SQLAlchemy + Alembic для PostgreSQL, ruff custom rules для запрета direct LLM imports.

---

### Этап 2: Надёжность интеграций (Приоритет: ВЫСОКИЙ)

**Цель:** Повысить устойчивость RabbitMQ, LLM fallback и RAG.

| # | Задача | Модуль | Ожидаемый результат | Метрика |
|---|--------|--------|---------------------|---------|
| 2.1 | Добавить retry с exponential backoff для LLM 429 (rate limit) перед fallback | LLM API | Снижение ненужных fallback на медленные провайдеры | -50% fallback events |
| 2.2 | Добавить retry для callback URL в RabbitMQ handlers (3 попытки, backoff) | RabbitMQ | Callback доставляется при transient failures | >99.5% callback delivery |
| 2.3 | Перенести `MAX_DELIVERY_ATTEMPTS` в settings (из env var) | RabbitMQ | Единообразная конфигурация | Все настройки в settings |
| 2.4 | Добавить PII маскирование в `handle_async_llm_request` напрямую (не через LLMManager) | RabbitMQ/PII | Гарантированное маскирование при обработке через очередь | PII masked в 100% queue messages |
| 2.5 | Добавить chunk versioning в RAG — удаление старых чанков при обновлении документа | RAG | Нет stale data в RAG | 0 duplicate chunks |
| 2.6 | Добавить integration tests с testcontainers (Tarantool, RabbitMQ) | Тесты | Тесты с реальными сервисами | >80% code coverage |
| 2.7 | Внедрить smoke tests в CI/CD (заменить placeholder) | CI/CD | Реальная проверка healthchecks | Smoke tests < 60 сек |

**Рекомендации:** tenacity для retry, testcontainers-python для интеграционных тестов.

---

### Этап 3: Архитектурная чистота (Приоритет: СРЕДНИЙ)

**Цель:** Устранить дублирование, убрать мёртвый код, подготовить к масштабированию.

| # | Задача | Модуль | Ожидаемый результат | Метрика |
|---|--------|--------|---------------------|---------|
| 3.1 | Унифицировать расчёт рисков — единый `RiskCalculator` вместо дублирования | Агент | Один источник правды для risk score | 0 дублирования |
| 3.2 | Удалить мёртвый код: gRPC config, Redis config (или реализовать) | Код | Чистый конфиг без phantom-настроек | 0 мёртвого кода |
| 3.3 | Вынести промпты в файлы с версионированием (yaml/json) | Агент | A/B тестирование промптов | 100% промптов версионированы |
| 3.4 | Устранить circular imports через Dependency Injection | Код | Нет lazy imports ради circular deps | 0 _get_*() lazy import wrappers |
| 3.5 | Ограничить `_search_cache` dict в TarantoolClient (maxlen) | Storage | Нет unbounded memory growth | Кэш < 10000 entries |
| 3.6 | Удалить legacy endpoints или добавить deprecation warnings с redirect | API | Чистый API surface | 0 undocumented legacy endpoints |
| 3.7 | Обновить README — привести в соответствие с фактической структурой | Документация | Документация = код | 100% путей валидны |

**Рекомендации:** dependency-injector, ruff для dead code detection.

---

### Этап 4: Observability и Production Readiness (Приоритет: СРЕДНИЙ)

**Цель:** Подготовка к production-эксплуатации.

| # | Задача | Модуль | Ожидаемый результат | Метрика |
|---|--------|--------|---------------------|---------|
| 4.1 | Настроить OpenTelemetry tracing end-to-end (API → Agent → LLM → Storage) | Все | Полная трассировка запроса | 100% запросов с trace_id |
| 4.2 | Добавить Jaeger/Tempo для визуализации traces | Мониторинг | Визуальная карта зависимостей | MTTR < 15 мин |
| 4.3 | Настроить CD pipeline (GitHub Actions → staging → prod) | CI/CD | Автодеплой при merge в main | Деплой < 10 мин |
| 4.4 | Добавить backup/restore для Tarantool | Storage | Регулярные бэкапы | RPO < 1 час, RTO < 30 мин |
| 4.5 | Написать runbook для инцидентов (PII leak, LLM outage, Tarantool crash) | Документация | Стандартные процедуры | Top-10 инцидентов |
| 4.6 | Внедрить Alembic для миграций PostgreSQL | Storage | Версионированная схема | 100% миграций автоматизированы |

**Рекомендации:** OpenTelemetry SDK, Jaeger, ArgoCD.

---

### Этап 5: Качество LLM и аналитика (Приоритет: НИЗКИЙ)

**Цель:** Измеримость и повышение качества LLM-анализа.

| # | Задача | Модуль | Ожидаемый результат | Метрика |
|---|--------|--------|---------------------|---------|
| 5.1 | Создать ground truth dataset для backtesting risk score | Агент | Исторические данные с экспертной оценкой | >100 размеченных кейсов |
| 5.2 | Внедрить LLM evaluation framework (RAGAS/DeepEval) | LLM API | Автооценка качества | Faithfulness > 0.8 |
| 5.3 | Prompt regression testing | Агент | Автотесты при изменении промптов | 0 регрессий |
| 5.4 | Dashboard качества LLM (drift, latency, cost, PII detection rate) | Мониторинг | Real-time дашборд | Доступен в Grafana |
| 5.5 | A/B testing разных LLM-моделей | LLM API | Статистическое сравнение моделей | Значимые результаты |
| 5.6 | Метрики качества RAG (relevancy, precision@k) | RAG | Измеримость полезности RAG | Precision@3 > 0.7 |

**Рекомендации:** RAGAS, DeepEval, LangSmith.

---

### Этап 6: Enterprise Features (Приоритет: НИЗКИЙ)

**Цель:** Функции для корпоративных клиентов.

| # | Задача | Модуль | Ожидаемый результат | Метрика |
|---|--------|--------|---------------------|---------|
| 6.1 | RBAC (Role-Based Access Control): admin, analyst, viewer | API/UI | Ролевая модель | 100% endpoints с ролями |
| 6.2 | Multi-tenancy — изоляция данных между организациями | Storage/API | Нет data leaks | 0 cross-tenant access |
| 6.3 | SSO (SAML/OIDC) | API | Интеграция с IdP | AD/Okta работают |
| 6.4 | Batch analysis API (100+ ИНН за раз) | API/Агент | Массовая проверка | >50 analyses/min |
| 6.5 | Webhook уведомления о завершении анализа | API | Push-уведомления | >99.5% delivery |
| 6.6 | Замена Streamlit на полноценный frontend (React/Vue) | UI | Production-ready UI | RBAC, multi-tenant |
| 6.7 | Audit trail с immutable log | Все | Неизменяемый лог действий | 100% actions logged |

**Рекомендации:** Keycloak, FastAPI-Users, React/Next.js.

---

## 5. Приложения

### 5.1. Сводная таблица приоритетов

| Этап | Приоритет | Задач | Фокус | Ключевой результат |
|------|-----------|-------|-------|---------------------|
| 1 | ВЫСОКИЙ | 7 | PII + Critical | Гарантированная защита PII, нет потерь данных |
| 2 | ВЫСОКИЙ | 7 | Надёжность | Retry, integration tests, устойчивые интеграции |
| 3 | СРЕДНИЙ | 7 | Архитектура | Нет дублирования, чистый код, чистый API |
| 4 | СРЕДНИЙ | 6 | Operations | Production-ready, tracing, CD, backups |
| 5 | НИЗКИЙ | 6 | ML Quality | Измеримое качество LLM, backtesting |
| 6 | НИЗКИЙ | 7 | Enterprise | RBAC, multi-tenancy, batch API |

### 5.2. Зависимости между этапами

```
Этап 1 (PII + Critical) ──→ Этап 2 (Надёжность) ──→ Этап 3 (Архитектура)
                                                          ↓
                                              Этап 4 (Operations) ──→ Этап 5 (ML Quality)
                                                          ↓
                                              Этап 6 (Enterprise)
```

### 5.3. Матрица PII-рисков по точкам входа

| Точка входа | PII маскирование | Механизм | Риск |
|-------------|-----------------|----------|------|
| REST API → Agent workflow → `ainvoke()` | Автоматическое | `LLMManager._mask_prompt_pii()` | Низкий |
| REST API → LLM API → background task | Явное | `_process_llm_request_background()` | Низкий |
| RabbitMQ → analysis queue | Автоматическое | Через `execute_client_analysis()` → `ainvoke()` | Низкий |
| RabbitMQ → llm queue | Через LLMManager | `ainvoke_with_provider()` — **без mask_pii!** | **СРЕДНИЙ** |
| Прямой вызов LLM-провайдера | Отсутствует | Нет защиты | **ВЫСОКИЙ** |

### 5.4. Внешние API и SLA

| API | Таймаут | TTL кэша | Критичность | PII в запросе |
|-----|---------|----------|-------------|---------------|
| DaData | 30s | 2h | Высокая | ИНН (публичные данные) |
| Casebook | 30s | 2.7h | Высокая | ИНН (публичные данные) |
| InfoSphere | 45s | 1h | Средняя | ИНН (публичные данные) |
| Perplexity | 60s | 5min | Средняя | Поисковые запросы (маскированные) |
| Tavily | 60s | 5min | Средняя | Поисковые запросы (маскированные) |
| OpenRouter | 60s | 1h | Критическая | **Промпт — ОБЯЗАТЕЛЬНО маскировать** |
| HuggingFace | 30s | — | Средняя | **Промпт — ОБЯЗАТЕЛЬНО маскировать** |
| GigaChat | 30s | — | Низкая | **Промпт — ОБЯЗАТЕЛЬНО маскировать** |
| YandexGPT | 30s | — | Низкая | **Промпт — ОБЯЗАТЕЛЬНО маскировать** |
