# Runbook: Incident Response

## Содержание

1. [PII Leak (утечка персональных данных)](#1-pii-leak)
2. [LLM Provider Outage (недоступность LLM)](#2-llm-provider-outage)
3. [Tarantool Crash / Data Loss](#3-tarantool-crash)
4. [RabbitMQ Unavailable](#4-rabbitmq-unavailable)
5. [High Error Rate (HTTP 5xx)](#5-high-error-rate)
6. [Memory Leak / OOM Kill](#6-memory-leak)
7. [ChromaDB / RAG Failure](#7-chromadb-failure)
8. [Certificate / API Key Expiry](#8-api-key-expiry)
9. [Disk Full](#9-disk-full)
10. [Slow Analysis (timeout)](#10-slow-analysis)

---

## 1. PII Leak

**Severity:** CRITICAL
**SLA:** Немедленная реакция (< 15 мин)

### Симптомы
- Alert: `client_pii_masking_errors_total` > 0
- В логах: `PIIMaskingError` или `pii_detected: false` при известном PII
- Пользователь сообщил о видимых ИНН/ФИО в ответе LLM

### Диагностика

```bash
# Проверить метрики PII
curl -s http://localhost:8000/api/v1/metrics | grep pii

# Проверить последние LLM audit записи
docker exec tarantool-cache tarantool -e "
  for _, t in box.space.llm_audit.index.timestamp_idx:pairs(nil, {iterator='REQ'}) do
    if t.pii_detected then
      print(t.request_id .. ' pii=' .. tostring(t.pii_detected) .. ' provider=' .. t.provider)
    end
  end
"

# Проверить логи на ошибки маскирования
docker logs counterparty-analyzer 2>&1 | grep -i "pii\|mask\|PIIMaskingError" | tail -20
```

### Действия

1. **Немедленно**: Остановить обработку новых запросов
   ```bash
   # Остановить worker (RabbitMQ)
   docker compose stop worker
   ```

2. **Определить масштаб**: Сколько запросов прошли без маскирования
   ```bash
   docker exec tarantool-cache tarantool -e "
     local count = 0
     for _, t in box.space.llm_audit:pairs() do
       if t.pii_detected == false then count = count + 1 end
     end
     print('Requests without PII detection: ' .. count)
   "
   ```

3. **Исправить**: Обычно причина — сбой Presidio/spaCy модели
   ```bash
   # Проверить доступность spaCy модели
   docker exec counterparty-analyzer python -c "import spacy; nlp = spacy.load('ru_core_news_lg'); print('OK')"

   # Если модель не загружается — перезапуск контейнера
   docker compose restart app
   ```

4. **Верификация**: Убедиться что маскирование работает
   ```bash
   curl -X POST http://localhost:8000/api/v1/llm/mask-text \
     -H "Content-Type: application/json" \
     -d '{"text": "ИНН 7707083893, директор Иванов Иван"}'
   ```

5. **Уведомление**: Если PII утекли во внешний LLM — инцидент 152-ФЗ
   - Уведомить DPO (Data Protection Officer)
   - Зафиксировать в журнале инцидентов

### Предотвращение
- Ruff TID251 запрещает прямой импорт LLM-провайдеров
- `PIIMaskingError` блокирует LLM-вызов при сбое маскирования
- Мониторинг: `client_pii_masking_errors_total` alert

---

## 2. LLM Provider Outage

**Severity:** HIGH
**SLA:** < 30 мин

### Симптомы
- Alert: `client_llm_requests_total{status="failure"}` растёт
- Alert: `client_llm_fallbacks_total` активирован
- Пользователи получают ошибки анализа

### Диагностика

```bash
# Статус провайдеров
curl -s http://localhost:8000/api/v1/llm/providers | python -m json.tool

# Метрики LLM
curl -s http://localhost:8000/api/v1/metrics | grep llm

# Логи fallback
docker logs counterparty-analyzer 2>&1 | grep -i "fallback\|provider.*fail" | tail -20
```

### Действия

1. **Проверить fallback chain**: OpenRouter → HuggingFace → GigaChat → YandexGPT
   ```bash
   # Проверить каждый провайдер
   curl -s http://localhost:8000/api/v1/llm/providers
   ```

2. **Сбросить failed-статус провайдера** (если ложное срабатывание):
   ```bash
   curl -X POST http://localhost:8000/api/v1/llm/providers/openrouter/reset
   ```

3. **Проверить API ключи**: Могут быть revoked или rate-limited
   ```bash
   # Проверить env vars
   docker exec counterparty-analyzer env | grep -i "api_key\|token" | sed 's/=.*/=***/'
   ```

4. **Если все провайдеры недоступны**: Анализ переключится на ручной расчёт рисков
   - Risk score рассчитывается через `calculate_normalized_risk()` без LLM
   - Отчёт будет содержать данные, но без LLM-комментариев

### Предотвращение
- 4 LLM-провайдера с автоматическим fallback
- Retry с exponential backoff при 429
- Circuit breaker для каждого провайдера

---

## 3. Tarantool Crash

**Severity:** CRITICAL
**SLA:** < 30 мин (RPO < 1 час)

### Симптомы
- Alert: сервис tarantool unhealthy
- `app` контейнер логирует "Tarantool not available, using in-memory fallback"
- Данные отчётов недоступны

### Диагностика

```bash
# Статус контейнера
docker compose ps tarantool
docker logs tarantool-cache --tail 50

# Проверить место на диске
docker exec tarantool-cache df -h /var/lib/tarantool
```

### Действия

1. **Немедленно**: App переключается на in-memory fallback автоматически

2. **Перезапуск**:
   ```bash
   docker compose restart tarantool

   # Дождаться healthy
   docker compose ps tarantool
   ```

3. **Если данные повреждены** — восстановление из бэкапа:
   ```bash
   # Список доступных бэкапов
   ls ./backups/tarantool/

   # Восстановление
   ./scripts/tarantool_restore.sh 20260204_120000
   ```

4. **Если бэкапов нет** — пересоздание с нуля:
   ```bash
   docker compose stop app worker mcp
   docker compose rm -f tarantool
   docker volume rm $(docker volume ls -q | grep tarantool_data)
   docker compose up -d tarantool
   # Дождаться init.lua
   docker compose up -d app worker mcp
   ```

### Предотвращение
- Регулярные бэкапы: `./scripts/tarantool_backup.sh` (cron каждые 4 часа)
- In-memory fallback для graceful degradation
- Resource limits: 3GB memory, 2 CPU

---

## 4. RabbitMQ Unavailable

**Severity:** HIGH
**SLA:** < 30 мин

### Симптомы
- Worker контейнер falling/restarting
- Очереди не обрабатываются
- REST API продолжает работать (fallback на background tasks)

### Диагностика

```bash
# Статус
docker compose ps rabbitmq
docker logs rabbitmq-broker --tail 30

# Management UI
open http://localhost:15672  # RABBITMQ_USER / RABBITMQ_PASS
```

### Действия

1. **REST API работает**: При `QUEUE_ENABLED=false` (или недоступности RabbitMQ) — запросы обрабатываются через background tasks автоматически

2. **Перезапуск**:
   ```bash
   docker compose restart rabbitmq
   # Дождаться healthy, затем worker
   docker compose restart worker
   ```

3. **Проверить DLQ**: Failed сообщения сохраняются в Tarantool
   ```bash
   docker exec tarantool-cache tarantool -e "
     local count = 0
     for _, t in box.space.persistent:pairs() do
       if t.key:match('^dlq:') then count = count + 1 end
     end
     print('DLQ messages: ' .. count)
   "
   ```

### Предотвращение
- Автоматический fallback на background tasks
- DLQ с Dead Letter Exchange — сообщения не теряются
- Healthcheck каждые 10 секунд

---

## 5. High Error Rate

**Severity:** HIGH
**SLA:** < 30 мин

### Симптомы
- Alert: HTTP 5xx rate > 5%
- `client_errors_total` counter растёт
- Пользователи сообщают об ошибках

### Диагностика

```bash
# Метрики ошибок
curl -s http://localhost:8000/api/v1/metrics | grep error

# Логи ошибок
docker logs counterparty-analyzer 2>&1 | grep "ERROR\|500\|exception" | tail -30

# Трейсы (если Tempo включён)
# Grafana → Explore → Tempo → status=ERROR
```

### Действия

1. Определить паттерн ошибок (один endpoint или все)
2. Проверить внешние зависимости (DaData, Casebook, LLM)
3. Проверить ресурсы: `docker stats`
4. Перезапуск при необходимости: `docker compose restart app`

---

## 6. Memory Leak

**Severity:** MEDIUM
**SLA:** < 1 час

### Симптомы
- Alert: memory usage > 80%
- Container OOM killed
- `docker stats` показывает рост памяти

### Диагностика

```bash
# Текущее использование
docker stats --no-stream

# Memory monitor endpoint
curl -s http://localhost:8000/api/v1/metrics | grep memory

# Проверить кэш
docker exec tarantool-cache tarantool -e "print('cache=' .. box.space.cache:len())"
```

### Действия

1. **Очистить кэш**:
   ```bash
   docker exec tarantool-cache tarantool -e "cache_clear(); print('Cache cleared')"
   ```

2. **Перезапуск** (сбрасывает in-memory state):
   ```bash
   docker compose restart app
   ```

3. **Если повторяется**: Проверить `_search_cache` LRU лимит (maxlen=10000)

### Предотвращение
- LRU eviction в `_search_cache` (OrderedDict, maxlen=10000)
- Memory monitor с автоочисткой
- Resource limits: 2GB для app

---

## 7. ChromaDB Failure

**Severity:** LOW
**SLA:** < 2 часа

### Симптомы
- Логи: "ChromaDB not available"
- RAG контекст не добавляется к анализу
- Анализ работает, но без обогащения из прошлых отчётов

### Действия

Система продолжает работать без RAG (graceful degradation).

```bash
docker compose restart chroma
# Проверить
curl -s http://localhost:8100/api/v1/heartbeat
```

---

## 8. API Key Expiry

**Severity:** MEDIUM
**SLA:** < 1 час

### Симптомы
- 401/403 от внешних API
- `client_source_requests_total{status="failure"}` растёт

### Действия

1. Обновить ключ в `.env` файле
2. `docker compose restart app worker`
3. Или через HashiCorp Vault (если настроен)

---

## 9. Disk Full

**Severity:** HIGH
**SLA:** < 30 мин

### Действия

```bash
# Диагностика
df -h
docker system df

# Очистка
docker system prune -f
docker volume prune -f

# Ротация бэкапов Tarantool
ls -la ./backups/tarantool/ | head -20

# Очистка старых логов
find ./logs -name "*.log" -mtime +7 -delete

# Очистка старых отчётов PDF
find ./reports -name "*.pdf" -mtime +30 -delete
```

---

## 10. Slow Analysis

**Severity:** MEDIUM
**SLA:** < 1 час

### Симптомы
- `client_analysis_duration_seconds` > 300s
- Пользователи жалуются на timeout

### Диагностика

```bash
# Метрики по стадиям
curl -s http://localhost:8000/api/v1/metrics | grep analysis_duration

# Трейсы в Grafana → Tempo
# Найти самые долгие span'ы: http.request, llm.ainvoke

# Активные анализы
curl -s http://localhost:8000/api/v1/metrics | grep analysis_active
```

### Действия

1. Проверить latency внешних API (DaData, Casebook, Perplexity)
2. Проверить LLM latency — возможно провайдер перегружен
3. Проверить кэш — при холодном кэше анализ дольше

---

## Общие команды

```bash
# Статус всех сервисов
docker compose ps

# Логи конкретного сервиса
docker logs <container> --tail 50 -f

# Ресурсы
docker stats --no-stream

# Grafana дашборды
open http://localhost:3000

# Prometheus метрики
open http://localhost:9090

# Alertmanager
open http://localhost:9093

# RabbitMQ Management
open http://localhost:15672

# Tempo traces (через Grafana)
# Grafana → Explore → Datasource: Tempo
```

## Контакты

| Роль | Канал |
|------|-------|
| On-call инженер | Slack #alerts |
| DPO (инциденты PII) | Согласно регламенту 152-ФЗ |
| Alertmanager | Автоматические уведомления в Slack |
