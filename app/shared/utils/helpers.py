"""
General helper utilities.
"""

import asyncio
from typing import Any, Callable, Dict, List, Optional, TypeVar

from app.shared.logger import get_logger

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
    result = data
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
    func: Callable[..., T],
    max_retries: int = 3,
    delay: float = 1.0,
    backoff: float = 2.0,
    exceptions: tuple = (Exception,),
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
                    exc=str(e),
                )
                await asyncio.sleep(current_delay)
                current_delay *= backoff
            else:
                logger.error(
                    f"All {max_retries + 1} attempts failed",
                    func=func.__name__,
                    exc=str(e),
                )

    if last_exception:
        raise last_exception
    raise RuntimeError("Unexpected error in retry_async")


__all__ = [
    "safe_dict_get",
    "chunk_text",
    "retry_async",
]

