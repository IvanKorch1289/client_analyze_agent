"""
General helper utilities.

Combined from:
- app/shared/utils/helpers.py (chunk_text, retry_async, safe_dict_get)
- app/utility/helpers.py (clean_xml_dict, validate_inn, format_inn, get_client_ip)
"""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING, Any, Awaitable, Callable, Dict, List, Optional, Tuple, TypeVar

from app.shared.logger import get_logger

if TYPE_CHECKING:
    from starlette.requests import Request

logger = get_logger(__name__)

T = TypeVar("T")


def safe_dict_get(data: Dict[str, Any], *keys: str, default: Any = None) -> Any:
    """
    Safely get nested value from dictionary.

    Args:
        data: Dictionary
        *keys: Sequence of keys
        default: Default value if not found

    Returns:
        Value or default

    Examples:
        >>> safe_dict_get({"a": {"b": {"c": 42}}}, "a", "b", "c")
        42

        >>> safe_dict_get({"a": {"b": {}}}, "a", "b", "c", default="N/A")
        "N/A"
    """
    result: Any = data
    for key in keys:
        if not isinstance(result, dict):
            return default
        result = result.get(key)
        if result is None:
            return default
    return result


def chunk_text(text: str, chunk_size: int = 1000, overlap: int = 0) -> List[str]:
    """
    Split text into chunks.

    Args:
        text: Text to split
        chunk_size: Maximum chunk size
        overlap: Number of characters to overlap between chunks

    Returns:
        List of text chunks

    Examples:
        >>> chunks = chunk_text("A" * 2500, chunk_size=1000, overlap=100)
        >>> len(chunks)
        3
    """
    if not text:
        return []

    if len(text) <= chunk_size:
        return [text]

    chunks = []
    start = 0

    while start < len(text):
        end = start + chunk_size
        chunks.append(text[start:end])
        start = end - overlap

    return chunks


async def retry_async(
    func: Callable[..., Awaitable[T]],
    max_retries: int = 3,
    delay: float = 1.0,
    backoff: float = 2.0,
    exceptions: tuple[type[Exception], ...] = (Exception,),
    *args: Any,
    **kwargs: Any,
) -> T:
    """
    Retry async function with exponential backoff.

    Args:
        func: Async function to retry
        max_retries: Maximum number of retries
        delay: Initial delay between retries (seconds)
        backoff: Backoff multiplier
        exceptions: Tuple of exceptions to catch
        *args: Positional arguments for func
        **kwargs: Keyword arguments for func

    Returns:
        Result of func

    Raises:
        Last exception if all retries fail

    Examples:
        >>> async def fetch_data():
        ...     return await api_call()
        >>> result = await retry_async(fetch_data, max_retries=3, delay=1.0)
    """
    last_exception: Optional[Exception] = None
    current_delay = delay

    for attempt in range(max_retries + 1):
        try:
            return await func(*args, **kwargs)
        except exceptions as e:
            last_exception = e

            if attempt < max_retries:
                logger.warning(
                    f"Attempt {attempt + 1}/{max_retries + 1} failed, retrying in {current_delay}s",
                    func=func.__name__,
                    attempt=attempt + 1,
                    max_retries=max_retries + 1,
                    delay=current_delay,
                    exc=e,
                )
                await asyncio.sleep(current_delay)
                current_delay *= backoff
            else:
                logger.error(
                    f"All {max_retries + 1} attempts failed",
                    func=func.__name__,
                    exc=e,
                )

    if last_exception:
        raise last_exception
    raise RuntimeError("Unexpected error in retry_async")


def clean_xml_dict(data):
    """
    Clean XML dict by removing @ and # prefixes from keys.

    Args:
        data: Dictionary, list, or value to clean

    Returns:
        Cleaned data structure
    """
    if isinstance(data, dict):
        cleaned = {}
        for key, value in data.items():
            new_key = key
            if isinstance(key, str):
                new_key = key.lstrip("@#")
            cleaned[new_key] = clean_xml_dict(value)
        return cleaned
    elif isinstance(data, list):
        return [clean_xml_dict(item) for item in data]
    else:
        return data


def validate_inn(inn: str) -> Tuple[bool, str]:
    """
    Валидация ИНН с проверкой контрольной суммы.

    Args:
        inn: ИНН для проверки (строка из 10 или 12 цифр)

    Returns:
        Tuple[bool, str]: (валидность, сообщение об ошибке)
    """
    if not inn:
        return False, "ИНН не может быть пустым"

    # Убираем пробелы
    inn = inn.strip()

    # Проверка на цифры
    if not inn.isdigit():
        return False, "ИНН должен содержать только цифры"

    # Проверка длины
    if len(inn) not in (10, 12):
        return False, "ИНН должен содержать 10 цифр (юр.лицо) или 12 цифр (ИП/физ.лицо)"

    # Проверка контрольной суммы для ИНН юр.лица (10 цифр)
    if len(inn) == 10:
        coefficients = [2, 4, 10, 3, 5, 9, 4, 6, 8]
        checksum = sum(int(inn[i]) * coefficients[i] for i in range(9)) % 11 % 10
        if checksum != int(inn[9]):
            return False, "Неверная контрольная сумма ИНН"

    # Проверка контрольной суммы для ИНН ИП (12 цифр)
    elif len(inn) == 12:
        # Первая контрольная цифра (11-я)
        coefficients_11 = [7, 2, 4, 10, 3, 5, 9, 4, 6, 8]
        checksum_11 = sum(int(inn[i]) * coefficients_11[i] for i in range(10)) % 11 % 10
        if checksum_11 != int(inn[10]):
            return False, "Неверная контрольная сумма ИНН (11-я цифра)"

        # Вторая контрольная цифра (12-я)
        coefficients_12 = [3, 7, 2, 4, 10, 3, 5, 9, 4, 6, 8]
        checksum_12 = sum(int(inn[i]) * coefficients_12[i] for i in range(11)) % 11 % 10
        if checksum_12 != int(inn[11]):
            return False, "Неверная контрольная сумма ИНН (12-я цифра)"

    return True, ""


def format_inn(inn: str) -> str:
    """Форматирует ИНН для отображения."""
    inn = inn.strip()
    if len(inn) == 10:
        return f"{inn[:4]} {inn[4:6]} {inn[6:]}"
    elif len(inn) == 12:
        return f"{inn[:4]} {inn[4:6]} {inn[6:8]} {inn[8:]}"
    return inn


def get_client_ip(request: "Request") -> str:
    """
    Extract client IP address from request.

    Used by SlowAPI limiter in scheduler routes.
    """
    # Prefer X-Forwarded-For (first IP in list)
    try:
        xff = request.headers.get("x-forwarded-for")
        if xff:
            return xff.split(",")[0].strip()
    except Exception:
        pass

    # Fallback: X-Real-IP
    try:
        x_real = request.headers.get("x-real-ip")
        if x_real:
            return x_real.strip()
    except Exception:
        pass

    # Final fallback: request.client.host
    try:
        if request.client and request.client.host:
            return request.client.host
    except Exception:
        pass

    return "unknown"


__all__ = [
    "safe_dict_get",
    "chunk_text",
    "retry_async",
    "clean_xml_dict",
    "validate_inn",
    "format_inn",
    "get_client_ip",
]
