"""
Процессор документов для RAG.

Поддерживает:
- PDF (PyPDF2)
- DOCX (python-docx)
- TXT / Markdown

Выполняет:
1. Извлечение текста из файла
2. PII маскировку (через Presidio)
3. Разбивку на чанки с overlap
"""

from __future__ import annotations

import io
from typing import List, Tuple

from app.utility.logging_client import logger

# Допустимые MIME типы
ALLOWED_CONTENT_TYPES = {
    "application/pdf": "pdf",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document": "docx",
    "text/plain": "txt",
    "text/markdown": "md",
}

ALLOWED_EXTENSIONS = {".pdf", ".docx", ".txt", ".md"}


def parse_file(file_content: bytes, filename: str) -> str:
    """
    Извлекает текст из файла.

    Args:
        file_content: Бинарное содержимое файла
        filename: Имя файла (для определения типа)

    Returns:
        Извлечённый текст

    Raises:
        ValueError: Если формат не поддерживается
    """
    ext = _get_extension(filename)

    if ext == ".pdf":
        return _parse_pdf(file_content)
    elif ext == ".docx":
        return _parse_docx(file_content)
    elif ext in (".txt", ".md"):
        return file_content.decode("utf-8", errors="replace")
    else:
        raise ValueError(f"Unsupported file format: {ext}")


def chunk_text(
    text: str,
    chunk_size: int = 800,
    chunk_overlap: int = 100,
) -> List[str]:
    """
    Разбивает текст на чанки с перекрытием.

    Args:
        text: Входной текст
        chunk_size: Размер чанка в символах
        chunk_overlap: Перекрытие между чанками

    Returns:
        Список текстовых чанков
    """
    if not text or not text.strip():
        return []

    text = text.strip()

    if len(text) <= chunk_size:
        return [text]

    chunks: List[str] = []
    start = 0

    while start < len(text):
        end = start + chunk_size

        # Не обрезаем посередине слова — ищем ближайший пробел/перенос
        if end < len(text):
            # Пробуем найти конец предложения
            for sep in ("\n\n", "\n", ". ", "! ", "? ", " "):
                last_sep = text.rfind(sep, start + chunk_size // 2, end)
                if last_sep > start:
                    end = last_sep + len(sep)
                    break

        chunk = text[start:end].strip()
        if chunk:
            chunks.append(chunk)

        start = end - chunk_overlap
        if start >= len(text):
            break

    return chunks


def mask_pii_in_text(text: str) -> Tuple[str, bool]:
    """
    Маскирует PII в тексте перед индексацией в RAG.

    Args:
        text: Входной текст

    Returns:
        Tuple[masked_text, had_pii]
    """
    try:
        from app.shared.pii_protection import mask_pii

        result = mask_pii(text, mask_level="medium")
        if hasattr(result, "masked_text"):
            return result.masked_text, bool(result.replacements)
        # Fallback: если mask_pii возвращает строку
        return str(result), False
    except ImportError:
        logger.debug("PII masking not available, skipping", component="rag")
        return text, False
    except Exception as e:
        logger.warning(f"PII masking failed, using raw text: {e}", component="rag")
        return text, False


def validate_upload(filename: str, file_size: int, max_size_mb: int = 10) -> None:
    """
    Валидирует загружаемый файл.

    Raises:
        ValueError: Если файл не проходит валидацию
    """
    ext = _get_extension(filename)
    if ext not in ALLOWED_EXTENSIONS:
        raise ValueError(f"Формат {ext} не поддерживается. Допустимые: {', '.join(sorted(ALLOWED_EXTENSIONS))}")

    max_bytes = max_size_mb * 1024 * 1024
    if file_size > max_bytes:
        raise ValueError(f"Файл слишком большой: {file_size / 1024 / 1024:.1f}MB. Максимум: {max_size_mb}MB")


# =============================================================================
# INTERNAL PARSERS
# =============================================================================


_MAX_PDF_PAGES = 500
_MAX_PDF_CHARS = 5_000_000  # 5 MB of text


def _parse_pdf(content: bytes) -> str:
    """Извлекает текст из PDF с ограничением по страницам и объёму."""
    try:
        from PyPDF2 import PdfReader

        reader = PdfReader(io.BytesIO(content))

        if len(reader.pages) > _MAX_PDF_PAGES:
            logger.warning(
                f"PDF has {len(reader.pages)} pages, truncating to {_MAX_PDF_PAGES}",
                component="rag",
            )

        pages = []
        total_chars = 0
        for idx, page in enumerate(reader.pages):
            if idx >= _MAX_PDF_PAGES:
                break
            text = page.extract_text()
            if text:
                if total_chars + len(text) > _MAX_PDF_CHARS:
                    pages.append(text[: _MAX_PDF_CHARS - total_chars])
                    total_chars = _MAX_PDF_CHARS
                    break
                pages.append(text)
                total_chars += len(text)

        result = "\n\n".join(pages)
        logger.debug(
            f"PDF parsed: {min(len(reader.pages), _MAX_PDF_PAGES)}/{len(reader.pages)} pages, {len(result)} chars",
            component="rag",
        )
        return result

    except Exception as e:
        logger.error(f"PDF parsing failed: {e}", component="rag")
        raise ValueError(f"Не удалось прочитать PDF: {e}")


def _parse_docx(content: bytes) -> str:
    """Извлекает текст из DOCX."""
    try:
        from docx import Document

        doc = Document(io.BytesIO(content))
        paragraphs = []
        for para in doc.paragraphs:
            text = para.text.strip()
            if text:
                paragraphs.append(text)

        result = "\n\n".join(paragraphs)
        logger.debug(
            f"DOCX parsed: {len(paragraphs)} paragraphs, {len(result)} chars",
            component="rag",
        )
        return result

    except Exception as e:
        logger.error(f"DOCX parsing failed: {e}", component="rag")
        raise ValueError(f"Не удалось прочитать DOCX: {e}")


def _get_extension(filename: str) -> str:
    """Получает расширение файла в нижнем регистре."""
    import os

    _, ext = os.path.splitext(filename.lower())
    return ext
