# Disaster Recovery Plan - Client Analysis Agent

**Версия:** 1.0
**Дата:** 2026-01-20
**Ответственный:** DevOps Team

---

## 1. Обзор системы

### Компоненты

| Компонент | Критичность | RTO | RPO |
|-----------|-------------|-----|-----|
| FastAPI Backend | Critical | 15 min | 0 |
| Streamlit UI | High | 30 min | 0 |
| Tarantool Cache | High | 30 min | 1 hour |
| RabbitMQ | Medium | 1 hour | 0 |
| Prometheus | Low | 2 hours | 24 hours |
| Grafana | Low | 2 hours | 24 hours |

**RTO** - Recovery Time Objective (максимальное время восстановления)
**RPO** - Recovery Point Objective (максимальная потеря данных)

---

## 2. Сценарии сбоев

### 2.1 Сбой FastAPI Backend

**Симптомы:**
- HTTP 5xx ошибки
- Health check `/utility/health` не отвечает
- Prometheus alert: `ServiceDown`

**Причины:**
- OOM (Out of Memory)
- Deadlock в async коде
- Сбой зависимости (Tarantool, RabbitMQ)

**Восстановление:**
```bash
# 1. Проверить логи
docker logs counterparty-analyzer --tail 100

# 2. Перезапустить контейнер
docker-compose restart app

# 3. Если не помогает - пересобрать
docker-compose down app
docker-compose up -d --build app

# 4. Проверить health
curl http://localhost:8000/utility/health
```

### 2.2 Сбой Tarantool

**Симптомы:**
- Ошибки "Connection refused" в логах
- Кэш не работает (медленные запросы)

**Причины:**
- Corrupted WAL/snapshot
- Disk full
- Memory exhausted

**Восстановление:**
```bash
# 1. Проверить состояние
docker exec tarantool-cache tarantoolctl status

# 2. Проверить место на диске
docker exec tarantool-cache df -h

# 3. При corruption - восстановить из snapshot
docker-compose down tarantool
rm -rf /var/lib/docker/volumes/client_analyze_agent_tarantool_data/_data/*.xlog
docker-compose up -d tarantool

# 4. Прогреть кэш (опционально)
# Кэш прогреется автоматически при первых запросах
```

### 2.3 Сбой LLM провайдеров

**Симптомы:**
- Prometheus alert: `AllLLMProvidersFailing`
- Высокое количество fallbacks
- Медленные ответы (>60 сек)

**Причины:**
- OpenRouter/HuggingFace/GigaChat недоступны
- Rate limits
- Network issues

**Восстановление:**
```bash
# 1. Проверить статус провайдеров
curl -s https://status.openai.com/api/v2/status.json
curl -s https://status.huggingface.co/api/v2/status.json

# 2. Проверить API ключи
grep -E "OPENROUTER|HUGGINGFACE|GIGACHAT" .env

# 3. Временно отключить неработающих провайдеров
# Отредактировать app/agents/llm_manager.py:
# self._provider_status[LLMProvider.OPENROUTER] = False

# 4. Перезапустить приложение
docker-compose restart app
```

### 2.4 Сбой внешних API (DaData, InfoSphere, Casebook)

**Симптомы:**
- Prometheus alert: `DataSourceUnavailable`
- Частичные отчёты (missing data)

**Причины:**
- API недоступен
- Истёк API ключ
- Rate limits

**Восстановление:**
```bash
# 1. Проверить доступность
curl -I https://dadata.ru/api/v2/

# 2. Проверить лимиты в dashboard провайдера

# 3. Система продолжит работать с доступными источниками
# Fallback логика обработает недоступность
```

---

## 3. Backup стратегия

### 3.1 Tarantool Snapshots

```bash
# Автоматические snapshots каждые 6 часов
# Конфигурация в init.lua:
box.cfg {
    checkpoint_interval = 21600,  -- 6 hours
    checkpoint_count = 4,         -- Keep last 4 snapshots
}

# Ручной snapshot
docker exec tarantool-cache tarantoolctl snapshot
```

### 3.2 Backup отчётов

```bash
# Отчёты хранятся в ./reports/
# Ежедневный backup в S3 (настроить cron):
0 2 * * * aws s3 sync ./reports/ s3://backup-bucket/reports/$(date +%Y-%m-%d)/
```

### 3.3 Конфигурация

```bash
# Backup .env и docker-compose.yml
cp .env .env.backup.$(date +%Y%m%d)
cp docker-compose.yml docker-compose.yml.backup.$(date +%Y%m%d)
```

---

## 4. Мониторинг и Alerting

### 4.1 Health Checks

| Endpoint | Интервал | Timeout |
|----------|----------|---------|
| `/utility/health` | 30s | 10s |
| `/metrics` | 15s | 5s |
| Prometheus targets | 30s | 5s |

### 4.2 Prometheus Alerts

```yaml
# Критические алерты (P1):
- HighErrorRate (>5% 5xx за 5 минут)
- ServiceDown (FastAPI недоступен)
- AllLLMProvidersFailing (>50% failures)
- DataSourceUnavailable (любой источник)

# Предупреждения (P2):
- HighLLMLatency (P95 >60s)
- LowCacheHitRate (<50%)
- HighMemoryUsage (>2GB)
```

### 4.3 Notification Channels

```yaml
# Настроить в Alertmanager:
receivers:
  - name: 'critical'
    slack_configs:
      - channel: '#alerts-critical'
    pagerduty_configs:
      - service_key: '<key>'

  - name: 'warning'
    slack_configs:
      - channel: '#alerts-warning'
```

---

## 5. Rollback процедуры

### 5.1 Откат версии приложения

```bash
# 1. Определить предыдущую рабочую версию
docker images | grep counterparty

# 2. Откатить на предыдущий образ
docker tag counterparty-analyzer:previous counterparty-analyzer:latest
docker-compose up -d app

# 3. Или откатить через git
git log --oneline -10
git checkout <commit-hash>
docker-compose up -d --build app
```

### 5.2 Откат конфигурации

```bash
# 1. Восстановить .env
cp .env.backup.<date> .env

# 2. Перезапустить
docker-compose restart
```

---

## 6. Контакты

| Роль | Контакт | Телефон |
|------|---------|---------|
| DevOps Lead | devops@company.com | +7-XXX-XXX-XXXX |
| Backend Lead | backend@company.com | +7-XXX-XXX-XXXX |
| On-call | oncall@company.com | PagerDuty |

---

## 7. Чеклист восстановления

### При полном отказе системы:

- [ ] Проверить статус всех контейнеров: `docker-compose ps`
- [ ] Проверить логи: `docker-compose logs --tail 50`
- [ ] Проверить сеть: `docker network inspect client_analyze_agent_app-network`
- [ ] Проверить volumes: `docker volume ls`
- [ ] Перезапустить все сервисы: `docker-compose down && docker-compose up -d`
- [ ] Проверить health: `curl localhost:8000/utility/health`
- [ ] Проверить метрики: `curl localhost:8000/metrics`
- [ ] Проверить UI: открыть http://localhost:5000
- [ ] Выполнить тестовый анализ
- [ ] Уведомить команду о восстановлении

---

**Последнее обновление:** 2026-01-20
**Следующий review:** 2026-04-20 (каждые 3 месяца)
