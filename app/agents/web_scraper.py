"""
Web Scraper Agent: скрейпинг полных текстов из TOP ссылок.

Используется для получения полного содержимого страниц из результатов Tavily
для более глубокого анализа LLM.
"""

import asyncio
import re
from typing import Any, Dict, List

import httpx

from app.shared.utils.formatters import truncate
from app.utility.logging_client import logger

# Попытка импорта BeautifulSoup (опционально)
try:
    from bs4 import BeautifulSoup

    HAS_BS4 = True
except ImportError:
    HAS_BS4 = False
    logger.warning(
        "BeautifulSoup not installed. Using regex-based HTML cleaning. Install: pip install beautifulsoup4",
        component="web_scraper",
    )

# Конфигурация
MAX_PAGE_CONTENT_LENGTH = 10000  # 10k символов на страницу
SCRAPE_TIMEOUT_SECONDS = 15  # Таймаут на одну страницу
MAX_CONCURRENT_SCRAPES = 3  # Максимум параллельных запросов
USER_AGENT = "Mozilla/5.0 (compatible; AnalyzeAgent/1.0; +https://example.com/bot)"


async def scrape_top_tavily_links(
    tavily_results: List[Dict[str, Any]],
    *,
    top_n: int = 5,
    max_content_length: int = MAX_PAGE_CONTENT_LENGTH,
) -> List[Dict[str, Any]]:
    """
    Скрейпит полные тексты из TOP-N ссылок Tavily.

    Args:
        tavily_results: Результаты поиска Tavily (list of dicts с url, title, content)
        top_n: Количество ссылок для скрейпинга (default: 5)
        max_content_length: Максимальная длина текста с одной страницы

    Returns:
        List[Dict] с url, full_content, title, error

    Examples:
        >>> results = [{"url": "https://...", "title": "...", "score": 0.9}, ...]
        >>> full_texts = await scrape_top_tavily_links(results, top_n=5)
        >>> # [{"url": "...", "full_content": "...", "title": "..."}, ...]
    """
    if not tavily_results:
        return []

    # Фильтруем и сортируем по score
    valid_results = [r for r in tavily_results if r.get("url") and isinstance(r.get("url"), str)]

    # Сортировка по релевантности (score)
    valid_results.sort(key=lambda x: x.get("score", 0), reverse=True)

    # Берём TOP-N
    top_links = valid_results[:top_n]

    if not top_links:
        logger.warning("Web scraper: no valid URLs to scrape", component="web_scraper")
        return []

    logger.info(
        f"Web scraper: starting scrape of {len(top_links)} URLs",
        component="web_scraper",
    )

    # Ограничение параллельности
    semaphore = asyncio.Semaphore(MAX_CONCURRENT_SCRAPES)

    async def _scrape_with_semaphore(result: Dict) -> Dict[str, Any]:
        async with semaphore:
            return await _scrape_single_page(
                url=result["url"],
                title=result.get("title", ""),
                max_content_length=max_content_length,
            )

    # Параллельный скрейпинг
    full_texts = await asyncio.gather(*[_scrape_with_semaphore(r) for r in top_links], return_exceptions=True)

    # Фильтруем исключения
    valid_texts = []
    for item in full_texts:
        if isinstance(item, Exception):
            logger.error(f"Web scraper: exception during scrape: {item}", component="web_scraper")
            continue
        if isinstance(item, dict):
            valid_texts.append(item)

    total_chars = sum(len(t.get("full_content", "")) for t in valid_texts)
    scraped_count = sum(1 for t in valid_texts if t.get("full_content"))

    logger.info(
        f"Web scraper: completed. scraped_pages={scraped_count}/{len(top_links)}, total_chars={total_chars}",
        component="web_scraper",
    )

    return valid_texts


async def _scrape_single_page(
    url: str,
    title: str = "",
    max_content_length: int = MAX_PAGE_CONTENT_LENGTH,
) -> Dict[str, Any]:
    """
    Скрейпит одну страницу.

    Args:
        url: URL страницы
        title: Заголовок (из Tavily)
        max_content_length: Макс длина текста

    Returns:
        Dict с url, full_content, title, error
    """
    try:
        async with httpx.AsyncClient(
            timeout=SCRAPE_TIMEOUT_SECONDS,
            follow_redirects=True,
            headers={"User-Agent": USER_AGENT},
        ) as client:
            response = await client.get(url)
            response.raise_for_status()

            # Проверка content-type (только HTML)
            content_type = response.headers.get("content-type", "")
            if "text/html" not in content_type.lower():
                return {
                    "url": url,
                    "title": title,
                    "full_content": "",
                    "error": f"Not HTML: {content_type}",
                }

            # Парсинг HTML
            if HAS_BS4:
                # Используем BeautifulSoup (лучшее качество)
                soup = BeautifulSoup(response.text, "html.parser")

                # Удаляем script, style, nav, footer
                for tag in soup(["script", "style", "nav", "footer", "header", "aside"]):
                    tag.decompose()

                # Извлекаем текст
                text = soup.get_text(separator="\n", strip=True)
            else:
                # Fallback: regex-based очистка (хуже, но работает)
                text = _clean_html_regex(response.text)

            # Очистка (убираем лишние пробелы, переносы)
            lines = [line.strip() for line in text.split("\n") if line.strip()]
            clean_text = "\n".join(lines)

            # Обрезка до max_content_length
            final_text = truncate(clean_text, max_content_length)

            logger.debug(
                f"Web scraper: scraped {url} ({len(final_text)} chars)",
                component="web_scraper",
            )

            return {
                "url": url,
                "title": title,
                "full_content": final_text,
                "char_count": len(final_text),
                "error": None,
            }

    except httpx.TimeoutException:
        logger.warning(f"Web scraper: timeout for {url}", component="web_scraper")
        return {
            "url": url,
            "title": title,
            "full_content": "",
            "error": "Timeout",
        }
    except httpx.HTTPError as e:
        logger.warning(f"Web scraper: HTTP error for {url}: {e}", component="web_scraper")
        return {
            "url": url,
            "title": title,
            "full_content": "",
            "error": f"HTTP {e.response.status_code if hasattr(e, 'response') else 'error'}",
        }
    except Exception as e:
        logger.error(f"Web scraper: unexpected error for {url}: {e}", component="web_scraper")
        return {
            "url": url,
            "title": title,
            "full_content": "",
            "error": str(e),
        }


async def scrape_urls_batch(
    urls: List[str],
    *,
    max_concurrent: int = MAX_CONCURRENT_SCRAPES,
    max_content_length: int = MAX_PAGE_CONTENT_LENGTH,
) -> List[Dict[str, Any]]:
    """
    Скрейпит список URL с ограничением параллельности.

    Args:
        urls: Список URL для скрейпинга
        max_concurrent: Максимум параллельных запросов
        max_content_length: Макс длина текста с страницы

    Returns:
        List[Dict] с результатами скрейпинга
    """
    semaphore = asyncio.Semaphore(max_concurrent)

    async def _scrape_with_sem(url: str) -> Dict[str, Any]:
        async with semaphore:
            return await _scrape_single_page(url, "", max_content_length)

    results = await asyncio.gather(*[_scrape_with_sem(url) for url in urls], return_exceptions=True)

    # Фильтруем исключения
    return [r for r in results if isinstance(r, dict)]


def _clean_html_regex(html: str) -> str:
    """
    Fallback: очистка HTML через regex (если нет BeautifulSoup).

    Менее качественно, но работает без зависимостей.
    """
    # Удаляем script и style теги с содержимым
    html = re.sub(r"<script[^>]*>.*?</script>", "", html, flags=re.DOTALL | re.IGNORECASE)
    html = re.sub(r"<style[^>]*>.*?</style>", "", html, flags=re.DOTALL | re.IGNORECASE)

    # Удаляем HTML теги
    html = re.sub(r"<[^>]+>", " ", html)

    # Декодируем HTML entities
    html = html.replace("&nbsp;", " ")
    html = html.replace("&lt;", "<")
    html = html.replace("&gt;", ">")
    html = html.replace("&amp;", "&")
    html = html.replace("&quot;", '"')
    html = html.replace("&#39;", "'")

    # Убираем множественные пробелы
    html = re.sub(r"\s+", " ", html)

    return html.strip()


__all__ = [
    "scrape_top_tavily_links",
    "scrape_urls_batch",
]
