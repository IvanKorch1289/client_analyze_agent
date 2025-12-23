"""
API tools for external data sources.

All tools are async and use proper validation.
"""

from typing import Any, Dict, Literal

from httpx import AsyncClient, HTTPStatusError, RequestError
from pydantic import BaseModel, Field, field_validator

from app.shared.config import settings
from app.shared.exceptions import APIError
from app.shared.logger import get_logger
from app.shared.security import sanitize_for_llm, validate_inn

logger = get_logger(__name__)


# ============================================================================
# Request Models
# ============================================================================


class DaDataRequest(BaseModel):
    """Request for DaData API."""

    query: str = Field(..., max_length=500, description="Company name or INN")
    count: int = Field(default=10, ge=1, le=20, description="Max results")

    @field_validator("query")
    @classmethod
    def validate_query(cls, v: str) -> str:
        """Validate and sanitize query."""
        return sanitize_for_llm(v, max_length=500, strict=False)


class CasebookRequest(BaseModel):
    """Request for Casebook API."""

    inn: str = Field(..., description="Company INN (10 or 12 digits)")
    include_cases: bool = Field(default=True, description="Include court cases")
    include_bankruptcy: bool = Field(default=True, description="Include bankruptcy info")

    @field_validator("inn")
    @classmethod
    def validate_inn_field(cls, v: str) -> str:
        """Validate INN format."""
        is_valid, error = validate_inn(v)
        if not is_valid and v:  # Allow empty if validation passes
            raise ValueError(error)
        return v.strip()


class InfosferaRequest(BaseModel):
    """Request for Infosfera API."""

    inn: str = Field(..., description="Company INN")
    include_finance: bool = Field(default=True, description="Include financial data")
    include_licenses: bool = Field(default=False, description="Include licenses")


class PerplexityRequest(BaseModel):
    """Request for Perplexity AI search."""

    query: str = Field(..., max_length=1000, description="Search query")
    focus: str = Field(
        default="general",
        description="Search focus: general, news, academic, etc.",
    )

    @field_validator("query")
    @classmethod
    def validate_query(cls, v: str) -> str:
        """Validate and sanitize query."""
        return sanitize_for_llm(v, max_length=1000, strict=False)


class TavilyRequest(BaseModel):
    """Request for Tavily search."""

    query: str = Field(..., max_length=1000, description="Search query")
    max_results: int = Field(default=5, ge=1, le=10, description="Max results")
    search_depth: Literal["basic", "advanced", "fast", "ultra-fast"] = Field(
        default="basic",
        description="Search depth",
    )

    @field_validator("query")
    @classmethod
    def validate_query(cls, v: str) -> str:
        """Validate and sanitize query."""
        return sanitize_for_llm(v, max_length=1000, strict=False)


# ============================================================================
# Tool Functions
# ============================================================================


async def fetch_dadata_company_tool(request: DaDataRequest) -> Dict[str, Any]:
    """
    Fetch company data from DaData API.

    Args:
        request: Validated request

    Returns:
        Company information from ЕГРЮЛ

    Raises:
        APIError: If API call fails

    Examples:
        >>> result = await fetch_dadata_company_tool(
        ...     DaDataRequest(query="Сбербанк", count=5)
        ... )
    """
    logger.log_action("dadata_api_call", query=request.query, count=request.count)

    try:
        async with AsyncClient(timeout=30.0) as client:
            response = await client.post(
                "https://suggestions.dadata.ru/suggestions/api/4_1/rs/suggest/party",
                headers={
                    "Authorization": f"Token {settings.DADATA_API_TOKEN}",
                    "X-Secret": settings.DADATA_API_SECRET,
                    "Content-Type": "application/json",
                },
                json={
                    "query": request.query,
                    "count": request.count,
                },
            )
            response.raise_for_status()

            data = response.json()
            logger.log_action(
                "dadata_api_success",
                status_code=response.status_code,
                results_count=len(data.get("suggestions", [])),
            )

            return data

    except HTTPStatusError as e:
        status_code = e.response.status_code if e.response else None
        logger.error(
            "dadata_api_failed",
            exc=e,
            query=request.query,
            status_code=status_code,
        )
        raise APIError(
            f"DaData API error: {e}",
            status_code=status_code,
            api_name="DaData",
            original_error=e,
        )
    except RequestError as e:
        logger.error("dadata_api_failed", exc=e, query=request.query)
        raise APIError(
            f"DaData API request error: {e}",
            api_name="DaData",
            original_error=e,
        )


async def fetch_casebook_data_tool(request: CasebookRequest) -> Dict[str, Any]:
    """
    Fetch court cases and bankruptcy data from Casebook API.

    Args:
        request: Validated request

    Returns:
        Court cases and bankruptcy information

    Raises:
        APIError: If API call fails
    """
    logger.log_action("casebook_api_call", inn=request.inn)

    try:
        async with AsyncClient(timeout=30.0) as client:
            # Casebook API endpoint (placeholder - adjust based on actual API)
            response = await client.get(
                "https://api3.casebook.ru/api/search",
                headers={
                    "Authorization": f"Bearer {settings.CASEBOOK_API_KEY}",
                    "Content-Type": "application/json",
                },
                params={
                    "inn": request.inn,
                    "include_cases": request.include_cases,
                    "include_bankruptcy": request.include_bankruptcy,
                },
            )
            response.raise_for_status()

            data = response.json()
            logger.log_action(
                "casebook_api_success",
                status_code=response.status_code,
                inn=request.inn,
            )

            return data

    except HTTPStatusError as e:
        status_code = e.response.status_code if e.response else None
        logger.error(
            "casebook_api_failed",
            exc=e,
            inn=request.inn,
            status_code=status_code,
        )
        raise APIError(
            f"Casebook API error: {e}",
            status_code=status_code,
            api_name="Casebook",
            original_error=e,
        )
    except RequestError as e:
        logger.error("casebook_api_failed", exc=e, inn=request.inn)
        raise APIError(
            f"Casebook API request error: {e}",
            api_name="Casebook",
            original_error=e,
        )


async def fetch_infosfera_data_tool(request: InfosferaRequest) -> Dict[str, Any]:
    """
    Fetch financial and license data from Infosfera API.

    Args:
        request: Validated request

    Returns:
        Financial and license information

    Raises:
        APIError: If API call fails
    """
    logger.log_action("infosfera_api_call", inn=request.inn)

    try:
        async with AsyncClient(timeout=30.0) as client:
            # Infosfera API endpoint (placeholder)
            response = await client.get(
                "https://api.infosfera.ru/v1/company",
                headers={
                    "Authorization": f"Bearer {settings.INFOSFERA_API_KEY}",
                    "Content-Type": "application/json",
                },
                params={
                    "inn": request.inn,
                    "finance": request.include_finance,
                    "licenses": request.include_licenses,
                },
            )
            response.raise_for_status()

            data = response.json()
            logger.log_action(
                "infosfera_api_success",
                status_code=response.status_code,
                inn=request.inn,
            )

            return data

    except HTTPStatusError as e:
        status_code = e.response.status_code if e.response else None
        logger.error(
            "infosfera_api_failed",
            exc=e,
            inn=request.inn,
            status_code=status_code,
        )
        raise APIError(
            f"Infosfera API error: {e}",
            status_code=status_code,
            api_name="Infosfera",
            original_error=e,
        )
    except RequestError as e:
        logger.error("infosfera_api_failed", exc=e, inn=request.inn)
        raise APIError(
            f"Infosfera API request error: {e}",
            api_name="Infosfera",
            original_error=e,
        )


async def search_perplexity_tool(request: PerplexityRequest) -> Dict[str, Any]:
    """
    Search using Perplexity AI.

    Args:
        request: Validated request

    Returns:
        Search results with citations

    Raises:
        APIError: If API call fails
    """
    logger.log_action("perplexity_search", query=request.query, focus=request.focus)

    try:
        from app.services.perplexity_client import PerplexityClient

        client = PerplexityClient()
        result = await client.ask(
            question=request.query,
            system_prompt=request.focus,
        )

        logger.log_action(
            "perplexity_search_success",
            query=request.query,
            results_count=len(result.get("citations", [])),
        )

        return result

    except Exception as e:
        logger.error("perplexity_search_failed", exc=e, query=request.query)
        raise APIError(
            f"Perplexity search error: {e}",
            api_name="Perplexity",
            original_error=e,
        )


async def search_tavily_tool(request: TavilyRequest) -> Dict[str, Any]:
    """
    Search using Tavily.

    Args:
        request: Validated request

    Returns:
        Structured search results

    Raises:
        APIError: If API call fails
    """
    logger.log_action(
        "tavily_search",
        query=request.query,
        max_results=request.max_results,
        depth=request.search_depth,
    )

    try:
        from app.services.tavily_client import TavilyClient

        client = TavilyClient()
        result = await client.search(
            query=request.query,
            max_results=request.max_results,
            search_depth=request.search_depth,
        )

        logger.log_action(
            "tavily_search_success",
            query=request.query,
            results_count=len(result.get("results", [])),
        )

        return result

    except Exception as e:
        logger.error("tavily_search_failed", exc=e, query=request.query)
        raise APIError(
            f"Tavily search error: {e}",
            api_name="Tavily",
            original_error=e,
        )


__all__ = [
    "DaDataRequest",
    "CasebookRequest",
    "InfosferaRequest",
    "PerplexityRequest",
    "TavilyRequest",
    "fetch_dadata_company_tool",
    "fetch_casebook_data_tool",
    "fetch_infosfera_data_tool",
    "search_perplexity_tool",
    "search_tavily_tool",
]
