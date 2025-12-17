import re
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

data_router = APIRouter(
    prefix="/data",
    tags=["Внешние данные"],
    responses={404: {"description": "Не найдено"}},
)


def validate_inn(inn: str) -> bool:
    """Validate Russian INN format (10 or 12 digits)."""
    return bool(re.match(r"^\d{10}$|^\d{12}$", inn))


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
    if not validate_inn(request.inn):
        return {"status": "error", "message": "Неверный формат ИНН (должно быть 10 или 12 цифр)"}
    
    client = PerplexityClient.get_instance()

    if not client.is_configured():
        return {"status": "error", "message": "Perplexity API key не настроен"}

    result = await client.ask(
        question=request.query, search_recency_filter=request.search_recency
    )

    if result.get("success"):
        return {
            "status": "success",
            "inn": request.inn,
            "content": result.get("content", ""),
            "citations": result.get("citations", []),
            "model": result.get("model"),
        }
    return {"status": "error", "message": result.get("error", "Неизвестная ошибка")}


@data_router.post("/search/tavily")
async def tavily_search(request: TavilyRequest):
    """Search via Tavily."""
    if not validate_inn(request.inn):
        return {"status": "error", "message": "Неверный формат ИНН (должно быть 10 или 12 цифр)"}
    
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
        }
    return {"status": "error", "message": result.get("error", "Неизвестная ошибка")}
