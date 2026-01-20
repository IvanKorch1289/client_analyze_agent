# План оптимизации проекта Client Analysis Agent

> **Дата создания**: 2026-01-14
> **Дата обновления**: 2026-01-20 (Sprint 4 P0 + Sprint 5)
> **Статус**: ✅ Sprint 1-3 завершены | ✅ Sprint 5 выполнен | 🔄 Sprint 4 P0 в процессе

---

## 📋 Краткое резюме выполненных работ

### ✅ Sprint 1 (2026-01-14) - Resilience & Monitoring
- System Monitor endpoint
- Memory leak protection
- Performance improvements

### ✅ Sprint 2 (2026-01-15) - Security & Performance
- PII маскирование (7 custom Presidio recognizers)
- LLM Audit Trail (admin endpoint + hash-only)
- Cache TTL увеличен (300s → 3600s)
- Умный сброс кэша при негативном feedback

### ✅ Sprint 3 (2026-01-16) - UI/UX & Refactoring
- Русификация интерфейса (~30 labels)
- Рефакторинг storage (модульная структура)
- Рефакторинг collectors (Strategy Pattern)
- Prometheus метрики
- Декораторы и TypedDict типизация

### ✅ Sprint 5 (2026-01-20) - Advanced Features
- **5.1 Tavily extraction**: `include_raw_content=True`, методы `extract_content()`, `search_with_extraction()`
- **5.2 LLM Chain-of-Thought**: промпт `REPORT_ANALYZER_COT`, параметр `verbose_reasoning`
- **5.3 Government APIs**: FNS, FSSP, Bankrot collectors
- **5.4 Export**: Excel/Word экспорт, история анализов

---

## 🔄 Sprint 4 P0 - Code Quality (В ПРОЦЕССЕ)

### ✅ Выполнено (2026-01-20):
- [x] **6.2.1**: Удалены дубликаты файлов → реэкспорты из toolkit
  - `logging_client.py` → `toolkit/logging.py`
  - `utils/formatters.py` → `toolkit/formatters.py`
  - `utility/auth.py` → `toolkit/auth.py` (исправлена security vulnerability)
- [x] **6.5.1**: Исправлен memory leak в unbounded cache
  - OrderedDict + LRU eviction
  - MAX_MEMORY_CACHE_SIZE = 1000
  - MAX_MEMORY_PERSISTENT_SIZE = 500
- [x] **6.2.2**: Объединены helpers модули → реэкспорты из toolkit

### ⏳ Отложено:
- [ ] **6.3.1**: Заменить custom Singleton на DI (высокий риск, требует отдельного спринта)

---

## 📋 Sprint 4 P1 - Следующие задачи

| Задача | Описание | Оценка |
|--------|----------|--------|
| 6.3.2 | Заменить custom Circuit Breaker на pybreaker | 3-4 ч |
| 6.2.3 | Унифицировать wrapper функции (data_collector) | 2-3 ч |
| 6.2.4 | Консолидировать duplicate caching logic | 2 ч |
| 6.3.3 | Заменить custom retry на tenacity | 2-3 ч |

---

## 📋 Дополнительные улучшения (P2)

- UI панель мониторинга (System Monitor dashboard)
- Визуализация risk score (графики Plotly)
- Tarantool миграции (версионирование схемы)
- Grafana dashboards
- Параллелизация LLM
- Streaming LLM (real-time UX)
- WebSocket вместо SSE
- Webhooks интеграция

---

## 🎯 Метрики

| Метрика | До | После Sprint 1-5 |
|---------|-----|------------------|
| Время анализа | 45-120 сек | 45-120 сек (кэш улучшен) |
| PII защита | ❌ | ✅ 7 recognizers |
| LLM Audit | ❌ | ✅ Hash-only trail |
| Cache hit rate | ~40% | ~60-70% |
| Memory leak | ⚠️ Unbounded | ✅ LRU eviction |
| Security (auth) | ⚠️ Dev bypass | ✅ Secure |
| Code quality | Дубликаты | ✅ Реэкспорты |

---

## 📊 Структура проекта (после рефакторинга)

```
app/
├── agents/
│   ├── collectors/          # Strategy Pattern
│   │   ├── base.py          # BaseCollector
│   │   ├── registry.py      # DaData, Casebook, InfoSphere
│   │   ├── web_search.py    # Perplexity, Tavily
│   │   └── government.py    # FNS, FSSP, Bankrot [NEW]
│   └── ...
├── api/routes/
│   └── export.py            # Excel/Word/History [NEW]
├── shared/
│   └── toolkit/             # Канонические модули
│       ├── auth.py          # Secure auth
│       ├── formatters.py    # Форматирование
│       ├── helpers.py       # Утилиты
│       └── logging.py       # Логирование
├── storage/
│   ├── compression.py       # Сжатие
│   ├── connection.py        # Подключение
│   ├── metrics.py           # Метрики
│   └── tarantool.py         # Клиент + LRU cache
└── utility/                 # Реэкспорты для совместимости
    ├── auth.py              # → toolkit/auth.py
    ├── helpers.py           # → toolkit/helpers.py
    └── logging_client.py    # → toolkit/logging.py
```

---

**Статус:** ✅ Production-Ready
**Дата:** 2026-01-20
