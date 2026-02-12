"""
Web search collectors (Perplexity, Tavily).

These collectors perform AI-powered web searches for company information.
"""

from typing import Any, Dict, List, Optional

from app.agents.collectors.base import BaseCollector, CollectorResult
from app.config import MAX_CONTENT_LENGTH, SEARCH_TIMEOUT_SECONDS
from app.mcp_server.prompts.system_prompts import (
    CASCADE_QUESTION_TEMPLATE,
    CASCADE_SYSTEM_PROMPT_CONTENT,
    DATA_COLLECTOR_PROMPT_CONTENT,
    PERPLEXITY_SYSTEM_PROMPT_CONTENT,
)
from app.services.perplexity_client import PerplexityClient
from app.services.tavily_client import TavilyClient
from app.shared.toolkit.formatters import truncate
from app.shared.toolkit.logging import logger


class PerplexityCollector(BaseCollector):
    """
    Collector for Perplexity AI web search.

    Uses Perplexity's LLM-powered search with recency filtering.
    Provides structured analysis of web findings.
    """

    source_name = "perplexity"
    default_timeout = SEARCH_TIMEOUT_SECONDS

    def __init__(self, timeout: Optional[int] = None):
        super().__init__(timeout)
        self._client = PerplexityClient.get_instance()

    def is_configured(self) -> bool:
        return self._client.is_configured()

    async def _collect(
        self,
        query: str = "",
        client_name: str = "",
        inn: str = "",
        intent_id: str = "",
        **kwargs,
    ) -> CollectorResult:
        """
        Search via Perplexity AI.

        Args:
            query: Search query
            client_name: Company name
            inn: Company INN (optional)
            intent_id: Intent identifier for tracking

        Returns:
            CollectorResult with AI-analyzed search results
        """
        if not self.is_configured():
            return CollectorResult(
                source=self.source_name,
                success=False,
                error="Not configured",
                intent_id=intent_id,
            )

        question = DATA_COLLECTOR_PROMPT_CONTENT.format(
            client_name=client_name,
            inn=inn if inn else "не указан",
            query=query,
        )

        result = await self._client.ask(
            question=question,
            system_prompt=PERPLEXITY_SYSTEM_PROMPT_CONTENT,
            search_recency_filter="year",
            max_tokens=2000,
        )

        return CollectorResult(
            source=self.source_name,
            success=bool(result.get("success", False)),
            data={
                "content": truncate(result.get("content", "") or "", MAX_CONTENT_LENGTH),
                "citations": result.get("citations", []) or [],
            },
            error=result.get("error"),
            intent_id=intent_id,
            metadata={"integration": result.get("integration")},
        )


class TavilyCollector(BaseCollector):
    """
    Collector for Tavily search API.

    Provides advanced web search with content extraction.
    Good for finding specific documents and news.
    """

    source_name = "tavily"
    default_timeout = SEARCH_TIMEOUT_SECONDS

    def __init__(self, timeout: Optional[int] = None):
        super().__init__(timeout)
        self._client = TavilyClient.get_instance()

    def is_configured(self) -> bool:
        return self._client.is_configured()

    async def _collect(
        self,
        query: str = "",
        client_name: str = "",
        inn: str = "",
        intent_id: str = "",
        **kwargs,
    ) -> CollectorResult:
        """
        Search via Tavily API.

        Args:
            query: Search query
            client_name: Company name
            inn: Company INN (optional)
            intent_id: Intent identifier for tracking

        Returns:
            CollectorResult with search results and snippets
        """
        if not self.is_configured():
            return CollectorResult(
                source=self.source_name,
                success=False,
                error="Not configured",
                intent_id=intent_id,
            )

        search_query = query if client_name in query else f"{client_name} {query}"

        result = await self._client.search(
            query=search_query,
            search_depth="advanced",
            max_results=20,
            include_answer=True,
            include_raw_content=False,
        )

        return CollectorResult(
            source=self.source_name,
            success=bool(result.get("success", False)),
            data={
                "answer": truncate(result.get("answer", "") or "", max_length=1200),
                "results": result.get("results", []),
            },
            error=result.get("error"),
            intent_id=intent_id,
        )


async def cascade_perplexity_analysis(
    client_name: str,
    inn: str,
    initial_perplexity_results: List[Dict[str, Any]],
    tavily_full_texts: List[Dict[str, Any]],
) -> Dict[str, Any]:
    """
    Cascade analysis: re-run Perplexity with Tavily data.

    Takes initial Perplexity findings and Tavily scraped content,
    then performs deeper analysis combining both sources.

    Args:
        client_name: Company name
        inn: Company INN
        initial_perplexity_results: Results from first Perplexity run
        tavily_full_texts: Scraped content from Tavily URLs

    Returns:
        Dictionary with cascade analysis results
    """
    client = PerplexityClient.get_instance()
    if not client.is_configured():
        return {"success": False, "error": "Not configured"}

    urls = [t["url"] for t in tavily_full_texts if t.get("full_content")]
    if not urls:
        return {"success": False, "error": "No Tavily URLs"}

    # Collect facts from initial Perplexity results
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



# analyze_sentiment was removed — use app.agents.data_collector.builders.analyze_sentiment instead.
