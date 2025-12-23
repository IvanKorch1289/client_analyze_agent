"""
Reference data for analysis and validation.

Contains enums, constants, and reference values used in analysis.
"""

from enum import Enum
from typing import Dict, List


# ============================================================================
# RISK ASSESSMENT
# ============================================================================


class RiskLevel(str, Enum):
    """Risk level classification."""

    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


RISK_LEVELS: Dict[str, Dict[str, any]] = {
    "low": {
        "label": "Низкий риск",
        "score_range": (0, 24),
        "color": "green",
        "description": "Минимальные риски, можно работать",
    },
    "medium": {
        "label": "Средний риск",
        "score_range": (25, 49),
        "color": "yellow",
        "description": "Умеренные риски, требуется проверка",
    },
    "high": {
        "label": "Высокий риск",
        "score_range": (50, 74),
        "color": "orange",
        "description": "Значительные риски, требуется осторожность",
    },
    "critical": {
        "label": "Критический риск",
        "score_range": (75, 100),
        "color": "red",
        "description": "Критические риски, рекомендуется отказ",
    },
}


RISK_CATEGORIES: Dict[str, Dict[str, any]] = {
    "legal_risk": {
        "label": "Юридический риск",
        "description": "Ликвидация, судебные дела, исполнительные производства",
        "weight": 1.5,
        "indicators": [
            "Статус ликвидации",
            "Арбитражные дела",
            "Исполнительные производства",
            "Административные нарушения",
        ],
    },
    "financial_risk": {
        "label": "Финансовый риск",
        "description": "Долги, убытки, банкротство",
        "weight": 1.3,
        "indicators": [
            "Процедура банкротства",
            "Кредиторская задолженность",
            "Отрицательный финансовый результат",
            "Налоговые долги",
        ],
    },
    "reputation_risk": {
        "label": "Репутационный риск",
        "description": "Негативные отзывы, скандалы, жалобы",
        "weight": 0.8,
        "indicators": [
            "Негативные отзывы",
            "Жалобы клиентов",
            "Упоминание в СМИ (негатив)",
            "Низкие рейтинги",
        ],
    },
    "operational_risk": {
        "label": "Операционный риск",
        "description": "Отсутствие лицензий, нарушения",
        "weight": 1.0,
        "indicators": [
            "Отсутствие лицензий",
            "Нарушения законодательства",
            "Проверки надзорных органов",
            "Санитарные нарушения",
        ],
    },
    "affiliation_risk": {
        "label": "Риск аффилированности",
        "description": "Связи с проблемными компаниями",
        "weight": 0.7,
        "indicators": [
            "Связь с банкротами",
            "Массовый адрес регистрации",
            "Массовый руководитель",
            "Недостоверные сведения в ЕГРЮЛ",
        ],
    },
    "sanctions_risk": {
        "label": "Риск санкций",
        "description": "Санкции, ограничения, черные списки",
        "weight": 2.0,
        "indicators": [
            "Включение в санкционные списки",
            "Ограничения на деятельность",
            "Блокировка счетов",
            "Запрет на валютные операции",
        ],
    },
}


# ============================================================================
# SEARCH CATEGORIES
# ============================================================================


SEARCH_CATEGORIES: Dict[str, Dict[str, any]] = {
    "legal": {
        "label": "Юридические данные",
        "description": "ЕГРЮЛ, статус, учредители, лицензии",
        "priority": 1,
        "keywords": ["ЕГРЮЛ", "учредители", "статус", "лицензии", "регистрация"],
    },
    "court": {
        "label": "Судебные дела",
        "description": "Арбитражные дела, банкротство, исполнительные производства",
        "priority": 2,
        "keywords": ["арбитраж", "банкротство", "исполнительное производство", "суд"],
    },
    "finance": {
        "label": "Финансы",
        "description": "Выручка, долги, налоги, кредиты",
        "priority": 3,
        "keywords": ["выручка", "прибыль", "долги", "налоги", "финансы"],
    },
    "news_year": {
        "label": "Новости за год",
        "description": "Актуальные новости за последний год",
        "priority": 4,
        "keywords": ["новости", "последний год", "актуальное"],
    },
    "reputation": {
        "label": "Репутация",
        "description": "Отзывы, жалобы, черные списки, рейтинги",
        "priority": 5,
        "keywords": ["отзывы", "жалобы", "рейтинг", "репутация", "черный список"],
    },
    "affiliates": {
        "label": "Связанные лица",
        "description": "Связанные лица, дочерние компании, бенефициары",
        "priority": 6,
        "keywords": ["связанные лица", "аффилированные", "бенефициары", "дочерние"],
    },
    "sanctions": {
        "label": "Санкции",
        "description": "Санкции, ограничения, запреты",
        "priority": 7,
        "keywords": ["санкции", "ограничения", "запреты", "блокировка"],
    },
    "custom": {
        "label": "Пользовательский запрос",
        "description": "Запрос по дополнительным заметкам пользователя",
        "priority": 8,
        "keywords": [],
    },
}


# ============================================================================
# COMPANY STATUS
# ============================================================================


COMPANY_STATUSES: Dict[str, Dict[str, any]] = {
    "ACTIVE": {
        "label": "Действующая",
        "risk_modifier": 0,
        "description": "Компания активна, ведет деятельность",
    },
    "LIQUIDATING": {
        "label": "В процессе ликвидации",
        "risk_modifier": +30,
        "description": "Компания в процессе ликвидации",
    },
    "LIQUIDATED": {
        "label": "Ликвидирована",
        "risk_modifier": +50,
        "description": "Компания ликвидирована, прекратила существование",
    },
    "BANKRUPT": {
        "label": "Банкрот",
        "risk_modifier": +40,
        "description": "Компания признана банкротом",
    },
    "REORGANIZING": {
        "label": "Реорганизация",
        "risk_modifier": +15,
        "description": "Компания в процессе реорганизации",
    },
}


# ============================================================================
# API SOURCE METADATA
# ============================================================================


API_SOURCES: Dict[str, Dict[str, any]] = {
    "dadata": {
        "name": "DaData",
        "base_url": "https://suggestions.dadata.ru",
        "docs_url": "https://dadata.ru/api/",
        "description": "Официальные данные из ЕГРЮЛ",
        "fields": [
            "name.full_with_opf",
            "inn",
            "kpp",
            "ogrn",
            "state.status",
            "state.registration_date",
            "address.value",
            "management.name",
            "management.post",
        ],
    },
    "casebook": {
        "name": "Casebook",
        "base_url": "https://api3.casebook.ru",
        "docs_url": "https://api3.casebook.ru/api-docs/",
        "description": "Арбитражные дела и банкротства",
        "fields": [
            "cases[].case_number",
            "cases[].decision",
            "cases[].amount",
            "bankruptcy.stage",
            "bankruptcy.manager",
        ],
    },
    "infosfera": {
        "name": "Инфосфера",
        "base_url": "https://api.infosfera.ru",
        "docs_url": "https://infosfera.ru/api/",
        "description": "Финансовые показатели и лицензии",
        "fields": [
            "finance.revenue",
            "finance.profit",
            "finance.debt",
            "licenses[].number",
            "licenses[].type",
        ],
    },
    "perplexity": {
        "name": "Perplexity AI",
        "base_url": "https://api.perplexity.ai",
        "docs_url": "https://docs.perplexity.ai/",
        "description": "AI-powered веб-поиск с цитированием",
        "fields": [
            "content",
            "citations[].url",
            "citations[].title",
        ],
    },
    "tavily": {
        "name": "Tavily",
        "base_url": "https://api.tavily.com",
        "docs_url": "https://docs.tavily.com/",
        "description": "Структурированный поиск по веб-источникам",
        "fields": [
            "results[].title",
            "results[].url",
            "results[].content",
            "answer",
        ],
    },
}


__all__ = [
    "RiskLevel",
    "RISK_LEVELS",
    "RISK_CATEGORIES",
    "SEARCH_CATEGORIES",
    "COMPANY_STATUSES",
    "API_SOURCES",
]

