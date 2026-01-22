"""
Result builders for data collection.

Contains functions for building and converting search results
from various data sources into a unified format.
"""

from typing import Any, Dict, List

from app.config import MAX_CONTENT_LENGTH
from app.shared.utils.formatters import truncate


def build_search_results(source_data: Dict[str, Any], intents: List[Dict[str, str]]) -> List[Dict[str, Any]]:
    """Собирает единый массив search_results для report_analyzer."""
    search_results = []

    # 1) Реестровые источники (по ИНН)
    search_results.extend(convert_registry_sources_to_search_results(source_data))

    # 2) Веб-поиск по интентам: Perplexity + Tavily -> объединяем в один результат на интент
    perpl = source_data.get("perplexity", {}) or {}
    tav = source_data.get("tavily", {}) or {}

    perpl_intents = perpl.get("intents", {}) if isinstance(perpl, dict) else {}
    tav_intents = tav.get("intents", {}) if isinstance(tav, dict) else {}

    for intent in intents:
        intent_id = str(intent.get("id") or "unknown")
        description = str(intent.get("description") or intent_id)
        query = str(intent.get("query") or "")

        perpl_res = perpl_intents.get(intent_id, {}) if isinstance(perpl_intents, dict) else {}
        tav_res = tav_intents.get(intent_id, {}) if isinstance(tav_intents, dict) else {}

        content_parts: List[str] = []
        citations: List[str] = []
        success = False

        if isinstance(perpl_res, dict) and perpl_res.get("success"):
            perpl_content = perpl_res.get("content", "") or ""
            if perpl_content:
                content_parts.append(f"[Perplexity]\n{perpl_content}")
            citations.extend(perpl_res.get("citations", []) or [])
            success = True

        if isinstance(tav_res, dict) and tav_res.get("success"):
            answer = tav_res.get("answer", "") or ""
            results_text = "\n".join(
                [
                    (r.get("content", "") or r.get("snippet", "") or "").strip()
                    for r in (tav_res.get("results", []) or [])[:3]
                    if isinstance(r, dict)
                ]
            ).strip()
            tav_block = "\n\n".join([p for p in [answer, results_text] if p]).strip()
            if tav_block:
                content_parts.append(f"[Tavily]\n{truncate(tav_block, max_length=1600)}")
            citations.extend(
                [r.get("url") for r in (tav_res.get("results", []) or []) if isinstance(r, dict) and r.get("url")]
            )
            success = True

        combined = truncate("\n\n".join([p for p in content_parts if p]).strip(), MAX_CONTENT_LENGTH)
        if not combined:
            search_results.append(
                {
                    "intent_id": intent_id,
                    "description": description,
                    "query": query,
                    "success": False,
                    "content": "",
                    "citations": [],
                    "sentiment": {"label": "neutral", "score": 0.0},
                }
            )
            continue

        search_results.append(
            {
                "intent_id": intent_id,
                "description": description,
                "query": query,
                "success": success,
                "content": combined,
                "citations": list(dict.fromkeys([c for c in citations if c]))[:20],
                "sentiment": analyze_sentiment(combined),
            }
        )

    return search_results


def convert_registry_sources_to_search_results(
    source_data: Dict[str, Any],
) -> List[Dict[str, Any]]:
    """Конвертирует DaData/Casebook/InfoSphere в формат search_results."""
    search_results: List[Dict[str, Any]] = []

    dadata = source_data.get("dadata", {})
    if dadata and dadata.get("success"):
        data = dadata.get("data", {})
        content = f"Компания: {data.get('name', {}).get('full_with_opf', 'Н/Д')}\n"
        content += f"Статус: {data.get('state', {}).get('status', 'Н/Д')}\n"
        content += f"Адрес: {data.get('address', {}).get('value', 'Н/Д')}"

        status = data.get("state", {}).get("status", "")
        sentiment = {"label": "negative", "score": -0.5} if status == "LIQUIDATED" else {"label": "neutral", "score": 0}

        search_results.append(
            {
                "intent_id": "dadata_info",
                "description": "Реестровые данные (DaData)",
                "query": "Информация из ЕГРЮЛ",
                "success": True,
                "content": content,
                "citations": [],
                "sentiment": sentiment,
            }
        )

    casebook = source_data.get("casebook", {})
    if casebook and casebook.get("success"):
        cases = casebook.get("data", [])
        case_count = len(cases)
        content = f"Найдено судебных дел: {case_count}"
        if case_count > 0:
            content += f"\nПоследние дела: {', '.join([str(c.get('caseNumber', '')) for c in cases[:5]])}"

        if case_count > 10:
            sentiment = {"label": "negative", "score": -0.7}
        elif case_count > 3:
            sentiment = {"label": "negative", "score": -0.3}
        else:
            sentiment = {"label": "neutral", "score": 0}

        search_results.append(
            {
                "intent_id": "lawsuits",
                "description": "Судебные дела (Casebook)",
                "query": "Арбитражные дела",
                "success": True,
                "content": content,
                "citations": [],
                "sentiment": sentiment,
            }
        )

    infosphere = source_data.get("infosphere", {})
    if infosphere and infosphere.get("success"):
        data = infosphere.get("data", {})
        content = f"Проверка по базам: {len(data) if isinstance(data, list) else 'выполнена'}"
        search_results.append(
            {
                "intent_id": "infosphere_check",
                "description": "Проверка контрагента (InfoSphere)",
                "query": "Проверка по базам данных",
                "success": True,
                "content": content,
                "citations": [],
                "sentiment": {"label": "neutral", "score": 0},
            }
        )

    return search_results


def analyze_sentiment(text: str) -> Dict[str, Any]:
    """Простой анализ тональности текста."""
    if not text:
        return {"label": "neutral", "score": 0.0}

    text_lower = text.lower()

    negative_words = [
        "банкрот",
        "долг",
        "суд",
        "иск",
        "штраф",
        "нарушен",
        "проблем",
        "риск",
        "опасн",
        "негатив",
        "плох",
        "ухудш",
        "кризис",
        "ликвидир",
    ]
    positive_words = [
        "рост",
        "прибыл",
        "успех",
        "надежн",
        "стабильн",
        "лидер",
        "качеств",
        "довольн",
        "рекоменд",
        "хорош",
        "отличн",
        "позитив",
    ]

    neg_count = sum(1 for word in negative_words if word in text_lower)
    pos_count = sum(1 for word in positive_words if word in text_lower)

    total = neg_count + pos_count
    if total == 0:
        return {"label": "neutral", "score": 0.0}

    score = (pos_count - neg_count) / max(total, 1)
    score = max(-1.0, min(1.0, score))

    if score > 0.2:
        label = "positive"
    elif score < -0.2:
        label = "negative"
    else:
        label = "neutral"

    return {"label": label, "score": round(score, 2)}


__all__ = [
    "build_search_results",
    "convert_registry_sources_to_search_results",
    "analyze_sentiment",
]
