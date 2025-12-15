"""
Search Agent: выполняет параллельный поиск через Perplexity API.
"""
import asyncio
from typing import Any, Dict, List

from app.advanced_funcs.logging_client import logger
from app.services.perplexity_client import PerplexityClient


async def search_single_intent(
    client: PerplexityClient,
    intent: Dict[str, str]
) -> Dict[str, Any]:
    """Выполняет один поисковый запрос."""
    intent_id = intent.get("id", "unknown")
    query = intent.get("query", "")
    description = intent.get("description", "")
    
    try:
        result = await client.ask(
            question=query,
            system_prompt=(
                "Ты - аналитик бизнес-разведки. Найди и кратко изложи информацию по запросу. "
                "Выдели позитивные и негативные факты. Отвечай на русском языке. "
                "Укажи источники информации."
            ),
            search_recency_filter="month"
        )
        
        if result.get("success"):
            content = result.get("content", "")
            sentiment = analyze_sentiment(content)
            
            return {
                "intent_id": intent_id,
                "description": description,
                "query": query,
                "success": True,
                "content": content,
                "citations": result.get("citations", []),
                "sentiment": sentiment,
                "sentiment_score": sentiment["score"]
            }
        else:
            return {
                "intent_id": intent_id,
                "description": description,
                "query": query,
                "success": False,
                "error": result.get("error", "Unknown error"),
                "sentiment": {"label": "unknown", "score": 0}
            }
            
    except Exception as e:
        logger.error(f"Search error for intent {intent_id}: {e}", component="search_agent")
        return {
            "intent_id": intent_id,
            "description": description,
            "query": query,
            "success": False,
            "error": str(e),
            "sentiment": {"label": "unknown", "score": 0}
        }


def analyze_sentiment(text: str) -> Dict[str, Any]:
    """
    Простой анализ тональности на основе ключевых слов.
    Returns: {"label": "positive"|"negative"|"neutral", "score": -1.0 to 1.0}
    """
    text_lower = text.lower()
    
    negative_words = [
        "банкрот", "долг", "суд", "иск", "штраф", "нарушен", "проблем",
        "скандал", "мошен", "обман", "жалоб", "претензи", "убыт",
        "риск", "опасн", "негатив", "плох", "ухудш", "кризис"
    ]
    
    positive_words = [
        "рост", "прибыл", "успех", "надежн", "стабильн", "лидер",
        "качеств", "довольн", "рекоменд", "хорош", "отличн", "позитив",
        "развит", "инновац", "партнер", "доверие", "награ"
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


async def search_agent(state: Dict[str, Any]) -> Dict[str, Any]:
    """
    Агент поиска: выполняет параллельные запросы к Perplexity.
    
    Входные данные:
        - search_intents: List[Dict] - список поисковых запросов от оркестратора
    
    Выходные данные:
        - search_results: List[Dict] - результаты поиска с sentiment analysis
        - current_step: str
    """
    search_intents = state.get("search_intents", [])
    
    if not search_intents:
        logger.warning("Search Agent: no search intents provided", component="search_agent")
        return {
            **state,
            "search_results": [],
            "current_step": "analyzing",
            "search_error": "No search intents"
        }
    
    client = PerplexityClient.get_instance()
    
    if not client.is_configured():
        logger.error("Search Agent: Perplexity API key not configured", component="search_agent")
        return {
            **state,
            "search_results": [],
            "current_step": "analyzing",
            "search_error": "Perplexity API key not configured"
        }
    
    logger.info(f"Search Agent: запуск {len(search_intents)} параллельных поисков", component="search_agent")
    
    tasks = [search_single_intent(client, intent) for intent in search_intents]
    results = await asyncio.gather(*tasks, return_exceptions=True)
    
    search_results = []
    for i, result in enumerate(results):
        if isinstance(result, Exception):
            search_results.append({
                "intent_id": search_intents[i].get("id", f"unknown_{i}"),
                "success": False,
                "error": str(result),
                "sentiment": {"label": "unknown", "score": 0}
            })
        else:
            search_results.append(result)
    
    successful = sum(1 for r in search_results if r.get("success"))
    logger.info(
        f"Search Agent: завершено {successful}/{len(search_results)} успешных запросов",
        component="search_agent"
    )
    
    return {
        **state,
        "search_results": search_results,
        "current_step": "analyzing"
    }
