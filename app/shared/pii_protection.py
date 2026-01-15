"""
PII Protection Module

Masks personally identifiable information before sending to external LLMs.
Uses Microsoft Presidio for detection and anonymization.
"""

import hashlib
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

# Lazy imports
_analyzer = None
_anonymizer = None


@dataclass
class PIIMaskingResult:
    """Result of PII masking operation."""

    masked_text: str
    original_text: str
    replacements: List[Dict[str, Any]]
    detected_pii_types: List[str]
    pii_count: int


def get_analyzer():
    """Lazy initialization of Presidio Analyzer."""
    global _analyzer
    if _analyzer is None:
        from presidio_analyzer import AnalyzerEngine

        _analyzer = AnalyzerEngine()
    return _analyzer


def get_anonymizer():
    """Lazy initialization of Presidio Anonymizer."""
    global _anonymizer
    if _anonymizer is None:
        from presidio_anonymizer import AnonymizerEngine

        _anonymizer = AnonymizerEngine()
    return _anonymizer


# Russian context PII entities
PII_ENTITIES_RU = [
    "PERSON",  # ФИО
    "PHONE_NUMBER",  # Телефоны
    "EMAIL_ADDRESS",  # Email
    "CREDIT_CARD",  # Карты
    "IBAN_CODE",  # Банковские счета
    "IP_ADDRESS",  # IP адреса
    "DATE_TIME",  # Даты (в т.ч. рождения)
    "LOCATION",  # Адреса/локации
    "URL",  # URLs с данными
    "RU_INN",  # ИНН (custom)
    "RU_SNILS",  # СНИЛС (custom)
]


def mask_pii(
    text: str,
    language: str = "ru",
    mask_level: str = "high",
    entities: Optional[List[str]] = None,
) -> PIIMaskingResult:
    """
    Mask PII in text using Presidio.

    Args:
        text: Text to mask
        language: Language code ("ru", "en")
        mask_level: "low" (only ИНН), "medium" (+ phone/email), "high" (all)
        entities: Custom list of entities to mask (overrides mask_level)

    Returns:
        PIIMaskingResult with masked text and metadata
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
            entities_to_detect = ["RU_INN", "CREDIT_CARD", "IBAN_CODE"]
        elif mask_level == "medium":
            entities_to_detect = [
                "RU_INN",
                "PHONE_NUMBER",
                "EMAIL_ADDRESS",
                "CREDIT_CARD",
                "IBAN_CODE",
            ]
        else:  # high
            entities_to_detect = PII_ENTITIES_RU
    else:
        entities_to_detect = entities

    analyzer = get_analyzer()
    anonymizer = get_anonymizer()

    # Analyze text
    # Map "ru" to "en" as Presidio doesn't have Russian NER models
    # We rely on pattern matching for Russian-specific entities
    analysis_language = "en" if language == "ru" else language

    results = analyzer.analyze(text=text, language=analysis_language, entities=entities_to_detect)

    if not results:
        return PIIMaskingResult(
            masked_text=text,
            original_text=text,
            replacements=[],
            detected_pii_types=[],
            pii_count=0,
        )

    # Anonymize
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
        masked_text: Text with masked PII
        replacements: List of replacements from mask_pii()

    Returns:
        Text with original PII restored
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
    """
    return hashlib.sha256(text.encode("utf-8"), usedforsecurity=False).hexdigest()[:16]


__all__ = [
    "PIIMaskingResult",
    "mask_pii",
    "unmask_pii",
    "compute_text_hash",
    "PII_ENTITIES_RU",
]
