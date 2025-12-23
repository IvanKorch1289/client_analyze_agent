"""
Validation and cache management tools.
"""

from typing import Any, Dict, Optional

from pydantic import BaseModel, Field, field_validator

from app.shared.logger import get_logger
from app.shared.security import sanitize_for_llm

logger = get_logger(__name__)


# ============================================================================
# Request Models
# ============================================================================


class ValidateInputRequest(BaseModel):
    """Request to validate user input."""

    text: str = Field(..., max_length=10000, description="Text to validate")
    strict: bool = Field(
        default=True,
        description="Strict mode (raise error on suspicious patterns)",
    )


class InvalidateCacheRequest(BaseModel):
    """Request to invalidate cache."""

    cache_key: Optional[str] = Field(
        default=None,
        max_length=200,
        description="Specific cache key (or None for all)",
    )
    pattern: Optional[str] = Field(
        default=None,
        max_length=200,
        description="Pattern to match cache keys",
    )

    @field_validator("cache_key", "pattern")
    @classmethod
    def validate_key(cls, v: Optional[str]) -> Optional[str]:
        """Validate cache key format."""
        if v:
            # Only allow alphanumeric, underscore, hyphen, colon, asterisk
            import re
            if not re.match(r"^[a-zA-Z0-9_:*-]+$", v):
                raise ValueError(
                    "Cache key must contain only alphanumeric, underscore, hyphen, colon, asterisk"
                )
        return v


# ============================================================================
# Tool Functions
# ============================================================================


async def validate_input_tool(request: ValidateInputRequest) -> Dict[str, Any]:
    """
    Validate user input for security.

    Checks for prompt injection, XSS, and other malicious patterns.

    Args:
        request: Validated request

    Returns:
        Validation result with sanitized text

    Raises:
        SecurityError: If strict=True and suspicious patterns found

    Examples:
        >>> result = await validate_input_tool(
        ...     ValidateInputRequest(text="Analyze company ABC", strict=True)
        ... )
        >>> result
        {
            'is_valid': True,
            'sanitized_text': 'Analyze company ABC',
            'warnings': []
        }
    """
    logger.log_action(
        "validate_input_start",
        text_length=len(request.text),
        strict=request.strict,
    )

    try:
        from app.shared.security import sanitize_for_llm

        sanitized = sanitize_for_llm(
            request.text,
            max_length=10000,
            strict=request.strict,
        )

        logger.log_action(
            "validate_input_success",
            original_length=len(request.text),
            sanitized_length=len(sanitized),
        )

        return {
            "is_valid": True,
            "sanitized_text": sanitized,
            "original_length": len(request.text),
            "sanitized_length": len(sanitized),
            "warnings": [],
        }

    except Exception as e:
        logger.error("validate_input_failed", exc=e)

        return {
            "is_valid": False,
            "sanitized_text": "",
            "original_length": len(request.text),
            "sanitized_length": 0,
            "warnings": [str(e)],
        }


async def invalidate_cache_tool(request: InvalidateCacheRequest) -> Dict[str, Any]:
    """
    Invalidate cache entries.

    Can invalidate specific key, pattern, or all cache.

    Args:
        request: Validated request

    Returns:
        Invalidation result with count

    Raises:
        Exception: If cache operation fails

    Examples:
        >>> result = await invalidate_cache_tool(
        ...     InvalidateCacheRequest(pattern="dadata:*")
        ... )
        >>> result
        {'status': 'success', 'invalidated_count': 15}
    """
    logger.log_action(
        "invalidate_cache_start",
        cache_key=request.cache_key,
        pattern=request.pattern,
    )

    try:
        from app.services.app_actions import dispatch_cache_invalidate

        result = await dispatch_cache_invalidate(
            cache_key=request.cache_key,
            pattern=request.pattern,
        )

        logger.log_action(
            "invalidate_cache_success",
            cache_key=request.cache_key,
            pattern=request.pattern,
            invalidated_count=result.get("invalidated_count", 0),
        )

        return result

    except Exception as e:
        logger.error(
            "invalidate_cache_failed",
            exc=e,
            cache_key=request.cache_key,
            pattern=request.pattern,
        )
        raise


__all__ = [
    "ValidateInputRequest",
    "InvalidateCacheRequest",
    "validate_input_tool",
    "invalidate_cache_tool",
]

