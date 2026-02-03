"""
RAG Context Builder для обогащения анализа клиентов.

Формирует дополнительный контекст для LLM на основе:
- Похожих прошлых анализов (по embedding similarity)
- Загруженных документов (семантический поиск)
- Исторических паттернов риска

Graceful degradation: если Chroma/RAG недоступны — возвращает пустой контекст.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from app.shared.toolkit.logging import logger

# Максимальный размер RAG-контекста в символах (~2000 токенов)
MAX_RAG_CONTEXT_CHARS = 6000


class RAGContextBuilder:
    """Строит RAG-контекст для обогащения промптов LLM."""

    async def get_similar_reports(
        self,
        query: str,
        k: int = 3,
    ) -> List[Dict[str, Any]]:
        """
        Находит похожие прошлые анализы.

        Args:
            query: Текстовый запрос для поиска похожих отчётов
            k: Количество похожих отчётов

        Returns:
            Список похожих отчётов с метаданными и distance
        """
        try:
            from app.services.chroma_service import get_chroma_service
            from app.services.embedding_service import get_embedding_service

            emb_service = get_embedding_service()
            query_embedding = emb_service.embed_text(query)

            chroma = get_chroma_service()
            results = chroma.search_similar_reports(query_embedding, k=k)

            logger.debug(
                f"RAG: found {len(results)} similar reports",
                component="rag_context",
            )
            return results

        except Exception as e:
            logger.warning(f"RAG similar reports failed: {e}", component="rag_context")
            return []

    async def search_relevant_documents(
        self,
        query: str,
        k: int = 3,
    ) -> List[Dict[str, Any]]:
        """
        Поиск релевантных загруженных документов.

        Args:
            query: Текст запроса
            k: Количество результатов

        Returns:
            Список релевантных чанков
        """
        try:
            from app.services.chroma_service import get_chroma_service
            from app.services.embedding_service import get_embedding_service

            emb_service = get_embedding_service()
            query_embedding = emb_service.embed_text(query)

            chroma = get_chroma_service()
            results = chroma.search_documents(query_embedding, k=k)

            logger.debug(
                f"RAG: found {len(results)} relevant documents",
                component="rag_context",
            )
            return results

        except Exception as e:
            logger.warning(f"RAG document search failed: {e}", component="rag_context")
            return []

    async def build_context(
        self,
        client_name: str,
        inn: str,
        current_findings: Optional[List[str]] = None,
        k_reports: int = 3,
        k_documents: int = 3,
    ) -> str:
        """
        Формирует полный RAG-контекст для LLM.

        Args:
            client_name: Название компании
            inn: ИНН компании
            current_findings: Текущие findings (если уже есть)
            k_reports: Количество похожих отчётов
            k_documents: Количество релевантных документов

        Returns:
            Отформатированный текст для вставки в промпт (или пустая строка)
        """
        from app.config.settings import settings

        if not settings.chroma.enabled:
            return ""

        parts: List[str] = []

        # 1. Похожие отчёты
        report_query: str = f"{client_name} ИНН {inn}"
        if current_findings:
            report_query += " " + " ".join(current_findings[:5])

        similar_reports = await self.get_similar_reports(report_query, k=k_reports)
        if similar_reports:
            parts.append("### Похожие прошлые анализы")
            for i, report in enumerate(similar_reports, 1):
                meta = report.get("metadata", {})
                distance = report.get("distance")
                similarity = f" (схожесть: {1 - distance:.0%})" if distance is not None else ""

                entry = f"{i}. **{meta.get('client_name', 'N/A')}** (ИНН: {meta.get('inn', 'N/A')}){similarity}"
                if meta.get("risk_score"):
                    entry += f"\n   Риск: {meta['risk_score']}/100"
                if meta.get("risk_level"):
                    entry += f" ({meta['risk_level']})"

                doc_text = report.get("document", "")
                if doc_text:
                    # Берём первые 500 символов
                    summary = doc_text[:500]
                    if len(doc_text) > 500:
                        summary += "..."
                    entry += f"\n   {summary}"

                parts.append(entry)

        # 2. Релевантные документы
        search_query = f"{client_name} ИНН {inn}"
        relevant_docs = await self.search_relevant_documents(search_query, k=k_documents)
        if relevant_docs:
            parts.append("\n### Релевантные документы из базы знаний")
            for i, doc in enumerate(relevant_docs, 1):
                meta = doc.get("metadata", {})
                filename = meta.get("filename", "unknown")
                doc_text = doc.get("document", "")[:400]
                if doc_text:
                    parts.append(f"{i}. [{filename}]: {doc_text}")

        if not parts:
            return ""

        # Обрезаем до лимита
        context = "\n".join(parts)
        if len(context) > MAX_RAG_CONTEXT_CHARS:
            context = context[:MAX_RAG_CONTEXT_CHARS] + "\n[...контекст обрезан]"

        logger.structured(
            "debug",
            "rag_context_built",
            component="rag_context",
            similar_reports=len(similar_reports),
            relevant_docs=len(relevant_docs),
            context_chars=len(context),
        )

        return context


async def get_rag_context(
    client_name: str,
    inn: str,
    current_findings: Optional[List[str]] = None,
) -> str:
    """
    Вспомогательная функция для получения RAG-контекста.

    Возвращает пустую строку если RAG отключён или недоступен.
    """
    try:
        builder = RAGContextBuilder()
        return await builder.build_context(
            client_name=client_name,
            inn=inn,
            current_findings=current_findings,
        )
    except Exception as e:
        logger.warning(f"RAG context generation failed: {e}", component="rag_context")
        return ""
