from typing import List, Optional

from fastapi import APIRouter
from pydantic import BaseModel

from app.services.perplexity_client import PerplexityClient
from app.services.tavily_client import TavilyClient
from app.storage.tarantool import TarantoolClient

utility_router = APIRouter(
    prefix="/utility",
    tags=["Утилиты"],
    responses={404: {"description": "Не найдено"}},
)


class PerplexityRequest(BaseModel):
    query: str
    search_recency: str = "month"


class TavilyRequest(BaseModel):
    query: str
    search_depth: str = "basic"
    max_results: int = 5
    include_answer: bool = True
    include_domains: Optional[List[str]] = None
    exclude_domains: Optional[List[str]] = None


@utility_router.get("/validate_cache")
async def validate_cache(confirm: bool):
    client = await TarantoolClient.get_instance()
    await client.invalidate_all_keys(confirm)
    return {
        "status": "success",
        "message": "Кэш инвалидирован" if confirm else "Операция отменена",
    }


@utility_router.post("/perplexity/search")
async def perplexity_search(request: PerplexityRequest):
    """Поиск информации через Perplexity AI."""
    client = PerplexityClient.get_instance()
    
    if not client.is_configured():
        return {
            "status": "error",
            "message": "Perplexity API key не настроен"
        }
    
    result = await client.ask(
        question=request.query,
        search_recency_filter=request.search_recency
    )
    
    if result.get("success"):
        return {
            "status": "success",
            "content": result.get("content", ""),
            "citations": result.get("citations", []),
            "model": result.get("model")
        }
    return {
        "status": "error",
        "message": result.get("error", "Неизвестная ошибка")
    }


@utility_router.get("/perplexity/status")
async def perplexity_status():
    """Проверка статуса Perplexity API."""
    client = PerplexityClient.get_instance()
    return {
        "configured": client.is_configured(),
        "message": "API key настроен" if client.is_configured() else "API key не настроен"
    }


@utility_router.post("/tavily/search")
async def tavily_search(request: TavilyRequest):
    """Поиск информации через Tavily API."""
    client = TavilyClient.get_instance()
    
    if not client.is_configured():
        return {
            "status": "error",
            "message": "Tavily API key не настроен. Добавьте TAVILY_TOKEN в секреты."
        }
    
    result = await client.search(
        query=request.query,
        search_depth=request.search_depth,
        max_results=request.max_results,
        include_answer=request.include_answer,
        include_domains=request.include_domains,
        exclude_domains=request.exclude_domains
    )
    
    if result.get("success"):
        return {
            "status": "success",
            "answer": result.get("answer", ""),
            "results": result.get("results", []),
            "query": request.query
        }
    return {
        "status": "error",
        "message": result.get("error", "Неизвестная ошибка")
    }


@utility_router.get("/tavily/status")
async def tavily_status():
    """Проверка статуса Tavily API."""
    client = TavilyClient.get_instance()
    return {
        "configured": client.is_configured(),
        "message": "API key настроен" if client.is_configured() else "API key не настроен"
    }
