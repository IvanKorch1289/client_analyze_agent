"""
Favorites API - управление избранными компаниями пользователя.

Sprint 2+: Quick access to frequently analyzed companies.
"""

from datetime import datetime
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException, Query, Request
from pydantic import BaseModel, Field

from app.api.rate_limit import limiter_for_client_ip
from app.config.constants import RATE_LIMIT_SEARCH_PER_MINUTE
from app.storage.tarantool import TarantoolClient
from app.utility.logging_client import logger

favorites_router = APIRouter(
    prefix="/favorites",
    tags=["Избранное"],
    responses={404: {"description": "Не найдено"}},
)

limiter = limiter_for_client_ip()


class FavoriteCompany(BaseModel):
    """Избранная компания."""

    company_name: str = Field(..., description="Название компании")
    inn: str = Field(..., description="ИНН компании (10 или 12 цифр)")
    notes: Optional[str] = Field(None, description="Заметки пользователя о компании")


class FavoriteResponse(BaseModel):
    """Ответ с информацией об избранной компании."""

    favorite_id: str
    company_name: str
    inn: str
    notes: Optional[str]
    added_at: str
    last_analyzed_at: Optional[str]


@favorites_router.get("", response_model=List[FavoriteResponse])
@limiter.limit(f"{RATE_LIMIT_SEARCH_PER_MINUTE}/minute")
async def list_favorites(
    request: Request,
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
) -> List[FavoriteResponse]:
    """
    Получить список избранных компаний.

    Returns:
        Список избранных компаний с сортировкой по дате добавления (новые первые)
    """
    try:
        client = await TarantoolClient.get_instance()
        cache_repo = client.get_cache_repository()

        # Получаем избранные из кэша (используем namespace 'favorites')
        favorites_raw = await cache_repo.list_by_prefix(prefix="favorite:", limit=limit, offset=offset)

        favorites = []
        for fav_data in favorites_raw:
            try:
                favorites.append(
                    FavoriteResponse(
                        favorite_id=fav_data.get("key", "").replace("favorite:", ""),
                        company_name=fav_data.get("value", {}).get("company_name", ""),
                        inn=fav_data.get("value", {}).get("inn", ""),
                        notes=fav_data.get("value", {}).get("notes"),
                        added_at=fav_data.get("value", {}).get("added_at", ""),
                        last_analyzed_at=fav_data.get("value", {}).get("last_analyzed_at"),
                    )
                )
            except Exception as e:
                logger.warning(f"Failed to parse favorite: {e}")
                continue

        return favorites

    except Exception as e:
        logger.error(f"List favorites error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to list favorites: {str(e)}") from e


@favorites_router.post("", response_model=Dict[str, Any])
@limiter.limit(f"{RATE_LIMIT_SEARCH_PER_MINUTE}/minute")
async def add_favorite(request: Request, favorite: FavoriteCompany) -> Dict[str, Any]:
    """
    Добавить компанию в избранное.

    Args:
        favorite: Данные компании для добавления

    Returns:
        ID созданной записи и статус
    """
    try:
        client = await TarantoolClient.get_instance()
        cache_repo = client.get_cache_repository()

        # Генерируем ID на основе ИНН (чтобы не было дубликатов)
        favorite_id = f"favorite:{favorite.inn}"

        # Проверяем существование
        existing = await cache_repo.get(favorite_id)
        if existing:
            raise HTTPException(
                status_code=409,
                detail=f"Company with INN {favorite.inn} is already in favorites",
            )

        # Сохраняем в кэш
        favorite_data = {
            "company_name": favorite.company_name,
            "inn": favorite.inn,
            "notes": favorite.notes,
            "added_at": datetime.now().isoformat(),
            "last_analyzed_at": None,
        }

        await cache_repo.set(
            key=favorite_id,
            value=favorite_data,
            ttl=0,  # Бессрочное хранение
        )

        logger.structured(
            "info",
            "favorite_added",
            component="favorites_api",
            inn=favorite.inn,
            company_name=favorite.company_name,
        )

        return {
            "status": "success",
            "favorite_id": favorite.inn,
            "message": f"Company {favorite.company_name} added to favorites",
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Add favorite error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to add favorite: {str(e)}") from e


@favorites_router.delete("/{inn}")
@limiter.limit(f"{RATE_LIMIT_SEARCH_PER_MINUTE}/minute")
async def remove_favorite(request: Request, inn: str) -> Dict[str, Any]:
    """
    Удалить компанию из избранного.

    Args:
        inn: ИНН компании для удаления

    Returns:
        Статус удаления
    """
    try:
        client = await TarantoolClient.get_instance()
        cache_repo = client.get_cache_repository()

        favorite_id = f"favorite:{inn}"

        # Проверяем существование
        existing = await cache_repo.get(favorite_id)
        if not existing:
            raise HTTPException(status_code=404, detail=f"Company with INN {inn} not found in favorites")

        # Удаляем
        await cache_repo.delete(favorite_id)

        logger.structured(
            "info",
            "favorite_removed",
            component="favorites_api",
            inn=inn,
        )

        return {
            "status": "success",
            "message": f"Company with INN {inn} removed from favorites",
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Remove favorite error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to remove favorite: {str(e)}") from e


@favorites_router.patch("/{inn}")
@limiter.limit(f"{RATE_LIMIT_SEARCH_PER_MINUTE}/minute")
async def update_favorite(
    request: Request,
    inn: str,
    notes: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Обновить заметки для избранной компании.

    Args:
        inn: ИНН компании
        notes: Новые заметки (или None для удаления)

    Returns:
        Обновлённые данные
    """
    try:
        client = await TarantoolClient.get_instance()
        cache_repo = client.get_cache_repository()

        favorite_id = f"favorite:{inn}"

        # Получаем существующую запись
        existing = await cache_repo.get(favorite_id)
        if not existing:
            raise HTTPException(status_code=404, detail=f"Company with INN {inn} not found in favorites")

        # Обновляем notes
        existing["notes"] = notes

        # Сохраняем обратно
        await cache_repo.set(
            key=favorite_id,
            value=existing,
            ttl=0,  # Бессрочное хранение
        )

        logger.structured(
            "info",
            "favorite_updated",
            component="favorites_api",
            inn=inn,
        )

        return {
            "status": "success",
            "favorite": existing,
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Update favorite error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to update favorite: {str(e)}") from e


@favorites_router.post("/{inn}/mark-analyzed")
@limiter.limit(f"{RATE_LIMIT_SEARCH_PER_MINUTE}/minute")
async def mark_favorite_analyzed(request: Request, inn: str) -> Dict[str, Any]:
    """
    Отметить что компания была проанализирована (обновить last_analyzed_at).

    Автоматически вызывается после успешного анализа избранной компании.

    Args:
        inn: ИНН компании

    Returns:
        Статус обновления
    """
    try:
        client = await TarantoolClient.get_instance()
        cache_repo = client.get_cache_repository()

        favorite_id = f"favorite:{inn}"

        # Получаем существующую запись
        existing = await cache_repo.get(favorite_id)
        if not existing:
            # Не ошибка - просто компания не в избранном
            return {"status": "skipped", "message": "Company not in favorites"}

        # Обновляем last_analyzed_at
        existing["last_analyzed_at"] = datetime.now().isoformat()

        # Сохраняем обратно
        await cache_repo.set(
            key=favorite_id,
            value=existing,
            ttl=0,
        )

        return {"status": "success", "last_analyzed_at": existing["last_analyzed_at"]}

    except Exception as e:
        logger.error(f"Mark favorite analyzed error: {e}", exc_info=True)
        # Не падаем - это не критичная операция
        return {"status": "error", "message": str(e)}


__all__ = ["favorites_router"]
