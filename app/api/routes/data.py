from typing import List, Optional

from fastapi import APIRouter
from pydantic import BaseModel

from app.services.fetch_data import (
    fetch_company_info,
    fetch_from_casebook,
    fetch_from_dadata,
    fetch_from_infosphere,
)
from app.services.perplexity_client import PerplexityClient
from app.services.tavily_client import TavilyClient
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
async def perplexity_search(request: PerplexityRequest):
    """Search via Perplexity."""
    is_valid, error_msg = validate_inn(request.inn)
    if not is_valid:
        return {"status": "error", "message": error_msg}
    
    client = PerplexityClient.get_instance()

    if not client.is_configured():
        return {"status": "error", "message": "Perplexity API key не настроен"}

    # Клиент Perplexity работает через LangChain (OpenAI-compatible).
    result = await client.ask(question=request.query, search_recency_filter=request.search_recency)

    if result.get("success"):
        return {
            "status": "success",
            "inn": request.inn,
            "content": result.get("content", ""),
            "citations": result.get("citations", []),
            "model": result.get("model"),
            "integration": result.get("integration"),
        }
    return {"status": "error", "message": result.get("error", "Неизвестная ошибка")}


@data_router.post("/search/tavily")
async def tavily_search(request: TavilyRequest):
    """Search via Tavily."""
    is_valid, error_msg = validate_inn(request.inn)
    if not is_valid:
        return {"status": "error", "message": error_msg}
    
    client = TavilyClient.get_instance()

    if not client.is_configured():
        return {
            "status": "error",
            "message": "Tavily API key не настроен. Добавьте TAVILY_TOKEN в секреты.",
        }

    result = await client.search(
        query=request.query,
        search_depth=request.search_depth,
        max_results=request.max_results,
        include_answer=request.include_answer,
        include_domains=request.include_domains,
        exclude_domains=request.exclude_domains,
    )

    if result.get("success"):
        return {
            "status": "success",
            "inn": request.inn,
            "answer": result.get("answer", ""),
            "results": result.get("results", []),
            "query": request.query,
            "cached": result.get("cached", False),
            "integration": result.get("integration"),
        }
    return {"status": "error", "message": result.get("error", "Неизвестная ошибка")}
