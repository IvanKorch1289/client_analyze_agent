"""
Shared utility functions for agents.

Common functions used across multiple agents to avoid duplication.
"""

from datetime import datetime
from typing import Tuple


def truncate(text: str, max_length: int = 5000, suffix: str = "...") -> str:
    """
    Обрезка текста до максимальной длины.
    
    Args:
        text: Исходный текст
        max_length: Максимальная длина
        suffix: Суффикс для обрезанного текста
        
    Returns:
        Обрезанный текст с суффиксом
        
    Examples:
        >>> truncate("Long text" * 1000, 100)
        "Long textLong textLong text..."
    """
    if not text:
        return ""
    if len(text) <= max_length:
        return text
    return text[:max_length - len(suffix)] + suffix


def format_ts(ts: any = None) -> str:
    """
    Форматирование timestamp в ISO формат.
    
    Args:
        ts: Unix timestamp или datetime объект (None = текущее время)
        
    Returns:
        ISO форматированная строка
        
    Examples:
        >>> format_ts(1703260800)
        "2023-12-22T16:00:00"
        
        >>> format_ts()  # Current time
        "2025-12-22T15:30:00"
    """
    try:
        if ts is None:
            return datetime.utcnow().isoformat()
        if isinstance(ts, datetime):
            return ts.isoformat()
        if isinstance(ts, (int, float)):
            return datetime.fromtimestamp(float(ts)).isoformat()
        return str(ts)
    except Exception:
        return datetime.utcnow().isoformat()


def validate_inn(inn: str) -> Tuple[bool, str]:
    """
    Валидация ИНН.
    
    Args:
        inn: ИНН для проверки
        
    Returns:
        (is_valid, error_message)
        
    Examples:
        >>> validate_inn("7707083893")
        (True, "")
        
        >>> validate_inn("123")
        (False, "ИНН должен содержать 10 или 12 цифр")
    """
    inn = (inn or "").strip()
    
    if not inn:
        return True, ""  # ИНН опционален
    
    if not inn.isdigit():
        return False, "ИНН должен содержать только цифры"
    
    if len(inn) not in (10, 12):
        return False, "ИНН должен содержать 10 (юрлица) или 12 (ИП) цифр"
    
    return True, ""


def safe_dict_get(data: dict, *keys, default=None):
    """
    Безопасное получение вложенного значения из словаря.
    
    Args:
        data: Словарь
        *keys: Последовательность ключей
        default: Значение по умолчанию
        
    Returns:
        Значение или default
        
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


__all__ = [
    "truncate",
    "format_ts",
    "validate_inn",
    "safe_dict_get",
]

