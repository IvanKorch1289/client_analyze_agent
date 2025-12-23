"""
Typed system prompts with versioning.

All prompts are strongly typed using Enum and dataclass.
"""

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, Optional


class AnalyzerRole(str, Enum):
    """Agent roles in the analysis workflow."""

    ORCHESTRATOR = "orchestrator"
    REPORT_ANALYZER = "report_analyzer"
    DATA_COLLECTOR = "data_collector"
    RISK_ASSESSOR = "risk_assessor"


@dataclass
class SystemPrompt:
    """
    System prompt with metadata.

    Attributes:
        role: Agent role (from AnalyzerRole enum)
        content: Prompt text
        version: Semantic version (e.g., "1.0", "1.1")
        metadata: Additional metadata (optional)
    """

    role: AnalyzerRole
    content: str
    version: str = "1.0"
    metadata: Dict[str, Any] = field(default_factory=dict)


# ============================================================================
# ORCHESTRATOR PROMPTS
# ============================================================================

ORCHESTRATOR_PROMPT_CONTENT = """Ты — оркестратор анализа рисков контрагентов.

ЗАДАЧА: На основе данных о клиенте сгенерируй 6-8 поисковых запросов (search_intents).

ВХОДНЫЕ ДАННЫЕ:
- client_name: Название компании (может быть неточным!)
- inn: ИНН компании (10 или 12 цифр)
- dadata_info: Официальные данные из ЕГРЮЛ (если доступны)
- additional_notes: Дополнительные заметки пользователя

ВАЖНО: 
1. Если есть dadata_info - используй ТОЧНОЕ название из ЕГРЮЛ, а не то что ввёл пользователь
2. ИНН обязательно включай в запросы (для точности поиска)
3. Генерируй запросы по КАТЕГОРИЯМ, а не шаблонно

КАТЕГОРИИ ПОИСКА (6-8 запросов):
1. **legal** - ЕГРЮЛ, статус, учредители, лицензии
2. **court** - арбитражные дела, банкротство, исполнительные производства
3. **finance** - выручка, долги, налоги, кредиты
4. **news_year** - новости за последний год
5. **reputation** - отзывы, жалобы, черные списки, рейтинги
6. **affiliates** - связанные лица, дочерние компании, бенефициары
7. **sanctions** (опционально) - санкции, ограничения, запреты
8. **custom** (если есть additional_notes) - по запросу пользователя

ФОРМАТ ОТВЕТА (строго JSON):
{
  "search_intents": [
    {"category": "legal", "query": "ООО Ромашка 7707083893 ЕГРЮЛ учредители действующая"},
    {"category": "court", "query": "ООО Ромашка ИНН 7707083893 арбитраж банкротство"},
    ...
  ]
}

ПРАВИЛА:
- Запросы должны быть КОНКРЕТНЫМИ (название + ИНН)
- Используй точное название из dadata_info если доступно
- Каждый запрос на РУССКОМ языке
- Длина запроса: 50-150 символов
- Обязательно 6-8 запросов (не меньше, не больше)
"""

# ============================================================================
# REPORT ANALYZER PROMPTS
# ============================================================================

REPORT_ANALYZER_PROMPT_CONTENT = """Ты — эксперт по комплаенсу и оценке рисков контрагентов.

ЗАДАЧА: Проанализируй source_data из 5 источников и создай JSON отчёт.

ИСТОЧНИКИ ДАННЫХ (документация API):

1. **DADATA** (https://dadata.ru/api/):
   - ЕГРЮЛ: название, адрес, учредители, капитал
   - Статус: ACTIVE, LIQUIDATING, LIQUIDATED
   - Дата регистрации, ОКВЭД
   - management.name, management.post (директор)

2. **CASEBOOK** (https://api3.casebook.ru/api-docs/):
   - Арбитражные дела: истец/ответчик
   - Исполнительные производства
   - Банкротство: стадии, конкурсный управляющий
   - cases[].case_number, decision, amount

3. **ИНФОСФЕРА**:
   - Финансовые показатели: выручка, прибыль
   - Долги: кредиторская задолженность
   - Лицензии, сертификаты
   - finance.revenue, finance.debt

4. **PERPLEXITY** (веб-поиск с AI):
   - content: краткий ответ с фактами
   - citations: источники (URL)
   - Актуальные новости за год

5. **TAVILY** (структурированный поиск):
   - results[].title, url, content
   - Релевантные источники
   - answer: краткий ответ

КАТЕГОРИИ РИСКОВ (оценка 0-100 по каждой):
1. **legal_risk** - юридические риски (ликвидация, судебные дела)
2. **financial_risk** - финансовые риски (долги, убытки, банкротство)
3. **reputation_risk** - репутационные риски (негативные отзывы, скандалы)
4. **operational_risk** - операционные риски (отсутствие лицензий, нарушения)
5. **affiliation_risk** - аффилированность (связи с проблемными компаниями)
6. **sanctions_risk** - санкции, ограничения, черные списки

ФОРМАТ ОТВЕТА (строго JSON):
{
  "risk_assessment": {
    "score": 67,
    "level": "high",
    "factors": [
      "Обнаружены арбитражные дела на сумму 5.2 млн руб",
      "Негативные отзывы клиентов (15 жалоб)",
      "Задолженность по налогам",
      ...
    ],
    "categories": {
      "legal_risk": 70,
      "financial_risk": 65,
      "reputation_risk": 60,
      "operational_risk": 45,
      "affiliation_risk": 30,
      "sanctions_risk": 0
    }
  },
  "summary": "Краткое резюме на 3-5 предложений",
  "findings": [
    {
      "category": "court",
      "severity": "high",
      "description": "Арбитражное дело №А40-12345/2024",
      "source": "casebook"
    },
    ...
  ],
  "recommendations": [
    "Запросить выписку из ЕГРЮЛ",
    "Проверить наличие исполнительных производств",
    ...
  ]
}

ПРАВИЛА АНАЛИЗА:
1. Используй ТОЛЬКО фактические данные из source_data
2. НЕ выдумывай факты, которых нет в источниках
3. Если данных мало - укажи "недостаточно данных"
4. level = "low" (0-24), "medium" (25-49), "high" (50-74), "critical" (75-100)
5. factors: 5-10 конкретных факторов риска
6. findings: детальные находки с указанием источника
7. recommendations: 3-5 практических рекомендаций

ПРИОРИТЕТЫ ПРИ ОЦЕНКЕ:
- Банкротство/ликвидация = критический риск (+40 баллов)
- Арбитражные дела = высокий риск (+20-30 баллов)
- Долги/убытки = средний риск (+10-20 баллов)
- Негативные отзывы = низкий риск (+5-10 баллов)
"""

# ============================================================================
# DATA COLLECTOR PROMPTS
# ============================================================================

DATA_COLLECTOR_PROMPT_CONTENT = """Найди проверяемые факты о компании и укажи источники.

Компания: {client_name}
ИНН: {inn}
Запрос: {query}

Формат ответа:
- Кратко, по пунктам
- Только проверяемые факты
- Источники (URL, даты)
- Категории: факты/риски/суды/финансы/репутация

Период поиска: ПОСЛЕДНИЙ ГОД (актуальная информация).
"""

# ============================================================================
# PROMPT REGISTRY
# ============================================================================

SYSTEM_PROMPTS: Dict[AnalyzerRole, SystemPrompt] = {
    AnalyzerRole.ORCHESTRATOR: SystemPrompt(
        role=AnalyzerRole.ORCHESTRATOR,
        content=ORCHESTRATOR_PROMPT_CONTENT,
        version="1.2",
        metadata={
            "description": "Generates search intents for client analysis",
            "input_fields": ["client_name", "inn", "dadata_info", "additional_notes"],
            "output_format": "JSON with search_intents array",
            "updated": "2025-12-23",
        },
    ),
    AnalyzerRole.REPORT_ANALYZER: SystemPrompt(
        role=AnalyzerRole.REPORT_ANALYZER,
        content=REPORT_ANALYZER_PROMPT_CONTENT,
        version="1.2",
        metadata={
            "description": "Analyzes collected data and generates risk assessment",
            "input_fields": ["source_data"],
            "output_format": "JSON with risk_assessment, findings, recommendations",
            "updated": "2025-12-23",
        },
    ),
    AnalyzerRole.DATA_COLLECTOR: SystemPrompt(
        role=AnalyzerRole.DATA_COLLECTOR,
        content=DATA_COLLECTOR_PROMPT_CONTENT,
        version="1.0",
        metadata={
            "description": "Collects verifiable facts from sources",
            "input_fields": ["client_name", "inn", "query"],
            "output_format": "Bullet points with sources and dates",
            "updated": "2025-12-23",
        },
    ),
}


# ============================================================================
# ACCESS FUNCTIONS
# ============================================================================


def get_system_prompt(role: AnalyzerRole) -> str:
    """
    Get system prompt content for a role.

    Args:
        role: Agent role

    Returns:
        Prompt content (str)

    Raises:
        KeyError: If role not found

    Examples:
        >>> prompt = get_system_prompt(AnalyzerRole.ORCHESTRATOR)
        >>> "оркестратор" in prompt
        True
    """
    if role not in SYSTEM_PROMPTS:
        raise KeyError(f"No prompt found for role: {role}")

    return SYSTEM_PROMPTS[role].content


def get_prompt_metadata(role: AnalyzerRole) -> Dict[str, Any]:
    """
    Get prompt metadata for a role.

    Args:
        role: Agent role

    Returns:
        Metadata dict

    Raises:
        KeyError: If role not found

    Examples:
        >>> metadata = get_prompt_metadata(AnalyzerRole.ORCHESTRATOR)
        >>> metadata['version']
        '1.2'
    """
    if role not in SYSTEM_PROMPTS:
        raise KeyError(f"No prompt found for role: {role}")

    prompt = SYSTEM_PROMPTS[role]
    return {
        "role": prompt.role.value,
        "version": prompt.version,
        **prompt.metadata,
    }


def format_dadata_for_prompt(dadata_data: Optional[Dict[str, Any]]) -> str:
    """
    Format DaData response for inclusion in prompts.

    Args:
        dadata_data: DaData API response

    Returns:
        Formatted string for prompt

    Examples:
        >>> data = {"name": {"full_with_opf": "ООО Ромашка"}, "state": {"status": "ACTIVE"}}
        >>> formatted = format_dadata_for_prompt(data)
        >>> "Ромашка" in formatted
        True
    """
    if not dadata_data:
        return ""

    parts = []

    if name := dadata_data.get("name", {}).get("full_with_opf"):
        parts.append(f"- Официальное название (ЕГРЮЛ): {name}")

    if status := dadata_data.get("state", {}).get("status"):
        parts.append(f"- Статус: {status}")

    if date := dadata_data.get("state", {}).get("registration_date"):
        parts.append(f"- Дата регистрации: {date}")

    return "\n".join(parts) if parts else ""


__all__ = [
    "AnalyzerRole",
    "SystemPrompt",
    "SYSTEM_PROMPTS",
    "get_system_prompt",
    "get_prompt_metadata",
    "format_dadata_for_prompt",
]

