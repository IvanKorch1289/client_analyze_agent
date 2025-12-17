import hashlib
from functools import wraps
from typing import Any, Callable

from app.utility.logging_client import logger
from app.storage.tarantool import TarantoolClient


def cache_response(ttl: int = 3600):
    def decorator(func: Callable) -> Callable:
        @wraps(func)
        async def wrapper(*args, **kwargs) -> Any:
            cache = await TarantoolClient.get_instance()

            key_parts = [func.__module__, func.__name__]
            key_parts.extend(str(arg) for arg in args)
            key_parts.extend(f"{k}={v}" for k, v in sorted(kwargs.items()))

            raw_key = ":".join(key_parts)
            key = hashlib.md5(
                raw_key.encode("utf-8"), usedforsecurity=False
            ).hexdigest()
            cache_key = f"cache:{key}"

            try:
                cached = await cache.get(cache_key)
                if cached is not None:
                    logger.debug(
                        f"Cache HIT: {raw_key} → {cache_key}", component="cache"
                    )
                    return cached
                logger.debug(f"Cache MISS: {raw_key} → {cache_key}", component="cache")
            except Exception as e:
                logger.warning(
                    f"Cache GET error for {cache_key}: {e}", component="cache"
                )

            try:
                result = await func(*args, **kwargs)
            except Exception:
                logger.warning(
                    f"Function {func.__name__} raised exception, not caching",
                    component="cache",
                )
                raise

            if isinstance(result, (dict, list)):
                if not (isinstance(result, dict) and "error" in result):
                    try:
                        await cache.set(cache_key, result, ttl=ttl)
                        logger.debug(
                            f"Cache SET: {cache_key}, ttl={ttl}", component="cache"
                        )
                    except Exception as e:
                        logger.warning(
                            f"Cache SET failed for {cache_key}: {e}", component="cache"
                        )
                else:
                    logger.debug(
                        f"Skip caching error response: {result}", component="cache"
                    )
            else:
                logger.debug(
                    f"Skip caching non-serializable result: {type(result)}",
                    component="cache",
                )

            return result

        return wrapper

    return decorator
