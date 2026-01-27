"""
Модуль защиты персональных данных (PII)

Маскирует персональные данные перед отправкой во внешние LLM.
Использует Microsoft Presidio с кастомными распознавателями для русского языка.
Поддерживает Reversible Pseudonymization с нумерованными псевдонимами.
"""

import hashlib
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

# Lazy imports
_analyzer = None
_anonymizer = None
_recognizers_registered = False


@dataclass
class PIIMaskingResult:
    """Результат операции маскирования PII с обратимой псевдонимизацией."""

    masked_text: str
    original_text: str
    replacements: List[Dict[str, Any]]  # Содержит маппинг для размаскирования
    detected_pii_types: List[str]
    pii_count: int
    pii_detected: bool  # Флаг обнаружения PII


def _create_russian_recognizers():
    """
    Create custom Presidio recognizers for Russian PII entities.

    Returns:
        List of PatternRecognizer instances
    """
    from presidio_analyzer import Pattern, PatternRecognizer

    recognizers = []

    # 1. RU_INN (ИНН) - 10 или 12 цифр
    recognizers.append(
        PatternRecognizer(
            supported_entity="RU_INN",
            name="RU INN Recognizer",
            supported_language="ru",
            patterns=[
                Pattern(
                    name="inn_pattern",
                    regex=r"\b\d{10}\b|\b\d{12}\b",  # 10 или 12 цифр
                    score=0.85,
                )
            ],
            context=["ИНН", "INN", "налоговый номер", "идентификационный номер"],
        )
    )

    # 2. RU_OGRN (ОГРН/ОГРНИП) - 13 или 15 цифр
    recognizers.append(
        PatternRecognizer(
            supported_entity="RU_OGRN",
            name="RU OGRN Recognizer",
            supported_language="ru",
            patterns=[
                Pattern(
                    name="ogrn_pattern",
                    regex=r"\b\d{13}\b|\b\d{15}\b",  # 13 или 15 цифр
                    score=0.8,
                )
            ],
            context=["ОГРН", "ОГРНИП", "OGRN", "регистрационный номер"],
        )
    )

    # 3. RU_SNILS (СНИЛС) - XXX-XXX-XXX XX
    recognizers.append(
        PatternRecognizer(
            supported_entity="RU_SNILS",
            name="RU SNILS Recognizer",
            supported_language="ru",
            patterns=[
                Pattern(
                    name="snils_pattern",
                    regex=r"\b\d{3}[\-\s]?\d{3}[\-\s]?\d{3}[\-\s]?\d{2}\b",
                    score=0.9,
                )
            ],
            context=["СНИЛС", "SNILS", "страховой номер"],
        )
    )

    # 4. RU_PERSON (ФИО кириллицей) - улучшенный распознаватель
    # Примечание: Presidio использует IGNORECASE по умолчанию, поэтому паттерн [А-ЯЁ]
    # ловит любые буквы. Используем низкий базовый score - требуется контекст.
    recognizers.append(
        PatternRecognizer(
            supported_entity="RU_PERSON",
            name="RU Person Name Recognizer",
            supported_language="ru",
            patterns=[
                # Фамилия Имя Отчество - с типичными окончаниями отчества
                Pattern(
                    name="full_name_with_patronymic",
                    regex=r"\b[А-ЯЁ][а-яё]+\s+[А-ЯЁ][а-яё]+\s+[А-ЯЁ][а-яё]+(ич|на|вич|вна)\b",
                    score=0.85,  # Высокий score - отчество явно указывает на ФИО
                ),
                # Фамилия Имя Отчество - общий паттерн (низкий score без контекста)
                Pattern(
                    name="full_name_pattern",
                    regex=r"\b[А-ЯЁ][а-яё]+\s+[А-ЯЁ][а-яё]+\s+[А-ЯЁ][а-яё]+\b",
                    score=0.35,  # Низкий score - требуется контекст (+0.35)
                ),
                # Фамилия И.О.
                Pattern(
                    name="abbreviated_name_pattern",
                    regex=r"\b[А-ЯЁ][а-яё]+\s+[А-ЯЁ]\.\s*[А-ЯЁ]\.",
                    score=0.75,  # Формат И.О. более специфичен
                ),
            ],
            context=[
                "директор",
                "генеральный директор",
                "руководитель",
                "владелец",
                "ФИО",
                "гражданин",
                "гражданка",
            ],
        )
    )

    # 5. RU_ADDRESS (российские адреса)
    recognizers.append(
        PatternRecognizer(
            supported_entity="RU_ADDRESS",
            name="RU Address Recognizer",
            supported_language="ru",
            patterns=[
                # г. Москва, ул. Ленина, д. 1
                Pattern(
                    name="full_address_pattern",
                    regex=r"г\.\s*[А-ЯЁ][а-яё\-]+(?:,\s*(?:ул|пр\-кт|пер|наб|бул|пл)\.\s*[А-ЯЁа-яё\s\-]+)?(?:,\s*д\.\s*\d+)?",
                    score=0.75,
                ),
                # Индекс, город, улица
                Pattern(
                    name="postal_address_pattern",
                    regex=r"\b\d{6},\s*[А-ЯЁ][а-яё\-\s]+,\s*[А-ЯЁа-яё\s\-]+",
                    score=0.7,
                ),
            ],
            context=["адрес", "местонахождение", "address", "расположен"],
        )
    )

    # 6. RU_PASSPORT (серия и номер паспорта)
    recognizers.append(
        PatternRecognizer(
            supported_entity="RU_PASSPORT",
            name="RU Passport Recognizer",
            supported_language="ru",
            patterns=[
                # Формат с пробелом: XXXX XXXXXX или XX XX XXXXXX
                Pattern(
                    name="passport_pattern_spaced",
                    regex=r"\b\d{2}\s+\d{2}\s+\d{6}\b|\b\d{4}\s+\d{6}\b",
                    score=0.9,
                ),
                # Формат без пробела только с контекстом (низкий score без контекста)
                Pattern(
                    name="passport_pattern_compact",
                    regex=r"\b\d{4}\d{6}\b",
                    score=0.5,  # Низкий score - требуется контекст для активации
                ),
            ],
            context=["паспорт", "passport", "серия", "номер паспорта", "документ"],
        )
    )

    # 7. RU_PHONE (российские телефоны) - улучшенный
    recognizers.append(
        PatternRecognizer(
            supported_entity="RU_PHONE",
            name="RU Phone Recognizer",
            supported_language="ru",
            patterns=[
                # +7 (XXX) XXX-XX-XX
                Pattern(
                    name="phone_pattern_formatted",
                    regex=r"\+?7\s*[\(\[]?\d{3}[\)\]]?\s*\d{3}[\-\s]?\d{2}[\-\s]?\d{2}\b",
                    score=0.85,
                ),
                # 8 XXX XXX XX XX
                Pattern(
                    name="phone_pattern_8",
                    regex=r"\b8\s*[\(\[]?\d{3}[\)\]]?\s*\d{3}[\-\s]?\d{2}[\-\s]?\d{2}\b",
                    score=0.85,
                ),
            ],
            context=["телефон", "тел", "phone", "моб", "контакт"],
        )
    )

    return recognizers


def _register_russian_recognizers(analyzer):
    """
    Register custom Russian recognizers with the analyzer.

    Args:
        analyzer: AnalyzerEngine instance
    """
    global _recognizers_registered
    if _recognizers_registered:
        return

    recognizers = _create_russian_recognizers()

    for recognizer in recognizers:
        analyzer.registry.add_recognizer(recognizer)

    _recognizers_registered = True


def get_analyzer():
    """
    Lazy initialization of Presidio Analyzer with Russian recognizers.

    Tries to use ru_core_news_lg (large model for better Russian name recognition),
    falls back to ru_core_news_sm if large model is not available.
    """
    global _analyzer
    if _analyzer is None:
        from presidio_analyzer import AnalyzerEngine
        from presidio_analyzer.nlp_engine import NlpEngineProvider

        # Попытка использовать большую модель для лучшего распознавания русских ФИО
        # Fallback на маленькую модель, если большая не установлена
        ru_model = "ru_core_news_lg"  # Предпочтительная большая модель

        try:
            import spacy

            try:
                spacy.load(ru_model)
            except OSError:
                # Большая модель не установлена, используем маленькую
                ru_model = "ru_core_news_sm"
                import logging

                logging.warning(
                    f"Large Russian spaCy model not found, using {ru_model}. "
                    "Install ru_core_news_lg for better recognition: "
                    "python -m spacy download ru_core_news_lg"
                )
        except ImportError:
            ru_model = "ru_core_news_sm"

        # Configure NLP engine to support both Russian and English
        configuration = {
            "nlp_engine_name": "spacy",
            "models": [
                {"lang_code": "ru", "model_name": ru_model},
                {"lang_code": "en", "model_name": "en_core_web_sm"},
            ],
        }
        nlp_engine = NlpEngineProvider(nlp_configuration=configuration).create_engine()
        _analyzer = AnalyzerEngine(nlp_engine=nlp_engine, supported_languages=["ru", "en"])
        _register_russian_recognizers(_analyzer)

    return _analyzer


def get_anonymizer():
    """Lazy initialization of Presidio Anonymizer."""
    global _anonymizer
    if _anonymizer is None:
        from presidio_anonymizer import AnonymizerEngine

        _anonymizer = AnonymizerEngine()
    return _anonymizer


# Russian context PII entities (updated with new recognizers)
PII_ENTITIES_RU = [
    # Presidio built-in
    "PERSON",  # ФИО (fallback)
    "PHONE_NUMBER",  # Телефоны (fallback)
    "EMAIL_ADDRESS",  # Email
    "CREDIT_CARD",  # Карты
    "IBAN_CODE",  # Банковские счета
    "IP_ADDRESS",  # IP адреса
    "DATE_TIME",  # Даты
    "LOCATION",  # Адреса (fallback)
    "URL",  # URLs
    # Custom Russian recognizers
    "RU_INN",  # ИНН (custom)
    "RU_OGRN",  # ОГРН (custom)
    "RU_SNILS",  # СНИЛС (custom)
    "RU_PERSON",  # ФИО кириллицей (custom)
    "RU_ADDRESS",  # Российские адреса (custom)
    "RU_PASSPORT",  # Паспорт (custom)
    "RU_PHONE",  # Российские телефоны (custom)
]


def mask_pii(
    text: str,
    language: str = "ru",
    mask_level: str = "high",
    entities: Optional[List[str]] = None,
) -> PIIMaskingResult:
    """
    Mask PII in text using Reversible Pseudonymization.

    Использует нумерованные псевдонимы вместо простых тегов для обеспечения
    полной обратимости маскирования. Например:
    - "Иванов Иван" → "[CLIENT_NAME_1]"
    - "Петров Петр" → "[CLIENT_NAME_2]"

    Args:
        text: Text to mask
        language: Language code ("ru", "en")
        mask_level: "low" (ИНН/ОГРН), "medium" (+ phone/email), "high" (all PII)
        entities: Custom list of entities to mask (overrides mask_level)

    Returns:
        PIIMaskingResult with masked text and reversible mapping

    Example:
        >>> result = mask_pii("ИНН 7707083893, директор Иванов Иван, тел +7(499)123-45-67")
        >>> print(result.masked_text)
        "ИНН [INN_1], директор [CLIENT_NAME_1], тел [PHONE_1]"
        >>> print(result.replacements)  # Содержит маппинг для размаскирования
    """
    if not text or not text.strip():
        return PIIMaskingResult(
            masked_text=text,
            original_text=text,
            replacements=[],
            detected_pii_types=[],
            pii_count=0,
            pii_detected=False,
        )

    # Determine entities to detect based on mask_level
    if entities is None:
        if mask_level == "low":
            # Минимум: только финансовые идентификаторы
            entities_to_detect = [
                "RU_INN",
                "RU_OGRN",
                "CREDIT_CARD",
                "IBAN_CODE",
            ]
        elif mask_level == "medium":
            # Средний: + контакты
            entities_to_detect = [
                "RU_INN",
                "RU_OGRN",
                "RU_PHONE",
                "PHONE_NUMBER",
                "EMAIL_ADDRESS",
                "CREDIT_CARD",
                "IBAN_CODE",
            ]
        else:  # high - максимальная защита
            entities_to_detect = PII_ENTITIES_RU
    else:
        entities_to_detect = entities

    analyzer = get_analyzer()

    # Analyze text
    # Use "ru" for Russian recognizers, they support multiple languages
    # score_threshold=0.5 filters out low-confidence matches
    results = analyzer.analyze(text=text, language=language, entities=entities_to_detect, score_threshold=0.5)

    if not results:
        return PIIMaskingResult(
            masked_text=text,
            original_text=text,
            replacements=[],
            detected_pii_types=[],
            pii_count=0,
            pii_detected=False,
        )

    # Build replacements map with NUMBERED pseudonyms for reversibility
    # Sort by start position to process in reverse order (preserve offsets)
    sorted_results = sorted(results, key=lambda r: r.start, reverse=True)

    # Счетчики для каждого типа сущностей
    entity_counters: Dict[str, int] = {}
    replacements = []
    detected_types = set()

    # Маппинг entity_type -> читаемое имя для псевдонима
    ENTITY_PSEUDONYM_NAMES = {
        "RU_INN": "INN",
        "RU_OGRN": "OGRN",
        "RU_SNILS": "SNILS",
        "RU_PERSON": "CLIENT_NAME",
        "PERSON": "PERSON_NAME",
        "RU_ADDRESS": "ADDRESS",
        "LOCATION": "LOCATION",
        "RU_PASSPORT": "PASSPORT",
        "RU_PHONE": "PHONE",
        "PHONE_NUMBER": "PHONE",
        "EMAIL_ADDRESS": "EMAIL",
        "CREDIT_CARD": "CARD",
        "IBAN_CODE": "IBAN",
        "IP_ADDRESS": "IP",
        "DATE_TIME": "DATE",
        "URL": "URL",
    }

    # Создаем маскированный текст, заменяя с конца (чтобы сохранить оффсеты)
    masked_text = text
    for r in sorted_results:
        entity_type = r.entity_type
        detected_types.add(entity_type)

        # Получаем оригинальное значение
        original_value = text[r.start : r.end]

        # Получаем счетчик для этого типа сущности
        entity_counters[entity_type] = entity_counters.get(entity_type, 0) + 1
        counter = entity_counters[entity_type]

        # Создаем читаемый псевдоним с номером
        pseudonym_base = ENTITY_PSEUDONYM_NAMES.get(entity_type, entity_type)
        masked_value = f"[{pseudonym_base}_{counter}]"

        # Заменяем в тексте (с конца, чтобы не сбить оффсеты)
        masked_text = masked_text[: r.start] + masked_value + masked_text[r.end :]

        # Сохраняем маппинг для размаскирования
        replacements.append(
            {
                "start": r.start,
                "end": r.end,
                "entity_type": entity_type,
                "original": original_value,
                "masked": masked_value,
                "operator": "replace",
            }
        )

    # Переворачиваем replacements обратно (для логичного порядка)
    replacements = list(reversed(replacements))

    return PIIMaskingResult(
        masked_text=masked_text,
        original_text=text,
        replacements=replacements,
        detected_pii_types=sorted(detected_types),
        pii_count=len(replacements),
        pii_detected=len(replacements) > 0,
    )


def unmask_pii(masked_text: str, replacements: List[Dict[str, Any]]) -> str:
    """
    Restore original PII in masked text using reversible pseudonymization mapping.

    Использует маппинг из mask_pii() для точного восстановления оригинальных
    значений PII. Поддерживает нумерованные псевдонимы.

    Args:
        masked_text: Text with masked PII (e.g., "ИНН [INN_1], директор [CLIENT_NAME_1]")
        replacements: List of replacements from mask_pii() with mapping

    Returns:
        Text with original PII restored

    Example:
        >>> masked = "ИНН [INN_1], директор [CLIENT_NAME_1], тел [PHONE_1]"
        >>> replacements = [
        ...     {"masked": "[INN_1]", "original": "7707083893"},
        ...     {"masked": "[CLIENT_NAME_1]", "original": "Иванов Иван"},
        ...     {"masked": "[PHONE_1]", "original": "+7(499)123-45-67"}
        ... ]
        >>> unmask_pii(masked, replacements)
        "ИНН 7707083893, директор Иванов Иван, тел +7(499)123-45-67"
    """
    result = masked_text

    # Заменяем все псевдонимы на оригинальные значения
    # Порядок не важен, т.к. псевдонимы уникальны (нумерованные)
    for repl in replacements:
        masked_value = repl["masked"]
        original_value = repl["original"]

        # Заменяем ВСЕ вхождения этого псевдонима (обычно одно)
        # В ответе LLM может быть повторено несколько раз
        result = result.replace(masked_value, original_value)

    return result


def compute_text_hash(text: str) -> str:
    """
    Compute SHA256 hash of text for audit logging.

    Args:
        text: Text to hash

    Returns:
        Hex digest of SHA256 hash (first 16 chars)

    Example:
        >>> compute_text_hash("ИНН 7707083893")
        "a3f2e1d4b5c6..."
    """
    return hashlib.sha256(text.encode("utf-8"), usedforsecurity=False).hexdigest()[:16]


__all__ = [
    "PIIMaskingResult",
    "mask_pii",
    "unmask_pii",
    "compute_text_hash",
    "PII_ENTITIES_RU",
]
