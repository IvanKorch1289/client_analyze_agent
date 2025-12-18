from typing import Tuple


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
