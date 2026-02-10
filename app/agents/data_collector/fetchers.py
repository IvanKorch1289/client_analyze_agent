"""
Data source fetchers for parallel data collection.

Contains fetch functions for:
- Perplexity AI (web search with LLM)
- Tavily (web search and scraping)
- DaData (EGRUL registry)
- InfoSphere (multi-database checks)
- Casebook (court cases)
"""

import asyncio
from typing import List

from app.config import (
    MAX_CONTENT_LENGTH,
    SEARCH_TIMEOUT_SECONDS,
)
from app.services.fetch_data import (
    fetch_from_casebook,
    fetch_from_dadata,
    fetch_from_infosphere,
)
from app.services.perplexity_client import PerplexityClient
from app.services.tavily_client import TavilyClient
from app.shared.types import (
    CascadeResult,
    CasebookResult,
    DaDataResult,
    InfoSphereResult,
    PerplexityResult,
    TavilyResult,
    TavilyFullText,
)
from app.mcp_server.prompts.system_prompts import (
    CASCADE_QUESTION_TEMPLATE,
    CASCADE_SYSTEM_PROMPT_CONTENT,
    DATA_COLLECTOR_PROMPT_CONTENT,
    PERPLEXITY_SYSTEM_PROMPT_CONTENT,
)
from app.shared.toolkit.formatters import truncate
from app.shared.toolkit.logging import logger


async def fetch_perplexity(intent_id: str, query: str, client_name: str, inn: str = "") -> PerplexityResult:
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
        question = DATA_COLLECTOR_PROMPT_CONTENT.format(
            client_name=client_name,
            inn=inn if inn else "не указан",
            query=query,
        )

        result = await asyncio.wait_for(
            client.ask(
                question=question,
                system_prompt=PERPLEXITY_SYSTEM_PROMPT_CONTENT,
                search_recency_filter="year",
                max_tokens=2000,
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


async def cascade_perplexity_analysis(
    client_name: str,
    inn: str,
    initial_perplexity_results: List[PerplexityResult],
    tavily_full_texts: List[TavilyFullText],
) -> CascadeResult:
    """
    CASCADE АНАЛИЗ - повторный Perplexity с учётом Tavily данных.

    После вызова Tavily и получения ссылок на сайты запускает повторно
    Perplexity для анализа предыдущей информации + найденных данных Tavily.
    """
    client = PerplexityClient.get_instance()
    if not client.is_configured():
        return {"success": False, "error": "Not configured"}

    urls = [t["url"] for t in tavily_full_texts if t.get("full_content")]
    if not urls:
        return {"success": False, "error": "No Tavily URLs"}

    initial_facts = []
    for result in initial_perplexity_results[:3]:
        if result.get("success") and result.get("content"):
            initial_facts.append(result["content"][:500])

    question = CASCADE_QUESTION_TEMPLATE.format(
        client_name=client_name,
        inn=inn,
        initial_facts=chr(10).join(f"- {fact}" for fact in initial_facts),
        tavily_urls=chr(10).join(f"- {url}" for url in urls[:5]),
    )

    try:
        result = await client.ask(
            question=question,
            system_prompt=CASCADE_SYSTEM_PROMPT_CONTENT,
            search_recency_filter="year",
            max_tokens=3000,
            use_cache=True,
        )

        return {
            "success": result.get("success", False),
            "content": result.get("content", ""),
            "citations": result.get("citations", []),
            "urls_analyzed": urls[:5],
        }
    except Exception as e:
        logger.error(f"Cascade analysis failed: {e}", component="cascade")
        return {"success": False, "error": str(e)}


async def fetch_tavily(intent_id: str, query: str, client_name: str, inn: str = "") -> TavilyResult:
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
        result = await asyncio.wait_for(
            client.search(
                query=query if client_name in query else f"{client_name} {query}",
                search_depth="advanced",
                max_results=20,
                include_answer=True,
                include_raw_content=False,
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
        return {
            "source": "tavily",
            "intent_id": intent_id,
            "success": False,
            "error": "Timeout",
        }
    except Exception as e:
        return {
            "source": "tavily",
            "intent_id": intent_id,
            "success": False,
            "error": str(e),
        }


async def fetch_dadata(inn: str) -> DaDataResult:
    """
    Обёртка для DaData с обработкой ошибок.
    Timeout: 30s (быстрый источник).
    """
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


async def fetch_infosphere(inn: str) -> InfoSphereResult:
    """
    Обёртка для InfoSphere с обработкой ошибок.
    Многостраничный источник, требует до 6 минут.
    Таймаут обрабатывается в http_client (360s).
    """
    if not inn or not inn.isdigit():
        return {"source": "infosphere", "success": False, "error": "Invalid INN"}

    try:
        logger.info(
            f"InfoSphere: starting long fetch for INN {inn} (may take up to 6 min)",
            component="data_collector",
        )
        result = await fetch_from_infosphere(inn)
        logger.info(f"InfoSphere: fetch completed for INN {inn}", component="data_collector")
        return {
            "source": "infosphere",
            "success": "error" not in result,
            "data": result.get("data", {}),
            "error": result.get("error"),
        }
    except Exception as e:
        logger.error(f"InfoSphere: fetch failed for INN {inn}: {e}", component="data_collector")
        return {"source": "infosphere", "success": False, "error": str(e)}


async def fetch_casebook(inn: str) -> CasebookResult:
    """
    Обёртка для Casebook с обработкой ошибок.
    Многостраничный источник (100+ страниц арбитражных дел).
    Требует до 6 минут. Таймаут в http_client (360s).
    """
    if not inn or not inn.isdigit():
        return {"source": "casebook", "success": False, "error": "Invalid INN"}

    try:
        logger.info(
            f"Casebook: starting long fetch for INN {inn} (may take up to 6 min, multi-page)",
            component="data_collector",
        )
        result = await fetch_from_casebook(inn)

        cases_count = len(result.get("data", [])) if result.get("data") else 0
        logger.info(
            f"Casebook: fetch completed for INN {inn}, found {cases_count} cases",
            component="data_collector",
        )

        return {
            "source": "casebook",
            "success": "error" not in result,
            "data": result.get("data", []),
            "error": result.get("error"),
        }
    except Exception as e:
        logger.error(f"Casebook: fetch failed for INN {inn}: {e}", component="data_collector")
        return {"source": "casebook", "success": False, "error": str(e)}


__all__ = [
    "fetch_perplexity",
    "cascade_perplexity_analysis",
    "fetch_tavily",
    "fetch_dadata",
    "fetch_infosphere",
    "fetch_casebook",
]
