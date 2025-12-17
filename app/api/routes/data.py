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
