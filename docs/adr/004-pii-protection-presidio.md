# ADR-004: Use Presidio for PII protection

## Status
Accepted

## Context

The Client Analysis Agent processes sensitive business data including:
- Company registration numbers (INN, OGRN)
- Personal names of executives and founders
- Passport numbers and SNILS
- Addresses and phone numbers

Russian Federal Law 152-FZ requires:
- Personal data must not be transferred outside Russia without consent
- Processing must be minimized to what's necessary
- Audit trail of all personal data processing

When using cloud LLM providers (especially non-Russian ones like OpenRouter/HuggingFace), we risk:
- Sending PII to foreign servers (152-FZ violation)
- Data retention by LLM providers
- Potential data breaches

## Decision

We implemented **Microsoft Presidio** with custom Russian recognizers for PII detection and masking.

### Implementation:

1. **Detection**: 7 custom recognizers for Russian PII types
2. **Masking**: Reversible placeholder replacement before LLM calls
3. **Unmasking**: Restore original values in LLM responses
4. **Audit**: Log all masking operations with hash-only mode

### Custom Recognizers:

| Recognizer | Pattern | Example |
|------------|---------|---------|
| RU_INN | 10 or 12 digits with checksum | 7707083893 |
| RU_OGRN | 13 or 15 digits | 1027700132195 |
| RU_SNILS | XXX-XXX-XXX XX format | 123-456-789 01 |
| RU_PERSON | Cyrillic names (Фамилия И.О.) | Иванов И.И. |
| RU_ADDRESS | Russian address patterns | г. Москва, ул. Ленина, д. 1 |
| RU_PASSPORT | Russian passport format | 45 06 123456 |
| RU_PHONE | Russian phone numbers | +7 (999) 123-45-67 |

## Consequences

### Positive:
- **152-FZ Compliance**: Zero PII leakage to cloud LLMs
- **Reversible**: Original data preserved in responses
- **Audit Trail**: Complete tracking for regulatory inspections
- **Extensible**: Easy to add new recognizer types

### Negative:
- **Performance**: ~50-100ms overhead per LLM call
- **False Positives**: Some numbers may be incorrectly flagged as INN
- **Context Loss**: LLM sees placeholders, may affect analysis quality
- **Maintenance**: Custom recognizers need updates for edge cases

### Mitigations:
- Confidence thresholds to reduce false positives
- Context-aware masking (only mask in specific fields)
- Regular testing with production-like data
- Hash-only audit mode for privacy

## Implementation Details

```python
from presidio_analyzer import AnalyzerEngine
from presidio_anonymizer import AnonymizerEngine

# Custom Russian recognizers
analyzer = AnalyzerEngine()
analyzer.registry.add_recognizer(RussianINNRecognizer())
analyzer.registry.add_recognizer(RussianPersonRecognizer())
# ... other recognizers

def mask_pii(text: str, level: str = "high") -> MaskResult:
    """Mask PII in text before LLM call."""
    results = analyzer.analyze(text, language="ru")

    # Filter by confidence threshold
    if level == "high":
        results = [r for r in results if r.score >= 0.7]

    # Replace with placeholders
    masked_text, replacements = anonymizer.anonymize(text, results)

    return MaskResult(
        masked_text=masked_text,
        replacements=replacements,
        detected_types=[r.entity_type for r in results]
    )

def unmask_pii(text: str, replacements: dict) -> str:
    """Restore original PII in LLM response."""
    for placeholder, original in replacements.items():
        text = text.replace(placeholder, original)
    return text
```

## Alternatives Considered

### Jay Guard Proxy
- **Pros**: Enterprise-grade, centralized policy management
- **Cons**: Additional infrastructure, licensing costs
- **Decision**: Optional layer, not required with Presidio

### Regex-Only Detection
- **Pros**: Fast, no dependencies
- **Cons**: High false positive rate, hard to maintain
- **Rejected because**: Presidio provides ML-based detection with better accuracy

### On-Premise LLM Only
- **Pros**: No data leaves premises
- **Cons**: Quality/capability limitations, high infrastructure cost
- **Rejected because**: Cloud LLMs provide significantly better analysis quality

### Data Tokenization Service
- **Pros**: Centralized, secure token vault
- **Cons**: Additional service to maintain, network dependency
- **Rejected because**: Presidio's in-process masking is sufficient for our use case
