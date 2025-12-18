import asyncio
from typing import Any, Dict

import xmltodict

from app.config import settings
from app.services.http_client import AsyncHttpClient
from app.storage.tarantool import TarantoolClient
from app.utility.decorators import cache_with_tarantool
from app.utility.helpers import clean_xml_dict
from app.utility.logging_client import logger


async def fetch_from_dadata(inn: str) -> Dict[str, Any]:
    """
    Fetch company data from DaData API.
    
    Args:
        inn: Company INN (10 or 12 digits)
        
    Returns:
        Dict with company data or error
    """
    # Check cache
    cache_key = f"dadata:{inn}"
    client = await TarantoolClient.get_instance()
    cache_repo = client.get_cache_repository()
    
    cached = await cache_repo.get(cache_key)
    if cached:
        logger.debug(f"DaData cache HIT for {inn}", component="dadata")
        return cached

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
            logger.warning(
                f"DaData returned {resp.status_code}: {resp.text}", component="dadata"
            )
            return {"error": f"DaData error: {resp.status_code}"}
        
        data = resp.json()
        suggestions = data.get("suggestions", [])
        if not suggestions:
            return {"error": "No data found in DaData"}
        
        result = {"status": "success", "data": suggestions[0]["data"]}
        
        # Save to cache
        await cache_repo.set_with_ttl(
            cache_key, result, ttl=settings.dadata.cache_ttl or 7200, source="dadata"
        )
        logger.debug(f"DaData cache SET for {inn}", component="dadata")
        
        return result
        
    except Exception as e:
        logger.exception(f"DaData request failed for INN {inn}", component="dadata")
        return {"error": f"DaData request failed: {str(e)}"}


@cache_with_tarantool(ttl=3600, source="infosphere")
async def fetch_from_infosphere(inn: str) -> Dict[str, Any]:
    """
    Fetch company data from InfoSphere API.
    
    Args:
        inn: Company INN
        
    Returns:
        Dict with company data or error
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
        resp = await http_client.request(
            "POST", url, content=xml_body, headers={"Content-Type": "application/xml"}
        )
        if resp.status_code != 200:
            logger.warning(
                f"InfoSphere returned {resp.status_code}", component="infosphere"
            )
            return {"error": f"InfoSphere error: {resp.status_code}"}
        
        raw_data = xmltodict.parse(resp.text)
        cleaned = clean_xml_dict(raw_data.get("Response", {}).get("Source", []))
        return {"status": "success", "data": cleaned}
        
    except Exception as e:
        logger.exception(
            f"InfoSphere request failed for INN {inn}", component="infosphere"
        )
        return {"error": f"InfoSphere request failed: {str(e)}"}


@cache_with_tarantool(ttl=9600, source="casebook")
async def fetch_from_casebook(inn: str) -> Dict[str, Any]:
    """
    Fetch court cases from Casebook API.
    
    Args:
        inn: Company INN
        
    Returns:
        Dict with court cases or error
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
        
    except Exception as e:
        logger.exception(f"Casebook request failed for INN {inn}", component="casebook")
        return {"error": f"Casebook request failed: {str(e)}"}


@cache_with_tarantool(ttl=9600, source="company_info")
async def fetch_company_info(inn: str) -> Dict[str, Any]:
    """
    Fetch all company info from multiple sources.
    
    Aggregates data from DaData, InfoSphere, and Casebook in parallel.
    
    Args:
        inn: Company INN
        
    Returns:
        Dict with aggregated data from all sources
    """
    logger.info(f"Fetching data for INN: {inn}", component="company_info")

    if not inn.isdigit() or len(inn) not in (10, 12):
        logger.warning(f"Invalid INN format: {inn}", component="company_info")
        return {"error": "Invalid INN"}

    # Параллельные запросы
    dadata_task = asyncio.create_task(fetch_from_dadata(inn))
    infosphere_task = asyncio.create_task(fetch_from_infosphere(inn))
    casebook_task = asyncio.create_task(fetch_from_casebook(inn))

    results = await asyncio.gather(
        dadata_task, infosphere_task, casebook_task, return_exceptions=True
    )

    processed_results = {}
    source_names = ["dadata", "infosphere", "casebook"]
    for name, result in zip(source_names, results, strict=False):
        if isinstance(result, Exception):
            logger.error(
                f"Error fetching from {name}: {result}", component="company_info"
            )
            processed_results[name] = {"error": str(result)}
        else:
            processed_results[name] = result

    return {
        "inn": inn,
        "sources": processed_results,
    }
