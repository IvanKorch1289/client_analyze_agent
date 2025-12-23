from __future__ import annotations

from typing import TYPE_CHECKING, Tuple

if TYPE_CHECKING:
    # Optional typing only; avoids runtime dependency issues
    from starlette.requests import Request


def clean_xml_dict(data):
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
