# Руководство по развёртыванию — Client Analyze Agent

> Пошаговая инструкция по настройке и запуску системы в различных окружениях

## Содержание

- [Предварительные требования](#предварительные-требования)
- [Переменные окружения](#переменные-окружения)
- [Опциональные сервисы](#опциональные-сервисы)
- [Режим разработки](#режим-разработки)
- [Режим production](#режим-production)
- [Health Checks и мониторинг](#health-checks-и-мониторинг)
- [Масштабирование](#масштабирование)
- [Docker развёртывание](#docker-развёртывание)

---

## Предварительные требования

### Системные требования

| Компонент | Минимум | Рекомендуется |
|-----------|---------|---------------|
| Python | 3.11+ | 3.11.x |
| RAM | 2 GB | 4 GB |
| CPU | 2 cores | 4 cores |
| Диск | 1 GB | 5 GB |

### Обязательные зависимости

```bash
# Python 3.11+
python3 --version

# pip или poetry
pip --version
# или
poetry --version
```

### Обязательные API ключи

Для полноценной работы системы необходимы:

| Сервис | Переменная | Назначение |
|--------|------------|------------|
| OpenRouter | `OPENROUTER_API_KEY` | Основной LLM провайдер |
| Perplexity | `PERPLEXITY_API_KEY` | Веб-поиск AI |
| Tavily | `TAVILY_TOKEN` | Расширенный веб-поиск |

### Опциональные API ключи

| Сервис | Переменная | Назначение |
|--------|------------|------------|
| HuggingFace | `HUGGINGFACE_API_KEY` | Fallback LLM #1 |
| GigaChat | `GIGACHAT_API_KEY` | Fallback LLM #2 |
| YandexGPT | `YANDEX_API_KEY` | Fallback LLM #3 |
| DaData | `DADATA_API_KEY` | Данные компаний |
| Casebook | `CASEBOOK_API_KEY` | Судебные дела |
| InfoSphere | `INFOSPHERE_API_KEY` | Финансовая аналитика |

---

## Переменные окружения

### Минимальная конфигурация

Создайте файл `.env` в корне проекта:

```bash
# === ОБЯЗАТЕЛЬНЫЕ ===

# LLM провайдер (основной)
OPENROUTER_API_KEY=sk-or-v1-xxxxxxx

# Веб-поиск
PERPLEXITY_API_KEY=pplx-xxxxxxx
TAVILY_TOKEN=tvly-xxxxxxx

# Безопасность
ADMIN_TOKEN=your_secure_admin_token_here

# === РЕКОМЕНДУЕМЫЕ ===

# Режим приложения
APP_ENV=development  # или production

# Порты (по умолчанию)
BACKEND_PORT=8000
STREAMLIT_PORT=5000
```

### Полная конфигурация

```bash
# ===========================================
# CORE CONFIGURATION
# ===========================================

# Режим приложения
APP_ENV=production
DEBUG=false
LOG_LEVEL=INFO

# Безопасность
ADMIN_TOKEN=your_secure_admin_token_minimum_32_chars

# ===========================================
# LLM PROVIDERS
# ===========================================

# OpenRouter (основной)
OPENROUTER_API_KEY=sk-or-v1-xxxxxxx
OPENROUTER_MODEL=anthropic/claude-3.5-sonnet

# Fallback провайдеры (опционально)
HUGGINGFACE_API_KEY=hf_xxxxxxx
GIGACHAT_API_KEY=xxxxxxx
YANDEX_API_KEY=xxxxxxx

# ===========================================
# SEARCH PROVIDERS
# ===========================================

# Perplexity AI
PERPLEXITY_API_KEY=pplx-xxxxxxx

# Tavily
TAVILY_TOKEN=tvly-xxxxxxx

# ===========================================
# DATA PROVIDERS
# ===========================================

# DaData
DADATA_API_KEY=xxxxxxx
DADATA_SECRET_KEY=xxxxxxx

# Casebook
CASEBOOK_API_KEY=xxxxxxx

# InfoSphere
INFOSPHERE_API_KEY=xxxxxxx

# ===========================================
# STORAGE (опционально)
# ===========================================

# Tarantool
TARANTOOL_HOST=localhost
TARANTOOL_PORT=3301
TARANTOOL_USER=admin
TARANTOOL_PASSWORD=xxxxxxx

# ===========================================
# MESSAGING (опционально)
# ===========================================

# RabbitMQ
RABBITMQ_URL=amqp://guest:guest@localhost:5672/
RABBITMQ_QUEUE=client_analysis

# ===========================================
# EMAIL (опционально)
# ===========================================

SMTP_HOST=smtp.example.com
SMTP_PORT=587
SMTP_USER=user@example.com
SMTP_PASSWORD=xxxxxxx
SMTP_FROM=noreply@example.com
```

### Загрузка переменных

Система автоматически загружает `.env` при запуске через `python-dotenv`.

---

## Опциональные сервисы

### Tarantool (кэширование)

Tarantool используется для хранения отчётов и кэширования. При недоступности система работает в fallback-режиме (in-memory).

**Установка Tarantool:**

```bash
# Ubuntu/Debian
curl -L https://tarantool.io/release/2/installer.sh | bash
sudo apt-get install tarantool

# Или через Docker
docker run -d --name tarantool \
  -p 3301:3301 \
  tarantool/tarantool:2.11
```

**Конфигурация:**

```bash
TARANTOOL_HOST=localhost
TARANTOOL_PORT=3301
TARANTOOL_USER=admin
TARANTOOL_PASSWORD=your_password
```

**Проверка подключения:**

```bash
curl http://localhost:8000/api/v1/utility/tarantool/status
```

### RabbitMQ (очередь сообщений)

RabbitMQ используется для асинхронной обработки задач. Опционален для базового использования.

**Установка:**

```bash
# Docker
docker run -d --name rabbitmq \
  -p 5672:5672 \
  -p 15672:15672 \
  rabbitmq:3-management
```

**Конфигурация:**

```bash
RABBITMQ_URL=amqp://guest:guest@localhost:5672/
```

**Проверка:**

```bash
curl http://localhost:8000/api/v1/utility/queue/stats
```

---

## Режим разработки

### Быстрый старт

```bash
# 1. Клонировать репозиторий
git clone <repo-url>
cd client-analyze-agent

# 2. Создать виртуальное окружение (опционально, для локальной разработки)
python -m venv venv
source venv/bin/activate  # Linux/Mac
# или
.\venv\Scripts\activate  # Windows

# 3. Установить зависимости
pip install -r requirements.txt
# или
poetry install

# 4. Настроить переменные окружения
cp .env.example .env
# Редактировать .env с вашими API ключами

# 5. Запустить приложение
python run.py
```

### Порты

| Сервис | Порт | URL |
|--------|------|-----|
| FastAPI Backend | 8000 | http://localhost:8000 |
| Streamlit Frontend | 5000 | http://localhost:5000 |
| API Docs | 8000 | http://localhost:8000/docs |

### Отдельный запуск компонентов

```bash
# Только backend
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload

# Только frontend
streamlit run app/frontend/app.py --server.port 5000

# MCP Server (опционально)
python -m app.mcp_server.main
```

### Hot Reload

В режиме разработки:

```bash
# Backend с автоперезагрузкой
uvicorn app.main:app --reload --reload-dir app

# Frontend (Streamlit автоматически перезагружается)
streamlit run app/frontend/app.py
```

---

## Режим production

### Подготовка

1. **Проверьте все обязательные переменные окружения**
2. **Установите production-значения:**

```bash
APP_ENV=production
DEBUG=false
LOG_LEVEL=INFO
```

3. **Убедитесь в наличии Tarantool (рекомендуется)**

### Запуск

```bash
# Gunicorn для production
gunicorn app.main:app \
  --bind 0.0.0.0:8000 \
  --workers 4 \
  --worker-class uvicorn.workers.UvicornWorker \
  --timeout 120 \
  --keep-alive 5 \
  --access-logfile - \
  --error-logfile -

# Streamlit (в отдельном процессе)
streamlit run app/frontend/app.py \
  --server.port 5000 \
  --server.address 0.0.0.0 \
  --server.headless true \
  --browser.gatherUsageStats false
```

### Systemd сервисы

> **Примечание:** Ниже приведены примеры конфигурации systemd для production-развёртывания. Эти файлы нужно создать вручную на сервере.

**Backend сервис** (`/etc/systemd/system/client-analyzer-backend.service`):

```ini
[Unit]
Description=Client Analyzer Backend
After=network.target

[Service]
Type=simple
User=www-data
WorkingDirectory=/opt/client-analyzer
EnvironmentFile=/opt/client-analyzer/.env
ExecStart=/opt/client-analyzer/venv/bin/gunicorn app.main:app \
  --bind 0.0.0.0:8000 \
  --workers 4 \
  --worker-class uvicorn.workers.UvicornWorker \
  --timeout 120
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
```

**Frontend сервис** (`/etc/systemd/system/client-analyzer-frontend.service`):

```ini
[Unit]
Description=Client Analyzer Frontend
After=network.target

[Service]
Type=simple
User=www-data
WorkingDirectory=/opt/client-analyzer
EnvironmentFile=/opt/client-analyzer/.env
ExecStart=/opt/client-analyzer/venv/bin/streamlit run app/frontend/app.py \
  --server.port 5000 \
  --server.address 0.0.0.0 \
  --server.headless true
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
```

**Управление:**

```bash
sudo systemctl enable client-analyzer-backend
sudo systemctl enable client-analyzer-frontend
sudo systemctl start client-analyzer-backend
sudo systemctl start client-analyzer-frontend
```

### Nginx reverse proxy

> **Примечание:** Пример конфигурации Nginx. Создайте файл `/etc/nginx/sites-available/client-analyzer.conf`.

```nginx
upstream backend {
    server 127.0.0.1:8000;
}

upstream frontend {
    server 127.0.0.1:5000;
}

server {
    listen 80;
    server_name your-domain.com;

    # Frontend (Streamlit)
    location / {
        proxy_pass http://frontend;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_read_timeout 86400;
    }

    # Backend API
    location /api/ {
        proxy_pass http://backend;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_read_timeout 300;
    }

    # Swagger docs
    location /docs {
        proxy_pass http://backend;
        proxy_set_header Host $host;
    }
}
```

---

## Health Checks и мониторинг

### Эндпоинты проверки

| Эндпоинт | Описание | Использование |
|----------|----------|---------------|
| `GET /api/v1/utility/health` | Базовая проверка | Load balancer |
| `GET /api/v1/utility/health?deep=true` | Глубокая проверка | Мониторинг |
| `GET /api/v1/utility/metrics` | HTTP метрики | Prometheus |
| `GET /api/v1/utility/app-metrics` | Метрики приложения | Grafana |

### Примеры проверок

**Базовый health check:**

```bash
curl -f http://localhost:8000/api/v1/utility/health
```

**Ожидаемый ответ:**

```json
{
  "status": "healthy",
  "issues": null,
  "components": {
    "http_client": "healthy",
    "tarantool": "healthy",
    "openrouter": {"configured": true, "status": "ready"},
    "perplexity": {"configured": true, "status": "ready"},
    "tavily": {"configured": true, "status": "ready"}
  }
}
```

**Глубокая проверка (с реальными запросами):**

```bash
curl http://localhost:8000/api/v1/utility/health?deep=true
```

### Kubernetes liveness/readiness

```yaml
livenessProbe:
  httpGet:
    path: /api/v1/utility/health
    port: 8000
  initialDelaySeconds: 10
  periodSeconds: 30
  timeoutSeconds: 5
  failureThreshold: 3

readinessProbe:
  httpGet:
    path: /api/v1/utility/health?deep=true
    port: 8000
  initialDelaySeconds: 15
  periodSeconds: 60
  timeoutSeconds: 30
  failureThreshold: 2
```

### Мониторинг Circuit Breakers

```bash
# Статус всех CB
curl http://localhost:8000/api/v1/utility/circuit-breakers

# Сброс конкретного CB (admin)
curl -X POST http://localhost:8000/api/v1/utility/circuit-breakers/perplexity/reset \
  -H "X-Auth-Token: your_admin_token"
```

### Логирование

```bash
# Получить логи
curl "http://localhost:8000/api/v1/utility/logs?limit=100&since_minutes=30" \
  -H "X-Auth-Token: your_admin_token"

# Статистика логов
curl http://localhost:8000/api/v1/utility/logs/stats \
  -H "X-Auth-Token: your_admin_token"
```

---

## Масштабирование

### Горизонтальное масштабирование

**Backend (FastAPI):**

- Stateless — можно запускать несколько инстансов
- Используйте load balancer (Nginx, HAProxy, K8s Ingress)
- Рекомендуется: 2-4 worker'а на CPU core

```bash
# Gunicorn с несколькими workers
gunicorn app.main:app \
  --workers $(nproc) \
  --worker-class uvicorn.workers.UvicornWorker
```

**Frontend (Streamlit):**

- Каждый инстанс обслуживает отдельных пользователей
- Для высокой нагрузки используйте несколько инстансов за load balancer

### Вертикальное масштабирование

**Рекомендации по ресурсам:**

| Нагрузка | RAM | CPU | Workers |
|----------|-----|-----|---------|
| Низкая (< 10 req/min) | 2 GB | 2 | 2 |
| Средняя (10-50 req/min) | 4 GB | 4 | 4 |
| Высокая (> 50 req/min) | 8 GB | 8 | 8 |

### Кэширование

**Tarantool:**

- Рекомендуется для production
- TTL кэша: 24 часа для данных, 30 дней для отчётов
- При недоступности — fallback на in-memory

**Redis (альтернатива):**

Поддержка Redis может быть добавлена для:
- Session storage
- Rate limiting
- Distributed caching

---

## Docker развёртывание

> **Примечание:** Ниже приведены примеры конфигурации Docker для production. Dockerfile и docker-compose.yml нужно создать в корне проекта.

### Сборка образа

```bash
docker build -t client-analyzer:latest .
```

### Docker Compose

```yaml
version: '3.8'

services:
  backend:
    build: .
    ports:
      - "8000:8000"
    environment:
      - APP_ENV=production
      - OPENROUTER_API_KEY=${OPENROUTER_API_KEY}
      - PERPLEXITY_API_KEY=${PERPLEXITY_API_KEY}
      - TAVILY_TOKEN=${TAVILY_TOKEN}
      - ADMIN_TOKEN=${ADMIN_TOKEN}
      - TARANTOOL_HOST=tarantool
    depends_on:
      - tarantool
    command: >
      gunicorn app.main:app 
      --bind 0.0.0.0:8000 
      --workers 4 
      --worker-class uvicorn.workers.UvicornWorker

  frontend:
    build: .
    ports:
      - "5000:5000"
    environment:
      - BACKEND_URL=http://backend:8000
    depends_on:
      - backend
    command: >
      streamlit run app/frontend/app.py 
      --server.port 5000 
      --server.address 0.0.0.0

  tarantool:
    image: tarantool/tarantool:2.11
    ports:
      - "3301:3301"
    volumes:
      - tarantool_data:/var/lib/tarantool

  rabbitmq:
    image: rabbitmq:3-management
    ports:
      - "5672:5672"
      - "15672:15672"

volumes:
  tarantool_data:
```

### Запуск

```bash
# Создать .env файл с переменными
docker-compose up -d

# Проверить логи
docker-compose logs -f

# Остановить
docker-compose down
```

---

## Чек-лист развёртывания

### Pre-deployment

- [ ] Python 3.11+ установлен
- [ ] Все зависимости установлены
- [ ] `.env` файл создан и заполнен
- [ ] Обязательные API ключи настроены
- [ ] `ADMIN_TOKEN` установлен (минимум 32 символа)

### Deployment

- [ ] Backend запускается без ошибок
- [ ] Frontend доступен на порту 5000
- [ ] Health check возвращает `healthy`
- [ ] Swagger UI доступен на `/docs`

### Post-deployment

- [ ] Тестовый анализ выполняется успешно
- [ ] PDF генерация работает
- [ ] Логи записываются корректно
- [ ] Circuit breakers в состоянии `closed`

### Production

- [ ] HTTPS настроен (reverse proxy)
- [ ] Rate limiting активен
- [ ] Мониторинг настроен
- [ ] Бэкапы Tarantool настроены
- [ ] Алерты на ошибки настроены
