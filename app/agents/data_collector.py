"""
Data Collector Agent: параллельный сбор данных из всех источников.
Casebook, InfoSphere, DaData + Perplexity, Tavily
"""

import asyncio
import time
from typing import Any, Dict, List, Optional

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
MAX_WEB_CONTENT_CHARS = 2500


def _truncate(text: str, max_len: int = MAX_WEB_CONTENT_CHARS) -> str:
    if not text:
        return ""
    if len(text) <= max_len:
        return text
    return text[: max_len - 3] + "..."


async def _fetch_perplexity(intent_id: str, query: str, client_name: str) -> Dict[str, Any]:
    """Запрос к Perplexity AI."""
    client = PerplexityClient.get_instance()
    if not client.is_configured():
        return {
            "source": "perplexity",
            "intent_id": intent_id,
            "success": False,
            "error": "Not configured",
        }

    try:
        question = (
            "Найди проверяемые факты о компании и укажи источники.\n"
            f"Компания: {client_name}\n"
            f"Запрос: {query}\n"
            "Формат: кратко, по пунктам (факты/риски/упоминания в СМИ/суды/финансы)."
        )
        system_prompt = (
            "Ты аналитик комплаенса. Ищи только проверяемые факты, не выдумывай. "
            "Пиши по-русски."
        )

        # Требование: клиент Perplexity работает через LangChain.
        result = await asyncio.wait_for(
            client.ask(
                question=question,
                system_prompt=system_prompt,
                search_recency_filter="month",
            ),
            timeout=SEARCH_TIMEOUT,
        )

        return {
            "source": "perplexity",
            "intent_id": intent_id,
            "success": bool(result.get("success", False)),
            "content": _truncate(result.get("content", "") or ""),
            "citations": result.get("citations", []) or [],
            "error": result.get("error"),
            "integration": result.get("integration"),
        }
    except asyncio.TimeoutError:
        return {
            "source": "perplexity",
            "intent_id": intent_id,
            "success": False,
            "error": "Timeout",
        }
    except Exception as e:
        return {
            "source": "perplexity",
            "intent_id": intent_id,
            "success": False,
            "error": str(e),
        }


async def _fetch_tavily(intent_id: str, query: str, client_name: str) -> Dict[str, Any]:
    """Запрос к Tavily Search."""
    client = TavilyClient.get_instance()
    if not client.is_configured():
        return {
            "source": "tavily",
            "intent_id": intent_id,
            "success": False,
            "error": "Not configured",
        }

    try:
        result = await asyncio.wait_for(
            client.search(
                query=query if client_name in query else f"{client_name} {query}",
                search_depth="advanced",
                max_results=10,
                include_answer=True,
            ),
            timeout=SEARCH_TIMEOUT,
        )
        return {
            "source": "tavily",
            "intent_id": intent_id,
            "success": bool(result.get("success", False)),
            "answer": _truncate(result.get("answer", "") or "", max_len=1200),
            "results": result.get("results", []),
            "error": result.get("error"),
        }
    except asyncio.TimeoutError:
        return {"source": "tavily", "intent_id": intent_id, "success": False, "error": "Timeout"}
    except Exception as e:
        return {"source": "tavily", "intent_id": intent_id, "success": False, "error": str(e)}


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

    # Фаза 1: параллельные источники по ИНН
    inn_tasks: List[asyncio.Task] = []
    if inn and inn.isdigit() and len(inn) in (10, 12):
        inn_tasks = [
            asyncio.create_task(_fetch_dadata_wrapper(inn)),
            asyncio.create_task(_fetch_infosphere_wrapper(inn)),
            asyncio.create_task(_fetch_casebook_wrapper(inn)),
        ]

    inn_results: List[Any] = []
    if inn_tasks:
        inn_results = await asyncio.gather(*inn_tasks, return_exceptions=True)

    # Фаза 2: веб-поиск (после получения реестровых данных)
    intents: List[Dict[str, str]] = []
    if isinstance(search_intents, list) and search_intents:
        intents = [i for i in search_intents if isinstance(i, dict) and i.get("id") and i.get("query")]
    if not intents:
        intents = [{"id": "reputation", "query": client_name, "description": "Общая репутация и отзывы"}]

    semaphore = asyncio.Semaphore(MAX_CONCURRENT)

    async def _bounded(coro):
        async with semaphore:
            return await coro

    web_tasks: List[asyncio.Task] = []
    for intent in intents:
        intent_id = str(intent.get("id"))
        query = str(intent.get("query") or client_name)
        web_tasks.append(asyncio.create_task(_bounded(_fetch_perplexity(intent_id, query, client_name))))
        web_tasks.append(asyncio.create_task(_bounded(_fetch_tavily(intent_id, query, client_name))))

    web_results: List[Any] = []
    if web_tasks:
        web_results = await asyncio.gather(*web_tasks, return_exceptions=True)

    results = [*inn_results, *web_results]

    source_data = {
        "dadata": None,
        "infosphere": None,
        "casebook": None,
        "perplexity": {"success": True, "intents": {}, "errors": []},
        "tavily": {"success": True, "intents": {}, "errors": []},
    }

    for result in results:
        if isinstance(result, Exception):
            logger.error(f"Data collection error: {result}", component="data_collector")
            continue

        source = result.get("source")
        if not source:
            continue

        if source in ("dadata", "infosphere", "casebook"):
            source_data[source] = result
            continue

        if source in ("perplexity", "tavily"):
            intent_id = result.get("intent_id") or "unknown"
            container = source_data[source]
            if isinstance(container, dict):
                intents_map = container.setdefault("intents", {})
                intents_map[intent_id] = result
                if not result.get("success"):
                    container.setdefault("errors", []).append(
                        {"intent_id": intent_id, "error": result.get("error")}
                    )
                    container["success"] = False
            continue

    successful_sources = [k for k, v in source_data.items() if v and v.get("success")]
    duration_ms = (time.perf_counter() - start_time) * 1000

    search_results = _build_search_results(source_data, intents)

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
            "web_intents_count": len(intents),
        },
        "current_step": "analyzing",
    }


def _build_search_results(
    source_data: Dict[str, Any], intents: List[Dict[str, str]]
) -> List[Dict[str, Any]]:
    """Собирает единый массив search_results для report_analyzer."""
    search_results = []

    # 1) Реестровые источники (по ИНН)
    search_results.extend(_convert_registry_sources_to_search_results(source_data))

    # 2) Веб-поиск по интентам: Perplexity + Tavily -> объединяем в один результат на интент
    perpl = source_data.get("perplexity", {}) or {}
    tav = source_data.get("tavily", {}) or {}

    perpl_intents = perpl.get("intents", {}) if isinstance(perpl, dict) else {}
    tav_intents = tav.get("intents", {}) if isinstance(tav, dict) else {}

    for intent in intents:
        intent_id = str(intent.get("id") or "unknown")
        description = str(intent.get("description") or intent_id)
        query = str(intent.get("query") or "")

        perpl_res = perpl_intents.get(intent_id, {}) if isinstance(perpl_intents, dict) else {}
        tav_res = tav_intents.get(intent_id, {}) if isinstance(tav_intents, dict) else {}

        content_parts: List[str] = []
        citations: List[str] = []
        success = False

        if isinstance(perpl_res, dict) and perpl_res.get("success"):
            perpl_content = perpl_res.get("content", "") or ""
            if perpl_content:
                content_parts.append(f"[Perplexity]\n{perpl_content}")
            citations.extend(perpl_res.get("citations", []) or [])
            success = True

        if isinstance(tav_res, dict) and tav_res.get("success"):
            answer = tav_res.get("answer", "") or ""
            results_text = "\n".join(
                [
                    (r.get("content", "") or r.get("snippet", "") or "").strip()
                    for r in (tav_res.get("results", []) or [])[:3]
                    if isinstance(r, dict)
                ]
            ).strip()
            tav_block = "\n\n".join([p for p in [answer, results_text] if p]).strip()
            if tav_block:
                content_parts.append(f"[Tavily]\n{_truncate(tav_block, max_len=1600)}")
            citations.extend(
                [
                    r.get("url")
                    for r in (tav_res.get("results", []) or [])
                    if isinstance(r, dict) and r.get("url")
                ]
            )
            success = True

        combined = _truncate("\n\n".join([p for p in content_parts if p]).strip())
        if not combined:
            # Если оба источника упали — фиксируем это как неуспех, но сохраняем intent_id/query.
            search_results.append(
                {
                    "intent_id": intent_id,
                    "description": description,
                    "query": query,
                    "success": False,
                    "content": "",
                    "citations": [],
                    "sentiment": {"label": "neutral", "score": 0.0},
                }
            )
            continue

        search_results.append(
            {
                "intent_id": intent_id,
                "description": description,
                "query": query,
                "success": success,
                "content": combined,
                "citations": list(dict.fromkeys([c for c in citations if c]))[:20],
                "sentiment": _analyze_sentiment(combined),
            }
        )

    return search_results


def _convert_registry_sources_to_search_results(
    source_data: Dict[str, Any],
) -> List[Dict[str, Any]]:
    """Конвертирует DaData/Casebook/InfoSphere в формат search_results."""
    search_results: List[Dict[str, Any]] = []

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
