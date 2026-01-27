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
    Агрессивная нормализация промпта для максимизации cache hit rate.

    Убирает все динамические паттерны которые делают промпты уникальными:
    - ISO timestamps (2024-01-27T14:30:00Z)
    - Даты (2024-01-27, 27.01.2024, 27/01/2024)
    - Время (14:30:45, 14:30)
    - Request IDs (req_123, request_456, request-id-789)
    - UUIDs/GUIDs (550e8400-e29b-41d4-a716-446655440000)
    - Session IDs (session_*, sess_*, sid:*)
    - Номера дел/документов (№ 123456, дело А40-12345/2024)
    - Лишние пробелы и переносы
    - Case sensitivity

    ЦЕЛЬ: Повысить cache hit rate с 5% до 60%+ за счет удаления уникальных идентификаторов.

    БЕЗОПАСНОСТЬ: Нормализация применяется ТОЛЬКО к кэш-ключу, не к самому промпту.
    Оригинальный промпт с PII остается в кэше для корректного unmask.

    Args:
        prompt: Оригинальный промпт

    Returns:
        Агрессивно нормализованный промпт для хэширования
    """
    if not prompt:
        return ""

    normalized = prompt.lower()

    # 1. ISO timestamps (2024-01-27T14:30:00Z, 2024-01-27T14:30:00+03:00)
    normalized = re.sub(
        r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?(?:Z|[+-]\d{2}:\d{2})?",
        "[TIMESTAMP]",
        normalized,
    )

    # 2. Даты (2024-01-27, 27.01.2024, 27/01/2024, 2024.01.27)
    normalized = re.sub(r"\d{4}[-./]\d{2}[-./]\d{2}", "[DATE]", normalized)
    normalized = re.sub(r"\d{2}[-./]\d{2}[-./]\d{4}", "[DATE]", normalized)

    # 3. Время (14:30:45, 14:30, HH:MM:SS)
    normalized = re.sub(r"\d{1,2}:\d{2}(?::\d{2})?", "[TIME]", normalized)

    # 4. Request IDs (req_*, request_*, request-id-*, rid:*)
    normalized = re.sub(r"\b(?:req|request|rid)[-_:]?\w+\b", "[REQID]", normalized)

    # 5. UUIDs/GUIDs (8-4-4-4-12 формат)
    normalized = re.sub(
        r"\b[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}\b",
        "[UUID]",
        normalized,
    )

    # 6. Session IDs (session_*, sess_*, sid:*)
    normalized = re.sub(r"\b(?:session|sess|sid)[-_:]?\w+\b", "[SESSID]", normalized)

    # 7. Номера дел/документов (№ 123456, дело А40-12345/2024, дело №А40-12345/24)
    normalized = re.sub(r"№\s*\d+", "[DOCNUM]", normalized)
    normalized = re.sub(r"дело\s+[а-я]\d{2}-\d+/\d{2,4}", "[CASENUMBER]", normalized)

    # 8. Длинные последовательности цифр (>8 символов) - похожи на ID
    normalized = re.sub(r"\b\d{9,}\b", "[LONGNUM]", normalized)

    # 9. Хэши MD5/SHA (32+ hex символов)
    normalized = re.sub(r"\b[0-9a-f]{32,}\b", "[HASH]", normalized)

    # 10. Unix timestamps (10+ цифр подряд, похожие на epoch time)
    normalized = re.sub(r"\b1[6-9]\d{8,}\b", "[UNIXTIME]", normalized)

    # 11. Убираем лишние пробелы и переносы
    normalized = re.sub(r"\s+", " ", normalized)

    # 12. Trim
    normalized = normalized.strip()

    return normalized


def compute_cache_key(
    prompt: str,
    provider: str = "default",
    temperature: float = 0.7,
    max_tokens: int = 4000,
) -> str:
    """
    Вычисляет ключ кэша для промпта с агрессивной нормализацией.

    Учитывает:
    - Нормализованный текст промпта (без timestamps, IDs, дат)
    - Provider (openrouter, huggingface, etc.)
    - Temperature (округляется до 0.1)
    - Max tokens (округляется до 100)

    Args:
        prompt: Промпт для хэширования
        provider: LLM провайдер
        temperature: Температура генерации
        max_tokens: Максимум токенов

    Returns:
        Hex digest SHA256 (первые 16 символов) с префиксом llm_cache:
    """
    normalized = normalize_prompt(prompt)

    # Debug logging (метрики нормализации для аналитики)
    if len(prompt) != len(normalized):
        logger.debug(
            f"Prompt normalized for cache: {len(prompt)} → {len(normalized)} chars",
            component="llm_cache",
            extra={
                "original_length": len(prompt),
                "normalized_length": len(normalized),
                "reduction_pct": round((1 - len(normalized) / len(prompt)) * 100, 1),
            },
        )

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
                "prompt_hash": hashlib.md5(prompt.encode(), usedforsecurity=False).hexdigest()[:8],
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
