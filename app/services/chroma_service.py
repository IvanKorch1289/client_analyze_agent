"""
Сервис для работы с ChromaDB (векторная БД для RAG).

Предоставляет:
- Хранение и поиск embeddings отчётов
- Хранение и поиск embeddings загруженных документов
- Управление коллекциями (stats, delete, list)

ChromaDB подключается в режиме local (встроенный) или client (удалённый).
"""

from __future__ import annotations

import time
import threading
from typing import Any, Dict, List, Optional

from app.utility.logging_client import logger


class ChromaService:
    """Singleton сервис для работы с ChromaDB."""

    _instance: Optional["ChromaService"] = None
    _lock = threading.Lock()

    def __init__(self) -> None:
        self._client: Any = None
        self._reports_collection: Any = None
        self._documents_collection: Any = None
        self._initialized = False

    @classmethod
    def get_instance(cls) -> "ChromaService":
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = ChromaService()
        return cls._instance

    def _ensure_initialized(self) -> None:
        """Инициализирует клиент ChromaDB при первом обращении."""
        if self._initialized:
            return

        import chromadb

        from app.config.settings import settings

        cfg = settings.chroma

        if cfg.mode == "client":
            self._client = chromadb.HttpClient(host=cfg.host, port=cfg.port)
            logger.info(
                f"ChromaDB connected (client mode): {cfg.host}:{cfg.port}",
                component="rag",
            )
        else:
            import os

            os.makedirs(cfg.persist_dir, exist_ok=True)
            self._client = chromadb.PersistentClient(path=cfg.persist_dir)
            logger.info(
                f"ChromaDB initialized (local mode): {cfg.persist_dir}",
                component="rag",
            )

        self._reports_collection = self._client.get_or_create_collection(
            name=cfg.reports_collection,
            metadata={"hnsw:space": "cosine"},
        )
        self._documents_collection = self._client.get_or_create_collection(
            name=cfg.documents_collection,
            metadata={"hnsw:space": "cosine"},
        )
        self._initialized = True

    # =========================================================================
    # REPORTS COLLECTION
    # =========================================================================

    def add_report(
        self,
        report_id: str,
        embedding: List[float],
        text: str,
        metadata: Dict[str, Any],
    ) -> str:
        """
        Добавляет отчёт в коллекцию reports.

        Args:
            report_id: ID отчёта из Tarantool
            embedding: Вектор embedding
            text: Текстовое содержимое для хранения
            metadata: Метаданные (client_name, inn, risk_score и т.д.)

        Returns:
            ID документа в Chroma
        """
        self._ensure_initialized()

        # Приводим метаданные к примитивным типам (Chroma требует str/int/float/bool)
        safe_metadata = _sanitize_metadata(metadata)
        safe_metadata["indexed_at"] = time.time()
        safe_metadata["doc_type"] = "report"

        doc_id = f"report:{report_id}"

        self._reports_collection.upsert(
            ids=[doc_id],
            embeddings=[embedding],
            documents=[text],
            metadatas=[safe_metadata],
        )

        logger.info(
            f"Report indexed in Chroma: {report_id}",
            component="rag",
        )
        return doc_id

    def search_similar_reports(
        self,
        query_embedding: List[float],
        k: int = 5,
        where: Optional[Dict[str, Any]] = None,
    ) -> List[Dict[str, Any]]:
        """
        Поиск похожих отчётов по embedding.

        Args:
            query_embedding: Вектор запроса
            k: Количество результатов
            where: Фильтр метаданных (Chroma where clause)

        Returns:
            Список результатов с id, distance, metadata, document
        """
        self._ensure_initialized()

        query_params: Dict[str, Any] = {
            "query_embeddings": [query_embedding],
            "n_results": k,
            "include": ["documents", "metadatas", "distances"],
        }
        if where:
            query_params["where"] = where

        results = self._reports_collection.query(**query_params)
        return _format_chroma_results(results)

    def get_report(self, report_id: str) -> Optional[Dict[str, Any]]:
        """Получить проиндексированный отчёт по ID."""
        self._ensure_initialized()
        doc_id = f"report:{report_id}"

        try:
            result = self._reports_collection.get(
                ids=[doc_id],
                include=["documents", "metadatas"],
            )
            if result["ids"]:
                return {
                    "id": result["ids"][0],
                    "document": result["documents"][0] if result["documents"] else None,
                    "metadata": result["metadatas"][0] if result["metadatas"] else {},
                }
        except Exception:
            pass
        return None

    def delete_report(self, report_id: str) -> bool:
        """Удалить отчёт из Chroma."""
        self._ensure_initialized()
        doc_id = f"report:{report_id}"
        try:
            self._reports_collection.delete(ids=[doc_id])
            logger.info(f"Report removed from Chroma: {report_id}", component="rag")
            return True
        except Exception as e:
            logger.error(f"Failed to delete report {report_id}: {e}", component="rag")
            return False

    def list_reports(self, offset: int = 0, limit: int = 50) -> Dict[str, Any]:
        """Список проиндексированных отчётов."""
        self._ensure_initialized()

        result = self._reports_collection.get(
            include=["metadatas"],
            limit=limit,
            offset=offset,
        )

        items = []
        for i, doc_id in enumerate(result["ids"]):
            meta = result["metadatas"][i] if result["metadatas"] else {}
            items.append({"id": doc_id, "metadata": meta})

        return {
            "items": items,
            "total": self._reports_collection.count(),
            "offset": offset,
            "limit": limit,
        }

    # =========================================================================
    # DOCUMENTS COLLECTION
    # =========================================================================

    def add_document_chunks(
        self,
        doc_id: str,
        chunks: List[str],
        embeddings: List[List[float]],
        metadata: Dict[str, Any],
    ) -> int:
        """
        Добавляет чанки документа в коллекцию documents.

        Args:
            doc_id: ID документа
            chunks: Список текстовых чанков
            embeddings: Embeddings для каждого чанка
            metadata: Общие метаданные документа

        Returns:
            Количество добавленных чанков
        """
        self._ensure_initialized()

        ids = []
        docs = []
        metas = []
        embs = []

        base_meta = _sanitize_metadata(metadata)
        base_meta["doc_type"] = "document"
        base_meta["indexed_at"] = time.time()
        base_meta["parent_doc_id"] = doc_id

        for i, (chunk, embedding) in enumerate(zip(chunks, embeddings)):
            chunk_id = f"doc:{doc_id}:chunk:{i}"
            ids.append(chunk_id)
            docs.append(chunk)
            embs.append(embedding)

            chunk_meta = {**base_meta, "chunk_index": i, "total_chunks": len(chunks)}
            metas.append(chunk_meta)

        self._documents_collection.upsert(
            ids=ids,
            embeddings=embs,
            documents=docs,
            metadatas=metas,
        )

        logger.info(
            f"Document indexed: {doc_id} ({len(chunks)} chunks)",
            component="rag",
        )
        return len(chunks)

    def search_documents(
        self,
        query_embedding: List[float],
        k: int = 5,
        where: Optional[Dict[str, Any]] = None,
    ) -> List[Dict[str, Any]]:
        """Поиск похожих документов/чанков по embedding."""
        self._ensure_initialized()

        query_params: Dict[str, Any] = {
            "query_embeddings": [query_embedding],
            "n_results": k,
            "include": ["documents", "metadatas", "distances"],
        }
        if where:
            query_params["where"] = where

        results = self._documents_collection.query(**query_params)
        return _format_chroma_results(results)

    def delete_document(self, doc_id: str) -> bool:
        """Удалить документ и все его чанки из Chroma."""
        self._ensure_initialized()
        try:
            self._documents_collection.delete(
                where={"parent_doc_id": doc_id},
            )
            logger.info(f"Document removed from Chroma: {doc_id}", component="rag")
            return True
        except Exception as e:
            logger.error(f"Failed to delete document {doc_id}: {e}", component="rag")
            return False

    def list_documents(self, offset: int = 0, limit: int = 50) -> Dict[str, Any]:
        """Список уникальных загруженных документов."""
        self._ensure_initialized()

        result = self._documents_collection.get(
            include=["metadatas"],
            limit=limit * 10,  # берём больше, т.к. один документ = несколько чанков
            offset=0,
        )

        # Группируем по parent_doc_id
        seen_docs: Dict[str, Dict[str, Any]] = {}
        for i, doc_id in enumerate(result["ids"]):
            meta = result["metadatas"][i] if result["metadatas"] else {}
            parent_id = meta.get("parent_doc_id", doc_id)
            if parent_id not in seen_docs:
                seen_docs[parent_id] = {
                    "id": parent_id,
                    "metadata": {k: v for k, v in meta.items() if k not in ("chunk_index", "total_chunks")},
                    "chunk_count": meta.get("total_chunks", 1),
                }

        all_docs = list(seen_docs.values())
        return {
            "items": all_docs[offset : offset + limit],
            "total": len(all_docs),
            "offset": offset,
            "limit": limit,
        }

    # =========================================================================
    # SEMANTIC SEARCH (unified across collections)
    # =========================================================================

    def semantic_search(
        self,
        query_embedding: List[float],
        k: int = 10,
        collection: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """
        Семантический поиск по всем или указанной коллекции.

        Args:
            query_embedding: Вектор запроса
            k: Количество результатов
            collection: 'reports', 'documents' или None (обе)

        Returns:
            Отсортированный список результатов
        """
        self._ensure_initialized()
        results = []

        if collection in (None, "reports"):
            results.extend(self.search_similar_reports(query_embedding, k=k))

        if collection in (None, "documents"):
            results.extend(self.search_documents(query_embedding, k=k))

        # Сортируем по distance (меньше = лучше)
        results.sort(key=lambda r: r.get("distance", float("inf")))
        return results[:k]

    # =========================================================================
    # STATS
    # =========================================================================

    def get_stats(self) -> Dict[str, Any]:
        """Статистика по коллекциям Chroma."""
        self._ensure_initialized()

        return {
            "reports_count": self._reports_collection.count(),
            "documents_chunks_count": self._documents_collection.count(),
            "initialized": self._initialized,
        }


# =============================================================================
# HELPERS
# =============================================================================


def _sanitize_metadata(metadata: Dict[str, Any]) -> Dict[str, Any]:
    """Приводит метаданные к типам, поддерживаемым ChromaDB (str/int/float/bool)."""
    safe: Dict[str, Any] = {}
    for key, value in metadata.items():
        if isinstance(value, (str, int, float, bool)):
            safe[key] = value
        elif value is None:
            safe[key] = ""
        elif isinstance(value, (list, dict)):
            safe[key] = str(value)[:500]  # Truncate complex types
        else:
            safe[key] = str(value)[:500]
    return safe


def _format_chroma_results(raw_results: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Форматирует результаты Chroma query в удобный список."""
    items = []

    ids = raw_results.get("ids", [[]])[0]
    documents = raw_results.get("documents", [[]])[0]
    metadatas = raw_results.get("metadatas", [[]])[0]
    distances = raw_results.get("distances", [[]])[0]

    for i, doc_id in enumerate(ids):
        items.append(
            {
                "id": doc_id,
                "document": documents[i] if i < len(documents) else None,
                "metadata": metadatas[i] if i < len(metadatas) else {},
                "distance": distances[i] if i < len(distances) else None,
            }
        )

    return items


def get_chroma_service() -> ChromaService:
    """Получить singleton экземпляр ChromaService."""
    return ChromaService.get_instance()
