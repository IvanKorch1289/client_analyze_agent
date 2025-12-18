from typing import List, Optional

from fastapi import APIRouter, Request
from pydantic import BaseModel

from app.api.compat import fail
from app.services.fetch_data import (
    fetch_company_info,
    fetch_from_casebook,
    fetch_from_dadata,
    fetch_from_infosphere,
)
from app.services.perplexity_client import PerplexityClient
from app.services.tavily_client import TavilyClient
from app.schemas.api import PerplexitySearchResponse, TavilySearchResponse
from app.utility.helpers import validate_inn

data_router = APIRouter(
    prefix="/data",
    tags=["Внешние данные"],
    responses={404: {"description": "Не найдено"}},
)


class PerplexityRequest(BaseModel):
    inn: str
    search_query: str
    search_recency: str = "month"
    
    @property
    def query(self) -> str:
        return f"ИНН {self.inn}: {self.search_query}. Ответь только фактами без предположений."


class TavilyRequest(BaseModel):
    inn: str
    search_query: str
    search_depth: str = "basic"
    max_results: int = 5
    include_answer: bool = True
    include_domains: Optional[List[str]] = None
    exclude_domains: Optional[List[str]] = None
    
    @property
    def query(self) -> str:
        return f"ИНН {self.inn} {self.search_query}"


@data_router.get("/client/infosphere/{inn}")
async def get_infosphere_data(inn: str):
    return await fetch_from_infosphere(inn)


@data_router.get("/client/dadata/{inn}")
async def get_dadata_data(inn: str):
    return await fetch_from_dadata(inn)


@data_router.get("/client/casebook/{inn}")
async def get_casebook_data(inn: str):
    return await fetch_from_casebook(inn)


@data_router.get("/client/info/{inn}")
async def get_all_client_data(inn: str):
    return await fetch_company_info(inn)


@data_router.post("/search/perplexity")
async def perplexity_search(
    http_request: Request, payload: PerplexityRequest
) -> PerplexitySearchResponse:
    """Search via Perplexity."""
    is_valid, error_msg = validate_inn(payload.inn)
    if not is_valid:
        return fail(http_request, status_code=400, message=error_msg)
    
    client = PerplexityClient.get_instance()

    if not client.is_configured():
        return fail(
            http_request,
            status_code=503,
            message="Perplexity API key не настроен",
        )

    # Клиент Perplexity работает через LangChain (OpenAI-compatible).
    result = await client.ask(
        question=payload.query, search_recency_filter=payload.search_recency
    )

    if result.get("success"):
        return {
            "status": "success",
            "inn": payload.inn,
            "content": result.get("content", ""),
            "citations": result.get("citations", []),
            "model": result.get("model"),
            "integration": result.get("integration"),
        }
    return fail(
        http_request,
        status_code=502,
        message=result.get("error", "Неизвестная ошибка"),
    )


@data_router.post("/search/tavily")
async def tavily_search(http_request: Request, payload: TavilyRequest) -> TavilySearchResponse:
    """Search via Tavily."""
    is_valid, error_msg = validate_inn(payload.inn)
    if not is_valid:
        return fail(http_request, status_code=400, message=error_msg)
    
    client = TavilyClient.get_instance()

    if not client.is_configured():
        return fail(
            http_request,
            status_code=503,
            message="Tavily API key не настроен. Добавьте TAVILY_TOKEN в секреты.",
        )

    result = await client.search(
        query=payload.query,
        search_depth=payload.search_depth,
        max_results=payload.max_results,
        include_answer=payload.include_answer,
        include_domains=payload.include_domains,
        exclude_domains=payload.exclude_domains,
    )

    if result.get("success"):
        return {
            "status": "success",
            "inn": payload.inn,
            "answer": result.get("answer", ""),
            "results": result.get("results", []),
            "query": payload.query,
            "cached": result.get("cached", False),
            "integration": result.get("integration"),
        }
    return fail(
        http_request,
        status_code=502,
        message=result.get("error", "Неизвестная ошибка"),
    )
