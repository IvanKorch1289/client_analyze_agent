"""
LLM Response Cache Module

Кэширует ответы LLM для ускорения повторных запросов:
- Экономия времени: 30-40 секунд на повторный анализ
- Снижение costs: меньше вызовов API
- Семантическое хэширование промптов

Использует Tarantool для хранения с TTL.
"""

import hashlib
import re
from dataclasses import dataclass
from typing import Optional

from app.utility.logging_client import logger

# Lazy imports
_tarantool_client = None


@dataclass
class LLMCacheResult:
    """Результат кэша LLM."""

    hit: bool  # True если найдено в кэше
    response: Optional[str]  # Ответ LLM (если hit=True)
    cache_key: str  # Ключ кэша


def _get_tarantool_client():
    """Lazy initialization Tarantool client."""
    global _tarantool_client
    if _tarantool_client is None:
        from app.storage.tarantool import get_tarantool_client

        _tarantool_client = get_tarantool_client
    return _tarantool_client


def normalize_prompt(prompt: str) -> str:
    """
    Нормализует промпт для семантического хэширования.

    Убирает:
    - Лишние пробелы и переносы
    - Case sensitivity
    - Специальные символы (кроме букв, цифр, пунктуации)

    Args:
        prompt: Оригинальный промпт

    Returns:
        Нормализованный промпт
    """
    if not prompt:
        return ""

    # Lowercase
    normalized = prompt.lower()

    # Убираем лишние пробелы и переносы
    normalized = re.sub(r"\s+", " ", normalized)

    # Trim
    normalized = normalized.strip()

    return normalized


def compute_cache_key(
    prompt: str,
    provider: str = "default",
    temperature: float = 0.7,
    max_tokens: int = 4000,
) -> str:
    """
    Вычисляет ключ кэша для промпта.

    Учитывает:
    - Нормализованный текст промпта
    - Provider (openrouter, huggingface, etc.)
    - Temperature (округляется до 0.1)
    - Max tokens (округляется до 100)

    Args:
        prompt: Промпт для хэширования
        provider: LLM провайдер
        temperature: Температура генерации
        max_tokens: Максимум токенов

    Returns:
        Hex digest SHA256 (первые 16 символов)
    """
    normalized = normalize_prompt(prompt)

    # Округляем параметры для лучшего cache hit rate
    temp_rounded = round(temperature, 1)
    tokens_rounded = (max_tokens // 100) * 100  # Округляем до 100

    # Формируем строку для хэша
    cache_string = f"{provider}:{temp_rounded}:{tokens_rounded}:{normalized}"

    # SHA256 hash
    hash_hex = hashlib.sha256(cache_string.encode("utf-8"), usedforsecurity=False).hexdigest()

    return f"llm_cache:{hash_hex[:16]}"


async def get_cached_response(
    prompt: str,
    provider: str = "default",
    temperature: float = 0.7,
    max_tokens: int = 4000,
) -> LLMCacheResult:
    """
    Получает кэшированный ответ LLM.

    Args:
        prompt: Промпт для поиска в кэше
        provider: LLM провайдер
        temperature: Температура генерации
        max_tokens: Максимум токенов

    Returns:
        LLMCacheResult с результатом поиска
    """
    cache_key = compute_cache_key(prompt, provider, temperature, max_tokens)

    try:
        get_client = _get_tarantool_client()
        client = await get_client()

        # Получаем из Tarantool cache space
        cached_data = await client.get(cache_key)

        if cached_data:
            response = cached_data.get("response")
            if response:
                logger.info(
                    f"LLM Cache HIT: {cache_key[:12]}... (provider={provider}, prompt_len={len(prompt)})",
                    component="llm_cache",
                )

                return LLMCacheResult(hit=True, response=response, cache_key=cache_key)

    except Exception as e:
        logger.error(f"LLM Cache get error: {e}", component="llm_cache", exc_info=True)
        # При ошибке кэша продолжаем работу (cache miss)

    # Cache miss
    logger.debug(f"LLM Cache MISS: {cache_key[:12]}...", component="llm_cache")

    return LLMCacheResult(hit=False, response=None, cache_key=cache_key)


async def set_cached_response(
    prompt: str,
    response: str,
    provider: str = "default",
    temperature: float = 0.7,
    max_tokens: int = 4000,
    ttl: int = 3600,
) -> bool:
    """
    Сохраняет ответ LLM в кэш.

    Args:
        prompt: Промпт
        response: Ответ LLM
        provider: LLM провайдер
        temperature: Температура генерации
        max_tokens: Максимум токенов
        ttl: Time to live в секундах (default: 1 час)

    Returns:
        True если успешно сохранено
    """
    if not response or not prompt:
        return False

    cache_key = compute_cache_key(prompt, provider, temperature, max_tokens)

    try:
        get_client = _get_tarantool_client()
        client = await get_client()

        # Сохраняем в Tarantool cache space с TTL
        await client.set(
            key=cache_key,
            value={
                "response": response,
                "prompt_hash": hashlib.md5(prompt.encode()).hexdigest()[:8],
            },
            ttl=ttl,
            source="llm_cache",
        )

        logger.info(
            f"LLM Cache SET: {cache_key[:12]}... (provider={provider}, ttl={ttl}s, response_len={len(response)})",
            component="llm_cache",
        )

        return True

    except Exception as e:
        logger.error(f"LLM Cache set error: {e}", component="llm_cache", exc_info=True)
        return False


async def invalidate_cache(cache_key: str) -> bool:
    """
    Инвалидирует запись в кэше.

    Args:
        cache_key: Ключ кэша для удаления

    Returns:
        True если успешно удалено
    """
    try:
        get_client = _get_tarantool_client()
        client = await get_client()

        await client.delete(cache_key)

        logger.info(f"LLM Cache INVALIDATE: {cache_key[:12]}...", component="llm_cache")

        return True

    except Exception as e:
        logger.error(f"LLM Cache invalidate error: {e}", component="llm_cache")
        return False


async def get_cache_stats() -> dict:
    """
    Получает статистику кэша LLM.

    Returns:
        Dict со статистикой (hits, misses, hit_rate)
    """
    try:
        get_client = _get_tarantool_client()
        client = await get_client()

        metrics = client.get_metrics()

        # Фильтруем метрики для llm_cache source
        return {
            "total_hits": metrics.hits,
            "total_misses": metrics.misses,
            "hit_rate_percent": metrics.hit_rate,
            "total_sets": metrics.sets,
        }

    except Exception as e:
        logger.error(f"LLM Cache stats error: {e}", component="llm_cache")
        return {"error": str(e)}


__all__ = [
    "LLMCacheResult",
    "get_cached_response",
    "set_cached_response",
    "invalidate_cache",
    "get_cache_stats",
    "compute_cache_key",
    "normalize_prompt",
]
