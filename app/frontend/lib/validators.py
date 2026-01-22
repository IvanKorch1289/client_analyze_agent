"""
Frontend validation utilities.

NOTE: validate_inn is imported from the canonical source app.shared.security
to avoid code duplication. All INN validation across the project should use
the same implementation.
"""

from __future__ import annotations

import re
from datetime import date, datetime
from typing import NamedTuple, Optional, Tuple, Union

# Import canonical validate_inn from shared module - single source of truth
from app.shared.security import (
    validate_inn_extended as _validate_inn_extended_internal,
)


class ValidationResult(NamedTuple):
    """Result of a validation operation."""

    is_valid: bool
    error_message: str
    field_name: Optional[str] = None
    suggestion: Optional[str] = None

    def __bool__(self) -> bool:
        return self.is_valid


def validate_inn_extended(inn: str, *, required: bool = False) -> ValidationResult:
    """
    Extended INN validation with ValidationResult.

    This is a wrapper around the canonical app.shared.security.validate_inn_extended
    that returns a frontend-compatible ValidationResult NamedTuple.

    Args:
        inn: The INN string to validate
        required: Whether the field is required

    Returns:
        ValidationResult with detailed information
    """
    result = _validate_inn_extended_internal(inn, required=required)
    return ValidationResult(
        is_valid=result.is_valid,
        error_message=result.error_message,
        field_name="ИНН",
        suggestion=result.suggestion,
    )


def validate_inn(inn: str, *, required: bool = False) -> Tuple[bool, str]:
    """
    Validate Russian INN (simple wrapper).

    This is a wrapper around validate_inn_extended that returns a simple tuple.

    Args:
        inn: The INN string to validate
        required: Whether the field is required

    Returns:
        Tuple of (is_valid, error_message)
    """
    result = validate_inn_extended(inn, required=required)
    return result.is_valid, result.error_message


def validate_client_name_extended(name: str, *, required: bool = True) -> ValidationResult:
    """
    Extended client name validation with ValidationResult.

    This is the canonical implementation - validate_client_name() is a wrapper.

    Args:
        name: The company name to validate
        required: Whether the field is required

    Returns:
        ValidationResult with detailed information
    """
    name = (name or "").strip()
    if not name:
        if required:
            return ValidationResult(
                is_valid=False,
                error_message="Название компании обязательно для заполнения",
                field_name="Название компании",
                suggestion='Введите полное название, например: ООО "Ромашка"',
            )
        return ValidationResult(is_valid=True, error_message="")

    if len(name) < 2:
        return ValidationResult(
            is_valid=False,
            error_message="Название компании слишком короткое",
            field_name="Название компании",
            suggestion="Название должно содержать минимум 2 символа",
        )

    if len(name) > 200:
        return ValidationResult(
            is_valid=False,
            error_message=f"Название компании слишком длинное ({len(name)} символов)",
            field_name="Название компании",
            suggestion="Сократите название до 200 символов или используйте аббревиатуру",
        )

    return ValidationResult(is_valid=True, error_message="", field_name="Название компании")


def validate_client_name(name: str, *, required: bool = True) -> Tuple[bool, str]:
    """
    Validate client/company name (simple wrapper).

    Args:
        name: The company name to validate
        required: Whether the field is required

    Returns:
        Tuple of (is_valid, error_message)
    """
    result = validate_client_name_extended(name, required=required)
    return result.is_valid, result.error_message


def validate_email_extended(email: str, *, required: bool = False) -> ValidationResult:
    """
    Extended email validation with ValidationResult.

    Args:
        email: The email address to validate
        required: Whether the field is required

    Returns:
        ValidationResult with detailed information
    """
    email = (email or "").strip().lower()
    if not email:
        if required:
            return ValidationResult(
                is_valid=False,
                error_message="Email обязателен для заполнения",
                field_name="Email",
                suggestion="Введите корректный email адрес, например: contact@company.ru",
            )
        return ValidationResult(is_valid=True, error_message="")

    email_pattern = r"^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$"
    if not re.match(email_pattern, email):
        if "@" not in email:
            return ValidationResult(
                is_valid=False,
                error_message="Email должен содержать символ @",
                field_name="Email",
                suggestion="Добавьте @ между именем пользователя и доменом",
            )
        if "." not in email.split("@")[-1]:
            return ValidationResult(
                is_valid=False,
                error_message="Email должен содержать домен (например, .ru, .com)",
                field_name="Email",
                suggestion="Проверьте правильность домена email",
            )
        return ValidationResult(
            is_valid=False,
            error_message="Некорректный формат email",
            field_name="Email",
            suggestion="Пример корректного email: user@example.com",
        )

    if len(email) > 254:
        return ValidationResult(
            is_valid=False,
            error_message=f"Email слишком длинный ({len(email)} символов)",
            field_name="Email",
            suggestion="Максимальная длина email — 254 символа",
        )

    return ValidationResult(is_valid=True, error_message="", field_name="Email")


def validate_email(email: str, *, required: bool = False) -> Tuple[bool, str]:
    """
    Validate email address format (simple wrapper).

    Args:
        email: The email address to validate
        required: Whether the field is required

    Returns:
        Tuple of (is_valid, error_message)
    """
    result = validate_email_extended(email, required=required)
    return result.is_valid, result.error_message


def validate_phone_extended(phone: str, *, required: bool = False) -> ValidationResult:
    """
    Extended Russian phone validation with ValidationResult.

    Args:
        phone: The phone number to validate
        required: Whether the field is required

    Returns:
        ValidationResult with detailed information
    """
    phone = (phone or "").strip()
    if not phone:
        if required:
            return ValidationResult(
                is_valid=False,
                error_message="Номер телефона обязателен для заполнения",
                field_name="Телефон",
                suggestion="Введите номер в формате +7 (XXX) XXX-XX-XX",
            )
        return ValidationResult(is_valid=True, error_message="")

    digits = re.sub(r"[^\d]", "", phone)

    if len(digits) < 10:
        return ValidationResult(
            is_valid=False,
            error_message=f"Номер телефона слишком короткий ({len(digits)} цифр)",
            field_name="Телефон",
            suggestion="Российский номер должен содержать 10-11 цифр",
        )

    if len(digits) > 11:
        return ValidationResult(
            is_valid=False,
            error_message=f"Номер телефона слишком длинный ({len(digits)} цифр)",
            field_name="Телефон",
            suggestion="Проверьте номер — возможно, введены лишние цифры",
        )

    if len(digits) == 11 and digits[0] not in ("7", "8"):
        return ValidationResult(
            is_valid=False,
            error_message="Российский номер должен начинаться с 7 или 8",
            field_name="Телефон",
            suggestion="Замените первую цифру на 7 или 8",
        )

    return ValidationResult(is_valid=True, error_message="", field_name="Телефон")


def validate_phone(phone: str, *, required: bool = False) -> Tuple[bool, str]:
    """
    Validate Russian phone number (simple wrapper).

    Args:
        phone: The phone number to validate
        required: Whether the field is required

    Returns:
        Tuple of (is_valid, error_message)
    """
    result = validate_phone_extended(phone, required=required)
    return result.is_valid, result.error_message


def validate_date_range(
    start: Optional[Union[date, datetime, str]],
    end: Optional[Union[date, datetime, str]],
    *,
    max_days: Optional[int] = None,
    allow_same_day: bool = True,
) -> Tuple[bool, str]:
    """
    Validate a date range (simple wrapper).

    Args:
        start: Start date (date, datetime, or ISO string)
        end: End date (date, datetime, or ISO string)
        max_days: Maximum allowed days between start and end
        allow_same_day: Whether start == end is allowed

    Returns:
        Tuple of (is_valid, error_message)
    """
    result = validate_date_range_extended(start, end, max_days=max_days, allow_same_day=allow_same_day)
    return result.is_valid, result.error_message


def validate_date_range_extended(
    start: Optional[Union[date, datetime, str]],
    end: Optional[Union[date, datetime, str]],
    *,
    max_days: Optional[int] = None,
    allow_same_day: bool = True,
    field_name: str = "Период",
) -> ValidationResult:
    """
    Extended date range validation with ValidationResult.

    Args:
        start: Start date
        end: End date
        max_days: Maximum allowed days between start and end
        allow_same_day: Whether start == end is allowed
        field_name: Name of the field for error messages

    Returns:
        ValidationResult with detailed information
    """

    def to_date(d: Optional[Union[date, datetime, str]]) -> Optional[date]:
        if d is None:
            return None
        if isinstance(d, datetime):
            return d.date()
        if isinstance(d, date):
            return d
        if isinstance(d, str):
            try:
                return datetime.fromisoformat(d.replace("Z", "+00:00")).date()
            except ValueError:
                return None
        return None

    start_date = to_date(start)
    end_date = to_date(end)

    if start_date is None and end_date is None:
        return ValidationResult(is_valid=True, error_message="")

    if start_date is None:
        return ValidationResult(
            is_valid=False,
            error_message="Дата начала периода не указана",
            field_name=field_name,
            suggestion="Выберите дату начала периода",
        )

    if end_date is None:
        return ValidationResult(
            is_valid=False,
            error_message="Дата окончания периода не указана",
            field_name=field_name,
            suggestion="Выберите дату окончания периода",
        )

    if not allow_same_day and start_date == end_date:
        return ValidationResult(
            is_valid=False,
            error_message="Дата начала и окончания не могут совпадать",
            field_name=field_name,
            suggestion="Выберите разные даты для начала и окончания периода",
        )

    if start_date > end_date:
        return ValidationResult(
            is_valid=False,
            error_message="Дата начала не может быть позже даты окончания",
            field_name=field_name,
            suggestion="Поменяйте местами даты начала и окончания",
        )

    if max_days is not None:
        delta = (end_date - start_date).days
        if delta > max_days:
            return ValidationResult(
                is_valid=False,
                error_message=f"Период не может превышать {max_days} дней",
                field_name=field_name,
                suggestion=f"Выбран период в {delta} дней. Сократите период до {max_days} дней",
            )

    return ValidationResult(is_valid=True, error_message="", field_name=field_name)
