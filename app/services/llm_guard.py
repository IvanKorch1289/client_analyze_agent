"""
LLM Guard Service - сервис защиты персональных данных при работе с LLM.

Обеспечивает анонимизацию PII (персонально идентифицируемой информации)
перед отправкой в LLM и восстановление данных в ответах.

Поддерживаемые типы PII:
- ИНН (10 и 12 цифр)
- Телефоны (российский формат)
- Email адреса
- Имена (ФИО)
- Паспортные данные
- СНИЛС
- Банковские карты
"""

import re
from typing import Dict, List, Optional, Tuple

from pydantic import BaseModel, Field

from app.utility.logging_client import logger


class PIIMatch(BaseModel):
    """Найденные персональные данные."""

    pii_type: str = Field(description="Тип PII (INN, PHONE, EMAIL и т.д.)")
    original_value: str = Field(description="Оригинальное значение")
    token: str = Field(description="Токен для замены")
    start_pos: int = Field(description="Начальная позиция в тексте")
    end_pos: int = Field(description="Конечная позиция в тексте")


class SanitizeResult(BaseModel):
    """Результат санитизации текста."""

    sanitized_text: str = Field(description="Текст с замененными PII")
    has_pii: bool = Field(description="Флаг наличия PII в тексте")
    pii_count: int = Field(default=0, description="Количество найденных PII")
    pii_types: List[str] = Field(default_factory=list, description="Типы найденных PII")


class LLMGuardService:
    """
    Сервис защиты персональных данных при работе с LLM.
    
    Анонимизирует PII перед отправкой в LLM и восстанавливает
    оригинальные значения в ответах.
    
    Пример использования:
        guard = LLMGuardService()
        
        # Санитизация входных данных
        result = guard.sanitize_input("ИНН клиента: 7707083893")
        # result.sanitized_text = "ИНН клиента: [INN_1]"
        
        # Вызов LLM с безопасным текстом
        llm_response = await llm.ainvoke(result.sanitized_text)
        
        # Восстановление оригинальных данных в ответе
        final_response = guard.restore_output(llm_response)
    """

    def __init__(self):
        """Инициализация LLM Guard Service."""
        self._vault: Dict[str, str] = {}
        self._counters: Dict[str, int] = {}
        
        self._patterns: Dict[str, re.Pattern] = {
            "INN": re.compile(r"\b(\d{10}|\d{12})\b"),
            "PHONE": re.compile(
                r"(?:\+7|8)[\s\-]?\(?(\d{3})\)?[\s\-]?(\d{3})[\s\-]?(\d{2})[\s\-]?(\d{2})"
            ),
            "EMAIL": re.compile(
                r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b"
            ),
            "PASSPORT": re.compile(r"\b(\d{4})\s*(\d{6})\b"),
            "SNILS": re.compile(r"\b(\d{3})[\s\-]?(\d{3})[\s\-]?(\d{3})[\s\-]?(\d{2})\b"),
            "CARD": re.compile(r"\b(\d{4})[\s\-]?(\d{4})[\s\-]?(\d{4})[\s\-]?(\d{4})\b"),
            "NAME": re.compile(
                r"\b([А-ЯЁ][а-яё]+)\s+([А-ЯЁ][а-яё]+)(?:\s+([А-ЯЁ][а-яё]+))?\b"
            ),
        }
        
        logger.info("LLMGuardService инициализирован", component="llm_guard")

    def _generate_token(self, pii_type: str) -> str:
        """
        Генерирует уникальный токен для PII.
        
        Args:
            pii_type: Тип PII (INN, PHONE, EMAIL и т.д.)
            
        Returns:
            str: Токен вида [TYPE_N]
        """
        if pii_type not in self._counters:
            self._counters[pii_type] = 0
        self._counters[pii_type] += 1
        return f"[{pii_type}_{self._counters[pii_type]}]"

    def _is_valid_inn(self, value: str) -> bool:
        """
        Проверяет валидность ИНН по контрольной сумме.
        
        Args:
            value: Строка с ИНН
            
        Returns:
            bool: True если ИНН валиден
        """
        if len(value) == 10:
            weights = [2, 4, 10, 3, 5, 9, 4, 6, 8]
            checksum = sum(int(value[i]) * weights[i] for i in range(9)) % 11 % 10
            return checksum == int(value[9])
        elif len(value) == 12:
            weights1 = [7, 2, 4, 10, 3, 5, 9, 4, 6, 8]
            weights2 = [3, 7, 2, 4, 10, 3, 5, 9, 4, 6, 8]
            checksum1 = sum(int(value[i]) * weights1[i] for i in range(10)) % 11 % 10
            checksum2 = sum(int(value[i]) * weights2[i] for i in range(11)) % 11 % 10
            return checksum1 == int(value[10]) and checksum2 == int(value[11])
        return False

    def sanitize_input(self, text: str) -> SanitizeResult:
        """
        Санитизирует текст, заменяя PII на токены.
        
        Заменяет персональные данные на безопасные токены вида [TYPE_N].
        Сохраняет маппинг токен -> оригинальное значение в vault.
        
        Args:
            text: Исходный текст с возможными PII
            
        Returns:
            SanitizeResult: Результат санитизации с очищенным текстом
        """
        if not text:
            return SanitizeResult(sanitized_text="", has_pii=False)
        
        sanitized = text
        found_pii_types: List[str] = []
        pii_count = 0
        
        for pii_type, pattern in self._patterns.items():
            matches = list(pattern.finditer(sanitized))
            
            offset = 0
            for match in matches:
                original_value = match.group(0)
                
                if pii_type == "INN" and not self._is_valid_inn(original_value):
                    continue
                
                token = self._generate_token(pii_type)
                self._vault[token] = original_value
                
                start = match.start() + offset
                end = match.end() + offset
                sanitized = sanitized[:start] + token + sanitized[end:]
                
                offset += len(token) - len(original_value)
                pii_count += 1
                
                if pii_type not in found_pii_types:
                    found_pii_types.append(pii_type)
        
        has_pii = pii_count > 0
        
        if has_pii:
            logger.info(
                f"Санитизация завершена: найдено {pii_count} PII",
                component="llm_guard",
                pii_types=found_pii_types,
            )
        
        return SanitizeResult(
            sanitized_text=sanitized,
            has_pii=has_pii,
            pii_count=pii_count,
            pii_types=found_pii_types,
        )

    def restore_output(self, text: str) -> str:
        """
        Восстанавливает оригинальные значения PII в тексте.
        
        Заменяет токены вида [TYPE_N] на оригинальные значения из vault.
        
        Args:
            text: Текст с токенами
            
        Returns:
            str: Текст с восстановленными оригинальными значениями
        """
        if not text:
            return ""
        
        restored = text
        restored_count = 0
        
        for token, original_value in self._vault.items():
            if token in restored:
                restored = restored.replace(token, original_value)
                restored_count += 1
        
        if restored_count > 0:
            logger.debug(
                f"Восстановлено {restored_count} значений PII",
                component="llm_guard",
            )
        
        return restored

    def clear_vault(self) -> None:
        """
        Очищает vault с маппингом токенов.
        
        Рекомендуется вызывать после завершения сессии работы с LLM
        для освобождения памяти и предотвращения утечки данных.
        """
        vault_size = len(self._vault)
        self._vault.clear()
        self._counters.clear()
        
        logger.info(
            f"Vault очищен: удалено {vault_size} записей",
            component="llm_guard",
        )

    def get_vault_stats(self) -> Dict[str, int]:
        """
        Возвращает статистику по vault.
        
        Returns:
            Dict[str, int]: Словарь с количеством токенов каждого типа
        """
        stats: Dict[str, int] = {}
        for token in self._vault:
            match = re.match(r"\[([A-Z]+)_\d+\]", token)
            if match:
                pii_type = match.group(1)
                stats[pii_type] = stats.get(pii_type, 0) + 1
        return stats

    def mask_pii(self, text: str, mask_char: str = "*") -> str:
        """
        Маскирует PII в тексте без сохранения в vault.
        
        Полезно для логирования, когда не требуется восстановление.
        
        Args:
            text: Исходный текст
            mask_char: Символ для маскирования
            
        Returns:
            str: Текст с замаскированными PII
        """
        if not text:
            return ""
        
        masked = text
        
        for pii_type, pattern in self._patterns.items():
            def masker(match: re.Match) -> str:
                value = match.group(0)
                if pii_type == "INN" and not self._is_valid_inn(value):
                    return value
                visible_chars = min(4, len(value) // 4)
                return value[:visible_chars] + mask_char * (len(value) - visible_chars * 2) + value[-visible_chars:]
            
            masked = pattern.sub(masker, masked)
        
        return masked


_llm_guard_instance: Optional[LLMGuardService] = None


def get_llm_guard() -> LLMGuardService:
    """
    Получить singleton экземпляр LLMGuardService.
    
    Returns:
        LLMGuardService: Единственный экземпляр сервиса
    """
    global _llm_guard_instance
    
    if _llm_guard_instance is None:
        _llm_guard_instance = LLMGuardService()
    
    return _llm_guard_instance


__all__ = [
    "LLMGuardService",
    "PIIMatch",
    "SanitizeResult",
    "get_llm_guard",
]
