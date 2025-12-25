from fastapi import APIRouter, Request

from app.api.compat import fail
from app.schemas import (
    PerplexityRequest,
    PerplexitySearchResponse,
    TavilyRequest,
    TavilySearchResponse,
)
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


@data_router.get("/client/infosphere/{inn}")
async def get_infosphere_data(inn: str):
    """
    Получить данные компании из Инфосферы.

    Инфосфера предоставляет:
    - Финансовую аналитику
    - Кредитные рейтинги
    - Бизнес-показатели

    Args:
        inn: ИНН компании (10 цифр для юр. лиц, 12 для ИП)

    Returns:
        Данные из Инфосферы или ошибку, если сервис недоступен
    """
    return await fetch_from_infosphere(inn)


@data_router.get("/client/dadata/{inn}")
async def get_dadata_data(inn: str):
    """
    Получить данные компании из DaData.

    DaData предоставляет:
    - Регистрационные данные (ОГРН, дата регистрации)
    - Юридический и фактический адреса
    - Информацию о руководителях и учредителях
    - Коды ОКВЭД
    - Статус организации

    Args:
        inn: ИНН компании (10 цифр для юр. лиц, 12 для ИП)

    Returns:
        Данные из DaData или ошибку, если сервис недоступен
    """
    return await fetch_from_dadata(inn)


@data_router.get("/client/casebook/{inn}")
async def get_casebook_data(inn: str):
    """
    Получить судебные дела компании из Casebook.

    Casebook предоставляет:
    - Арбитражные дела (истец/ответчик)
    - Суммы исков
    - Статусы дел
    - Категории споров

    Args:
        inn: ИНН компании (10 цифр для юр. лиц, 12 для ИП)

    Returns:
        Список судебных дел или ошибку, если сервис недоступен
    """
    return await fetch_from_casebook(inn)


@data_router.get("/client/info/{inn}")
async def get_all_client_data(inn: str):
    """
    Получить данные компании из всех источников одновременно.

    Выполняет параллельные запросы к:
    - DaData (регистрационные данные)
    - Casebook (судебные дела)
    - Инфосфера (финансовая аналитика)

    Args:
        inn: ИНН компании (10 цифр для юр. лиц, 12 для ИП)

    Returns:
        Агрегированные данные из всех доступных источников
    """
    return await fetch_company_info(inn)


@data_router.post("/search/perplexity")
async def perplexity_search(http_request: Request, payload: PerplexityRequest) -> PerplexitySearchResponse:
    """
    Веб-поиск через Perplexity AI.

    Perplexity AI предоставляет:
    - Актуальную информацию из интернета
    - AI-суммаризацию результатов
    - Ссылки на источники (citations)

    **Параметры запроса:**
    - `inn`: ИНН компании для контекста
    - `query`: Поисковый запрос
    - `search_recency`: Актуальность результатов (day/week/month)

    **Пример запроса:**
    ```json
    {
        "inn": "7707083893",
        "query": "судебные дела банкротство",
        "search_recency": "month"
    }
    ```

    Returns:
        Результат поиска с AI-ответом и ссылками на источники
    """
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
    result = await client.ask(question=payload.query, search_recency_filter=payload.search_recency)

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
    """
    Веб-поиск через Tavily.

    Tavily предоставляет:
    - Расширенный поиск по веб-страницам
    - Настраиваемую глубину поиска
    - Опциональную AI-суммаризацию

    **Параметры запроса:**
    - `inn`: ИНН компании для контекста
    - `query`: Поисковый запрос
    - `search_depth`: Глубина поиска (basic/advanced)
    - `max_results`: Максимальное количество результатов (1-10)
    - `include_answer`: Включить AI-ответ (true/false)
    - `include_domains`: Список доменов для включения
    - `exclude_domains`: Список доменов для исключения

    **Пример запроса:**
    ```json
    {
        "inn": "7707083893",
        "query": "судебные дела",
        "search_depth": "advanced",
        "max_results": 10,
        "include_answer": true
    }
    ```

    Returns:
        Список релевантных страниц со сниппетами и опциональным AI-ответом
    """
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
