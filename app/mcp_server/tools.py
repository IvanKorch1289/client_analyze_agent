import os
import re
from datetime import datetime
from typing import Any, Dict, List, Optional

import aiofiles

from app.mcp_server.server import mcp
from app.services.fetch_data import fetch_company_info
from app.services.perplexity_client import PerplexityClient
from app.services.tavily_client import TavilyClient


@mcp.tool(
    name="Подсчёт количества файлов.",
    description="Подсчитывает количество файлов и папок в указанной директории.",
    tags={"catalog", "filesystem"},
)
async def count_files_in_directory(directory_path: str) -> Dict[str, Any]:
    """Подсчитывает количество файлов и папок в указанной директории.

    Используй, когда пользователь спрашивает о содержимом папки: сколько файлов, папок, их размер.
    Функция проверяет существование пути, права доступа и возвращает детальную статистику.

    Аргументы:
        directory_path (str): путь к директории (обязательный)

    Возвращает:
        Словарь с:
        - file_count: количество файлов
        - directory_count: количество подпапок
        - total_size_bytes: общий размер в байтах
        - files: список имён файлов
        - directories: список имён папок
        При ошибке — объект с полем 'error'.
    """
    try:
        if not os.path.exists(directory_path):
            return {
                "error": {
                    "type": "directory_not_found",
                    "message": f"Directory {directory_path} does not exist",
                }
            }

        if not os.path.isdir(directory_path):
            return {
                "error": {
                    "type": "not_a_directory",
                    "message": f"{directory_path} is not a directory",
                }
            }

        items = os.listdir(directory_path)
        files = []
        directories = []

        for item in items:
            full_path = os.path.join(directory_path, item)
            if os.path.isfile(full_path):
                files.append(item)
            elif os.path.isdir(full_path):
                directories.append(item)

        total_size = sum(
            os.path.getsize(os.path.join(directory_path, f)) for f in files
        )

        return {
            "status": "success",
            "directory": os.path.abspath(directory_path),
            "file_count": len(files),
            "directory_count": len(directories),
            "total_size_bytes": total_size,
            "files": files,
            "directories": directories,
            "summary": f"Found {len(files)} files and {len(directories)} directories",
        }
    except PermissionError:
        return {
            "error": {
                "type": "permission_denied",
                "message": f"Permission denied accessing {directory_path}",
            }
        }
    except Exception as e:
        return {
            "error": {
                "type": "unexpected_error",
                "message": f"Unexpected error: {str(e)}",
            }
        }


@mcp.tool(
    name="Возврат текущей даты.",
    description="Возвращает текущую дату и время в формате 'ГГГГ-ММ-ДД ЧЧ:ММ:СС.",
    tags={"catalog", "time"},
)
async def get_current_time() -> Dict[str, Any]:
    """Возвращает текущую дату и время в формате 'ГГГГ-ММ-ДД ЧЧ:ММ:СС'.

    Используй, когда пользователь спрашивает 'который час', 'сегодняшнюю дату' или 'текущее время'.
    Не используй, если в запросе есть 'не нужно время' или 'без даты'.

    Аргументы: отсутствуют.

    Возвращает:
       Структурированный словарь с датой и временем.
    """
    now = datetime.now()
    return {
        "status": "success",
        "current_time": now.strftime("%Y-%m-%d %H:%M:%S"),
        "timezone": "UTC+3",
        "summary": f"Текущее время: {now.strftime('%H:%M')}",
    }


@mcp.tool(
    name="Чтение файла.",
    description="Читает содержимое текстового файла и возвращает его как строку.",
    tags={"catalog", "filesystem"},
)
async def read_file_content(file_path: str) -> Dict[str, Any]:
    """Читает содержимое текстового файла и возвращает его как строку.

    Используй, когда нужно получить текст из файла для анализа, цитирования или проверки.
    Поддерживает только UTF-8. Проверяет существование файла и права доступа.

    Аргументы:
        file_path (str): путь к файлу (обязательный)

    Возвращает:
        Словарь с:
        - content: текст файла
        - size_bytes: размер в байтах
        - line_count: количество строк
        При ошибке — объект с полем 'error'.
    """
    try:
        if not os.path.exists(file_path):
            return {
                "error": {
                    "type": "file_not_found",
                    "message": f"File {file_path} does not exist",
                }
            }

        if not os.path.isfile(file_path):
            return {
                "error": {"type": "not_a_file", "message": f"{file_path} is not a file"}
            }

        async with aiofiles.open(file_path, "r", encoding="utf-8") as f:
            content = await f.read()

        return {
            "status": "success",
            "file_path": os.path.abspath(file_path),
            "content": content,
            "size_bytes": len(content.encode("utf-8")),
            "line_count": content.count("\n") + 1,
            "encoding": "utf-8",
            "summary": f"Successfully read {len(content)} characters",
        }
    except UnicodeDecodeError:
        return {
            "error": {
                "type": "encoding_error",
                "message": "Cannot decode file content as UTF-8 text",
            }
        }
    except PermissionError:
        return {
            "error": {
                "type": "permission_denied",
                "message": f"Permission denied reading {file_path}",
            }
        }
    except Exception as e:
        return {
            "error": {"type": "read_error", "message": f"Error reading file: {str(e)}"}
        }


@mcp.tool(
    name="Сохранение отчёта.",
    description="Сохраняет отчёт анализа в файл (.md или .txt).",
    tags={"catalog", "filesystem", "reports"},
)
async def save_report(
    content: str, filename: Optional[str] = None, format: str = "md"
) -> Dict[str, Any]:
    """Сохраняет отчёт анализа в файл.

    Используй для сохранения результатов анализа в файл.

    Аргументы:
        content (str): Содержимое отчёта (обязательный)
        filename (str, опционально): Имя файла. Генерируется автоматически, если не задано.
        format (str): Формат файла - md или txt (по умолчанию md)

    Возвращает:
        Словарь с путём к сохранённому файлу.
    """
    try:
        if filename and (
            "{" in filename or "}" in filename or "(" in filename or ")" in filename
        ):
            filename = None

        ext = ".md" if format == "md" else ".txt"
        
        if not filename:
            lines = content.splitlines()
            company_line = next(
                (
                    line
                    for line in lines
                    if "Наименование:" in line
                    or "Общество с ограниченной ответственностью" in line
                ),
                None,
            )
            if company_line:
                match = re.search(r'"([^"]+)"', company_line)
                company_name = match.group(1).replace(" ", "_") if match else "report"
            else:
                company_name = "report"

            now = datetime.now()
            timestamp = now.strftime("%Y%m%d_%H%M%S")
            filename = f"{company_name}-{timestamp}{ext}"
        else:
            filename = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "_", filename)
            if not filename.endswith((".txt", ".md")):
                filename += ext

        reports_dir = os.path.join(os.getcwd(), "reports")
        os.makedirs(reports_dir, exist_ok=True)
        filepath = os.path.join(reports_dir, filename)

        counter = 1
        original_name, file_ext = os.path.splitext(filename)
        while os.path.exists(filepath):
            filename = f"{original_name}_{counter}{file_ext}"
            filepath = os.path.join(reports_dir, filename)
            counter += 1

        async with aiofiles.open(filepath, "w", encoding="utf-8") as f:
            await f.write(content)

        return {
            "status": "success",
            "file_path": filepath,
            "filename": filename,
            "size_bytes": len(content.encode("utf-8")),
            "message": f"Report saved successfully at {filepath}",
            "summary": f"Report '{filename}' saved with {len(content)} characters",
        }
    except PermissionError:
        return {
            "error": {
                "type": "permission_denied",
                "message": "Permission denied: cannot create report file",
            }
        }
    except Exception as e:
        return {
            "error": {
                "type": "creation_error",
                "message": f"Error creating report: {str(e)}",
            }
        }


@mcp.tool(
    name="Получение информации о клиенте.",
    description="Получает полную информацию о компании по ИНН из DaData, Casebookm и InfoSphere.",
    tags={"catalog", "analyze"},
)
async def fetch_company_info_for_analyze(inn: str) -> Dict[str, Any]:
    """Получает полную информацию о компании по ИНН из DaData, Casebookm и InfoSphere.

    Используй, когда требуется анализ клиента, проверка юрлица, оценка рисков.
    Возвращает данные о статусе, руководителе, судебных делах, исполнительных производствах, поддержке.

    Аргументы:
        inn (str): ИНН компании (10 или 12 цифр, обязательный)

    Проверки:
        - Формат ИНН (только цифры, длина 10 или 12)
        - Существование компании

    Возвращает:
        Словарь с полями:
        - company_info: данные из DaData, InfoSphere, Casebook
        - inn: переданный ИНН
        При ошибке — объект с полем 'error'.
    """
    if not re.fullmatch(r"\d{10}|\d{12}", inn):
        return {
            "error": {
                "type": "invalid_inn",
                "message": "Invalid INN format. Must be 10 or 12 digits.",
            }
        }

    try:
        result = await fetch_company_info(inn)
        if "error" in result:
            return {
                "error": {"type": "company_fetch_failed", "message": result["error"]}
            }

        return {
            "status": "success",
            "company_info": result,
            "inn": inn,
            "summary": f"Successfully fetched data for INN {inn}",
        }
    except Exception as e:
        return {
            "error": {
                "type": "external_api_error",
                "message": f"Failed to fetch company info: {str(e)}",
            }
        }


@mcp.tool(
    name="Perplexity поиск",
    description="Поиск информации в интернете с помощью Perplexity AI. Возвращает актуальные данные с источниками.",
    tags={"catalog", "search", "ai"},
)
async def perplexity_search(
    query: str, search_recency: str = "month"
) -> Dict[str, Any]:
    """Поиск информации в интернете с помощью Perplexity AI.

    Используй для получения актуальной информации из интернета, когда нужны
    свежие данные, новости, факты или аналитика из веб-источников.

    Аргументы:
        query (str): Поисковый запрос (обязательный)
        search_recency (str): Фильтр по давности (day, week, month, year)

    Возвращает:
        Словарь с:
        - content: ответ от Perplexity
        - citations: список источников
        При ошибке — объект с полем 'error'.
    """
    client = PerplexityClient.get_instance()

    if not client.is_configured():
        return {
            "error": {
                "type": "not_configured",
                "message": "Perplexity API key not configured. Set PERPLEXITY_API_KEY environment variable.",
            }
        }

    try:
        result = await client.ask(
            question=query,
            system_prompt="Ты - полезный ассистент. Отвечай точно и кратко. Если вопрос на русском - отвечай на русском.",
            search_recency_filter=search_recency,
        )

        if not result.get("success"):
            return {
                "error": {
                    "type": "api_error",
                    "message": result.get("error", "Unknown error"),
                }
            }

        return {
            "status": "success",
            "content": result.get("content", ""),
            "citations": result.get("citations", []),
            "model": result.get("model"),
            "summary": f"Perplexity ответил на запрос: {query[:50]}...",
        }
    except Exception as e:
        return {
            "error": {
                "type": "perplexity_error",
                "message": f"Error calling Perplexity: {str(e)}",
            }
        }


@mcp.tool(
    name="Perplexity анализ",
    description="Анализ данных или документов с помощью Perplexity AI с возможностью поиска в интернете.",
    tags={"catalog", "analyze", "ai"},
)
async def perplexity_analyze(
    context: str, question: str, search_recency: str = "month"
) -> Dict[str, Any]:
    """Анализирует данные с помощью Perplexity AI.

    Используй для анализа предоставленных данных с возможностью дополнения
    информацией из интернета.

    Аргументы:
        context (str): Контекст/данные для анализа (обязательный)
        question (str): Вопрос для анализа (обязательный)
        search_recency (str): Фильтр по давности поиска (day, week, month, year)

    Возвращает:
        Словарь с результатом анализа и источниками.
    """
    client = PerplexityClient.get_instance()

    if not client.is_configured():
        return {
            "error": {
                "type": "not_configured",
                "message": "Perplexity API key not configured. Set PERPLEXITY_API_KEY environment variable.",
            }
        }

    messages = [
        {
            "role": "system",
            "content": "Ты - аналитик. Анализируй предоставленные данные и отвечай на вопросы. Используй поиск для дополнения информации. Отвечай на языке вопроса.",
        },
        {"role": "user", "content": f"Контекст:\n{context}\n\nВопрос: {question}"},
    ]

    try:
        result = await client.chat(
            messages=messages, search_recency_filter=search_recency
        )

        if not result.get("success"):
            return {
                "error": {
                    "type": "api_error",
                    "message": result.get("error", "Unknown error"),
                }
            }

        return {
            "status": "success",
            "analysis": result.get("content", ""),
            "citations": result.get("citations", []),
            "model": result.get("model"),
            "summary": f"Анализ выполнен: {question[:50]}...",
        }
    except Exception as e:
        return {
            "error": {
                "type": "perplexity_error",
                "message": f"Error calling Perplexity: {str(e)}",
            }
        }


@mcp.tool(
    name="Tavily поиск",
    description="Поиск информации в интернете с помощью Tavily Search API. Возвращает структурированные результаты с источниками.",
    tags={"catalog", "search", "web"},
)
async def tavily_search(
    query: str,
    search_depth: str = "basic",
    max_results: int = 5,
    include_answer: bool = True,
) -> Dict[str, Any]:
    """Поиск информации в интернете с помощью Tavily Search API.

    Используй для поиска актуальной информации из интернета с качественным
    ранжированием и структурированными результатами.

    Аргументы:
        query (str): Поисковый запрос (обязательный)
        search_depth (str): Глубина поиска - basic (быстрый) или advanced (глубокий)
        max_results (int): Максимальное количество результатов (1-10)
        include_answer (bool): Включить AI-сгенерированный ответ

    Возвращает:
        Словарь с:
        - answer: AI-сгенерированный ответ на запрос
        - results: список результатов с title, url, content, score
        При ошибке — объект с полем 'error'.
    """
    client = TavilyClient.get_instance()

    if not client.is_configured():
        return {
            "error": {
                "type": "not_configured",
                "message": "Tavily API key not configured. Set TAVILY_TOKEN environment variable.",
            }
        }

    try:
        result = await client.search(
            query=query,
            search_depth=search_depth,
            max_results=max_results,
            include_answer=include_answer,
        )

        if not result.get("success"):
            return {
                "error": {
                    "type": "api_error",
                    "message": result.get("error", "Unknown error"),
                }
            }

        formatted_results = []
        for r in result.get("results", []):
            formatted_results.append(
                {
                    "title": r.get("title", ""),
                    "url": r.get("url", ""),
                    "content": r.get("content", "")[:500],
                    "score": r.get("score", 0),
                }
            )

        return {
            "status": "success",
            "answer": result.get("answer", ""),
            "results": formatted_results,
            "results_count": len(formatted_results),
            "query": query,
            "response_time": result.get("response_time", 0),
            "summary": f"Найдено {len(formatted_results)} результатов для: {query[:50]}...",
        }
    except Exception as e:
        return {
            "error": {
                "type": "tavily_error",
                "message": f"Error calling Tavily: {str(e)}",
            }
        }


@mcp.tool(
    name="Tavily расширенный поиск",
    description="Расширенный поиск Tavily с фильтрацией по доменам и глубоким анализом.",
    tags={"catalog", "search", "web", "advanced"},
)
async def tavily_advanced_search(
    query: str,
    include_domains: Optional[List[str]] = None,
    exclude_domains: Optional[List[str]] = None,
    max_results: int = 10,
    include_raw_content: bool = False,
) -> Dict[str, Any]:
    """Расширенный поиск с фильтрацией по доменам.

    Используй для целевого поиска на определённых сайтах или исключения
    нежелательных источников. Например, поиск только на официальных
    государственных сайтах или исключение агрегаторов.

    Аргументы:
        query (str): Поисковый запрос (обязательный)
        include_domains (List[str]): Искать только на этих доменах (опционально)
        exclude_domains (List[str]): Исключить эти домены (опционально)
        max_results (int): Максимальное количество результатов (1-10)
        include_raw_content (bool): Включить полный HTML контент

    Возвращает:
        Расширенные результаты поиска с фильтрацией.
    """
    client = TavilyClient.get_instance()

    if not client.is_configured():
        return {
            "error": {
                "type": "not_configured",
                "message": "Tavily API key not configured. Set TAVILY_TOKEN environment variable.",
            }
        }

    try:
        result = await client.search(
            query=query,
            search_depth="advanced",
            max_results=max_results,
            include_answer=True,
            include_raw_content=include_raw_content,
            include_domains=include_domains,
            exclude_domains=exclude_domains,
        )

        if not result.get("success"):
            return {
                "error": {
                    "type": "api_error",
                    "message": result.get("error", "Unknown error"),
                }
            }

        formatted_results = []
        for r in result.get("results", []):
            item = {
                "title": r.get("title", ""),
                "url": r.get("url", ""),
                "content": r.get("content", ""),
                "score": r.get("score", 0),
            }
            if include_raw_content and r.get("raw_content"):
                item["raw_content"] = r.get("raw_content", "")[:2000]
            formatted_results.append(item)

        return {
            "status": "success",
            "answer": result.get("answer", ""),
            "results": formatted_results,
            "results_count": len(formatted_results),
            "query": query,
            "filters": {
                "include_domains": include_domains or [],
                "exclude_domains": exclude_domains or [],
            },
            "summary": f"Расширенный поиск: {len(formatted_results)} результатов",
        }
    except Exception as e:
        return {
            "error": {
                "type": "tavily_error",
                "message": f"Error calling Tavily: {str(e)}",
            }
        }


@mcp.tool(
    name="Tavily статус сервиса",
    description="Проверка статуса и метрик Tavily API - circuit breaker, кэш, счётчики запросов.",
    tags={"catalog", "monitoring", "web"},
)
async def tavily_status() -> Dict[str, Any]:
    """Получает статус Tavily API сервиса.

    Используй для мониторинга состояния подключения к Tavily,
    проверки circuit breaker, кэша и метрик.

    Возвращает:
        Статус сервиса, метрики и информацию о кэше.
    """
    client = TavilyClient.get_instance()

    try:
        status = await client.get_status()

        return {
            "status": "success",
            "service": "tavily",
            "configured": status.get("configured", False),
            "circuit_breaker": status.get("circuit_breaker", {}),
            "metrics": status.get("metrics", {}),
            "cache_stats": status.get("cache_stats", {}),
            "summary": "Tavily API "
            + ("доступен" if status.get("configured") else "не настроен"),
        }
    except Exception as e:
        return {
            "error": {
                "type": "status_error",
                "message": f"Error getting Tavily status: {str(e)}",
            }
        }
