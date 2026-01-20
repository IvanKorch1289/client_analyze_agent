# ADR-001: Использование Tarantool как кэш-хранилища

**Статус:** Принято
**Дата:** 2026-01-14
**Авторы:** Development Team

## Контекст

Система Client Analysis Agent требует высокопроизводительное кэширование для:
- Результатов API запросов (DaData, InfoSphere, Casebook)
- LLM ответов (дорогие вызовы ~30-40 сек)
- Результатов веб-поиска (Perplexity, Tavily)
- Истории анализов (threads)

## Рассмотренные альтернативы

### 1. Redis
**Плюсы:**
- Широко распространён
- Богатая экосистема
- Простой в использовании

**Минусы:**
- Только key-value, нет реляционных возможностей
- Нет встроенного Lua для сложной логики
- Ограниченная поддержка транзакций

### 2. PostgreSQL + Redis
**Плюсы:**
- Реляционные возможности PostgreSQL
- Кэширование в Redis

**Минусы:**
- Два сервиса для поддержки
- Сложность синхронизации
- Дополнительные ресурсы

### 3. Tarantool
**Плюсы:**
- In-memory с персистентностью
- Встроенный Lua для бизнес-логики
- Поддержка spaces (таблиц) с индексами
- Один сервис для кэша и хранения
- Высокая производительность (до 1M ops/sec)

**Минусы:**
- Меньшее сообщество чем Redis
- Требует изучения Lua

## Решение

Выбран **Tarantool** как единое решение для кэширования и хранения данных.

### Архитектура spaces:

```lua
-- cache: TTL-based кэш для API результатов
box.schema.space.create('cache', {if_not_exists = true})
box.space.cache:create_index('primary', {parts = {1, 'string'}})
box.space.cache:create_index('expires', {parts = {3, 'unsigned'}, unique = false})

-- reports: Отчёты анализа (30 дней retention)
box.schema.space.create('reports', {if_not_exists = true})
box.space.reports:create_index('primary', {parts = {1, 'string'}})
box.space.reports:create_index('by_inn', {parts = {3, 'string'}, unique = false})

-- threads: История анализов
box.schema.space.create('threads', {if_not_exists = true})
box.space.threads:create_index('primary', {parts = {1, 'string'}})
box.space.threads:create_index('by_client', {parts = {3, 'string'}, unique = false})

-- persistent: Долгосрочное хранение (audit logs, settings)
box.schema.space.create('persistent', {if_not_exists = true})
box.space.persistent:create_index('primary', {parts = {1, 'string'}})
```

### TTL политики:

| Space | TTL | Причина |
|-------|-----|---------|
| cache | 1-2 часа | Актуальность данных API |
| reports | 30 дней | Compliance требования |
| threads | 90 дней | История для аналитики |
| persistent | Без TTL | Audit logs, настройки |

## Последствия

### Позитивные:
- Единая точка для кэша и хранения
- Высокая производительность
- Возможность сложных запросов через Lua
- Меньше infrastructure overhead

### Негативные:
- Команда должна изучить Tarantool/Lua
- Меньше готовых решений/библиотек
- Необходимость написания собственных миграций

## Связанные документы
- `app/storage/tarantool.py` - Python клиент
- `app/storage/init.lua` - Инициализация spaces
- `docs/adr/002-llm-fallback.md` - LLM стратегия
