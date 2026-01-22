"""
Data Collector Agent: main agent function for parallel data collection.

Orchestrates data collection from all sources:
- Registry sources (DaData, InfoSphere, Casebook)
- Web search (Perplexity, Tavily)
- Web scraping (Tavily links)
- Cascade analysis (Perplexity + Tavily)
"""

import asyncio
import time
from typing import Any, Dict, List

from app.agents.data_collector.builders import build_search_results
from app.agents.data_collector.fetchers import (
    cascade_perplexity_analysis,
    fetch_casebook,
    fetch_dadata,
    fetch_infosphere,
    fetch_perplexity,
    fetch_tavily,
)
from app.agents.web_scraper import scrape_top_tavily_links
from app.config import MAX_CONCURRENT_SEARCHES
from app.utility.logging_client import logger


async def data_collector_agent(state: Dict[str, Any]) -> Dict[str, Any]:
    """
    Агент сбора данных: параллельные запросы ко всем источникам.

    Поддержка early_inn_tasks из workflow - если InfoSphere/Casebook
    уже запущены раньше, используем их вместо создания новых задач.

    Args:
        state: Agent state containing:
            - client_name: str - название компании
            - inn: str - ИНН компании (опционально)
            - search_intents: List[Dict] - поисковые запросы от оркестратора
            - _early_inn_tasks: Dict[str, Task] - задачи, запущенные в workflow

    Returns:
        Updated state with:
            - source_data: Dict - данные от всех источников
            - search_results: List - унифицированный формат результатов
            - collection_stats: Dict - статистика сбора
            - current_step: str - "analyzing"
    """
    client_name = state.get("client_name", "")
    inn = state.get("inn", "")
    search_intents = state.get("search_intents", [])
    early_inn_tasks = state.get("_early_inn_tasks", {})

    start_time = time.perf_counter()

    logger.structured(
        "info",
        "data_collection_started",
        component="data_collector",
        client_name=client_name[:50],
        inn=inn,
        intent_count=len(search_intents),
        has_early_tasks=bool(early_inn_tasks),
    )

    # Phase 1: Registry sources (INN-based)
    inn_results = await _collect_registry_sources(inn, early_inn_tasks)

    # Phase 2: Web search (after registry data)
    intents = _prepare_intents(search_intents, client_name)
    web_results = await _collect_web_sources(intents, client_name, inn)

    # Combine all results
    all_results = [*inn_results, *web_results]
    source_data = _organize_source_data(all_results)

    # Phase 3: Web scraping of top Tavily links
    tavily_full_texts = await _scrape_tavily_links(source_data)
    source_data["tavily_full_texts"] = tavily_full_texts

    # Phase 4: Cascade analysis (Perplexity + Tavily)
    await _run_cascade_analysis(source_data, client_name, inn, tavily_full_texts)

    # Build unified search results
    search_results = build_search_results(source_data, intents)

    # Calculate stats
    successful_sources = [k for k, v in source_data.items() if v and v.get("success")]
    duration_ms = (time.perf_counter() - start_time) * 1000

    logger.structured(
        "info",
        "data_collection_completed",
        component="data_collector",
        successful_sources=successful_sources,
        total_sources=len([v for v in source_data.values() if v]),
        search_results_count=len(search_results),
        scraped_pages=len(tavily_full_texts),
        has_cascade=bool(source_data.get("cascade_perplexity", {}).get("success")),
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


async def _collect_registry_sources(inn: str, early_inn_tasks: Dict[str, asyncio.Task]) -> List[Any]:
    """Collect data from registry sources (DaData, InfoSphere, Casebook)."""
    if not inn or not inn.isdigit() or len(inn) not in (10, 12):
        return []

    inn_tasks: List[asyncio.Task] = []

    # DaData - always create new task
    inn_tasks.append(asyncio.create_task(fetch_dadata(inn)))

    # InfoSphere - use early task if available
    if "infosphere" in early_inn_tasks:
        logger.info(
            "Data collector: using early-started InfoSphere task from workflow",
            component="data_collector",
        )
        inn_tasks.append(early_inn_tasks["infosphere"])
    else:
        inn_tasks.append(asyncio.create_task(fetch_infosphere(inn)))

    # Casebook - use early task if available
    if "casebook" in early_inn_tasks:
        logger.info(
            "Data collector: using early-started Casebook task from workflow",
            component="data_collector",
        )
        inn_tasks.append(early_inn_tasks["casebook"])
    else:
        inn_tasks.append(asyncio.create_task(fetch_casebook(inn)))

    return await asyncio.gather(*inn_tasks, return_exceptions=True)


def _prepare_intents(search_intents: List[Any], client_name: str) -> List[Dict[str, str]]:
    """Prepare and validate search intents."""
    intents: List[Dict[str, str]] = []
    if isinstance(search_intents, list) and search_intents:
        intents = [i for i in search_intents if isinstance(i, dict) and i.get("id") and i.get("query")]
    if not intents:
        intents = [
            {
                "id": "reputation",
                "query": client_name,
                "description": "Общая репутация и отзывы",
            }
        ]
    return intents


async def _collect_web_sources(intents: List[Dict[str, str]], client_name: str, inn: str) -> List[Any]:
    """Collect data from web sources (Perplexity, Tavily)."""
    semaphore = asyncio.Semaphore(MAX_CONCURRENT_SEARCHES)

    async def _bounded(coro):
        async with semaphore:
            return await coro

    web_tasks: List[asyncio.Task] = []
    for intent in intents:
        intent_id = str(intent.get("id"))
        query = str(intent.get("query") or client_name)
        web_tasks.append(asyncio.create_task(_bounded(fetch_perplexity(intent_id, query, client_name, inn))))
        web_tasks.append(asyncio.create_task(_bounded(fetch_tavily(intent_id, query, client_name, inn))))

    if not web_tasks:
        return []

    return await asyncio.gather(*web_tasks, return_exceptions=True)


def _organize_source_data(results: List[Any]) -> Dict[str, Any]:
    """Organize results into source_data structure."""
    source_data: Dict[str, Any] = {
        "dadata": None,
        "infosphere": None,
        "casebook": None,
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
                    container["successful_intents"] = int(container.get("successful_intents", 0)) + 1
                    container["success"] = True
                else:
                    container.setdefault("errors", []).append({"intent_id": intent_id, "error": result.get("error")})
                    container["failed_intents"] = int(container.get("failed_intents", 0)) + 1

    return source_data


async def _scrape_tavily_links(source_data: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Scrape top Tavily links for full content."""
    tavily_full_texts: List[Dict[str, Any]] = []

    if not source_data.get("tavily", {}).get("success"):
        return tavily_full_texts

    try:
        all_tavily_results = []
        tavily_intents = source_data["tavily"].get("intents", {})
        for intent_data in tavily_intents.values():
            if intent_data.get("success") and intent_data.get("results"):
                all_tavily_results.extend(intent_data["results"])

        if all_tavily_results:
            logger.info(
                "Data collector: starting web scraping of TOP-5 Tavily links",
                component="data_collector",
            )
            tavily_full_texts = await scrape_top_tavily_links(
                all_tavily_results,
                top_n=5,
                max_content_length=10000,
            )
            logger.info(
                f"Data collector: scraped {len(tavily_full_texts)} pages",
                component="data_collector",
            )
    except Exception as e:
        logger.error(f"Data collector: web scraping failed: {e}", component="data_collector")

    return tavily_full_texts


async def _run_cascade_analysis(
    source_data: Dict[str, Any],
    client_name: str,
    inn: str,
    tavily_full_texts: List[Dict[str, Any]],
) -> None:
    """Run cascade Perplexity analysis with Tavily data."""
    if not tavily_full_texts:
        return

    try:
        perplexity_results = []
        perpl = source_data.get("perplexity", {}) or {}
        perpl_intents = perpl.get("intents", {})
        for intent_data in perpl_intents.values():
            if intent_data.get("success"):
                perplexity_results.append(intent_data)

        if perplexity_results:
            logger.info(
                "Data collector: starting cascade Perplexity analysis",
                component="data_collector",
            )

            cascade_result = await cascade_perplexity_analysis(
                client_name=client_name,
                inn=inn,
                initial_perplexity_results=perplexity_results,
                tavily_full_texts=tavily_full_texts,
            )

            source_data["cascade_perplexity"] = cascade_result

            if cascade_result.get("success"):
                logger.info(
                    f"Data collector: cascade completed, {len(cascade_result.get('content', ''))} chars",
                    component="data_collector",
                )
    except Exception as e:
        logger.error(
            f"Data collector: cascade analysis error: {e}",
            component="data_collector",
        )


__all__ = ["data_collector_agent"]
