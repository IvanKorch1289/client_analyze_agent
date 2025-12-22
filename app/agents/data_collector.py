"""
Data Collector Agent: параллельный сбор данных из всех источников.
Casebook, InfoSphere, DaData + Perplexity, Tavily
"""

import asyncio
import time
from typing import Any, Dict, List, Optional

from app.agents.shared.prompts import DATA_COLLECTOR_SEARCH_PROMPT
from app.agents.shared.utils import truncate
from app.agents.web_scraper import scrape_top_tavily_links
from app.config import MAX_CONCURRENT_SEARCHES, MAX_CONTENT_LENGTH, SEARCH_TIMEOUT_SECONDS
from app.services.fetch_data import (
    fetch_from_casebook,
    fetch_from_dadata,
    fetch_from_infosphere,
)
from app.services.perplexity_client import PerplexityClient
from app.services.tavily_client import TavilyClient
from app.utility.logging_client import logger


async def _fetch_perplexity(intent_id: str, query: str, client_name: str, inn: str = "") -> Dict[str, Any]:
    """Запрос к Perplexity AI с recency=year."""
    client = PerplexityClient.get_instance()
    if not client.is_configured():
        return {
            "source": "perplexity",
            "intent_id": intent_id,
            "success": False,
            "error": "Not configured",
        }

    try:
        # Используем промпт из shared модуля
        question = DATA_COLLECTOR_SEARCH_PROMPT.format(
            client_name=client_name,
            inn=inn if inn else "не указан",
            query=query,
        )
        system_prompt = (
            "Ты аналитик комплаенса. Ищи только проверяемые факты из ПОСЛЕДНЕГО ГОДА. "
            "Не выдумывай. Пиши по-русски. Указывай источники и даты."
        )

        # P0: MAXIMUM DEPTH - recency="year", max_tokens увеличен
        result = await asyncio.wait_for(
            client.ask(
                question=question,
                system_prompt="Глубокий анализ за последний год. Ищи 20+ источников. Только проверяемые факты. Пиши по-русски.",
                search_recency_filter="year",  # БЫЛО: "month", СТАЛО: "year"
                max_tokens=2000,  # Увеличено для более полных ответов
            ),
            timeout=SEARCH_TIMEOUT_SECONDS,
        )

        return {
            "source": "perplexity",
            "intent_id": intent_id,
            "success": bool(result.get("success", False)),
            "content": truncate(result.get("content", "") or "", MAX_CONTENT_LENGTH),
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


async def _fetch_tavily(intent_id: str, query: str, client_name: str, inn: str = "") -> Dict[str, Any]:
    """Запрос к Tavily Search с time_range=year."""
    client = TavilyClient.get_instance()
    if not client.is_configured():
        return {
            "source": "tavily",
            "intent_id": intent_id,
            "success": False,
            "error": "Not configured",
        }

    try:
        # P0: MAXIMUM DEPTH - search_depth="extreme", max_results=20
        result = await asyncio.wait_for(
            client.search(
                query=query if client_name in query else f"{client_name} {query}",
                search_depth="advanced",  # "extreme" не поддерживается, используем "advanced"
                max_results=20,  # БЫЛО: 10, СТАЛО: 20
                include_answer=True,
                include_raw_content=False,  # Сначала сниппеты, потом скрейпим
            ),
            timeout=SEARCH_TIMEOUT_SECONDS,
        )
        return {
            "source": "tavily",
            "intent_id": intent_id,
            "success": bool(result.get("success", False)),
            "answer": truncate(result.get("answer", "") or "", max_length=1200),
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

    semaphore = asyncio.Semaphore(MAX_CONCURRENT_SEARCHES)

    async def _bounded(coro):
        async with semaphore:
            return await coro

    web_tasks: List[asyncio.Task] = []
    for intent in intents:
        intent_id = str(intent.get("id"))
        query = str(intent.get("query") or client_name)
        # P0: Передаём inn в функции для более точного поиска
        web_tasks.append(asyncio.create_task(_bounded(_fetch_perplexity(intent_id, query, client_name, inn))))
        web_tasks.append(asyncio.create_task(_bounded(_fetch_tavily(intent_id, query, client_name, inn))))

    web_results: List[Any] = []
    if web_tasks:
        web_results = await asyncio.gather(*web_tasks, return_exceptions=True)

    results = [*inn_results, *web_results]

    source_data = {
        "dadata": None,
        "infosphere": None,
        "casebook": None,
        # Для web-поиска: храним результаты по каждому intent_id.
        # success=True означает "хотя бы один интент успешно отработал".
        "perplexity": {
            "success": False,
            "intents": {},
            "errors": [],
            "successful_intents": 0,
            "failed_intents": 0,
        },
        "tavily": {
            "success": False,
            "intents": {},
            "errors": [],
            "successful_intents": 0,
            "failed_intents": 0,
        },
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
                if result.get("success"):
                    container["successful_intents"] = int(
                        container.get("successful_intents", 0)
                    ) + 1
                    container["success"] = True
                else:
                    container.setdefault("errors", []).append(
                        {"intent_id": intent_id, "error": result.get("error")}
                    )
                    container["failed_intents"] = int(
                        container.get("failed_intents", 0)
                    ) + 1
            continue

    successful_sources = [k for k, v in source_data.items() if v and v.get("success")]
    duration_ms = (time.perf_counter() - start_time) * 1000

    search_results = _build_search_results(source_data, intents)
    
    # P0: НОВОЕ - Скрейпинг TOP-5 ссылок Tavily для глубокого анализа
    tavily_full_texts = []
    if source_data.get("tavily", {}).get("success"):
        try:
            # Собираем все результаты Tavily
            all_tavily_results = []
            tavily_intents = source_data["tavily"].get("intents", {})
            for intent_data in tavily_intents.values():
                if intent_data.get("success") and intent_data.get("results"):
                    all_tavily_results.extend(intent_data["results"])
            
            if all_tavily_results:
                logger.info(
                    f"Data collector: starting web scraping of TOP-5 Tavily links",
                    component="data_collector"
                )
                tavily_full_texts = await scrape_top_tavily_links(
                    all_tavily_results,
                    top_n=5,
                    max_content_length=10000,
                )
                logger.info(
                    f"Data collector: scraped {len(tavily_full_texts)} pages",
                    component="data_collector"
                )
        except Exception as e:
            logger.error(
                f"Data collector: web scraping failed: {e}",
                component="data_collector"
            )
    
    # Добавляем полные тексты в source_data
    source_data["tavily_full_texts"] = tavily_full_texts

    logger.structured(
        "info",
        "data_collection_completed",
        component="data_collector",
        successful_sources=successful_sources,
        total_sources=len([v for v in source_data.values() if v]),
        search_results_count=len(search_results),
        scraped_pages=len(tavily_full_texts),
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
                content_parts.append(f"[Tavily]\n{truncate(tav_block, max_length=1600)}")
            citations.extend(
                [
                    r.get("url")
                    for r in (tav_res.get("results", []) or [])
                    if isinstance(r, dict) and r.get("url")
                ]
            )
            success = True

        combined = truncate("\n\n".join([p for p in content_parts if p]).strip(), MAX_CONTENT_LENGTH)
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
