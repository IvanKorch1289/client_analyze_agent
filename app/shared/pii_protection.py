"""
PII Protection Module

Masks personally identifiable information before sending to external LLMs.
Uses Microsoft Presidio for detection and anonymization with custom Russian recognizers.
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
    """Result of PII masking operation."""

    masked_text: str
    original_text: str
    replacements: List[Dict[str, Any]]
    detected_pii_types: List[str]
    pii_count: int


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
    recognizers.append(
        PatternRecognizer(
            supported_entity="RU_PERSON",
            name="RU Person Name Recognizer",
            supported_language="ru",
            patterns=[
                # Фамилия Имя Отчество
                Pattern(
                    name="full_name_pattern",
                    regex=r"\b[А-ЯЁ][а-яё]+\s+[А-ЯЁ][а-яё]+\s+[А-ЯЁ][а-яё]+\b",
                    score=0.85,
                ),
                # Фамилия И.О.
                Pattern(
                    name="abbreviated_name_pattern",
                    regex=r"\b[А-ЯЁ][а-яё]+\s+[А-ЯЁ]\.\s*[А-ЯЁ]\.",
                    score=0.8,
                ),
            ],
            context=[
                "директор",
                "генеральный директор",
                "руководитель",
                "владелец",
                "ФИО",
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
                Pattern(
                    name="passport_pattern",
                    regex=r"\b\d{4}\s*\d{6}\b",  # 4 цифры (серия) + 6 цифр (номер)
                    score=0.9,
                )
            ],
            context=["паспорт", "passport", "серия", "номер паспорта"],
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
    """Lazy initialization of Presidio Analyzer with Russian recognizers."""
    global _analyzer
    if _analyzer is None:
        from presidio_analyzer import AnalyzerEngine

        _analyzer = AnalyzerEngine()
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
    Mask PII in text using Presidio with custom Russian recognizers.

    Args:
        text: Text to mask
        language: Language code ("ru", "en")
        mask_level: "low" (ИНН/ОГРН), "medium" (+ phone/email), "high" (all PII)
        entities: Custom list of entities to mask (overrides mask_level)

    Returns:
        PIIMaskingResult with masked text and metadata

    Example:
        >>> result = mask_pii("ИНН 7707083893, директор Иванов Иван Иванович")
        >>> print(result.masked_text)
        "ИНН <RU_INN>, директор <RU_PERSON>"
        >>> print(result.detected_pii_types)
        ["RU_INN", "RU_PERSON"]
    """
    if not text or not text.strip():
        return PIIMaskingResult(
            masked_text=text,
            original_text=text,
            replacements=[],
            detected_pii_types=[],
            pii_count=0,
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
    anonymizer = get_anonymizer()

    # Analyze text
    # Use "ru" for Russian recognizers, they support multiple languages
    results = analyzer.analyze(
        text=text, language=language, entities=entities_to_detect
    )

    if not results:
        return PIIMaskingResult(
            masked_text=text,
            original_text=text,
            replacements=[],
            detected_pii_types=[],
            pii_count=0,
        )

    # Anonymize with angle brackets format: <ENTITY_TYPE>
    anonymized = anonymizer.anonymize(text=text, analyzer_results=results)

    # Build replacements map
    replacements = []
    detected_types = set()

    for item in anonymized.items:
        entity_type = item.entity_type
        detected_types.add(entity_type)

        # Get original text (before anonymization)
        original_value = text[item.start : item.end]

        # Get masked value (after anonymization)
        masked_value = anonymized.text[item.start : item.end]

        replacements.append(
            {
                "start": item.start,
                "end": item.end,
                "entity_type": entity_type,
                "original": original_value,
                "masked": masked_value,
                "operator": item.operator,
            }
        )

    return PIIMaskingResult(
        masked_text=anonymized.text,
        original_text=text,
        replacements=replacements,
        detected_pii_types=sorted(detected_types),
        pii_count=len(replacements),
    )


def unmask_pii(masked_text: str, replacements: List[Dict[str, Any]]) -> str:
    """
    Restore original PII in masked text.

    Args:
        masked_text: Text with masked PII (e.g., "ИНН <RU_INN>")
        replacements: List of replacements from mask_pii()

    Returns:
        Text with original PII restored

    Example:
        >>> masked = "ИНН <RU_INN>, директор <RU_PERSON>"
        >>> replacements = [...]
        >>> unmask_pii(masked, replacements)
        "ИНН 7707083893, директор Иванов Иван Иванович"
    """
    result = masked_text

    # Process in reverse order to preserve offsets
    for repl in reversed(replacements):
        masked_value = repl["masked"]
        original_value = repl["original"]

        # Replace first occurrence (should be only one at correct position)
        result = result.replace(masked_value, original_value, 1)

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
