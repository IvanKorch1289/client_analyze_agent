# Настройка внутренней LLM и проверка соответствия ТЗ

> **Дата анализа**: 2026-01-16
> **Аналитик**: Claude AI
> **Статус**: ✅ Workflow соответствует ТЗ | ⚠️ Требуется доработка для внутренней LLM

---

## 📋 Executive Summary

### ✅ Соответствие workflow ТЗ

Текущий граф агентов **ПОЛНОСТЬЮ СООТВЕТСТВУЕТ** требованиям ТЗ:

1. ✅ **Запрос данных по API** (DaData, InfoSphere, Casebook) - реализовано
2. ✅ **Запрос Tavily** - реализовано
3. ✅ **Запрос Perplexity** - реализовано
4. ✅ **Агрегация данных** - реализовано в `data_collector_agent`
5. ✅ **Обезличивание данных (PII masking)** - реализовано в `ainvoke` (Sprint 2)
6. ✅ **Передача на глубокий анализ LLM** - реализовано в `report_analyzer_agent`
7. ✅ **Сохранение результата** - реализовано в `file_writer_agent`
8. ✅ **Отправка результата в RabbitMQ** - реализовано в `broker.py`

### ⚠️ Подключение внутренней LLM

**ПРОБЛЕМА**: Текущие настройки предназначены для облачных LLM. Для внутренней LLM на отдельном сервере **требуется доработка**.

**РЕШЕНИЕ**: 3 варианта подключения (описано ниже).

---

## 🔄 Детальный анализ workflow

### Текущий граф агентов (LangGraph)

```
orchestrator_agent
    ↓
data_collector_agent (параллельный сбор)
    ├─ fetch_from_dadata (ИНН, ЕГРЮЛ)
    ├─ fetch_from_infosphere (12+ баз)
    ├─ fetch_from_casebook (судебные дела)
    ├─ fetch_perplexity (поиск с AI)
    └─ fetch_tavily (web scraping TOP-5 ссылок)
    ↓
    ↓ [АГРЕГАЦИЯ ДАННЫХ]
    ↓
report_analyzer_agent
    ↓
    ↓ [PII MASKING] ← обезличивание ПЕРЕД отправкой в LLM
    ↓
    ↓ [LLM АНАЛИЗ] ← глубокий анализ с risk scoring
    ↓
    ↓ [PII UNMASKING] ← восстановление данных в ответе
    ↓
file_writer_agent (сохранение PDF/JSON)
    ↓
[END] → если через RabbitMQ → отправка результата в очередь
```

### Соответствие ТЗ (построчная проверка)

| Требование ТЗ | Файл реализации | Статус |
|---------------|-----------------|--------|
| **1. Выполняется запрос данных по API** | `app/agents/data_collector.py:17-25` | ✅ Реализовано |
| → DaData (ЕГРЮЛ) | `fetch_from_dadata(inn)` | ✅ |
| → InfoSphere (12+ баз) | `fetch_from_infosphere(inn)` | ✅ |
| → Casebook (суды) | `fetch_from_casebook(inn)` | ✅ |
| **2. Выполняется запрос Tavily** | `app/agents/data_collector.py:197-217` | ✅ Реализовано |
| → Web scraping TOP-5 | `scrape_top_tavily_links()` | ✅ Параллельно (5 потоков) |
| **3. Выполняется запрос Perplexity** | `app/agents/data_collector.py:27-91` | ✅ Реализовано |
| → Cascade анализ | `_cascade_perplexity_analysis()` | ✅ Повторный Perplexity с Tavily данными |
| **4. Данные агрегируются** | `app/agents/data_collector.py:298-363` | ✅ Реализовано |
| → `_build_search_results()` | Объединение всех источников | ✅ |
| **5. Данные обезличиваются** | `app/agents/llm_manager.py:448-474` | ✅ Реализовано (Sprint 2) |
| → PII masking | `mask_pii(prompt, level="high")` | ✅ 7 recognizers (ИНН, ФИО, адреса) |
| → Перед отправкой в LLM | `masked_prompt → LLM` | ✅ |
| **6. Данные передаются на глубокий анализ LLM** | `app/agents/report_analyzer.py:98-174` | ✅ Реализовано |
| → Системный промпт | `AnalyzerRole.FINANCIAL_ANALYST` | ✅ |
| → Risk scoring | JSON schema с risk_assessment | ✅ |
| **7. Получаем и сохраняем результат** | `app/agents/file_writer.py` | ✅ Реализовано |
| → PDF генерация | `PDFGenerator().generate()` | ✅ |
| → JSON сохранение | `ClientAnalysisReport` schema | ✅ |
| **8. Если запрос через RabbitMQ → отправка результата в очередь** | `app/messaging/broker.py:84-110` | ✅ Реализовано |
| → Обработчик очереди | `handle_client_analysis()` | ✅ |
| → Возврат результата | `ClientAnalysisResult` | ✅ FastStream auto-publish |

**ИТОГО**: ✅ **8/8 требований выполнено (100%)**

---

## 🔌 Анализ настроек LLM провайдеров

### Текущая конфигурация (config/app.dev.yaml)

```yaml
openrouter:
  api_url: "https://openrouter.ai/api/v1"  # ⚠️ Облачный API
  model: "anthropic/claude-3.5-sonnet"
  temperature: 0.1
  max_tokens: 1000
  timeout: 60.0

huggingface:
  model: "meta-llama/Meta-Llama-3.1-70B-Instruct"  # ⚠️ Inference API
  temperature: 0.2
  max_tokens: 4096
  timeout: 120.0
  # ❌ НЕТ api_url/endpoint_url!

gigachat:
  model: "GigaChat-Pro"  # ⚠️ Только облачный (credentials-based)
  temperature: 0.2
  max_tokens: 4096
  timeout: 120.0

yandexgpt:
  model_uri: "gpt://folder_id/yandexgpt-lite"  # ⚠️ Только облачный
  temperature: 0.3
  max_tokens: 2000
  timeout: 60
```

### Анализ кода подключения

#### 1. OpenRouter (app/agents/llm_manager.py:170-205)

```python
def _get_openrouter_llm(self) -> Any:
    from langchain_openai import ChatOpenAI

    self._openrouter_llm = ChatOpenAI(
        openai_api_base=settings.openrouter.api_url,  # ✅ МОЖНО НАСТРОИТЬ!
        openai_api_key=settings.openrouter.api_key,
        model_name=settings.openrouter.model,
        temperature=settings.openrouter.temperature,
        # ...
    )
```

**✅ ПОДДЕРЖКА ВНУТРЕННЕЙ LLM**: OpenRouter использует `openai_api_base`, что позволяет подключить любой OpenAI-совместимый API.

**Совместимые фреймворки:**
- vLLM (OpenAI-compatible API)
- Text Generation Inference (TGI)
- LM Studio
- llama.cpp server
- FastChat
- LocalAI

#### 2. HuggingFace (app/agents/llm_manager.py:207-234)

```python
def _get_huggingface_llm(self) -> Any:
    from langchain_huggingface import HuggingFaceEndpoint

    self._huggingface_llm = HuggingFaceEndpoint(
        endpoint_url=None,  # ⚠️ None = Inference API
        repo_id=settings.huggingface.model,
        huggingfacehub_api_token=settings.huggingface.api_key,
        # ...
    )
```

**⚠️ ЧАСТИЧНАЯ ПОДДЕРЖКА**: `endpoint_url` можно настроить, но в коде жёстко прописан `None`.

**Требуется изменение:**
1. Добавить `endpoint_url` в конфиг
2. Передать в `HuggingFaceEndpoint(endpoint_url=settings.huggingface.endpoint_url)`

#### 3. GigaChat & YandexGPT

```python
# GigaChat - credentials-based auth (только Сбер облако)
self._gigachat_llm = GigaChat(
    credentials=settings.gigachat.api_key,
    model=settings.gigachat.model,
    # ❌ НЕТ api_url!
)

# YandexGPT - folder_id + model_uri (только Yandex облако)
self._yandexgpt_llm = YandexGPT(
    iam_token=settings.yandexgpt.api_key,
    folder_id=settings.yandexgpt.folder_id,
    # ❌ НЕТ api_url!
)
```

**❌ НЕТ ПОДДЕРЖКИ**: GigaChat и YandexGPT работают только с облачными API Сбера и Яндекса.

---

## 🛠️ Решения для подключения внутренней LLM

### Вариант 1: OpenRouter-compatible API (РЕКОМЕНДУЕТСЯ ✅)

**Описание**: Используем существующий `openrouter` провайдер, меняя только `api_url`.

**Шаги:**

1. **Установите OpenAI-compatible server на внутреннем сервере:**

   ```bash
   # Вариант A: vLLM (рекомендуется для production)
   docker run --gpus all \
     -p 8000:8000 \
     vllm/vllm-openai:latest \
     --model meta-llama/Meta-Llama-3.1-70B-Instruct \
     --host 0.0.0.0 \
     --port 8000

   # Вариант B: Text Generation Inference (TGI)
   docker run --gpus all \
     -p 8080:80 \
     ghcr.io/huggingface/text-generation-inference:latest \
     --model-id meta-llama/Meta-Llama-3.1-70B-Instruct

   # Вариант C: LM Studio (для разработки)
   # Скачать с https://lmstudio.ai/
   # Запустить локальный server (порт 1234)
   ```

2. **Измените конфигурацию (config/app.dev.yaml):**

   ```yaml
   openrouter:
     api_url: "http://internal-llm-server:8000/v1"  # ✅ Ваш внутренний сервер
     api_key: "dummy-key-not-used"  # Если auth не требуется
     model: "meta-llama/Meta-Llama-3.1-70B-Instruct"
     temperature: 0.1
     max_tokens: 4000
     timeout: 120.0  # Увеличьте для больших моделей
   ```

3. **Переменные окружения (.env):**

   ```bash
   OPENROUTER_API_URL=http://internal-llm-server:8000/v1
   OPENROUTER_API_KEY=dummy-key-not-used
   OPENROUTER_MODEL=meta-llama/Meta-Llama-3.1-70B-Instruct
   ```

4. **Проверьте подключение:**

   ```bash
   # Тест через curl
   curl http://internal-llm-server:8000/v1/models

   # Тест через admin API
   curl -X POST http://localhost:8000/admin/llm/test-provider/openrouter \
     -H "X-Auth-Token: ${ADMIN_TOKEN}"
   ```

**Преимущества:**
- ✅ Не требует изменения кода
- ✅ Работает с любой OpenAI-compatible API
- ✅ Fallback на другие провайдеры (HuggingFace, GigaChat)

**Недостатки:**
- ⚠️ Fallback провайдеры остаются облачными

---

### Вариант 2: Добавить новый провайдер (внутренняя LLM)

**Описание**: Добавляем новый enum провайдер `INTERNAL_LLM` с явным указанием на внутренний сервер.

**Шаги:**

1. **Добавьте новый провайдер в enum (app/agents/llm_manager.py:92-98):**

   ```python
   class LLMProvider(str, Enum):
       """Поддерживаемые LLM провайдеры."""

       INTERNAL_LLM = "internal_llm"  # ✅ НОВОЕ
       OPENROUTER = "openrouter"
       HUGGINGFACE = "huggingface"
       GIGACHAT = "gigachat"
       YANDEXGPT = "yandexgpt"
   ```

2. **Добавьте конфигурацию (config/app.dev.yaml):**

   ```yaml
   internal_llm:
     api_url: "http://internal-llm-server:8000/v1"
     api_key: "${INTERNAL_LLM_API_KEY}"
     model: "meta-llama/Meta-Llama-3.1-70B-Instruct"
     temperature: 0.2
     max_tokens: 4096
     timeout: 120.0
     verify_ssl: false  # Для internal сети
   ```

3. **Добавьте метод в LLMManager (app/agents/llm_manager.py):**

   ```python
   def _get_internal_llm(self) -> Any:
       """
       Получить внутреннюю LLM (primary провайдер).

       Returns:
           LLM: Настроенный LLM для внутреннего сервера
       """
       if self._internal_llm is None:
           if not settings.internal_llm.api_key:
               raise ValueError("Internal LLM API key not configured")
           from langchain_openai import ChatOpenAI

           self._internal_llm = ChatOpenAI(
               openai_api_base=settings.internal_llm.api_url,
               openai_api_key=settings.internal_llm.api_key,
               model_name=settings.internal_llm.model,
               temperature=settings.internal_llm.temperature,
               max_tokens=settings.internal_llm.max_tokens,
               timeout=settings.internal_llm.timeout,
           )

           logger.info(
               f"Internal LLM initialized: {settings.internal_llm.model}",
               component="llm_manager",
           )

       return self._internal_llm

   def _get_llm_by_provider(self, provider: LLMProvider) -> Any:
       if provider == LLMProvider.INTERNAL_LLM:  # ✅ НОВОЕ
           return self._get_internal_llm()
       elif provider == LLMProvider.OPENROUTER:
           return self._get_openrouter_llm()
       # ... остальные провайдеры
   ```

4. **Обновите fallback порядок (app/agents/llm_manager.py:121-125):**

   ```python
   def __init_once(self):
       self._fallback_order = [
           LLMProvider.INTERNAL_LLM,  # ✅ НОВОЕ - Primary
           LLMProvider.OPENROUTER,    # Fallback #1
           LLMProvider.HUGGINGFACE,   # Fallback #2
           LLMProvider.GIGACHAT,      # Fallback #3
       ]
   ```

5. **Обновите config schema (app/config/settings.py):**

   ```python
   class InternalLLMConfig(BaseModel):
       """Конфигурация внутренней LLM."""

       api_url: str = Field(default="http://localhost:8000/v1")
       api_key: str = Field(default_factory=lambda: os.getenv("INTERNAL_LLM_API_KEY", ""))
       model: str = Field(default="meta-llama/Meta-Llama-3.1-70B-Instruct")
       temperature: float = Field(default=0.2, ge=0.0, le=2.0)
       max_tokens: int = Field(default=4096, gt=0)
       timeout: float = Field(default=120.0, gt=0)
       verify_ssl: bool = Field(default=False)

   class Settings(BaseSettings):
       # ... существующие настройки ...
       internal_llm: InternalLLMConfig = Field(default_factory=InternalLLMConfig)
   ```

**Преимущества:**
- ✅ Явное разделение internal/external LLM
- ✅ Гибкая настройка fallback порядка
- ✅ Лучшая observability (логи, метрики)

**Недостатки:**
- ⚠️ Требует изменения кода (~100 строк)
- ⚠️ Нужно обновить тесты

---

### Вариант 3: HuggingFace Endpoint (для HuggingFace TGI)

**Описание**: Используем `huggingface` провайдер с настройкой `endpoint_url`.

**Шаги:**

1. **Обновите конфигурацию (config/app.dev.yaml):**

   ```yaml
   huggingface:
     endpoint_url: "http://internal-hf-server:8080"  # ✅ НОВОЕ
     model: "meta-llama/Meta-Llama-3.1-70B-Instruct"
     api_key: "${HUGGINGFACE_API_KEY}"  # Не требуется для TGI
     temperature: 0.2
     max_tokens: 4096
     timeout: 120.0
   ```

2. **Обновите код (app/agents/llm_manager.py:207-234):**

   ```python
   def _get_huggingface_llm(self) -> Any:
       from langchain_huggingface import HuggingFaceEndpoint

       # ✅ ИЗМЕНЕНО: используем endpoint_url из конфига
       endpoint_url = getattr(settings.huggingface, 'endpoint_url', None)

       self._huggingface_llm = HuggingFaceEndpoint(
           endpoint_url=endpoint_url,  # ✅ БЫЛО: None
           repo_id=settings.huggingface.model,
           huggingfacehub_api_token=settings.huggingface.api_key,
           temperature=settings.huggingface.temperature,
           max_new_tokens=settings.huggingface.max_tokens,
           top_p=settings.huggingface.top_p,
           timeout=settings.huggingface.timeout,
       )
   ```

3. **Обновите config schema (app/config/settings.py):**

   ```python
   class HuggingFaceConfig(BaseModel):
       endpoint_url: Optional[str] = Field(default=None)  # ✅ НОВОЕ
       model: str = Field(default="meta-llama/Meta-Llama-3.1-70B-Instruct")
       api_key: str = Field(default_factory=lambda: os.getenv("HUGGINGFACE_API_KEY", ""))
       # ... остальные поля
   ```

**Преимущества:**
- ✅ Минимальные изменения кода (~10 строк)
- ✅ Совместимо с HuggingFace Text Generation Inference

**Недостатки:**
- ⚠️ Только для TGI сервера (не vLLM, не llama.cpp)
- ⚠️ Fallback на облачный Inference API при недоступности

---

## 📊 Рекомендации

### Для production с внутренней LLM

**Рекомендуемая конфигурация:**

1. **Основной провайдер**: Вариант 2 (INTERNAL_LLM) - явное управление
2. **Fallback #1**: OpenRouter (для резервирования)
3. **Fallback #2**: HuggingFace Inference API (если облако разрешено)

**Fallback порядок:**
```
INTERNAL_LLM (internal server)
    → OpenRouter (cloud, if allowed)
    → HuggingFace (cloud, emergency only)
```

### Для разработки

**Рекомендуемая конфигурация:**

1. **Вариант 1** (OpenRouter-compatible) - проще настроить
2. **Сервер**: LM Studio (localhost:1234) - удобно для локальной разработки

### Проверка после настройки

**Чеклист:**

1. ✅ **Проверьте доступность сервера:**
   ```bash
   curl http://internal-llm-server:8000/v1/models
   ```

2. ✅ **Проверьте через admin API:**
   ```bash
   curl -X POST http://localhost:8000/admin/llm/test-provider/openrouter \
     -H "X-Auth-Token: ${ADMIN_TOKEN}"
   ```

3. ✅ **Запустите тестовый анализ:**
   ```bash
   curl -X POST http://localhost:8000/agent/analyze-client \
     -H "Content-Type: application/json" \
     -d '{"client_name": "ООО Тестовая", "inn": "7707083893"}'
   ```

4. ✅ **Проверьте LLM Audit Trail:**
   ```bash
   curl http://localhost:8000/admin/audit/llm?limit=10 \
     -H "X-Auth-Token: ${ADMIN_TOKEN}"
   ```

5. ✅ **Проверьте PII masking:**
   - Найдите в логах: `"PII detected and masked: X items"`
   - Убедитесь, что ИНН/ФИО не попали в LLM prompt

---

## 🔐 Безопасность и Compliance

### PII Protection (152-ФЗ)

**✅ РЕАЛИЗОВАНО** (Sprint 2):

```python
# app/agents/llm_manager.py:448-474
pii_result = pii.mask_pii(
    text=prompt,
    language="ru",
    mask_level="high",  # Максимальная защита
)
masked_prompt = pii_result.masked_text

# ⚠️ ВАЖНО: Отправляем masked_prompt вместо оригинального!
response = await self.ainvoke_with_provider(
    prompt=masked_prompt,  # ✅ Обезличенный промпт
    provider=provider
)

# Восстанавливаем PII в ответе
final_response = pii.unmask_pii(
    masked_text=response,
    replacements=pii_result.replacements
)
```

**7 recognizers для российских данных:**
- ✅ RU_INN (ИНН)
- ✅ RU_OGRN (ОГРН/ОГРНИП)
- ✅ RU_SNILS (СНИЛС)
- ✅ RU_PERSON (ФИО кириллицей)
- ✅ RU_ADDRESS (российские адреса)
- ✅ RU_PASSPORT (паспорта)
- ✅ RU_PHONE (российские телефоны)

### LLM Audit Trail

**✅ РЕАЛИЗОВАНО** (Sprint 2):

```python
# app/agents/llm_manager.py:549-576
if settings.secure.llm_audit_enabled:
    audit_logger.log_llm_call(
        provider=used_provider.value,
        model=settings.openrouter.model,
        operation="ainvoke",
        prompt_hash=hashlib.sha256(masked_prompt.encode()).hexdigest(),  # Hash-only!
        response_hash=hashlib.sha256(response_text.encode()).hexdigest(),
        pii_detected=bool(pii_result and pii_result.pii_detected),
        pii_count=pii_result.pii_count if pii_result else 0,
        detected_pii_types=pii_result.detected_pii_types if pii_result else [],
        # ...
    )
```

**Получение audit логов:**
```bash
GET /admin/audit/llm?limit=50&offset=0
```

---

## 🎯 Итоговые рекомендации

### ✅ Что работает без изменений

1. **Workflow соответствует ТЗ полностью (8/8)**
2. **PII masking работает** (7 recognizers)
3. **LLM Audit Trail работает** (hash-only для compliance)
4. **RabbitMQ интеграция работает** (результаты отправляются в очередь)

### ⚠️ Что нужно настроить для внутренней LLM

**Вариант 1 (БЫСТРО - 30 минут):**
- Изменить `openrouter.api_url` в конфиге на внутренний сервер
- Проверить доступность через admin API

**Вариант 2 (ПРАВИЛЬНО - 2-3 часа):**
- Добавить новый провайдер `INTERNAL_LLM`
- Настроить fallback порядок: internal → cloud
- Обновить тесты

**Вариант 3 (ДЛЯ TGI - 1 час):**
- Добавить `endpoint_url` в HuggingFace конфиг
- Обновить код подключения

### 📝 Следующие шаги

1. **Выберите вариант подключения** (рекомендуется Вариант 1 для быстрого старта)
2. **Разверните LLM сервер** (vLLM, TGI или LM Studio)
3. **Обновите конфигурацию** (config/app.dev.yaml + .env)
4. **Протестируйте через admin API** (/admin/llm/test-provider)
5. **Проверьте полный workflow** (запустите анализ клиента)
6. **Проверьте PII masking и audit trail** (/admin/audit/llm)

---

**Автор документа**: Claude AI (Anthropic)
**Дата**: 2026-01-16
**Версия**: 1.0
**Статус**: ✅ Production-Ready (с настройкой внутренней LLM)
