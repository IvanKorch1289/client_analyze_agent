"""
Security utilities for input sanitization and validation.

Protects against:
- Prompt injection attacks
- SQL injection (if applicable)
- XSS attacks
- Invalid data formats
"""

import html
import re
from typing import Tuple

from app.shared.exceptions import SecurityError, ValidationError


# Known prompt injection patterns
INJECTION_PATTERNS = [
    r"ignore\s+(previous|all|above)\s+instructions",
    r"new\s+instructions?:",
    r"system\s*:",
    r"(you\s+are|act\s+as|pretend|roleplay)",
    r"<\s*script",
    r"javascript:",
    r"\{\{\s*.*?\s*\}\}",  # Template injection
    r"\$\{\s*.*?\s*\}",  # Expression injection
]

COMPILED_INJECTION_PATTERNS = [re.compile(pattern, re.IGNORECASE) for pattern in INJECTION_PATTERNS]


def sanitize_for_llm(text: str, max_length: int = 10000, strict: bool = True) -> str:
    """
    Sanitize user input before passing to LLM.

    Protects against prompt injection and malicious input.

    Args:
        text: User input text
        max_length: Maximum allowed length
        strict: If True, raise error on suspicious patterns; if False, just clean

    Returns:
        Sanitized text

    Raises:
        SecurityError: If strict=True and injection pattern detected
        ValidationError: If input exceeds max_length

    Examples:
        >>> sanitize_for_llm("Analyze company ABC")
        "Analyze company ABC"

        >>> sanitize_for_llm("<script>alert('xss')</script>")
        SecurityError: Potential injection detected
    """
    if not isinstance(text, str):
        raise ValidationError(f"Expected string, got {type(text).__name__}")

    # Check length
    if len(text) > max_length:
        raise ValidationError(
            f"Input too long: {len(text)} chars (max: {max_length})",
            details={"length": len(text), "max_length": max_length},
        )

    # Check for injection patterns
    for pattern in COMPILED_INJECTION_PATTERNS:
        if pattern.search(text):
            if strict:
                raise SecurityError(
                    f"Potential injection detected: pattern '{pattern.pattern}' found",
                    details={"pattern": pattern.pattern, "text_preview": text[:100]},
                )
            else:
                # Log warning but continue
                from app.shared.logger import get_logger
                logger = get_logger(__name__)
                logger.warning(
                    "Suspicious pattern detected",
                    pattern=pattern.pattern,
                    text_preview=text[:100],
                )

    # Remove control characters (except newlines and tabs)
    text = "".join(char for char in text if char.isprintable() or char in ("\n", "\t"))

    # HTML escape for safety
    text = html.escape(text, quote=False)

    # Remove multiple consecutive newlines
    text = re.sub(r"\n{3,}", "\n\n", text)

    # Trim whitespace
    text = text.strip()

    return text


def validate_client_id(client_id: str) -> str:
    """
    Validate and sanitize client ID.

    Args:
        client_id: Client identifier

    Returns:
        Sanitized client ID

    Raises:
        ValidationError: If invalid format

    Examples:
        >>> validate_client_id("client_123")
        "client_123"

        >>> validate_client_id("client@123#$")
        ValidationError: Invalid client ID format
    """
    if not client_id:
        raise ValidationError("Client ID is required")

    # Allow alphanumeric, underscore, hyphen
    if not re.match(r"^[a-zA-Z0-9_-]{1,50}$", client_id):
        raise ValidationError(
            "Client ID must be 1-50 characters (alphanumeric, underscore, hyphen only)",
            details={"client_id": client_id},
        )

    return client_id.strip()


def validate_email(email: str) -> str:
    """
    Validate email format.

    Args:
        email: Email address

    Returns:
        Lowercase email

    Raises:
        ValidationError: If invalid format

    Examples:
        >>> validate_email("user@example.com")
        "user@example.com"

        >>> validate_email("invalid-email")
        ValidationError: Invalid email format
    """
    if not email:
        raise ValidationError("Email is required")

    # Basic email regex
    pattern = r"^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$"
    if not re.match(pattern, email):
        raise ValidationError(
            "Invalid email format",
            details={"email": email},
        )

    return email.lower().strip()


def validate_inn(inn: str) -> Tuple[bool, str]:
    """
    Validate Russian INN (ИНН).

    Args:
        inn: INN number (10 or 12 digits)

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
        return True, ""  # INN is optional

    # Only digits allowed
    if not inn.isdigit():
        return False, "ИНН должен содержать только цифры"

    # Length: 10 (legal entity) or 12 (individual)
    if len(inn) not in (10, 12):
        return False, "ИНН должен содержать 10 (юрлица) или 12 (ИП) цифр"

    return True, ""


def sanitize_for_sql(text: str) -> str:
    """
    Sanitize text for SQL queries (if direct SQL is used).

    NOTE: Prefer parameterized queries! This is a backup defense.

    Args:
        text: Text to sanitize

    Returns:
        Sanitized text

    Examples:
        >>> sanitize_for_sql("SELECT * FROM users; DROP TABLE users;")
        "SELECT FROM users DROP TABLE users"
    """
    # Remove common SQL injection patterns
    dangerous_patterns = [
        r";",  # Statement separator
        r"--",  # Comment
        r"/\*.*?\*/",  # Block comment
        r"xp_",  # Extended procedures
        r"sp_",  # System procedures
        r"\bexec\b",
        r"\bexecute\b",
        r"\binsert\b",
        r"\bupdate\b",
        r"\bdelete\b",
        r"\bdrop\b",
        r"\bcreate\b",
        r"\balter\b",
    ]

    result = text
    for pattern in dangerous_patterns:
        result = re.sub(pattern, "", result, flags=re.IGNORECASE)

    return result.strip()


def sanitize_filename(filename: str) -> str:
    """
    Sanitize filename to prevent path traversal.

    Args:
        filename: Original filename

    Returns:
        Safe filename

    Raises:
        ValidationError: If filename is invalid

    Examples:
        >>> sanitize_filename("report_2024.pdf")
        "report_2024.pdf"

        >>> sanitize_filename("../../etc/passwd")
        ValidationError: Invalid filename
    """
    if not filename:
        raise ValidationError("Filename is required")

    # Remove path separators
    filename = filename.replace("/", "").replace("\\", "").replace("..", "")

    # Allow only alphanumeric, underscore, hyphen, dot
    if not re.match(r"^[a-zA-Z0-9_.-]+$", filename):
        raise ValidationError(
            "Filename contains invalid characters",
            details={"filename": filename},
        )

    # Limit length
    if len(filename) > 255:
        raise ValidationError("Filename too long (max 255 chars)")

    return filename


__all__ = [
    "sanitize_for_llm",
    "validate_client_id",
    "validate_email",
    "validate_inn",
    "sanitize_for_sql",
    "sanitize_filename",
]

