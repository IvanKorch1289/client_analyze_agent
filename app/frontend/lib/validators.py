from __future__ import annotations

import re
from datetime import date, datetime
from typing import NamedTuple, Optional, Tuple, Union


class ValidationResult(NamedTuple):
    """Result of a validation operation."""
    is_valid: bool
    error_message: str
    field_name: Optional[str] = None
    suggestion: Optional[str] = None

    def __bool__(self) -> bool:
        return self.is_valid


def validate_inn(inn: str, *, required: bool = False) -> Tuple[bool, str]:
    """
    Validate Russian INN (ИНН).
    
    Args:
        inn: The INN string to validate
        required: Whether the field is required
    
    Returns:
        Tuple of (is_valid, error_message)
    """
    inn = (inn or "").strip()
    if not inn:
        if required:
            return False, "ИНН обязателен для заполнения"
        return True, ""
    if not inn.isdigit():
        return False, "ИНН должен содержать только цифры (0-9)"
    if len(inn) == 10:
        return True, ""
    if len(inn) == 12:
        return True, ""
    return False, "ИНН должен содержать 10 цифр для юридических лиц или 12 цифр для ИП/физических лиц"


def validate_inn_extended(inn: str, *, required: bool = False) -> ValidationResult:
    """
    Extended INN validation with ValidationResult.
    
    Args:
        inn: The INN string to validate
        required: Whether the field is required
    
    Returns:
        ValidationResult with detailed information
    """
    inn = (inn or "").strip()
    if not inn:
        if required:
            return ValidationResult(
                is_valid=False,
                error_message="ИНН обязателен для заполнения",
                field_name="ИНН",
                suggestion="Введите 10-значный ИНН организации или 12-значный ИНН ИП/физлица",
            )
        return ValidationResult(is_valid=True, error_message="")
    
    if not inn.isdigit():
        return ValidationResult(
            is_valid=False,
            error_message="ИНН должен содержать только цифры",
            field_name="ИНН",
            suggestion="Удалите все буквы и специальные символы из ИНН",
        )
    
    if len(inn) not in (10, 12):
        return ValidationResult(
            is_valid=False,
            error_message=f"ИНН должен содержать 10 или 12 цифр (введено: {len(inn)})",
            field_name="ИНН",
            suggestion="Для юридических лиц — 10 цифр, для ИП/физических лиц — 12 цифр",
        )
    
    return ValidationResult(is_valid=True, error_message="", field_name="ИНН")


def validate_client_name(name: str, *, required: bool = True) -> Tuple[bool, str]:
    """
    Validate client/company name.
    
    Args:
        name: The company name to validate
        required: Whether the field is required
    
    Returns:
        Tuple of (is_valid, error_message)
    """
    name = (name or "").strip()
    if not name:
        if required:
            return False, "Название компании обязательно для заполнения"
        return True, ""
    if len(name) < 2:
        return False, "Название компании слишком короткое (минимум 2 символа)"
    if len(name) > 200:
        return False, "Название компании слишком длинное (максимум 200 символов)"
    return True, ""


def validate_client_name_extended(name: str, *, required: bool = True) -> ValidationResult:
    """
    Extended client name validation with ValidationResult.
    
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


def validate_email(email: str, *, required: bool = False) -> Tuple[bool, str]:
    """
    Validate email address format.
    
    Args:
        email: The email address to validate
        required: Whether the field is required
    
    Returns:
        Tuple of (is_valid, error_message)
    """
    email = (email or "").strip().lower()
    if not email:
        if required:
            return False, "Email обязателен для заполнения"
        return True, ""
    
    email_pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
    if not re.match(email_pattern, email):
        return False, "Некорректный формат email. Пример: user@example.com"
    
    if len(email) > 254:
        return False, "Email слишком длинный (максимум 254 символа)"
    
    return True, ""


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
    
    email_pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
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


def validate_phone(phone: str, *, required: bool = False) -> Tuple[bool, str]:
    """
    Validate Russian phone number format.
    
    Accepts formats:
    - +7XXXXXXXXXX (11 digits with +7)
    - 8XXXXXXXXXX (11 digits with 8)
    - 7XXXXXXXXXX (11 digits with 7)
    - XXXXXXXXXX (10 digits, assumes +7)
    
    Args:
        phone: The phone number to validate
        required: Whether the field is required
    
    Returns:
        Tuple of (is_valid, error_message)
    """
    phone = (phone or "").strip()
    if not phone:
        if required:
            return False, "Номер телефона обязателен для заполнения"
        return True, ""
    
    digits = re.sub(r"[^\d]", "", phone)
    
    if len(digits) == 10:
        return True, ""
    
    if len(digits) == 11:
        if digits[0] in ("7", "8"):
            return True, ""
        return False, "Российский номер должен начинаться с 7 или 8"
    
    return False, "Номер телефона должен содержать 10 или 11 цифр. Пример: +7 (999) 123-45-67"


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


def validate_date_range(
    start: Optional[Union[date, datetime, str]],
    end: Optional[Union[date, datetime, str]],
    *,
    max_days: Optional[int] = None,
    allow_same_day: bool = True,
) -> Tuple[bool, str]:
    """
    Validate a date range.
    
    Args:
        start: Start date (date, datetime, or ISO string)
        end: End date (date, datetime, or ISO string)
        max_days: Maximum allowed days between start and end
        allow_same_day: Whether start == end is allowed
    
    Returns:
        Tuple of (is_valid, error_message)
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
        return True, ""
    
    if start_date is None:
        return False, "Дата начала периода не указана"
    
    if end_date is None:
        return False, "Дата окончания периода не указана"
    
    if not allow_same_day and start_date == end_date:
        return False, "Дата начала и окончания не могут совпадать"
    
    if start_date > end_date:
        return False, "Дата начала не может быть позже даты окончания"
    
    if max_days is not None:
        delta = (end_date - start_date).days
        if delta > max_days:
            return False, f"Период не может превышать {max_days} дней (выбрано: {delta} дней)"
    
    return True, ""


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
