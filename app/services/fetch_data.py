import asyncio
from typing import Any, Dict

import httpx
import xmltodict

from app.config import settings
from app.services.http_client import AsyncHttpClient
from app.shared.exceptions import APIError
from app.shared.decorators import cache_with_tarantool
from app.shared.toolkit.helpers import clean_xml_dict
from app.shared.toolkit.logging import logger


@cache_with_tarantool(ttl=86400, source="dadata", key_prefix="dadata:inn")
async def fetch_from_dadata(inn: str) -> Dict[str, Any]:
    """
    Получение данных компании из DaData API с агрессивным кэшированием (24ч).

    Кэширование безопасно: PII маскируется в llm_manager перед отправкой в LLM,
    кэш хранит сырые данные для внутреннего использования.

    Args:
        inn: ИНН компании (10 или 12 цифр)

    Returns:
        Dict с данными компании или ошибкой
    """
    url = settings.dadata.api_url
    headers = {
        "Authorization": f"Token {settings.dadata.api_key}",
        "Content-Type": "application/json",
    }
    payload = {"query": inn}

    # Fetch from API
    http_client = await AsyncHttpClient.get_instance()

    try:
        resp = await http_client.request("POST", url, json=payload, headers=headers)
        if resp.status_code != 200:
            logger.warning(f"DaData returned {resp.status_code}: {resp.text}", component="dadata")
            return {"error": f"DaData error: {resp.status_code}"}

        data = resp.json()
        suggestions = data.get("suggestions", [])
        if not suggestions:
            return {"error": "No data found in DaData"}

        result = {"status": "success", "data": suggestions[0]["data"]}
        return result

    except httpx.TimeoutException as e:
        logger.warning(f"DaData request timeout for INN {inn}", component="dadata")
        return {"error": f"DaData timeout: {str(e)}"}
    except httpx.HTTPStatusError as e:
        logger.warning(
            f"DaData HTTP error for INN {inn}: {e.response.status_code}",
            component="dadata",
        )
        return {"error": f"DaData HTTP error: {e.response.status_code}"}
    except (httpx.RequestError, APIError) as e:
        logger.exception(f"DaData request failed for INN {inn}", component="dadata")
        return {"error": f"DaData request failed: {str(e)}"}


@cache_with_tarantool(ttl=86400, source="infosphere")
async def fetch_from_infosphere(inn: str) -> Dict[str, Any]:
    """
    Получение данных компании из InfoSphere API с агрессивным кэшированием (24ч).

    InfoSphere проверяет ФССП, банкротство, ЦБ РФ, ЕГРЮЛ, ФНС, ФСИН и др.
    Кэширование на 24 часа дает 20x ускорение для повторных анализов.

    БЕЗОПАСНОСТЬ: Кэш содержит PII, но это внутреннее хранилище.
    Маскирование происходит в llm_manager перед отправкой в external LLM.

    Args:
        inn: ИНН компании

    Returns:
        Dict с данными компании или ошибкой
    """
    http_client = await AsyncHttpClient.get_instance()
    url = settings.infosphere.api_url
    sources = settings.infosphere.sources or "fssp,bankrot,cbr,egrul,fns,fsin,fmsdb,fms,gosuslugi,mvd,pfr,terrorist"
    xml_body = f"""<?xml version="1.0" encoding="UTF-8"?>
    <Request>
        <UserID>{settings.infosphere.login}</UserID>
        <Password>{settings.infosphere.password}</Password>
        <requestType>check</requestType>
        <sources>{sources}</sources>
        <timeout>300</timeout>
        <recursive>0</recursive>
        <async>0</async>
        <PersonReq>
            <inn>{inn}</inn>
        </PersonReq>
    </Request>"""

    try:
        resp = await http_client.request("POST", url, content=xml_body, headers={"Content-Type": "application/xml"})
        if resp.status_code != 200:
            logger.warning(f"InfoSphere returned {resp.status_code}", component="infosphere")
            return {"error": f"InfoSphere error: {resp.status_code}"}

        raw_data = xmltodict.parse(resp.text)
        cleaned = clean_xml_dict(raw_data.get("Response", {}).get("Source", []))
        return {"status": "success", "data": cleaned}

    except httpx.TimeoutException as e:
        logger.warning(f"InfoSphere request timeout for INN {inn}", component="infosphere")
        return {"error": f"InfoSphere timeout: {str(e)}"}
    except httpx.HTTPStatusError as e:
        logger.warning(
            f"InfoSphere HTTP error for INN {inn}: {e.response.status_code}",
            component="infosphere",
        )
        return {"error": f"InfoSphere HTTP error: {e.response.status_code}"}
    except (httpx.RequestError, APIError) as e:
        logger.exception(f"InfoSphere request failed for INN {inn}", component="infosphere")
        return {"error": f"InfoSphere request failed: {str(e)}"}


@cache_with_tarantool(ttl=86400, source="casebook")
async def fetch_from_casebook(inn: str) -> Dict[str, Any]:
    """
    Получение судебных дел из Casebook API с агрессивным кэшированием (24ч).

    Casebook может возвращать сотни дел, что занимает 5-6 минут при пагинации.
    Кэширование на 24 часа критично для производительности.

    БЕЗОПАСНОСТЬ: Судебные дела содержат PII (имена, адреса).
    Маскирование происходит в llm_manager перед отправкой в external LLM.

    Args:
        inn: ИНН компании

    Returns:
        Dict с судебными делами или ошибкой
    """
    http_client = await AsyncHttpClient.get_instance()
    url = settings.casebook.arbitr_url
    params = {
        "sideInn": inn,
        "size": settings.casebook.page_size or 100,
        "apikey": settings.casebook.api_key,
        "page": 1,
    }

    try:
        # Используем встроенную пагинацию
        all_cases = await http_client.fetch_all_pages(url=url, params=params)
        return {"status": "success", "data": all_cases}

    except httpx.TimeoutException as e:
        logger.warning(f"Casebook request timeout for INN {inn}", component="casebook")
        return {"error": f"Casebook timeout: {str(e)}"}
    except httpx.HTTPStatusError as e:
        logger.warning(
            f"Casebook HTTP error for INN {inn}: {e.response.status_code}",
            component="casebook",
        )
        return {"error": f"Casebook HTTP error: {e.response.status_code}"}
    except (httpx.RequestError, APIError) as e:
        logger.exception(f"Casebook request failed for INN {inn}", component="casebook")
        return {"error": f"Casebook request failed: {str(e)}"}


@cache_with_tarantool(ttl=86400, source="company_info")
async def fetch_company_info(inn: str) -> Dict[str, Any]:
    """
    Получение полной информации о компании из всех источников с кэшированием (24ч).

    Агрегирует данные из DaData, InfoSphere и Casebook параллельно.
    Каждый источник имеет собственный кэш, этот кэш для агрегированного результата.

    ПРОИЗВОДИТЕЛЬНОСТЬ:
    - Первый запрос: 6-8 минут (InfoSphere + Casebook медленные)
    - Повторный запрос: <1 секунды (все из кэша)
    - Ускорение: 20-100x

    Args:
        inn: ИНН компании

    Returns:
        Dict с агрегированными данными из всех источников
    """
    logger.info(f"Fetching data for INN: {inn}", component="company_info")

    if not inn.isdigit() or len(inn) not in (10, 12):
        logger.warning(f"Invalid INN format: {inn}", component="company_info")
        return {"error": "Invalid INN"}

    # Параллельные запросы
    dadata_task = asyncio.create_task(fetch_from_dadata(inn))
    infosphere_task = asyncio.create_task(fetch_from_infosphere(inn))
    casebook_task = asyncio.create_task(fetch_from_casebook(inn))

    results = await asyncio.gather(dadata_task, infosphere_task, casebook_task, return_exceptions=True)

    processed_results = {}
    source_names = ["dadata", "infosphere", "casebook"]
    for name, result in zip(source_names, results, strict=False):
        if isinstance(result, Exception):
            logger.error(f"Error fetching from {name}: {result}", component="company_info")
            processed_results[name] = {"error": str(result)}
        else:
            processed_results[name] = result

    return {
        "inn": inn,
        "sources": processed_results,
    }
