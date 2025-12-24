"""
Agent-Orchestrator: координирует workflow анализа клиентов.
Получает данные клиента и определяет стратегию поиска через LLM.
"""

from typing import Any, Dict, List, Optional

from app.agents.shared.llm import llm_generate_json
from app.mcp_server.prompts.system_prompts import format_dadata_for_prompt
from app.shared.security import validate_inn
from app.services.fetch_data import fetch_from_dadata
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
    Агент-оркестратор: валидирует входные данные и формирует план поиска через LLM.

    P0 ИЗМЕНЕНИЯ:
    - Получает точное название из DaData если есть ИНН
    - Использует LLM для генерации адаптивных search_intents
    - Fallback на жёсткие шаблоны если LLM недоступен

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

    # P0: Валидация ИНН
    if inn:
        is_valid, error_msg = validate_inn(inn)
        if not is_valid:
            logger.warning(f"Orchestrator: Invalid INN: {error_msg}", component="orchestrator")
            inn = ""  # Продолжаем без ИНН

    # P0: НОВОЕ - Получаем точное название из DaData если есть ИНН
    dadata_info = None
    canonical_name = client_name

    if inn and len(inn) in (10, 12):
        try:
            logger.info(f"Orchestrator: fetching DaData for INN {inn}", component="orchestrator")
            dadata_result = await fetch_from_dadata(inn)
            
            # P0-5: Улучшенная обработка ответа DaData
            if dadata_result and "error" not in dadata_result:
                if "data" in dadata_result and dadata_result["data"]:
                    dadata_info = dadata_result.get("data", {})
                    full_name = dadata_info.get("name", {}).get("full_with_opf")
                    if full_name:
                        canonical_name = full_name
                        logger.info(
                            f"Orchestrator: using canonical name from ЕГРЮЛ: {canonical_name}",
                            component="orchestrator",
                        )
                    else:
                        logger.warning(
                            f"Orchestrator: DaData returned data but no company name for INN {inn}",
                            component="orchestrator",
                        )
                else:
                    # P0-5: ИНН валиден, но данных нет
                    logger.warning(
                        f"Orchestrator: DaData returned no data for valid INN {inn}. "
                        f"Company might be liquidated, not registered, or INN is incorrect.",
                        component="orchestrator",
                    )
            else:
                error_msg = dadata_result.get("error", "Unknown error")
                logger.warning(
                    f"Orchestrator: DaData request failed for INN {inn}: {error_msg}",
                    component="orchestrator",
                )
        except Exception as e:
            logger.error(
                f"Orchestrator: DaData fetch exception for INN {inn}: {e}",
                component="orchestrator",
                exc_info=True,
            )

    # P0: НОВОЕ - Генерируем search_intents через LLM
    search_queries = await _generate_search_intents_llm(
        client_name=canonical_name,
        inn=inn,
        additional_notes=additional_notes,
        dadata_info=dadata_info,
    )

    # Fallback на старые шаблоны если LLM не вернул ничего
    if not search_queries:
        logger.warning(
            "Orchestrator: LLM failed, using fallback templates",
            component="orchestrator",
        )
        search_queries = _generate_search_intents_fallback(canonical_name, inn, additional_notes)

    logger.info(
        f"Orchestrator: сформировано {len(search_queries)} поисковых запросов",
        component="orchestrator",
    )

    return {
        **state,
        "search_intents": search_queries,
        "current_step": "searching",
        "orchestrator_result": {
            "client_name": canonical_name,
            "original_name": client_name,
            "inn": inn,
            "search_count": len(search_queries),
            "has_dadata": bool(dadata_info),
        },
    }


async def _generate_search_intents_llm(
    client_name: str,
    inn: str,
    additional_notes: str,
    dadata_info: Optional[Dict] = None,
) -> List[Dict[str, str]]:
    """
    P0: НОВОЕ - Генерация search_intents через LLM.

    Использует системный промпт для адаптивной генерации запросов.
    """
    from app.mcp_server.prompts.system_prompts import AnalyzerRole, get_system_prompt

    # Форматируем данные DaData для промпта
    dadata_section = ""
    if dadata_info:
        dadata_section = "\nДАННЫЕ ЕГРЮЛ:\n" + format_dadata_for_prompt(dadata_info)

    # Используем typed system prompt
    user_message = f"""На основе данных о клиенте сгенерируй поисковые запросы.

ДАННЫЕ КЛИЕНТА:
- Название: {client_name}
- ИНН: {inn if inn else "не указан"}{dadata_section}
- Доп. заметки: {additional_notes if additional_notes else "нет"}

Сгенерируй 6-8 запросов по категориям: legal, court, finance, news_year, reputation, affiliates.
Используй ТОЧНОЕ название из ЕГРЮЛ если доступно. Обязательно включай ИНН.

Ответ в формате JSON:
{{"search_intents": [{{"category": "legal", "query": "..."}}]}}"""

    try:
        result = await llm_generate_json(
            system_prompt=get_system_prompt(AnalyzerRole.ORCHESTRATOR),
            user_message=user_message,
            temperature=0.3,  # Низкая для точности
            max_tokens=1500,
            fallback_on_error={"search_intents": []},
        )

        search_intents = result.get("search_intents", [])

        # Валидация и нормализация
        normalized = []
        for idx, intent in enumerate(search_intents):
            if not isinstance(intent, dict):
                continue

            category = intent.get("category", f"generated_{idx}")
            query = intent.get("query", "")
            if not query:
                continue

            normalized.append(
                {
                    "id": category,
                    "query": query.strip(),
                    "description": intent.get("description", f"Поиск: {category}"),
                }
            )

        return normalized

    except Exception as e:
        logger.error(f"Orchestrator LLM generation failed: {e}", component="orchestrator")
        return []


def _generate_search_intents_fallback(
    client_name: str,
    inn: str,
    additional_notes: str,
) -> List[Dict[str, str]]:
    """
    Fallback: генерация search_intents по жёстким шаблонам.

    Используется если LLM недоступен или вернул пустой результат.
    """
    search_queries: List[Dict[str, str]] = []
    for intent in SEARCH_INTENTS:
        query = intent["query_template"].format(client_name=client_name, inn=inn if inn else "")
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

    return search_queries
