"""
Utility decorators для приложения.

Включает:
- cache_with_tarantool - кэширование через TarantoolClient
- async_retry - повторные попытки при ошибках
"""

import asyncio
import hashlib
from functools import wraps
from typing import Any, Callable, Optional, TypeVar

from app.utility.logging_client import logger

T = TypeVar("T")


def cache_with_tarantool(
    ttl: int = 3600,
    source: str = "api",
    key_prefix: Optional[str] = None,
):
    """
    Декоратор для кэширования результатов функций через Tarantool.

    Автоматически кэширует результаты асинхронных функций с заданным TTL.
    Поддерживает статистику по источникам данных.

    Args:
        ttl: Time To Live в секундах (default: 3600 = 1 час)
        source: Источник данных для статистики (default: "api")
        key_prefix: Префикс для ключа кэша (default: module.function_name)

    Returns:
        Декорированная функция с кэшированием

    Example:
        @cache_with_tarantool(ttl=7200, source="dadata")
        async def fetch_from_dadata(inn: str) -> Dict[str, Any]:
            # ... API call ...
            return result

        # При вызове:
        # 1) Проверяется кэш (ключ: "dadata:hash(inn)")
        # 2) Если есть - возвращается из кэша
        # 3) Если нет - выполняется функция, результат кэшируется
    """

    def decorator(func: Callable) -> Callable:
        @wraps(func)
        async def wrapper(*args, **kwargs) -> Any:
            # Генерируем ключ кэша
            func_name = func.__name__

            # Префикс: либо указанный, либо source:func_name
            prefix = key_prefix or f"{source}:{func_name}"

            # Создаем уникальный ключ на основе аргументов
            key_parts = [str(arg) for arg in args]
            key_parts.extend(f"{k}={v}" for k, v in sorted(kwargs.items()))
            args_str = ":".join(key_parts) if key_parts else "no_args"

            # Хэшируем для компактности
            args_hash = hashlib.md5(args_str.encode("utf-8"), usedforsecurity=False).hexdigest()[:16]

            cache_key = f"{prefix}:{args_hash}"

            # Получаем Tarantool клиент и cache repository
            from app.storage.tarantool import TarantoolClient

            try:
                client = await TarantoolClient.get_instance()
                cache_repo = client.get_cache_repository()

                # Проверяем кэш
                cached = await cache_repo.get(cache_key)
                if cached is not None:
                    logger.debug(
                        f"Cache HIT: {func_name}({args_str[:50]}...) [key: {cache_key[:30]}]",
                        component="cache_decorator",
                    )
                    return cached

                logger.debug(
                    f"Cache MISS: {func_name}({args_str[:50]}...) [key: {cache_key[:30]}]",
                    component="cache_decorator",
                )

            except Exception as e:
                logger.warning(f"Cache GET error: {e}", component="cache_decorator")
                # Продолжаем без кэша при ошибке

            # Выполняем функцию
            try:
                result = await func(*args, **kwargs)
            except Exception:
                logger.warning(
                    f"Function {func_name} raised exception, not caching",
                    component="cache_decorator",
                )
                raise

            # Кэшируем результат (только если нет ошибки)
            if result is not None:
                # Не кэшируем результаты с явными ошибками
                if isinstance(result, dict) and "error" in result:
                    logger.debug(
                        f"Skip caching error response from {func_name}",
                        component="cache_decorator",
                    )
                    return result

                try:
                    await cache_repo.set_with_ttl(cache_key, result, ttl=ttl, source=source)
                    logger.debug(
                        f"Cache SET: {func_name}, ttl={ttl}s [key: {cache_key[:30]}]",
                        component="cache_decorator",
                    )
                except Exception as e:
                    logger.warning(f"Cache SET failed: {e}", component="cache_decorator")

            return result

        return wrapper

    return decorator


def async_retry(
    max_attempts: int = 3,
    delay: float = 1.0,
    backoff: float = 2.0,
    exceptions: tuple = (Exception,),
):
    """
    Декоратор для повторных попыток выполнения асинхронных функций при ошибках.

    Args:
        max_attempts: Максимальное количество попыток (default: 3)
        delay: Начальная задержка между попытками в секундах (default: 1.0)
        backoff: Множитель для увеличения задержки (default: 2.0)
        exceptions: Кортеж исключений для retry (default: (Exception,))

    Returns:
        Декорированная функция с retry логикой

    Example:
        @async_retry(max_attempts=3, delay=1.0, exceptions=(httpx.TimeoutError,))
        async def fetch_api_data(url: str):
            return await http_client.get(url)
    """

    def decorator(func: Callable) -> Callable:
        @wraps(func)
        async def wrapper(*args, **kwargs) -> Any:
            last_exception = None
            current_delay = delay

            for attempt in range(1, max_attempts + 1):
                try:
                    return await func(*args, **kwargs)

                except exceptions as e:
                    last_exception = e

                    if attempt == max_attempts:
                        logger.error(
                            f"All {max_attempts} attempts failed for {func.__name__}",
                            component="retry_decorator",
                            exc_info=True,
                        )
                        raise

                    logger.warning(
                        f"Attempt {attempt}/{max_attempts} failed for {func.__name__}: {e}. "
                        f"Retrying in {current_delay}s...",
                        component="retry_decorator",
                    )

                    await asyncio.sleep(current_delay)
                    current_delay *= backoff

            # Не должно сюда попасть, но на случай
            if last_exception:
                raise last_exception

            return await func(*args, **kwargs)

        return wrapper

    return decorator


__all__ = [
    "cache_with_tarantool",
    "async_retry",
]
