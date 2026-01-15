# Sprint 2 - Security & Performance Improvements

> **Дата начала**: 2026-01-15
> **Статус**: В РАБОТЕ
> **Вариант**: C (Гибридный подход)

---

## 🎯 Цели Sprint 2

### Приоритет P0 (Критично)
1. ✅ **PII Маскирование** - максимальный уровень защиты (ИНН, телефоны, email, ФИО, адреса)
2. ✅ **Параллелизация Tavily web scraping** - ускорение на 8-10 секунд
3. ✅ **Увеличение TTL кэша** - с умным сбросом при негативном feedback
4. ✅ **Улучшение LLM Audit Trail** - полная трассировка для compliance

### Приоритет P1 (Опционально)
5. ⚠️ **Рефакторинг data_collector.py** - если останется время

---

## 📋 Детальный план задач

### Задача 2.1: PII Маскирование (P0 CRITICAL)

**Файлы:**
- `app/shared/pii_masking.py` (НОВЫЙ) - модуль маскирования
- `app/agents/llm_manager.py` (ИЗМЕНИТЬ) - интеграция
- `app/config/security.py` (ИЗМЕНИТЬ) - настройки уровней

**Функциональность:**
1. **Уровни маскирования:**
   - `high` (по умолчанию): ИНН, телефоны, email, ФИО, адреса, ОГРН
   - `medium`: ИНН, телефоны, email
   - `low`: только ИНН
   - `none`: без маскирования (для on-premise)

2. **PII паттерны:**
   - ИНН: `\b\d{10,12}\b`
   - Телефоны: `\+?7[\s\-]?\(?\d{3}\)?[\s\-]?\d{3}[\s\-]?\d{2}[\s\-]?\d{2}`
   - Email: `[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}`
   - ФИО: `[А-ЯЁ][а-яё]+\s+[А-ЯЁ][а-яё]+(?:\s+[А-ЯЁ][а-яё]+)?`
   - ОГРН: `\b\d{13,15}\b`
   - Адреса: `г\.\s*[А-ЯЁ][а-яё]+.*`

3. **Workflow:**
   - Mask перед LLM вызовом
   - Unmask после получения ответа
   - Сохранение replacements для восстановления
   - Логирование detected PII types (не сами данные!)

**Интеграция в LLM Manager:**
```python
async def ainvoke(self, prompt: str, mask_pii: bool = True, **kwargs):
    # 1. Mask PII
    if mask_pii:
        masked_result = pii_masking.mask_pii(prompt, level="high")
        prompt_to_send = masked_result["masked_text"]
        detected_pii = masked_result["detected_pii_types"]
    else:
        prompt_to_send = prompt
        detected_pii = []

    # 2. LLM call
    response = await self._call_llm(prompt_to_send, **kwargs)

    # 3. Unmask PII
    if mask_pii and masked_result["replacements"]:
        response = pii_masking.unmask_pii(response, masked_result["replacements"])

    # 4. Audit log
    await audit_logger.log(detected_pii=detected_pii, masked=mask_pii)

    return response
```

**Оценка времени:** 10-12 часов

---

### Задача 2.2: Параллелизация Tavily Web Scraping (P0)

**Файлы:**
- `app/agents/web_scraper.py` (ИЗМЕНИТЬ)
- `app/services/tavily_client.py` (ПРОВЕРИТЬ)

**Текущая реализация:**
```python
# МЕДЛЕННО: последовательно
for url in top_5_urls:
    content = await scrape_url(url)  # ~2-3s на URL
    results.append(content)
# Итого: 10-15 секунд
```

**Новая реализация:**
```python
# БЫСТРО: параллельно
tasks = [scrape_url(url) for url in top_5_urls]
results = await asyncio.gather(*tasks, return_exceptions=True)
# Итого: 3-5 секунд
```

**Обработка ошибок:**
- Graceful degradation - если URL fails, продолжаем с остальными
- Timeout 10s на URL (не блокируем весь scraping)
- Логирование failed URLs

**Оценка времени:** 4-5 часов

---

### Задача 2.3: Увеличение TTL кэша + умный сброс (P0)

**Файлы:**
- `app/services/http_client.py` (ИЗМЕНИТЬ) - TTL настройки
- `app/agents/report_analyzer.py` (ИЗМЕНИТЬ) - feedback handling
- `app/api/routes/reports.py` (ИЗМЕНИТЬ) - feedback endpoint

**Изменения TTL:**
```python
# БЫЛО:
CACHE_TTL = {
    "perplexity": 300,  # 5 минут
    "tavily": 300,      # 5 минут
}

# СТАЛО:
CACHE_TTL = {
    "perplexity": 3600,  # 1 час
    "tavily": 3600,      # 1 час
}
```

**Умный сброс кэша при feedback:**
```python
# app/api/routes/reports.py

@router.post("/reports/{thread_id}/feedback")
async def submit_feedback(
    thread_id: str,
    feedback: FeedbackRequest,  # rating, comment, focus_areas
):
    # Если rating < 3 (негативный) - сбрасываем кэш для этой компании
    if feedback.rating < 3:
        # Очищаем кэш Perplexity/Tavily для этого ИНН
        inn = await get_inn_from_thread(thread_id)
        await clear_cache_for_inn(inn, sources=["perplexity", "tavily"])

        logger.info(
            f"Cleared cache for INN {inn} due to negative feedback (rating={feedback.rating})"
        )

    # Обычная логика feedback
    ...
```

**Оценка времени:** 5-6 часов

---

### Задача 2.4: Улучшение LLM Audit Trail (P0)

**Файлы:**
- `app/shared/llm_audit.py` (УЛУЧШИТЬ существующий)
- `app/api/routes/admin.py` (ДОБАВИТЬ endpoint)
- `app/storage/tarantool.py` (ДОБАВИТЬ space для audit)

**Что улучшить:**
1. **Более детальный audit:**
   - SHA256 хэш промпта (не сам промпт!)
   - SHA256 хэш ответа
   - Detected PII types
   - Privacy mode (high/medium/low/none)
   - Provider + model
   - Duration, success, cache_hit
   - Session ID, user IP (если есть)

2. **Отдельный Tarantool space:**
   ```lua
   -- Space для audit trail (retention 90 дней)
   space = box.schema.space.create('llm_audit', {
       if_not_exists = true,
       format = {
           {name = 'audit_id', type = 'string'},
           {name = 'timestamp', type = 'number'},
           {name = 'prompt_hash', type = 'string'},
           {name = 'response_hash', type = 'string'},
           {name = 'provider', type = 'string'},
           {name = 'detected_pii', type = 'array'},
           {name = 'privacy_mode', type = 'string'},
           {name = 'success', type = 'boolean'},
           {name = 'duration_ms', type = 'number'},
       }
   })
   ```

3. **Admin API endpoint:**
   ```
   GET /admin/audit/llm?period=24h&provider=openrouter&privacy_mode=high
   ```

**Оценка времени:** 8-10 часов

---

### Задача 2.5: Рефакторинг data_collector.py (P1, опционально)

**Файлы:**
- `app/agents/data_collector.py` (720 строк → разделить)

**Новая структура:**
```
app/agents/data_collector/
  ├── __init__.py
  ├── collector.py          # Основной агент
  ├── dadata_fetcher.py     # DaData fetch logic
  ├── infosphere_fetcher.py # InfoSphere fetch logic
  ├── casebook_fetcher.py   # Casebook fetch logic
  ├── web_search_fetcher.py # Perplexity + Tavily
  └── result_builder.py     # _build_search_results() логика
```

**Оценка времени:** 10-12 часов (ТОЛЬКО если останется время)

---

## ⏱️ Оценка времени Sprint 2

| Задача | Оценка | Приоритет |
|--------|--------|-----------|
| 2.1 PII Маскирование | 10-12 ч | P0 |
| 2.2 Параллелизация Tavily | 4-5 ч | P0 |
| 2.3 Умный кэш TTL | 5-6 ч | P0 |
| 2.4 LLM Audit улучшение | 8-10 ч | P0 |
| 2.5 Рефакторинг (опц.) | 10-12 ч | P1 |
| **Итого P0** | **27-33 ч** | |
| **Итого P0+P1** | **37-45 ч** | |

**Рекомендация:** Фокус на P0 задачах (2.1-2.4), P1 делаем если останется время.

---

## 📊 Ожидаемые результаты

### Безопасность:
- ✅ **Compliance с 152-ФЗ** - полное PII маскирование
- ✅ **Audit trail** - трассировка всех LLM вызовов
- ✅ **Zero PII leakage** - никакие персональные данные не попадают в OpenRouter/HuggingFace

### Производительность:
- ⚡ **-8-10 секунд** на Tavily scraping (параллелизация)
- ⚡ **+20-30% cache hit rate** (увеличение TTL)
- ⚡ **Умный сброс** - актуальность данных при негативном feedback

### Качество:
- 📈 **Лучше UX** - быстрее + актуальнее
- 📈 **Production-ready** - готово к запуску с реальными клиентами
- 📈 **Compliance-ready** - готово к аудитам

---

## ✅ Definition of Done

Задача считается выполненной когда:
1. ✅ Код написан и прошёл линтеры (ruff, black, pyright)
2. ✅ Интеграционные тесты добавлены (где критично)
3. ✅ Документация обновлена (docstrings, комментарии)
4. ✅ Commit создан с подробным описанием
5. ✅ Push в remote branch выполнен

---

## 🚀 Старт Sprint 2

**Порядок выполнения:**
1. Task 2.1: PII Маскирование (самая критичная)
2. Task 2.2: Параллелизация Tavily (быстрая победа)
3. Task 2.3: Умный кэш TTL (средняя)
4. Task 2.4: LLM Audit улучшение (долгая но важная)
5. Task 2.5: Рефакторинг (если останется время)

**Начинаем с Task 2.1!** 🔐
