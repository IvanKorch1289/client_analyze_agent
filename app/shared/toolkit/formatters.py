"""
Text and data formatting utilities.
"""

import json
from datetime import datetime
from typing import Any, Dict, List


def truncate(text: str, max_length: int = 5000, suffix: str = "...") -> str:
    """
    Truncate text to maximum length.

    Args:
        text: Original text
        max_length: Maximum length
        suffix: Suffix for truncated text

    Returns:
        Truncated text with suffix

    Examples:
        >>> truncate("Long text" * 1000, 100)
        "Long textLong textLong text..."
    """
    if not text:
        return ""
    if len(text) <= max_length:
        return text
    return text[: max_length - len(suffix)] + suffix


def format_ts(ts: Any = None) -> str:
    """
    Format timestamp to ISO format.

    Args:
        ts: Unix timestamp, datetime object, or None (current time)

    Returns:
        ISO formatted string

    Examples:
        >>> format_ts(1703260800)
        "2023-12-22T16:00:00"

        >>> format_ts()  # Current time
        "2025-12-23T10:30:00"
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


def format_json(
    data: Dict[str, Any],
    indent: int = 2,
    ensure_ascii: bool = False,
) -> str:
    """
    Format dict to pretty JSON string.

    Args:
        data: Dictionary to format
        indent: Indentation level
        ensure_ascii: If False, allow unicode characters

    Returns:
        Formatted JSON string

    Raises:
        TypeError: If data is not JSON serializable

    Examples:
        >>> format_json({"name": "Company", "inn": "1234567890"})
        '{\\n  "name": "Company",\\n  "inn": "1234567890"\\n}'
    """
    return json.dumps(data, indent=indent, ensure_ascii=ensure_ascii)


def format_csv(data: List[Dict[str, Any]], delimiter: str = ",") -> str:
    """
    Format list of dicts to CSV string.

    Args:
        data: List of dictionaries
        delimiter: CSV delimiter

    Returns:
        CSV formatted string

    Examples:
        >>> format_csv([{"name": "A", "value": 1}, {"name": "B", "value": 2}])
        'name,value\\nA,1\\nB,2'
    """
    if not data:
        return ""

    # Get headers from first row
    headers = list(data[0].keys())
    lines = [delimiter.join(headers)]

    # Add data rows
    for row in data:
        values = [str(row.get(h, "")) for h in headers]
        lines.append(delimiter.join(values))

    return "\n".join(lines)


__all__ = [
    "truncate",
    "format_ts",
    "format_json",
    "format_csv",
]
