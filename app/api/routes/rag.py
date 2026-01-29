"""
API маршруты для RAG (Retrieval Augmented Generation).

Endpoints:
- POST /rag/reports/{report_id}/index — Индексировать отчёт (ручное подтверждение)
- DELETE /rag/reports/{report_id} — Удалить отчёт из RAG
- GET /rag/reports — Список проиндексированных отчётов
- GET /rag/reports/{report_id}/similar — Похожие отчёты
- POST /rag/search — Семантический поиск
- POST /rag/documents/upload — Загрузка файла в RAG
- GET /rag/documents — Список загруженных документов
- DELETE /rag/documents/{doc_id} — Удалить документ
- GET /rag/stats — Статистика RAG
"""

from __future__ import annotations

import time
import uuid
from typing import Any, Dict, Optional

from fastapi import APIRouter, File, HTTPException, Query, Request, UploadFile
from pydantic import BaseModel, Field

from app.utility.logging_client import logger

rag_router = APIRouter(prefix="/rag", tags=["RAG"])


# =============================================================================
# REQUEST / RESPONSE MODELS
# =============================================================================


class SearchRequest(BaseModel):
    query: str = Field(..., description="Текст поискового запроса")
    k: int = Field(default=10, ge=1, le=50, description="Количество результатов")
    collection: Optional[str] = Field(default=None, description="Коллекция: reports, documents или null (обе)")


class IndexReportResponse(BaseModel):
    status: str
    report_id: str
    vector_id: str
    client_name: Optional[str] = None
    inn: Optional[str] = None


# =============================================================================
# GUARD: проверяет что RAG включён
# =============================================================================


def _check_rag_enabled() -> None:
    from app.config.settings import settings

    if not settings.chroma.enabled:
        raise HTTPException(
            status_code=503,
            detail="RAG подсистема отключена. Установите CHROMA_ENABLED=true",
        )


# =============================================================================
# REPORTS
# =============================================================================


@rag_router.post(
    "/reports/{report_id}/index",
    response_model=IndexReportResponse,
    summary="Индексировать отчёт в RAG",
)
async def index_report(request: Request, report_id: str):
    """
    Индексация отчёта в векторную БД (Chroma).

    Процесс:
    1. Получает отчёт из Tarantool по report_id
    2. Генерирует embedding из findings + summary + risk
    3. Сохраняет в Chroma коллекцию reports

    Требует ручного подтверждения (не автоматический).
    """
    _check_rag_enabled()

    from app.services.chroma_service import get_chroma_service
    from app.services.embedding_service import get_embedding_service
    from app.storage.tarantool import TarantoolClient

    # 1. Получаем отчёт из Tarantool
    client = await TarantoolClient.get_instance()
    reports_repo = client.get_reports_repository()
    report_data = await reports_repo.get(report_id)

    if not report_data:
        raise HTTPException(status_code=404, detail=f"Отчёт {report_id} не найден в Tarantool")

    # 2. Генерируем embedding
    emb_service = get_embedding_service()
    embedding = emb_service.embed_report(report_data)

    # 3. Формируем текст и метаданные
    report_content = report_data.get("report", {})
    text_parts = []
    if report_data.get("client_name"):
        text_parts.append(f"Клиент: {report_data['client_name']}")
    if report_data.get("inn"):
        text_parts.append(f"ИНН: {report_data['inn']}")
    if report_content.get("summary"):
        text_parts.append(f"Резюме: {report_content['summary']}")

    findings = report_content.get("findings", [])
    if findings:
        text_parts.append("Выводы: " + "; ".join(str(f) for f in findings[:20]))

    text = "\n".join(text_parts) or "Отчёт без содержимого"

    risk = report_content.get("risk_assessment", {})
    metadata = {
        "report_id": report_id,
        "client_name": report_data.get("client_name", ""),
        "inn": report_data.get("inn", ""),
        "risk_score": risk.get("overall_score", risk.get("score", 0)),
        "risk_level": risk.get("level", risk.get("risk_level", "")),
        "session_id": report_data.get("session_id", ""),
        "created_at": report_data.get("created_at", ""),
    }

    # 4. Сохраняем в Chroma
    chroma = get_chroma_service()
    vector_id = chroma.add_report(
        report_id=report_id,
        embedding=embedding,
        text=text,
        metadata=metadata,
    )

    logger.structured(
        "info",
        "report_indexed_in_rag",
        component="rag_api",
        report_id=report_id,
        client_name=report_data.get("client_name"),
        inn=report_data.get("inn"),
    )

    return IndexReportResponse(
        status="indexed",
        report_id=report_id,
        vector_id=vector_id,
        client_name=report_data.get("client_name"),
        inn=report_data.get("inn"),
    )


@rag_router.delete("/reports/{report_id}", summary="Удалить отчёт из RAG")
async def delete_report_from_rag(report_id: str):
    _check_rag_enabled()

    from app.services.chroma_service import get_chroma_service

    chroma = get_chroma_service()
    ok = chroma.delete_report(report_id)
    if not ok:
        raise HTTPException(status_code=404, detail="Отчёт не найден в RAG")
    return {"status": "deleted", "report_id": report_id}


@rag_router.get("/reports", summary="Список проиндексированных отчётов")
async def list_indexed_reports(
    offset: int = Query(default=0, ge=0),
    limit: int = Query(default=50, ge=1, le=200),
):
    _check_rag_enabled()

    from app.services.chroma_service import get_chroma_service

    chroma = get_chroma_service()
    return chroma.list_reports(offset=offset, limit=limit)


@rag_router.get("/reports/{report_id}/similar", summary="Похожие отчёты")
async def find_similar_reports(report_id: str, k: int = Query(default=5, ge=1, le=20)):
    _check_rag_enabled()

    from app.services.chroma_service import get_chroma_service
    from app.services.embedding_service import get_embedding_service
    from app.storage.tarantool import TarantoolClient

    # Получаем отчёт и его embedding
    client = await TarantoolClient.get_instance()
    reports_repo = client.get_reports_repository()
    report_data = await reports_repo.get(report_id)

    if not report_data:
        raise HTTPException(status_code=404, detail=f"Отчёт {report_id} не найден")

    emb_service = get_embedding_service()
    query_embedding = emb_service.embed_report(report_data)

    chroma = get_chroma_service()
    results = chroma.search_similar_reports(query_embedding, k=k + 1)

    # Исключаем сам отчёт из результатов
    own_id = f"report:{report_id}"
    results = [r for r in results if r["id"] != own_id][:k]

    return {"report_id": report_id, "similar": results, "count": len(results)}


# =============================================================================
# SEMANTIC SEARCH
# =============================================================================


@rag_router.post("/search", summary="Семантический поиск")
async def semantic_search(req: SearchRequest):
    _check_rag_enabled()

    from app.services.chroma_service import get_chroma_service
    from app.services.embedding_service import get_embedding_service

    emb_service = get_embedding_service()
    query_embedding = emb_service.embed_text(req.query)

    chroma = get_chroma_service()
    results = chroma.semantic_search(
        query_embedding=query_embedding,
        k=req.k,
        collection=req.collection,
    )

    return {"query": req.query, "results": results, "count": len(results)}


# =============================================================================
# DOCUMENTS (file upload)
# =============================================================================


@rag_router.post("/documents/upload", summary="Загрузить файл в RAG")
async def upload_document(file: UploadFile = File(...)):
    """
    Загрузка файла (PDF, DOCX, TXT, MD) в RAG.

    Процесс:
    1. Валидация файла (формат, размер)
    2. Извлечение текста
    3. PII маскировка
    4. Разбивка на чанки
    5. Генерация embeddings
    6. Сохранение в Chroma
    """
    _check_rag_enabled()

    from app.config.settings import settings
    from app.services.chroma_service import get_chroma_service
    from app.services.document_processor import (
        chunk_text,
        mask_pii_in_text,
        parse_file,
        validate_upload,
    )
    from app.services.embedding_service import get_embedding_service

    # 1. Читаем содержимое
    content = await file.read()
    filename = file.filename or "unknown"
    file_size = len(content)

    # 2. Валидация
    max_size = settings.chroma.max_upload_size_mb
    validate_upload(filename, file_size, max_size_mb=max_size)

    # 3. Извлечение текста
    raw_text = parse_file(content, filename)
    if not raw_text.strip():
        raise HTTPException(status_code=400, detail="Файл не содержит текста")

    # 4. PII маскировка
    masked_text, had_pii = mask_pii_in_text(raw_text)

    # 5. Разбивка на чанки
    chunks = chunk_text(
        masked_text,
        chunk_size=settings.chroma.chunk_size,
        chunk_overlap=settings.chroma.chunk_overlap,
    )

    if not chunks:
        raise HTTPException(status_code=400, detail="Не удалось разбить текст на чанки")

    # 6. Генерация embeddings
    emb_service = get_embedding_service()
    embeddings = emb_service.embed_texts(chunks)

    # 7. Сохранение в Chroma
    doc_id = f"{uuid.uuid4().hex[:12]}_{filename}"
    metadata: Dict[str, Any] = {
        "filename": filename,
        "file_size": file_size,
        "content_type": file.content_type or "",
        "text_length": len(raw_text),
        "pii_masked": had_pii,
        "uploaded_at": time.time(),
    }

    chroma = get_chroma_service()
    chunk_count = chroma.add_document_chunks(
        doc_id=doc_id,
        chunks=chunks,
        embeddings=embeddings,
        metadata=metadata,
    )

    logger.structured(
        "info",
        "document_uploaded_to_rag",
        component="rag_api",
        doc_id=doc_id,
        filename=filename,
        chunks=chunk_count,
        pii_masked=had_pii,
    )

    return {
        "status": "indexed",
        "doc_id": doc_id,
        "filename": filename,
        "chunk_count": chunk_count,
        "text_length": len(raw_text),
        "pii_masked": had_pii,
    }


@rag_router.get("/documents", summary="Список загруженных документов")
async def list_documents(
    offset: int = Query(default=0, ge=0),
    limit: int = Query(default=50, ge=1, le=200),
):
    _check_rag_enabled()

    from app.services.chroma_service import get_chroma_service

    chroma = get_chroma_service()
    return chroma.list_documents(offset=offset, limit=limit)


@rag_router.delete("/documents/{doc_id}", summary="Удалить документ из RAG")
async def delete_document(doc_id: str):
    _check_rag_enabled()

    from app.services.chroma_service import get_chroma_service

    chroma = get_chroma_service()
    ok = chroma.delete_document(doc_id)
    if not ok:
        raise HTTPException(status_code=404, detail="Документ не найден в RAG")
    return {"status": "deleted", "doc_id": doc_id}


# =============================================================================
# STATS
# =============================================================================


@rag_router.get("/stats", summary="Статистика RAG")
async def rag_stats():
    _check_rag_enabled()

    from app.services.chroma_service import get_chroma_service
    from app.services.embedding_service import get_embedding_service

    chroma = get_chroma_service()
    emb = get_embedding_service()

    return {
        "chroma": chroma.get_stats(),
        "embedding": {
            "model_loaded": emb.is_loaded,
            "model_name": emb.model_name,
        },
    }
