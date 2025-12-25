# Руководство по устранению неполадок — Client Analyze Agent

> Решения типичных проблем и диагностика системы

## Содержание

- [Общие ошибки](#общие-ошибки)
- [Проблемы подключения](#проблемы-подключения)
- [LLM провайдеры и Fallback](#llm-провайдеры-и-fallback)
- [Оптимизация производительности](#оптимизация-производительности)
- [Отладка и логирование](#отладка-и-логирование)
- [FAQ](#faq)

---

## Общие ошибки

### Ошибка: "API key не настроен"

**Симптомы:**
```
503 Service Unavailable
"Perplexity API key не настроен. Добавьте PERPLEXITY_API_KEY в секреты."
```

**Причина:** Отсутствует или неверно указан API ключ.

**Решение:**

1. Проверьте наличие ключей в `.env`:
```bash
grep -E "(PERPLEXITY|TAVILY|OPENROUTER)" .env
```

2. Убедитесь в правильном формате:
```bash
PERPLEXITY_API_KEY=pplx-xxxxxxxxxxxxxxxx
TAVILY_TOKEN=tvly-xxxxxxxxxxxxxxxx
OPENROUTER_API_KEY=sk-or-v1-xxxxxxxxxxxxxxxx
```

3. Перезапустите приложение для применения изменений.

4. Проверьте через API:
```bash
curl http://localhost:8000/api/v1/utility/health?deep=true
```

---

### Ошибка: "Rate limit exceeded"

**Симптомы:**
```
429 Too Many Requests
"Rate limit exceeded. Try again in 60 seconds."
```

**Причина:** Превышен лимит запросов с одного IP.

**Решение:**

1. Подождите указанное время (обычно 60 секунд)

2. Для тестирования увеличьте лимиты в `app/config/constants.py`:
```python
RATE_LIMIT_ANALYZE_CLIENT_PER_MINUTE = 10  # было 3
RATE_LIMIT_SEARCH_PER_MINUTE = 50  # было 20
```

3. В production используйте разные IP или распределите нагрузку.

---

### Ошибка: "Unauthorized" / "Forbidden"

**Симптомы:**
```
401 Unauthorized — "Missing or invalid X-Auth-Token"
403 Forbidden — "Admin access required"
```

**Причина:** Отсутствует или неверный токен администратора.

**Решение:**

1. Проверьте `ADMIN_TOKEN` в `.env`

2. Передавайте токен в заголовке:
```bash
curl -H "X-Auth-Token: your_token" http://localhost:8000/api/v1/utility/config
```

3. В Streamlit введите токен в боковой панели

4. Проверьте роль:
```bash
curl -H "X-Auth-Token: your_token" http://localhost:8000/api/v1/utility/auth/role
```

---

### Ошибка: "Report not found"

**Симптомы:**
```
404 Not Found
"Report rpt_xxx not found"
```

**Причина:** 
- Отчёт не существует
- Tarantool в fallback-режиме (данные потеряны при перезапуске)
- TTL отчёта истёк (30 дней)

**Решение:**

1. Проверьте режим Tarantool:
```bash
curl http://localhost:8000/api/v1/utility/tarantool/status
```

2. Если `mode: in-memory` — данные не персистентны

3. Подключите реальный Tarantool для сохранения данных

---

### Ошибка: "Timeout" при анализе

**Симптомы:**
```
500 Internal Server Error
"Analysis timeout after 360 seconds"
```

**Причина:** 
- Медленный ответ внешних API
- Сетевые проблемы
- Перегрузка LLM провайдера

**Решение:**

1. Проверьте статус внешних сервисов:
```bash
curl http://localhost:8000/api/v1/utility/health?deep=true
```

2. Проверьте circuit breakers:
```bash
curl http://localhost:8000/api/v1/utility/circuit-breakers
```

3. Если CB в состоянии `open` — сбросьте:
```bash
curl -X POST http://localhost:8000/api/v1/utility/circuit-breakers/perplexity/reset \
  -H "X-Auth-Token: your_token"
```

4. Повторите запрос позже

---

### Ошибка генерации PDF

**Симптомы:**
```
"Ошибка при генерации PDF"
"PDF создан, но ссылка на скачивание не получена"
```

**Причина:**
- Отсутствуют данные в отчёте
- Ошибка форматирования
- Проблемы с файловой системой

**Решение:**

1. Используйте JSON как альтернативу (кнопка в интерфейсе)

2. Проверьте права на запись в директорию `reports/`:
```bash
ls -la reports/
# Должна быть запись для пользователя приложения
```

3. Проверьте логи:
```bash
curl "http://localhost:8000/api/v1/utility/logs?level=ERROR&limit=20" \
  -H "X-Auth-Token: your_token"
```

4. Попробуйте повторную генерацию

---

## Проблемы подключения

### Tarantool недоступен

**Симптомы:**
```
"Tarantool connection failed, using in-memory fallback"
utility/tarantool/status → mode: in-memory
```

**Диагностика:**

```bash
# Проверка подключения
nc -zv localhost 3301

# Проверка процесса
ps aux | grep tarantool

# Логи Tarantool
journalctl -u tarantool -n 50
```

**Решение:**

1. Запустите Tarantool:
```bash
# Systemd
sudo systemctl start tarantool

# Docker
docker start tarantool
```

2. Проверьте конфигурацию:
```bash
TARANTOOL_HOST=localhost
TARANTOOL_PORT=3301
```

3. Проверьте firewall:
```bash
sudo ufw allow 3301/tcp
```

4. Система будет работать в fallback-режиме, но данные не сохранятся при перезапуске.

---

### RabbitMQ недоступен

**Симптомы:**
```
"RabbitMQ connection failed"
queue/stats → error
```

**Диагностика:**

```bash
# Проверка подключения
nc -zv localhost 5672

# Management UI
curl http://localhost:15672/api/health/checks/alarms
```

**Решение:**

1. Запустите RabbitMQ:
```bash
docker start rabbitmq
# или
sudo systemctl start rabbitmq-server
```

2. Проверьте URL:
```bash
RABBITMQ_URL=amqp://guest:guest@localhost:5672/
```

3. RabbitMQ опционален — система работает без него для синхронных запросов.

---

### Внешние API недоступны

**Симптомы:**
```
502 Bad Gateway
"External API error: Connection refused"
```

**Диагностика:**

```bash
# Проверка доступности API
curl -I https://api.perplexity.ai
curl -I https://api.tavily.com

# Проверка DNS
nslookup api.perplexity.ai
```

**Решение:**

1. Проверьте интернет-соединение

2. Проверьте proxy/firewall настройки:
```bash
export HTTP_PROXY=
export HTTPS_PROXY=
```

3. Проверьте статус сервисов на их status pages

4. При временной недоступности система использует fallback провайдеры

---

## LLM провайдеры и Fallback

### Цепочка Fallback

Система автоматически переключается между LLM провайдерами:

```
OpenRouter (основной)
    ↓ при ошибке
HuggingFace (fallback #1)
    ↓ при ошибке
GigaChat (fallback #2)
    ↓ при ошибке
YandexGPT (fallback #3)
    ↓ при ошибке
Ошибка: "Все LLM провайдеры недоступны"
```

### Настройка провайдеров

```bash
# Основной (обязательный)
OPENROUTER_API_KEY=sk-or-v1-xxx
OPENROUTER_MODEL=anthropic/claude-3.5-sonnet

# Fallback (опциональные, но рекомендуются)
HUGGINGFACE_API_KEY=hf_xxx
GIGACHAT_API_KEY=xxx
YANDEX_API_KEY=xxx
```

### Проверка доступности

```bash
# Статус OpenRouter
curl http://localhost:8000/api/v1/utility/openrouter/status

# Глубокая проверка всех
curl http://localhost:8000/api/v1/utility/health?deep=true
```

### Типичные ошибки LLM

| Ошибка | Причина | Решение |
|--------|---------|---------|
| `Invalid API key` | Неверный ключ | Проверьте формат ключа |
| `Rate limit exceeded` | Лимит запросов | Подождите или используйте fallback |
| `Model not found` | Неверная модель | Проверьте `OPENROUTER_MODEL` |
| `Context length exceeded` | Слишком длинный запрос | Уменьшите объём данных |

---

## Оптимизация производительности

### Медленные анализы

**Причины и решения:**

1. **Много источников данных**
   - Уменьшите количество источников
   - Используйте кэширование

2. **Медленные внешние API**
   - Проверьте таймауты в конфигурации
   - Настройте circuit breakers

3. **Нехватка ресурсов**
   - Увеличьте RAM до 4 GB
   - Добавьте CPU cores
   - Увеличьте количество workers

### Настройка таймаутов

В `app/config/services.py`:

```python
# Быстрые источники
FAST_SOURCE_TIMEOUT = 30  # секунд

# Медленные источники (Casebook, InfoSphere)
SLOW_SOURCE_TIMEOUT = 360  # секунд

# LLM генерация
LLM_TIMEOUT = 120  # секунд
```

### Оптимизация кэша

```bash
# Проверка метрик кэша
curl http://localhost:8000/api/v1/utility/cache/metrics

# Ожидаемый hit_rate > 0.5 при активном использовании
```

**Низкий hit_rate:**

1. Увеличьте TTL кэша
2. Проверьте, что Tarantool подключен
3. Анализируйте паттерны запросов

### Оптимизация workers

```bash
# Рекомендация: 2-4 worker на CPU core
gunicorn app.main:app \
  --workers $(( $(nproc) * 2 + 1 )) \
  --worker-class uvicorn.workers.UvicornWorker
```

---

## Отладка и логирование

### Включение debug-режима

В `.env`:
```bash
APP_ENV=development
DEBUG=true
LOG_LEVEL=DEBUG
```

### Просмотр логов

**Через API:**

```bash
# Последние ошибки
curl "http://localhost:8000/api/v1/utility/logs?level=ERROR&limit=50" \
  -H "X-Auth-Token: your_token"

# Логи за последний час
curl "http://localhost:8000/api/v1/utility/logs?since_minutes=60" \
  -H "X-Auth-Token: your_token"
```

**Файлы логов:**

```bash
# Текущий лог
tail -f logs/$(date +%Y-%m-%d).log

# Поиск ошибок
grep -i error logs/*.log
```

### Структурированное логирование

Логи содержат:
- `timestamp` — время события
- `level` — уровень (DEBUG, INFO, WARNING, ERROR)
- `component` — компонент системы
- `message` — описание
- `extra` — дополнительные данные (JSON)

Пример:
```json
{
  "timestamp": "2025-12-25T10:00:00",
  "level": "ERROR",
  "component": "perplexity_client",
  "message": "API request failed",
  "extra": {
    "status_code": 429,
    "retry_after": 60
  }
}
```

### Трейсинг

```bash
# Получить трейсы
curl "http://localhost:8000/api/v1/utility/traces?limit=20" \
  -H "X-Auth-Token: your_token"

# Статистика
curl http://localhost:8000/api/v1/utility/traces/stats \
  -H "X-Auth-Token: your_token"
```

### Метрики приложения

```bash
# Общие метрики
curl http://localhost:8000/api/v1/utility/app-metrics \
  -H "X-Auth-Token: your_token"
```

Включает:
- Количество запросов по эндпоинтам
- Среднее время ответа
- Количество ошибок
- Статистика по статус-кодам

---

## FAQ

### Общие вопросы

**Q: Сколько времени занимает анализ?**

A: Обычно 45-90 секунд. Зависит от:
- Количества источников данных
- Скорости ответа внешних API
- Объёма найденной информации
- Нагрузки на LLM провайдера

---

**Q: Можно ли использовать систему без Tarantool?**

A: Да. Система автоматически переключается на in-memory режим. Ограничения:
- Данные теряются при перезапуске
- Не подходит для production
- Нет персистентного кэша

---

**Q: Как добавить новый источник данных?**

A: 
1. Создайте клиент в `app/services/`
2. Добавьте роут в `app/api/routes/data.py`
3. Интегрируйте в `app/agents/data_collector.py`
4. Обновите схемы в `app/schemas/`

---

**Q: Почему circuit breaker в состоянии "open"?**

A: Circuit breaker открывается после нескольких последовательных ошибок (обычно 5). Это защита от каскадных сбоев.

Решение:
1. Подождите восстановления (автоматическое)
2. Или сбросьте вручную через API
3. Проверьте причину ошибок в логах

---

**Q: Как масштабировать систему?**

A:
1. **Горизонтально:** запустите несколько инстансов backend за load balancer
2. **Вертикально:** увеличьте RAM/CPU, количество workers
3. **Кэширование:** подключите Tarantool, увеличьте TTL
4. **Очереди:** используйте RabbitMQ для асинхронной обработки

---

### Безопасность

**Q: Как защитить API?**

A:
1. Используйте `ADMIN_TOKEN` для административных эндпоинтов
2. Настройте HTTPS через reverse proxy
3. Ограничьте доступ по IP (firewall)
4. Не храните ключи в коде

---

**Q: Безопасно ли хранить API ключи в .env?**

A: Для development — да. Для production рекомендуется:
- HashiCorp Vault
- AWS Secrets Manager
- Kubernetes Secrets
- Переменные окружения сервера

---

### Troubleshooting checklist

При возникновении проблем:

1. [ ] Проверить health check: `/utility/health?deep=true`
2. [ ] Проверить логи: `/utility/logs?level=ERROR`
3. [ ] Проверить circuit breakers: `/utility/circuit-breakers`
4. [ ] Проверить конфигурацию: `/utility/config`
5. [ ] Проверить метрики: `/utility/app-metrics`
6. [ ] Перезапустить приложение
7. [ ] Проверить внешние зависимости (Tarantool, RabbitMQ)
8. [ ] Проверить API ключи в `.env`

---

## Контакты поддержки

При неразрешимых проблемах:

1. Соберите диагностическую информацию:
```bash
curl http://localhost:8000/api/v1/utility/health?deep=true > health.json
curl http://localhost:8000/api/v1/utility/logs?limit=100 > logs.json
```

2. Проверьте версию:
```bash
cat pyproject.toml | grep version
```

3. Опишите:
- Шаги воспроизведения
- Ожидаемое поведение
- Фактическое поведение
- Окружение (OS, Python version, Docker)
