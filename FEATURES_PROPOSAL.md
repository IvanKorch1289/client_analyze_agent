# Предложение новых фич для Client Analysis Agent

> **Дата**: 2026-01-16
> **Автор**: Claude (AI Analyst)
> **Статус**: Предложение

---

## Выполненные оптимизации в этом спринте

### 1. Модульная структура storage (tarantool.py)
**Было:** 1,069 строк в одном файле

**Стало:** Модульная структура
```
app/storage/
├── __init__.py          # Экспорт публичных API
├── tarantool.py         # Основной клиент (сокращён)
├── compression.py       # Сжатие/распаковка (NEW)
├── metrics.py           # Метрики кэша (NEW)
├── connection.py        # Управление соединением (NEW)
└── repositories/        # Репозитории
```

### 2. Collectors для data_collector.py
**Было:** 720 строк с логикой всех источников в одном файле

**Стало:** Strategy pattern
```
app/agents/collectors/
├── __init__.py          # Экспорт collectors
├── base.py              # BaseCollector, CollectorResult (NEW)
├── registry.py          # DaData, Casebook, InfoSphere (NEW)
└── web_search.py        # Perplexity, Tavily (NEW)
```

### 3. Prometheus метрики
**Добавлено:** `app/shared/prometheus_metrics.py`
- Метрики анализов (requests, duration, active)
- Метрики LLM (requests, latency, tokens, fallbacks)
- Метрики кэша (hit rate, size)
- Метрики источников (availability, latency)
- Метрики рисков (score distribution, alerts)

**Endpoint:** `GET /utility/metrics`

---

## Новые предложенные фичи

### Фича 1: Граф связей контрагентов (Company Graph)

**Описание:** Автоматическое построение графа связей между компаниями на основе:
- Общих учредителей/директоров
- Аффилированных лиц из DaData
- Совместных судебных дел
- Упоминаний в одних новостях

**Технические детали:**
```python
# Новый эндпоинт
@router.get("/analysis/{inn}/graph")
async def get_company_graph(inn: str, depth: int = 2) -> CompanyGraph:
    """
    Построить граф связей компании.

    depth=1: Прямые связи
    depth=2: Связи связей (расширенный анализ)
    """
    pass

# Модель данных
class CompanyNode:
    inn: str
    name: str
    risk_score: Optional[int]
    node_type: Literal["target", "founder", "director", "affiliate"]

class CompanyEdge:
    source_inn: str
    target_inn: str
    relation_type: str  # "founder", "director", "case", "news"
    weight: float  # Сила связи

class CompanyGraph:
    nodes: List[CompanyNode]
    edges: List[CompanyEdge]
    clusters: List[List[str]]  # Группы связанных компаний
```

**Выгода:**
- Выявление скрытых связей
- Обнаружение фирм-однодневок
- Анализ бенефициаров

---

### Фича 2: Изменения в реальном времени (Change Detection)

**Описание:** Мониторинг изменений в данных контрагента:
- Смена директора/учредителей
- Новые судебные дела
- Изменение статуса (ликвидация, банкротство)
- Публикации в СМИ

**Технические детали:**
```python
# Подписка на мониторинг
@router.post("/monitoring/subscribe")
async def subscribe_to_changes(
    inn: str,
    events: List[ChangeEventType],
    callback_url: Optional[str] = None,
    telegram_chat_id: Optional[str] = None,
) -> MonitoringSubscription:
    """
    Подписаться на изменения по контрагенту.

    events:
        - DIRECTOR_CHANGE
        - FOUNDER_CHANGE
        - NEW_LAWSUIT
        - STATUS_CHANGE
        - BANKRUPTCY_START
        - NEWS_MENTION
        - RISK_SCORE_CHANGE
    """
    pass

# Фоновая задача
async def check_changes_job():
    """Периодическая проверка изменений (cron: каждые 6 часов)."""
    for subscription in active_subscriptions:
        current_data = await fetch_company_data(subscription.inn)
        previous_data = await get_cached_data(subscription.inn)

        changes = detect_changes(current_data, previous_data)
        if changes:
            await notify_subscriber(subscription, changes)
```

**Выгода:**
- Проактивный мониторинг рисков
- Раннее предупреждение о проблемах
- Автоматизация compliance

---

### Фича 3: Умный кэш с предсказанием (Predictive Cache)

**Описание:** ML-модель для предсказания, какие компании будут запрошены, и предварительная загрузка данных.

**Технические детали:**
```python
# Анализ паттернов запросов
class PredictiveCacheManager:
    def __init__(self):
        self.request_history: List[RequestLog] = []
        self.model = load_prediction_model()

    def predict_next_requests(self, user_id: str, limit: int = 5) -> List[str]:
        """
        Предсказать следующие ИНН для запроса.

        Факторы:
        - История запросов пользователя
        - Связанные компании
        - Временные паттерны (начало месяца = больше проверок)
        - Отраслевая активность
        """
        features = self.extract_features(user_id)
        predictions = self.model.predict(features)
        return predictions[:limit]

    async def prefetch_predicted(self, user_id: str):
        """Предзагрузить данные для предсказанных запросов."""
        predicted_inns = self.predict_next_requests(user_id)
        for inn in predicted_inns:
            if not await self.cache.exists(inn):
                asyncio.create_task(self.background_fetch(inn))
```

**Выгода:**
- Ускорение отклика на 50-70%
- Снижение нагрузки на внешние API (батчинг)
- Лучший UX

---

### Фича 4: Отраслевой бенчмаркинг (Industry Benchmark)

**Описание:** Сравнение риск-скора компании с другими компаниями той же отрасли (ОКВЭД).

**Технические детали:**
```python
# Новый эндпоинт
@router.get("/benchmark/{inn}")
async def get_industry_benchmark(inn: str) -> BenchmarkReport:
    """
    Сравнить компанию с отраслевыми показателями.
    """
    company = await get_company_data(inn)
    okved = company.okved_main

    # Получить статистику по отрасли
    industry_stats = await get_industry_statistics(okved)

    return BenchmarkReport(
        company_inn=inn,
        okved=okved,
        industry_name=industry_stats.name,
        percentile=calculate_percentile(company.risk_score, industry_stats),
        comparison={
            "risk_score": {
                "company": company.risk_score,
                "industry_avg": industry_stats.avg_risk_score,
                "industry_median": industry_stats.median_risk_score,
            },
            "lawsuits": {
                "company": company.lawsuit_count,
                "industry_avg": industry_stats.avg_lawsuits,
            },
            "age_years": {
                "company": company.age_years,
                "industry_avg": industry_stats.avg_age,
            },
        },
        verdict=generate_verdict(company, industry_stats),
    )

class BenchmarkReport:
    company_inn: str
    okved: str
    industry_name: str
    percentile: int  # 0-100 (где находится компания среди отрасли)
    comparison: Dict[str, Dict[str, float]]
    verdict: str  # "Выше среднего", "В норме", "Ниже среднего"
```

**Выгода:**
- Контекст для риск-скора
- Понимание "нормальности" показателей
- Выявление аномалий в отрасли

---

### Фича 5: Генерация due diligence вопросов (AI Questions)

**Описание:** LLM генерирует список вопросов для углублённой проверки на основе найденных данных.

**Технические детали:**
```python
@router.get("/analysis/{report_id}/questions")
async def generate_dd_questions(report_id: str) -> DDQuestions:
    """
    Сгенерировать вопросы для due diligence на основе отчёта.
    """
    report = await get_report(report_id)

    prompt = f"""На основе анализа компании {report.company_name}:

Риск-скор: {report.risk_score}/100
Судебные дела: {report.lawsuit_count}
Статус: {report.status}
Найденные риски: {report.risks}

Сгенерируй 5-10 конкретных вопросов для углублённой проверки.
Вопросы должны:
- Уточнять выявленные риски
- Запрашивать документы для верификации
- Выявлять скрытые проблемы

Формат:
1. [Категория] Вопрос
"""

    questions = await llm.generate(prompt)

    return DDQuestions(
        report_id=report_id,
        questions=parse_questions(questions),
        priority_order=rank_questions(questions, report.risks),
    )

class DDQuestion:
    category: str  # "Финансы", "Юридические", "Репутация"
    question: str
    rationale: str  # Почему этот вопрос важен
    documents_needed: List[str]  # Какие документы запросить
```

**Выгода:**
- Структурирование процесса проверки
- Не упустить важные вопросы
- Обоснование для запроса документов

---

### Фича 6: Анализ контрактных рисков (Contract Risk)

**Описание:** Загрузка и анализ проекта договора с контрагентом для выявления рисков с учётом профиля компании.

**Технические детали:**
```python
@router.post("/contract-analysis")
async def analyze_contract(
    contract_file: UploadFile,
    counterparty_inn: str,
) -> ContractRiskReport:
    """
    Анализ договора с учётом профиля контрагента.
    """
    # Извлечь текст из договора (PDF/DOCX)
    contract_text = await extract_text(contract_file)

    # Получить профиль контрагента
    counterparty = await get_company_analysis(counterparty_inn)

    prompt = f"""Проанализируй договор с контрагентом.

ПРОФИЛЬ КОНТРАГЕНТА:
- Риск-скор: {counterparty.risk_score}
- Судебных дел: {counterparty.lawsuit_count}
- Возраст компании: {counterparty.age_years} лет
- Статус: {counterparty.status}

ТЕКСТ ДОГОВОРА:
{contract_text[:15000]}

Выяви риски:
1. Несоответствия профилю (компания не может выполнить обязательства)
2. Юридические риски (спорные формулировки)
3. Финансовые риски (невыгодные условия)
4. Риски исполнения (нереалистичные сроки/объёмы)

Для каждого риска укажи:
- Пункт договора
- Описание риска
- Рекомендация по исправлению
"""

    analysis = await llm.generate(prompt)

    return ContractRiskReport(
        contract_name=contract_file.filename,
        counterparty_inn=counterparty_inn,
        overall_risk=calculate_overall_risk(analysis),
        risks=parse_risks(analysis),
        recommendations=extract_recommendations(analysis),
    )
```

**Выгода:**
- Комплексная оценка сделки
- Учёт профиля контрагента при анализе договора
- Конкретные рекомендации по исправлению

---

### Фича 7: API для интеграции с 1С/SAP (ERP Integration)

**Описание:** Готовые коннекторы для интеграции с популярными ERP системами.

**Технические детали:**
```python
# Webhook для 1С
@router.post("/integrations/1c/webhook")
async def handle_1c_webhook(
    event: OneC_Event,
    api_key: str = Header(...),
) -> OneCResponse:
    """
    Обработка событий из 1С.

    События:
    - NEW_COUNTERPARTY: Автоматическая проверка нового контрагента
    - CONTRACT_CREATED: Проверка перед подписанием договора
    - PAYMENT_SCHEDULED: Проверка перед платежом
    """
    validate_api_key(api_key)

    if event.type == "NEW_COUNTERPARTY":
        analysis = await run_analysis(event.inn)
        return OneCResponse(
            status="completed",
            risk_score=analysis.risk_score,
            recommendation=analysis.recommendation,
        )

# Конфигурация для SAP
class SAPConnector:
    def __init__(self, config: SAPConfig):
        self.client = SAPClient(config)

    async def sync_counterparty_risks(self):
        """Синхронизация риск-скоров в SAP."""
        counterparties = await self.client.get_counterparties()

        for cp in counterparties:
            analysis = await get_cached_analysis(cp.inn)
            if analysis:
                await self.client.update_risk_score(
                    cp.id,
                    risk_score=analysis.risk_score,
                    last_check=analysis.created_at,
                )
```

**Выгода:**
- Автоматизация проверок в рабочих процессах
- Единая база рисков
- Снижение ручной работы

---

### Фича 8: Голосовой ассистент для проверки (Voice Assistant)

**Описание:** Telegram/VK бот с голосовым интерфейсом для быстрой проверки контрагента.

**Технические детали:**
```python
# Telegram бот
@dp.message(F.voice)
async def handle_voice(message: Message):
    """Обработка голосового сообщения."""
    # Скачать аудио
    audio = await message.voice.get_file()

    # Распознать речь (Whisper API)
    text = await transcribe_audio(audio)

    # Извлечь ИНН или название компании
    company = extract_company_from_text(text)

    if company.inn:
        analysis = await run_quick_analysis(company.inn)

        # Сгенерировать голосовой ответ
        response_text = f"""
        Компания {analysis.name}.
        Риск-скор: {analysis.risk_score} из 100.
        {analysis.short_summary}
        """

        audio_response = await text_to_speech(response_text)
        await message.answer_voice(audio_response)
    else:
        await message.answer("Не удалось определить компанию. Назовите ИНН или полное название.")
```

**Выгода:**
- Быстрая проверка "на ходу"
- Не нужен компьютер
- Удобно для выездных менеджеров

---

## Приоритизация

| # | Фича | Сложность | Ценность | Рекомендация |
|---|------|-----------|----------|--------------|
| 1 | Граф связей | Высокая | Высокая | P1 - Уникальная ценность |
| 2 | Change Detection | Средняя | Высокая | P1 - Критично для compliance |
| 3 | Predictive Cache | Высокая | Средняя | P2 - Оптимизация |
| 4 | Industry Benchmark | Средняя | Высокая | P1 - Контекст для решений |
| 5 | DD Questions | Низкая | Средняя | P2 - Улучшает UX |
| 6 | Contract Risk | Средняя | Высокая | P1 - Полезно для сделок |
| 7 | ERP Integration | Высокая | Высокая | P1 - Enterprise value |
| 8 | Voice Assistant | Средняя | Низкая | P3 - Nice to have |

---

## Рекомендуемый roadmap

### Фаза 1 (ближайший спринт)
1. **Change Detection** - базовый мониторинг изменений
2. **Industry Benchmark** - сравнение с отраслью

### Фаза 2 (следующий месяц)
3. **Граф связей** - базовая версия (глубина 1)
4. **Contract Risk** - анализ договоров

### Фаза 3 (2-3 месяца)
5. **ERP Integration** - коннектор для 1С
6. **DD Questions** - генерация вопросов

### Фаза 4 (3+ месяцев)
7. **Predictive Cache** - ML предсказание
8. **Voice Assistant** - голосовой бот

---

## Заключение

Предложенные фичи фокусируются на:
- **Глубине анализа** (граф связей, benchmark)
- **Проактивности** (change detection, predictive cache)
- **Интеграции** (ERP, voice)
- **Полноте сделки** (contract risk, DD questions)

Каждая фича построена на существующей архитектуре и может быть реализована инкрементально.
