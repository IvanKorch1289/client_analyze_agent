"""
Data Collector Agent: параллельный сбор данных из всех источников.
Casebook, InfoSphere, DaData + Perplexity, Tavily
"""

import asyncio
import time
from typing import Any, Dict, List

from app.services.fetch_data import (
    fetch_from_casebook,
    fetch_from_dadata,
    fetch_from_infosphere,
)
from app.services.perplexity_client import PerplexityClient
from app.services.tavily_client import TavilyClient
from app.utility.logging_client import logger

MAX_CONCURRENT = 5
SEARCH_TIMEOUT = 60


async def _fetch_perplexity(query: str, client_name: str) -> Dict[str, Any]:
    """Запрос к Perplexity AI."""
    client = PerplexityClient.get_instance()
    if not client.is_configured():
        return {"source": "perplexity", "success": False, "error": "Not configured"}

    try:
        result = await asyncio.wait_for(
            client.ask(
                question=f"Информация о компании {client_name}: {query}",
                system_prompt="Найди бизнес-информацию о компании. Выдели ключевые факты, риски, репутацию.",
                search_recency_filter="month",
            ),
            timeout=SEARCH_TIMEOUT,
        )
        return {
            "source": "perplexity",
            "success": result.get("success", False),
            "content": result.get("content", ""),
            "citations": result.get("citations", []),
            "error": result.get("error"),
        }
    except asyncio.TimeoutError:
        return {"source": "perplexity", "success": False, "error": "Timeout"}
    except Exception as e:
        return {"source": "perplexity", "success": False, "error": str(e)}


async def _fetch_tavily(query: str, client_name: str) -> Dict[str, Any]:
    """Запрос к Tavily Search."""
    client = TavilyClient.get_instance()
    if not client.is_configured():
        return {"source": "tavily", "success": False, "error": "Not configured"}

    try:
        result = await asyncio.wait_for(
            client.search(
                query=f"{client_name} {query}",
                search_depth="advanced",
                max_results=10,
                include_answer=True,
            ),
            timeout=SEARCH_TIMEOUT,
        )
        return {
            "source": "tavily",
            "success": result.get("success", False),
            "answer": result.get("answer", ""),
            "results": result.get("results", []),
            "error": result.get("error"),
        }
    except asyncio.TimeoutError:
        return {"source": "tavily", "success": False, "error": "Timeout"}
    except Exception as e:
        return {"source": "tavily", "success": False, "error": str(e)}


async def _fetch_dadata_wrapper(inn: str) -> Dict[str, Any]:
    """Обёртка для DaData с обработкой ошибок."""
    if not inn or not inn.isdigit():
        return {"source": "dadata", "success": False, "error": "Invalid INN"}

    try:
        result = await asyncio.wait_for(fetch_from_dadata(inn), timeout=30)
        return {
            "source": "dadata",
            "success": "error" not in result,
            "data": result.get("data", {}),
            "error": result.get("error"),
        }
    except asyncio.TimeoutError:
        return {"source": "dadata", "success": False, "error": "Timeout"}
    except Exception as e:
        return {"source": "dadata", "success": False, "error": str(e)}


async def _fetch_infosphere_wrapper(inn: str) -> Dict[str, Any]:
    """Обёртка для InfoSphere с обработкой ошибок."""
    if not inn or not inn.isdigit():
        return {"source": "infosphere", "success": False, "error": "Invalid INN"}

    try:
        result = await asyncio.wait_for(fetch_from_infosphere(inn), timeout=30)
        return {
            "source": "infosphere",
            "success": "error" not in result,
            "data": result.get("data", {}),
            "error": result.get("error"),
        }
    except asyncio.TimeoutError:
        return {"source": "infosphere", "success": False, "error": "Timeout"}
    except Exception as e:
        return {"source": "infosphere", "success": False, "error": str(e)}


async def _fetch_casebook_wrapper(inn: str) -> Dict[str, Any]:
    """Обёртка для Casebook с обработкой ошибок."""
    if not inn or not inn.isdigit():
        return {"source": "casebook", "success": False, "error": "Invalid INN"}

    try:
        result = await asyncio.wait_for(fetch_from_casebook(inn), timeout=30)
        return {
            "source": "casebook",
            "success": "error" not in result,
            "data": result.get("data", []),
            "error": result.get("error"),
        }
    except asyncio.TimeoutError:
        return {"source": "casebook", "success": False, "error": "Timeout"}
    except Exception as e:
        return {"source": "casebook", "success": False, "error": str(e)}


async def data_collector_agent(state: Dict[str, Any]) -> Dict[str, Any]:
    """
    Агент сбора данных: параллельные запросы ко всем источникам.

    Входные данные:
        - client_name: str - название компании
        - inn: str - ИНН компании (опционально)
        - search_intents: List[Dict] - поисковые запросы от оркестратора

    Выходные данные:
        - source_data: Dict - данные от всех источников
        - current_step: str
    """
    client_name = state.get("client_name", "")
    inn = state.get("inn", "")
    search_intents = state.get("search_intents", [])

    start_time = time.perf_counter()

    logger.structured(
        "info",
        "data_collection_started",
        component="data_collector",
        client_name=client_name[:50],
        inn=inn,
        intent_count=len(search_intents),
    )

    tasks = []

    if inn and inn.isdigit() and len(inn) in (10, 12):
        tasks.append(_fetch_dadata_wrapper(inn))
        tasks.append(_fetch_infosphere_wrapper(inn))
        tasks.append(_fetch_casebook_wrapper(inn))

    search_query = (
        search_intents[0].get("query", client_name) if search_intents else client_name
    )
    tasks.append(_fetch_perplexity(search_query, client_name))
    tasks.append(_fetch_tavily(search_query, client_name))

    results = await asyncio.gather(*tasks, return_exceptions=True)

    source_data = {
        "dadata": None,
        "infosphere": None,
        "casebook": None,
        "perplexity": None,
        "tavily": None,
    }

    for result in results:
        if isinstance(result, Exception):
            logger.error(f"Data collection error: {result}", component="data_collector")
            continue

        source = result.get("source")
        if source:
            source_data[source] = result

    successful_sources = [k for k, v in source_data.items() if v and v.get("success")]
    duration_ms = (time.perf_counter() - start_time) * 1000

    search_results = _convert_to_search_results(source_data)

    logger.structured(
        "info",
        "data_collection_completed",
        component="data_collector",
        successful_sources=successful_sources,
        total_sources=len([v for v in source_data.values() if v]),
        search_results_count=len(search_results),
        duration_ms=round(duration_ms, 2),
    )

    return {
        **state,
        "source_data": source_data,
        "search_results": search_results,
        "collection_stats": {
            "successful_sources": successful_sources,
            "duration_ms": round(duration_ms, 2),
        },
        "current_step": "analyzing",
    }


def _convert_to_search_results(source_data: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Конвертирует source_data в формат search_results для report_analyzer."""
    search_results = []

    perplexity = source_data.get("perplexity", {})
    if perplexity and perplexity.get("success"):
        content = perplexity.get("content", "")
        search_results.append(
            {
                "intent_id": "perplexity_search",
                "description": "Веб-поиск (Perplexity AI)",
                "query": "Информация о компании",
                "success": True,
                "content": content,
                "citations": perplexity.get("citations", []),
                "sentiment": _analyze_sentiment(content),
            }
        )

    tavily = source_data.get("tavily", {})
    if tavily and tavily.get("success"):
        answer = tavily.get("answer", "")
        results_text = "\n".join(
            [r.get("content", "") for r in tavily.get("results", [])[:3]]
        )
        content = f"{answer}\n\n{results_text}".strip()
        search_results.append(
            {
                "intent_id": "tavily_search",
                "description": "Веб-поиск (Tavily)",
                "query": "Информация о компании",
                "success": True,
                "content": content,
                "citations": [
                    r.get("url") for r in tavily.get("results", []) if r.get("url")
                ],
                "sentiment": _analyze_sentiment(content),
            }
        )

    dadata = source_data.get("dadata", {})
    if dadata and dadata.get("success"):
        data = dadata.get("data", {})
        content = f"Компания: {data.get('name', {}).get('full_with_opf', 'Н/Д')}\n"
        content += f"Статус: {data.get('state', {}).get('status', 'Н/Д')}\n"
        content += f"Адрес: {data.get('address', {}).get('value', 'Н/Д')}"

        status = data.get("state", {}).get("status", "")
        sentiment = (
            {"label": "negative", "score": -0.5}
            if status == "LIQUIDATED"
            else {"label": "neutral", "score": 0}
        )

        search_results.append(
            {
                "intent_id": "dadata_info",
                "description": "Реестровые данные (DaData)",
                "query": "Информация из ЕГРЮЛ",
                "success": True,
                "content": content,
                "citations": [],
                "sentiment": sentiment,
            }
        )

    casebook = source_data.get("casebook", {})
    if casebook and casebook.get("success"):
        cases = casebook.get("data", [])
        case_count = len(cases)
        content = f"Найдено судебных дел: {case_count}"
        if case_count > 0:
            content += f"\nПоследние дела: {', '.join([str(c.get('caseNumber', '')) for c in cases[:5]])}"

        if case_count > 10:
            sentiment = {"label": "negative", "score": -0.7}
        elif case_count > 3:
            sentiment = {"label": "negative", "score": -0.3}
        else:
            sentiment = {"label": "neutral", "score": 0}

        search_results.append(
            {
                "intent_id": "lawsuits",
                "description": "Судебные дела (Casebook)",
                "query": "Арбитражные дела",
                "success": True,
                "content": content,
                "citations": [],
                "sentiment": sentiment,
            }
        )

    infosphere = source_data.get("infosphere", {})
    if infosphere and infosphere.get("success"):
        data = infosphere.get("data", {})
        content = (
            f"Проверка по базам: {len(data) if isinstance(data, list) else 'выполнена'}"
        )
        search_results.append(
            {
                "intent_id": "infosphere_check",
                "description": "Проверка контрагента (InfoSphere)",
                "query": "Проверка по базам данных",
                "success": True,
                "content": content,
                "citations": [],
                "sentiment": {"label": "neutral", "score": 0},
            }
        )

    return search_results


def _analyze_sentiment(text: str) -> Dict[str, Any]:
    """Простой анализ тональности текста."""
    if not text:
        return {"label": "neutral", "score": 0.0}

    text_lower = text.lower()

    negative_words = [
        "банкрот",
        "долг",
        "суд",
        "иск",
        "штраф",
        "нарушен",
        "проблем",
        "риск",
        "опасн",
        "негатив",
        "плох",
        "ухудш",
        "кризис",
        "ликвидир",
    ]
    positive_words = [
        "рост",
        "прибыл",
        "успех",
        "надежн",
        "стабильн",
        "лидер",
        "качеств",
        "довольн",
        "рекоменд",
        "хорош",
        "отличн",
        "позитив",
    ]

    neg_count = sum(1 for word in negative_words if word in text_lower)
    pos_count = sum(1 for word in positive_words if word in text_lower)

    total = neg_count + pos_count
    if total == 0:
        return {"label": "neutral", "score": 0.0}

    score = (pos_count - neg_count) / max(total, 1)
    score = max(-1.0, min(1.0, score))

    if score > 0.2:
        label = "positive"
    elif score < -0.2:
        label = "negative"
    else:
        label = "neutral"

    return {"label": label, "score": round(score, 2)}
