"""
Data parsing utilities.
"""

import csv
import json
from io import StringIO
from typing import Any, Dict, List

from app.shared.exceptions import ValidationError


def parse_json(text: str, strict: bool = True) -> Dict[str, Any]:
    """
    Parse JSON string to dict.

    Args:
        text: JSON string
        strict: If True, raise error on invalid JSON; if False, return empty dict

    Returns:
        Parsed dictionary

    Raises:
        ValidationError: If JSON is invalid and strict=True

    Examples:
        >>> parse_json('{"name": "Company", "inn": "1234567890"}')
        {'name': 'Company', 'inn': '1234567890'}

        >>> parse_json('invalid json', strict=False)
        {}
    """
    if not text or not text.strip():
        return {}

    try:
        return json.loads(text)
    except json.JSONDecodeError as e:
        if strict:
            raise ValidationError(
                f"Invalid JSON: {e}",
                details={"error": str(e), "text_preview": text[:100]},
                original_error=e,
            )
        return {}


def parse_csv(
    text: str,
    delimiter: str = ",",
    has_header: bool = True,
) -> List[Dict[str, Any]]:
    """
    Parse CSV string to list of dicts.

    Args:
        text: CSV string
        delimiter: CSV delimiter
        has_header: If True, first row is headers

    Returns:
        List of dictionaries

    Raises:
        ValidationError: If CSV is invalid

    Examples:
        >>> parse_csv('name,value\\nA,1\\nB,2')
        [{'name': 'A', 'value': '1'}, {'name': 'B', 'value': '2'}]
    """
    if not text or not text.strip():
        return []

    try:
        if has_header:
            dict_reader = csv.DictReader(StringIO(text), delimiter=delimiter)
            return list(dict_reader)

        row_reader = csv.reader(StringIO(text), delimiter=delimiter)
        # Convert to list of lists if no header
        return [{"col_" + str(i): val for i, val in enumerate(row)} for row in row_reader]

    except Exception as e:
        raise ValidationError(
            f"Invalid CSV: {e}",
            details={"error": str(e), "text_preview": text[:100]},
            original_error=e,
        )


__all__ = [
    "parse_json",
    "parse_csv",
]
