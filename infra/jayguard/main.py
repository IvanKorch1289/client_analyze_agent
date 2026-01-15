"""
Jay Guard - PII Protection Proxy for LLM Requests

Masks personally identifiable information (PII) before sending to external LLMs.
"""
import os
from typing import Any, Dict, List, Optional

import httpx
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse

app = FastAPI(title="Jay Guard PII Protection Proxy")

# Lazy initialization
_analyzer = None
_anonymizer = None


def get_analyzer():
    """Lazy init Presidio Analyzer"""
    global _analyzer
    if _analyzer is None:
        from presidio_analyzer import AnalyzerEngine
        _analyzer = AnalyzerEngine()
    return _analyzer


def get_anonymizer():
    """Lazy init Presidio Anonymizer"""
    global _anonymizer
    if _anonymizer is None:
        from presidio_anonymizer import AnonymizerEngine
        _anonymizer = AnonymizerEngine()
    return _anonymizer


# PII entity types to detect (Russian context)
PII_ENTITIES = [
    "PERSON",           # ФИО
    "PHONE_NUMBER",     # Телефоны
    "EMAIL_ADDRESS",    # Email
    "CREDIT_CARD",      # Карты
    "IBAN_CODE",        # Счета
    "IP_ADDRESS",       # IP
    "DATE_TIME",        # Даты рождения
    "LOCATION",         # Адреса
    "URL",              # URLs с данными
]


def mask_pii(text: str, language: str = "en") -> tuple[str, List[Dict]]:
    """
    Mask PII in text using Presidio.

    Returns:
        (masked_text, replacements) - masked text and list of replacements for unmaskingHere is the text masked and a list to restore it later.
    """
    if not text or not text.strip():
        return text, []

    analyzer = get_analyzer()
    anonymizer = get_anonymizer()

    # Analyze text
    results = analyzer.analyze(
        text=text,
        language=language,
        entities=PII_ENTITIES
    )

    if not results:
        return text, []

    # Anonymize
    anonymized = anonymizer.anonymize(
        text=text,
        analyzer_results=results
    )

    # Build replacements map
    replacements = []
    for item in anonymized.items:
        replacements.append({
            "start": item.start,
            "end": item.end,
            "entity_type": item.entity_type,
            "original": text[item.start:item.end],
            "masked": anonymized.text[item.start:item.end]
        })

    return anonymized.text, replacements


def unmask_pii(text: str, replacements: List[Dict]) -> str:
    """Restore original PII in response."""
    result = text
    # Reverse order to preserve offsets
    for repl in reversed(replacements):
        masked = repl["masked"]
        original = repl["original"]
        result = result.replace(masked, original)
    return result


@app.get("/health")
async def health():
    """Health check"""
    return {"status": "healthy", "service": "jayguard"}


@app.post("/v1/chat/completions")
async def proxy_openrouter(request: Request):
    """
    Proxy OpenRouter API with PII masking.

    Compatible with OpenAI API format.
    """
    try:
        body = await request.json()
    except Exception as e:
        raise HTTPException(400, f"Invalid JSON: {e}")

    # Extract messages
    messages = body.get("messages", [])
    if not messages:
        raise HTTPException(400, "No messages provided")

    # Mask PII in messages
    replacements_per_message = []
    for msg in messages:
        content = msg.get("content", "")
        if isinstance(content, str):
            masked_content, repls = mask_pii(content)
            msg["content"] = masked_content
            replacements_per_message.append(repls)
        else:
            replacements_per_message.append([])

    # Forward to OpenRouter
    openrouter_key = os.getenv("OPENROUTER_API_KEY")
    if not openrouter_key:
        raise HTTPException(503, "OPENROUTER_API_KEY not configured")

    headers = {
        "Authorization": f"Bearer {openrouter_key}",
        "Content-Type": "application/json",
        "HTTP-Referer": "https://client-analysis-system.com",
        "X-Title": "Client Analysis System (via Jay Guard)"
    }

    async with httpx.AsyncClient(timeout=120.0) as client:
        try:
            response = await client.post(
                "https://openrouter.ai/api/v1/chat/completions",
                json=body,
                headers=headers
            )
            response.raise_for_status()
        except httpx.HTTPError as e:
            raise HTTPException(502, f"OpenRouter error: {e}")

    response_data = response.json()

    # Unmask PII in response
    choices = response_data.get("choices", [])
    for choice in choices:
        message = choice.get("message", {})
        content = message.get("content", "")
        if isinstance(content, str):
            # Use all replacements (we don't know which message generated this)
            all_repls = [r for repls in replacements_per_message for r in repls]
            unmasked = unmask_pii(content, all_repls)
            message["content"] = unmasked

    return JSONResponse(response_data)


@app.post("/analyze-pii")
async def analyze_pii_endpoint(request: Request):
    """
    Debug endpoint: analyze PII in text without masking.

    Body: {"text": "...", "language": "en"}
    """
    try:
        body = await request.json()
    except Exception:
        raise HTTPException(400, "Invalid JSON")

    text = body.get("text", "")
    language = body.get("language", "en")

    if not text:
        raise HTTPException(400, "No text provided")

    analyzer = get_analyzer()
    results = analyzer.analyze(
        text=text,
        language=language,
        entities=PII_ENTITIES
    )

    return {
        "text": text,
        "pii_found": len(results),
        "entities": [
            {
                "type": r.entity_type,
                "start": r.start,
                "end": r.end,
                "score": r.score,
                "text": text[r.start:r.end]
            }
            for r in results
        ]
    }


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8090)
