"""
Web search collectors (Perplexity, Tavily).

These collectors perform AI-powered web searches for company information.
"""

from typing import Any, Dict, List, Optional

from app.agents.collectors.base import BaseCollector, CollectorResult
from app.config import MAX_CONTENT_LENGTH, SEARCH_TIMEOUT_SECONDS
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

        question = f"""Найди проверяемые факты о компании и укажи источники.

Компания: {client_name}
ИНН: {inn if inn else "не указан"}
Запрос: {query}

Формат ответа:
- Кратко, по пунктам
- Только проверяемые факты
- Источники (URL, даты)
- Категории: факты/риски/суды/финансы/репутация

Период поиска: ПОСЛЕДНИЙ ГОД (актуальная информация)."""

        system_prompt = (
            "Глубокий анализ за последний год. Ищи 20+ источников. Только проверяемые факты. Пиши по-русски."
        )

        result = await self._client.ask(
            question=question,
            system_prompt=system_prompt,
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

    question = f"""Углублённый анализ компании {client_name} (ИНН: {inn}).

ПЕРВИЧНЫЕ НАХОДКИ Perplexity:
{chr(10).join(f"- {fact}" for fact in initial_facts)}

ДОПОЛНИТЕЛЬНЫЕ ИСТОЧНИКИ (Tavily):
{chr(10).join(f"- {url}" for url in urls[:5])}

Проанализируй источники, сопоставь с первичными находками, выяви риски."""

    try:
        result = await client.ask(
            question=question,
            system_prompt="Финансовый аналитик. Глубокий due diligence. Ищи риски и противоречия.",
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


def analyze_sentiment(text: str) -> Dict[str, Any]:
    """
    Simple sentiment analysis for Russian text.

    Args:
        text: Text to analyze

    Returns:
        Dictionary with label (positive/negative/neutral) and score
    """
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
