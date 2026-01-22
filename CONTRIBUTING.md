# Руководство по участию в разработке Client Analysis Agent

Благодарим за интерес к участию в разработке Client Analysis Agent! Этот документ содержит рекомендации и инструкции для участников проекта.

## Содержание

- [Кодекс поведения](#кодекс-поведения)
- [Начало работы](#начало-работы)
- [Настройка окружения разработки](#настройка-окружения-разработки)
- [Внесение изменений](#внесение-изменений)
- [Процесс Pull Request](#процесс-pull-request)
- [Стиль кода](#стиль-кода)
- [Тестирование](#тестирование)
- [Документация](#документация)

## Кодекс поведения

Участвуя в этом проекте, вы соглашаетесь:

- Быть уважительным и инклюзивным
- Принимать конструктивную критику с благодарностью
- Фокусироваться на том, что лучше для сообщества
- Проявлять эмпатию к другим участникам

## Начало работы

### Предварительные требования

- Python 3.12+
- Poetry (управление зависимостями)
- Docker и Docker Compose
- Git

### Форк и клонирование

1. Сделайте форк репозитория на GitHub
2. Клонируйте свой форк локально:
   ```bash
   git clone https://github.com/YOUR_USERNAME/client_analyze_agent.git
   cd client_analyze_agent
   ```
3. Добавьте upstream remote:
   ```bash
   git remote add upstream https://github.com/IvanKorch1289/client_analyze_agent.git
   ```

## Настройка окружения разработки

### 1. Установка зависимостей

```bash
# Установите Poetry, если еще не установлен
pip install poetry

# Установите зависимости проекта
poetry install

# Активируйте виртуальное окружение
poetry shell
```

### 2. Настройка переменных окружения

```bash
# Скопируйте файл с примером переменных окружения
cp .env.example .env

# Отредактируйте .env, добавив ваши API ключи
# Обязательные: OPENROUTER_API_KEY, DADATA_API_KEY и т.д.
```

### 3. Запуск сервисов

```bash
# Запустите все сервисы с помощью Docker Compose
docker-compose up -d

# Или запустите только зависимости (Tarantool, RabbitMQ)
docker-compose up -d tarantool rabbitmq
```

### 4. Запуск приложения

```bash
# Запустите основное приложение
python run.py

# Или запустите отдельные компоненты
python -m app.messaging.worker  # Worker
python -m app.mcp_server.main   # MCP Server
```

## Внесение изменений

### Соглашение об именовании веток

- `feature/` - Новые функции (например, `feature/add-new-data-source`)
- `fix/` - Исправления ошибок (например, `fix/circuit-breaker-timeout`)
- `docs/` - Изменения в документации (например, `docs/update-api-reference`)
- `refactor/` - Рефакторинг кода (например, `refactor/split-large-module`)
- `test/` - Добавление/изменение тестов (например, `test/add-integration-tests`)

### Рабочий процесс

1. Создайте новую ветку от `main`:
   ```bash
   git checkout main
   git pull upstream main
   git checkout -b feature/your-feature-name
   ```

2. Внесите изменения, следуя рекомендациям [Стиля кода](#стиль-кода)

3. Напишите тесты для новой функциональности

4. Запустите набор тестов:
   ```bash
   poetry run pytest
   ```

5. Запустите линтеры и проверку типов:
   ```bash
   poetry run ruff check .
   poetry run pyright
   ```

6. Зафиксируйте изменения:
   ```bash
   git add .
   git commit -m "feat: добавить интеграцию нового источника данных"
   ```

### Соглашение о коммитах

Мы следуем [Conventional Commits](https://www.conventionalcommits.org/ru/):

- `feat:` - Новая функция
- `fix:` - Исправление ошибки
- `docs:` - Только документация
- `style:` - Форматирование, изменений кода нет
- `refactor:` - Реструктуризация кода
- `test:` - Добавление тестов
- `chore:` - Задачи по обслуживанию

Примеры:
```
feat: добавить интеграцию Spark API
fix: исправить состояние гонки circuit breaker
docs: обновить руководство по развертыванию
refactor: разделить data_collector на модули
test: добавить юнит-тесты защиты PII
```

## Процесс Pull Request

### Перед отправкой

1. **Обновите вашу ветку** с последними изменениями из upstream:
   ```bash
   git fetch upstream
   git rebase upstream/main
   ```

2. **Запустите все проверки**:
   ```bash
   # Линтинг
   poetry run ruff check .

   # Проверка типов
   poetry run pyright

   # Тесты
   poetry run pytest

   # Сканирование безопасности
   poetry run bandit -r app
   ```

3. **Обновите документацию** при необходимости

### Отправка

1. Отправьте вашу ветку в ваш форк:
   ```bash
   git push origin feature/your-feature-name
   ```

2. Создайте Pull Request на GitHub

3. Заполните шаблон PR, указав:
   - Описание изменений
   - Связанные issue
   - Проведенное тестирование
   - Выполнение чек-листа

### Процесс ревью

- PR требуется как минимум одно одобрение
- Проверки CI должны быть успешными
- Оперативно отвечайте на комментарии ревью
- При необходимости объедините коммиты (squash)

## Стиль кода

### Руководство по стилю Python

Мы используем [Ruff](https://docs.astral.sh/ruff/) для линтинга со следующими правилами:

```toml
[tool.ruff.lint]
select = [
  "F",   # pyflakes
  "E",   # pycodestyle
  "I",   # isort
  "B",   # flake8-bugbear
  "C4",  # flake8-comprehensions
]
```

### Ключевые рекомендации

1. **Аннотации типов**: Используйте аннотации типов для всех сигнатур функций
   ```python
   async def fetch_data(inn: str, timeout: int = 30) -> dict[str, Any]:
       ...
   ```

2. **Docstrings**: Используйте docstring в стиле Google
   ```python
   def calculate_risk(data: dict) -> float:
       """Рассчитать нормализованную оценку риска.

       Args:
           data: Необработанные данные из нескольких источников.

       Returns:
           Оценка риска от 0.0 до 100.0.

       Raises:
           ValueError: Если данные неполные.
       """
   ```

3. **Async/Await**: Используйте async для операций ввода-вывода
   ```python
   # Хорошо
   async def fetch_all():
       results = await asyncio.gather(fetch_a(), fetch_b())

   # Плохо - блокировка в async контексте
   async def fetch_all():
       result_a = requests.get(...)  # Не делайте так
   ```

4. **Обработка ошибок**: Используйте специфические исключения
   ```python
   # Хорошо
   except CircuitBreakerOpenError as e:
       logger.warning(f"Circuit open: {e}")

   # Плохо
   except Exception:
       pass
   ```

5. **Импорты**: Группируйте и сортируйте с помощью isort
   ```python
   # Стандартная библиотека
   import asyncio
   from typing import Any

   # Сторонние библиотеки
   from fastapi import FastAPI
   from pydantic import BaseModel

   # Локальные
   from app.services.http_client import resilient_client
   ```

## Тестирование

### Структура тестов

```
tests/
├── unit/           # Юнит-тесты
├── integration/    # Интеграционные тесты
├── e2e/            # Сквозные тесты
├── performance/    # Тесты производительности
└── security/       # Тесты безопасности
```

### Запуск тестов

```bash
# Все тесты
poetry run pytest

# С покрытием
poetry run pytest --cov=app --cov-report=html

# Конкретный файл теста
poetry run pytest tests/test_risk_calculator.py

# Конкретный тест
poetry run pytest tests/test_api.py::test_health_endpoint

# Пропустить интеграционные тесты
SKIP_INTEGRATION=true poetry run pytest
```

### Написание тестов

```python
import pytest
from app.services.risk_calculator import calculate_risk

@pytest.mark.asyncio
async def test_calculate_risk_high():
    """Тест расчета риска для высокорискованной компании."""
    data = {
        "legal_issues": {"court_cases": 15},
        "financial": {"bankruptcy_risk": True},
    }

    score = await calculate_risk(data)

    assert score >= 70.0
    assert score <= 100.0


@pytest.fixture
def mock_http_client(mocker):
    """Mock HTTP клиента для изолированного тестирования."""
    return mocker.patch("app.services.http_client.resilient_client")
```

## Документация

### Типы документации

1. **Документация кода**: Docstrings в коде
2. **API документация**: OpenAPI/Swagger (генерируется автоматически)
3. **Пользовательская документация**: Директория `docs/`
4. **Архитектурные решения**: `docs/adr/` (ADR)

### Обновление документации

- Обновляйте соответствующую документацию при изменении функциональности
- Добавляйте ADR для значительных архитектурных изменений
- Поддерживайте README.md в актуальном состоянии с новыми функциями

### Сборка документации

```bash
# API документация генерируется автоматически на эндпоинте /docs
# Пользовательская документация находится в формате Markdown в docs/
```

## Вопросы?

- Откройте issue для сообщений об ошибках или запросов функций
- Используйте обсуждения для вопросов
- Проверяйте существующие issue перед созданием новых

---

Спасибо за участие в разработке Client Analysis Agent!
