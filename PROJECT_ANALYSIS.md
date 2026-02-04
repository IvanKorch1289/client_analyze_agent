# Аналитический отчёт: Система анализа контрагентов

**Дата:** 2026-02-04
**Версия проекта:** 0.1.0 (14 спринтов завершено)
**Статус:** MVP готов, требуется доработка для production

---

## 1. Краткий обзор проекта

### Миссия
Автоматизация проверки контрагентов для российского рынка с использованием мультиагентного LLM-подхода, внешних источников данных и нормализованной оценки рисков.

### Ключевые функциональности
| Функция | Реализация | Статус |
|---------|------------|--------|
| Мультиагентный workflow (LangGraph) | Orchestrator → Collector → Analyzer → Writer | Реализовано |
| Интеграция 7 источников данных | DaData, Casebook, InfoSphere, Perplexity, Tavily, Web Scraping, RAG | Реализовано |
| Нормализованная оценка рисков (0-100) | LLM-based + manual fallback | Реализовано |
| PII-защита (152-ФЗ) | 7 кастомных Presidio-распознавателей | Реализовано |
| Генерация отчётов (PDF/JSON) | ReportLab + custom templates | Реализовано |
| Streamlit UI | 10+ вкладок (анализ, мониторинг, RAG, сравнение) | Реализовано |
| LLM Fallback Chain | OpenRouter → HuggingFace → GigaChat → YandexGPT | Реализовано |
| Кэширование (Tarantool) | TTL, compression, LRU eviction, in-memory fallback | Реализовано |
| Мониторинг | Prometheus + Grafana + Alertmanager | Реализовано |
| MCP Server | 4 категории tools для IDE-интеграции | Реализовано |
| Очередь сообщений (RabbitMQ) | FastStream broker, DLQ, retries | Реализовано |
| Аутентификация | Admin Token (X-Auth-Token) | Базовая |
| gRPC интерфейс | Конфиг есть, код не реализован | Не реализовано |
| Redis-кэш | Конфиг есть, подключение не реализовано | Не реализовано |
| PostgreSQL | Упомянут в README, не используется | Не реализовано |

### Целевые пользователи
- Службы безопасности и compliance-отделы компаний
- Финансовые аналитики
- Юридические службы
- Кредитные отделы банков

---

## 2. Анализ текущего состояния

### 2.1. Что реализовано хорошо

#### Архитектура (оценка: 7/10)
- **Модульная агентная система** — чёткое разделение на Orchestrator, DataCollector, ReportAnalyzer, FileWriter
- **Registry pattern** для коллекторов данных — легко добавлять новые источники
- **Settings Facade** с группировкой (app, security, tarantool, queue, etc.) и hot-reload
- **Graceful degradation** — система работает при недоступности Tarantool, LLM-провайдеров
- **Multi-stage Docker build** — образ ~350MB вместо ~800MB

#### Безопасность (оценка: 8/10)
- **PII Protection** — 7 кастомных распознавателей для РФ (ИНН, ОГРН, СНИЛС, паспорт, ФИО, адрес, телефон)
- **PII блокировка** — при ошибке маскирования LLM-вызов блокируется (не degradation, а fail-safe)
- **LLM Audit** — аудит-лог всех LLM-вызовов для compliance
- **Rate Limiting** — per-route через SlowAPI
- **Input Validation** — Pydantic-схемы для всех endpoints
- **Security Headers** — CSP, HSTS, X-Frame-Options (опционально)
- **CI/CD Security** — Bandit, pip-audit, Trivy container scan

#### Наблюдаемость (оценка: 7/10)
- **Prometheus metrics** — кастомные метрики (LLM latency, fallback count, cache hit rate)
- **Grafana dashboard** — преднастроенный дашборд для мониторинга
- **Alertmanager** — правила алертинга (high error rate, slow response, OOM)
- **Structured logging** — loguru с JSON output + Rich для dev

#### Тестирование (оценка: 6/10)
- 26 тестовых файлов покрывающих API, E2E, security, load, benchmarks
- OWASP тесты безопасности
- Locust для нагрузочного тестирования
- Но: всё на моках, нет staging-тестов

### 2.2. Проблемные зоны

#### Хранение данных (оценка: 4/10)
- Tarantool используется как основная БД, но это KV-хранилище — нет реляционных запросов
- In-memory fallback теряет данные при рестарте
- Нет миграций схемы данных
- PostgreSQL заявлен, но не подключён
- Redis заявлен, но не подключён
- Жёсткие лимиты кэша (1000 entries) могут быть недостаточны для production

#### Код (оценка: 6/10)
- `asyncio.get_event_loop()` вместо `asyncio.get_running_loop()` — deprecated в Python 3.12+
- Дублирование логики расчёта рисков (risk_calculator.py vs report_analyzer.py)
- Hardcoded thinking messages в workflow
- Глобальные переменные модулей (_memory_cache, _memory_persistent) вместо инкапсуляции
- Search cache дублируется (dict + основной кэш)
- `_run_coroutine_sync()` создаёт новые потоки для sync-to-async bridge — потенциальный deadlock

#### Документация (оценка: 5/10)
- README содержит устаревшую структуру проекта
- API_REFERENCE.md хороший, но не автогенерируемый — может рассинхрониться
- Нет Architecture Decision Records (ADR)
- Нет runbook для инцидентов
- CHANGELOG хороший, но нет автоматизации (conventional commits)

---

## 3. Диагностика и проблемные точки

### 3.1. Технические риски

| Риск | Вероятность | Влияние | Описание |
|------|-------------|---------|----------|
| Потеря данных при рестарте | Высокая | Критическое | In-memory fallback теряет все кэшированные данные и threads |
| Deadlock в sync-async bridge | Средняя | Высокое | `_run_coroutine_sync()` создаёт потоки внутри async context |
| LLM rate limiting | Высокая | Среднее | При большой нагрузке все LLM-провайдеры могут вернуть 429 |
| Tarantool schema drift | Средняя | Высокое | Нет миграций — ручное обновление при каждом изменении |
| Memory leak в кэше | Низкая | Высокое | LRU eviction реализован, но search_cache dict не ограничен |
| Circular imports | Средняя | Среднее | Lazy imports повсеместно — признак архитектурных проблем |
| Единая точка отказа LLM | Средняя | Критическое | Если все 4 провайдера down — система не работает |

### 3.2. Организационные риски

| Риск | Вероятность | Влияние | Описание |
|------|-------------|---------|----------|
| Bus factor = 1 | Высокая | Критическое | Проект ведётся одним разработчиком |
| Устаревание документации | Высокая | Среднее | README уже не соответствует коду |
| Отсутствие staging | Высокая | Высокое | Нет промежуточной среды для тестирования |
| Нет CD | Средняя | Среднее | CI есть, автодеплой не настроен |

### 3.3. Аналитические проблемы

| Проблема | Описание |
|----------|----------|
| Нет backtesting | Невозможно проверить качество risk-score на исторических данных |
| Нет метрик качества LLM | Нет ground truth для оценки точности LLM-анализа |
| Нет A/B testing | Невозможно сравнить качество разных моделей на одних данных |
| Нет версионирования промптов | Промпты в коде, нет истории изменений и regression testing |

---

## 4. План доведения до идеала

### Этап 1: Стабилизация и Critical Fixes (Приоритет: ВЫСОКИЙ)

**Цель:** Устранить критические технические риски, обеспечить устойчивость данных.

| # | Задача | Ожидаемый результат | Метрика качества |
|---|--------|---------------------|------------------|
| 1.1 | Подключить PostgreSQL для персистентного хранения отчётов и аналитики | Отчёты сохраняются в реляционной БД, доступна SQL-аналитика | 0 потерь данных при рестарте |
| 1.2 | Внедрить Alembic для миграций БД | Версионированная схема, rollback при ошибках | 100% миграций автоматизированы |
| 1.3 | Заменить `asyncio.get_event_loop()` на `asyncio.get_running_loop()` | Нет deprecation warnings на Python 3.12+ | 0 deprecation warnings |
| 1.4 | Ограничить `_search_cache` dict в TarantoolClient | Нет unbounded memory growth | Размер кэша < 10000 entries |
| 1.5 | Исправить `_run_coroutine_sync()` — использовать `asyncio.run_coroutine_threadsafe()` | Нет потенциальных deadlocks | 0 deadlocks за 30 дней |
| 1.6 | Обновить README — привести в соответствие с фактической структурой | Документация точно отражает код | 100% путей валидны |

**Рекомендуемые инструменты:** Alembic, SQLAlchemy/SQLModel, asyncpg

---

### Этап 2: Тестирование и Quality Assurance (Приоритет: ВЫСОКИЙ)

**Цель:** Поднять покрытие тестами и добавить интеграционные тесты.

| # | Задача | Ожидаемый результат | Метрика качества |
|---|--------|---------------------|------------------|
| 2.1 | Настроить staging-окружение (Docker Compose + real services) | Тесты с реальными API (sandbox) | Staging доступен 24/7 |
| 2.2 | Добавить integration tests с testcontainers | Тесты с реальным Tarantool, RabbitMQ | >80% code coverage |
| 2.3 | Добавить contract tests для внешних API | Контракты DaData, Casebook, InfoSphere зафиксированы | 100% API контрактов проверены |
| 2.4 | Внедрить smoke tests в CI/CD | Реальная проверка healthchecks после деплоя | Smoke tests проходят < 60 сек |
| 2.5 | Добавить mutation testing (mutmut) | Проверка качества тестов | Mutation score > 60% |
| 2.6 | Настроить pre-commit hooks | Форматирование, линтинг, security до коммита | 100% коммитов проходят hooks |

**Рекомендуемые инструменты:** testcontainers-python, pact-python, mutmut, pre-commit

---

### Этап 3: Архитектурные улучшения (Приоритет: СРЕДНИЙ)

**Цель:** Устранить дублирование, улучшить модульность, подготовить к масштабированию.

| # | Задача | Ожидаемый результат | Метрика качества |
|---|--------|---------------------|------------------|
| 3.1 | Унифицировать расчёт рисков — единый RiskCalculator | Один источник правды для risk score | 0 дублирования логики |
| 3.2 | Вынести промпты в отдельные файлы/БД с версионированием | История изменений промптов, A/B тестирование | 100% промптов версионированы |
| 3.3 | Подключить Redis для rate limiting и session storage | Масштабирование rate limiting на кластер | Rate limiting работает при 3+ instances |
| 3.4 | Реализовать gRPC интерфейс (или убрать из конфига) | Либо работающий gRPC, либо чистый конфиг | 0 мёртвого кода |
| 3.5 | Устранить circular imports через Dependency Injection | Нет lazy imports ради circular deps | 0 lazy imports из-за circular deps |
| 3.6 | Добавить Structured Concurrency (TaskGroup) | Безопасная отмена параллельных задач | 0 orphaned tasks |
| 3.7 | Перейти на Pydantic Settings v2 для всех конфигов | Единообразная валидация конфигурации | 100% settings через Pydantic |

**Рекомендуемые инструменты:** Redis, grpcio, dependency-injector, Pydantic v2

---

### Этап 4: Observability и Operations (Приоритет: СРЕДНИЙ)

**Цель:** Готовность к production-эксплуатации.

| # | Задача | Ожидаемый результат | Метрика качества |
|---|--------|---------------------|------------------|
| 4.1 | Настроить OpenTelemetry tracing end-to-end | Полная трассировка запроса через все сервисы | 100% запросов с trace_id |
| 4.2 | Добавить Jaeger/Tempo для визуализации traces | Визуальная карта зависимостей | MTTR < 15 мин |
| 4.3 | Написать runbook для инцидентов | Стандартизированные процедуры реагирования | Runbook для Top-10 инцидентов |
| 4.4 | Настроить CD pipeline (GitHub Actions → staging → prod) | Автодеплой при merge в main | Деплой < 10 мин |
| 4.5 | Добавить canary deployments | Постепенный rollout с автоматическим rollback | < 1% error rate при деплое |
| 4.6 | Добавить backup/restore для Tarantool | Регулярные бэкапы, проверенный restore | RPO < 1 час, RTO < 30 мин |

**Рекомендуемые инструменты:** OpenTelemetry SDK, Jaeger, ArgoCD/GitHub Actions

---

### Этап 5: Аналитика и ML Quality (Приоритет: НИЗКИЙ)

**Цель:** Повысить качество и измеримость LLM-анализа.

| # | Задача | Ожидаемый результат | Метрика качества |
|---|--------|---------------------|------------------|
| 5.1 | Создать dataset с ground truth для backtesting | Исторические данные с экспертной оценкой | > 100 размеченных кейсов |
| 5.2 | Внедрить LLM evaluation framework (RAGAS/DeepEval) | Автоматическая оценка качества LLM-ответов | Faithfulness > 0.8, Relevancy > 0.85 |
| 5.3 | A/B testing моделей | Сравнение Claude vs GPT-4 vs Llama на одних данных | Статистически значимые результаты |
| 5.4 | Prompt regression testing | Автотесты при изменении промптов | 0 регрессий промптов |
| 5.5 | Dashboard качества LLM | Мониторинг drift, latency, cost per analysis | Real-time dashboard |
| 5.6 | Fine-tuning на российских данных | Специализированная модель для российского compliance | +15% к accuracy |

**Рекомендуемые инструменты:** RAGAS, DeepEval, LangSmith, Weights & Biases

---

### Этап 6: Enterprise Features (Приоритет: НИЗКИЙ)

**Цель:** Функции для корпоративных клиентов.

| # | Задача | Ожидаемый результат | Метрика качества |
|---|--------|---------------------|------------------|
| 6.1 | RBAC (Role-Based Access Control) | Роли: admin, analyst, viewer | 100% эндпоинтов с ролевой моделью |
| 6.2 | Multi-tenancy | Изоляция данных между организациями | 0 data leaks между тенантами |
| 6.3 | SSO (SAML/OIDC) | Интеграция с корпоративными IdP | SSO работает с AD/Okta |
| 6.4 | Audit trail с immutable log | Неизменяемый лог всех действий | 100% действий залогированы |
| 6.5 | API versioning (v2) | Обратная совместимость + новые features | v1 deprecated, v2 active |
| 6.6 | Webhook уведомления | Уведомление о завершении анализа | Webhook delivery > 99.5% |
| 6.7 | Batch analysis API | Массовая проверка (100+ ИНН за раз) | Throughput > 50 analyses/min |

**Рекомендуемые инструменты:** Keycloak, python-jose, FastAPI-Users, Celery

---

## 5. Приложения

### 5.1. Сводная таблица приоритетов

| Этап | Приоритет | Кол-во задач | Ключевой результат |
|------|-----------|-------------|---------------------|
| 1. Стабилизация | ВЫСОКИЙ | 6 | Нет потерь данных, нет deprecation warnings |
| 2. Тестирование | ВЫСОКИЙ | 6 | >80% coverage, staging, integration tests |
| 3. Архитектура | СРЕДНИЙ | 7 | Нет дублирования, масштабируемость |
| 4. Operations | СРЕДНИЙ | 6 | Production-ready, CD, tracing |
| 5. ML Quality | НИЗКИЙ | 6 | Измеримое качество LLM, backtesting |
| 6. Enterprise | НИЗКИЙ | 7 | RBAC, multi-tenancy, SSO |

### 5.2. Зависимости между этапами

```
Этап 1 (Стабилизация) ──→ Этап 2 (Тестирование) ──→ Этап 3 (Архитектура)
                                                          ↓
                                              Этап 4 (Operations) ──→ Этап 5 (ML Quality)
                                                          ↓
                                              Этап 6 (Enterprise)
```

### 5.3. Компоненты инфраструктуры (текущее состояние)

| Компонент | Версия | Статус | Healthcheck |
|-----------|--------|--------|-------------|
| FastAPI | 0.115+ | Production | /utility/health |
| Tarantool | 3.x | Production | TCP check |
| RabbitMQ | 3.12 | Production | Management API |
| ChromaDB | latest | Development | TCP check |
| Prometheus | latest | Production | /metrics |
| Grafana | latest | Production | /api/health |
| Alertmanager | latest | Production | /-/healthy |
| JayGuard | custom | Optional | /health |

### 5.4. Внешние API и SLA

| API | Таймаут | TTL кэша | Rate Limit | Критичность |
|-----|---------|----------|------------|-------------|
| DaData | 30s | 2h | 10 req/s | Высокая |
| Casebook | 30s | 2.7h | N/A | Высокая |
| InfoSphere | 45s | 1h | N/A | Средняя |
| Perplexity | 60s | 5min | N/A | Средняя |
| Tavily | 60s | 5min | N/A | Средняя |
| OpenRouter | 60s | 1h | Model-dependent | Критическая |
