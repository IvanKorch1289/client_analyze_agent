"""
Agent-Orchestrator: координирует workflow анализа клиентов.
Получает данные клиента и определяет стратегию поиска.
"""

from typing import Any, Dict, List

from app.utility.logging_client import logger

SEARCH_INTENTS = [
    {
        "id": "reputation",
        "query_template": "репутация компании {client_name} отзывы клиентов",
        "description": "Общая репутация и отзывы",
    },
    {
        "id": "lawsuits",
        "query_template": "{client_name} ИНН {inn} судебные дела арбитраж",
        "description": "Судебные разбирательства",
    },
    {
        "id": "news",
        "query_template": "{client_name} новости последние события",
        "description": "Актуальные новости",
    },
    {
        "id": "negative",
        "query_template": "{client_name} проблемы скандалы жалобы",
        "description": "Негативная информация",
    },
    {
        "id": "financial",
        "query_template": "{client_name} ИНН {inn} финансовое состояние банкротство",
        "description": "Финансовое положение",
    },
]


async def orchestrator_agent(state: Dict[str, Any]) -> Dict[str, Any]:
    """
    Агент-оркестратор: валидирует входные данные и формирует план поиска.

    Входные данные в state:
        - client_name: str - название компании
        - inn: str - ИНН компании (опционально)
        - additional_notes: str - дополнительные заметки (опционально)

    Выходные данные:
        - search_intents: List[Dict] - список поисковых запросов
        - current_step: str - текущий шаг workflow
    """
    client_name = state.get("client_name", "")
    inn = state.get("inn", "")
    additional_notes = state.get("additional_notes", "")

    if not client_name:
        logger.error("Orchestrator: client_name is required", component="orchestrator")
        return {
            **state,
            "error": "Название клиента обязательно",
            "current_step": "failed",
        }

    logger.info(
        f"Orchestrator: начинаем анализ клиента '{client_name}'",
        component="orchestrator",
    )

    search_queries: List[Dict[str, str]] = []
    for intent in SEARCH_INTENTS:
        query = intent["query_template"].format(
            client_name=client_name, inn=inn if inn else ""
        )
        search_queries.append(
            {
                "id": intent["id"],
                "query": query.strip(),
                "description": intent["description"],
            }
        )

    if additional_notes:
        search_queries.append(
            {
                "id": "custom",
                "query": f"{client_name} {additional_notes}",
                "description": "Дополнительный запрос",
            }
        )

    logger.info(
        f"Orchestrator: сформировано {len(search_queries)} поисковых запросов",
        component="orchestrator",
    )

    return {
        **state,
        "search_intents": search_queries,
        "current_step": "searching",
        "orchestrator_result": {
            "client_name": client_name,
            "inn": inn,
            "search_count": len(search_queries),
        },
    }
