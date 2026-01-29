"""
Сервис генерации embeddings для RAG.

Использует sentence-transformers с мультиязычной моделью,
оптимизированной для русского текста.

Модель загружается лениво при первом вызове (lazy loading).
"""

from __future__ import annotations

import threading
from typing import Any, Dict, List, Optional

from app.utility.logging_client import logger


class EmbeddingService:
    """Singleton сервис для генерации text embeddings.

    Примечание (H10): модель sentence-transformers выполняет CPU-bound inference,
    поэтому используется threading.Lock (не asyncio.Lock) — это корректно для
    синхронных вызовов через run_in_executor или из sync-контекста.
    """

    _instance: Optional["EmbeddingService"] = None
    _lock = threading.Lock()

    def __init__(self) -> None:
        self._model: Any = None
        self._model_name: Optional[str] = None
        self._model_lock = threading.Lock()
        logger.info("EmbeddingService initialized (model not loaded yet)", component="rag")

    @classmethod
    def get_instance(cls) -> "EmbeddingService":
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = EmbeddingService()
        return cls._instance

    def _ensure_model(self) -> None:
        """Загружает модель при первом вызове (lazy loading)."""
        if self._model is not None:
            return

        with self._model_lock:
            if self._model is not None:
                return

            from app.config.settings import settings

            model_name = settings.chroma.embedding_model

            logger.info(
                f"Loading embedding model: {model_name}",
                component="rag",
            )

            try:
                from sentence_transformers import SentenceTransformer

                self._model = SentenceTransformer(model_name)
                self._model_name = model_name
                logger.info(
                    f"Embedding model loaded: {model_name}",
                    component="rag",
                )
            except Exception as e:
                logger.error(
                    f"Failed to load embedding model {model_name}: {e}",
                    component="rag",
                )
                raise

    def embed_text(self, text: str) -> List[float]:
        """
        Генерирует embedding для текста.

        Args:
            text: Входной текст

        Returns:
            Вектор embedding (List[float])
        """
        self._ensure_model()
        embedding = self._model.encode(text, normalize_embeddings=True)
        return embedding.tolist()

    def embed_texts(self, texts: List[str], batch_size: int = 64) -> List[List[float]]:
        """
        Batch генерация embeddings для нескольких текстов.

        Args:
            texts: Список текстов
            batch_size: Максимальный размер батча (защита от OOM)

        Returns:
            Список векторов embedding
        """
        self._ensure_model()
        all_embeddings: List[List[float]] = []
        for i in range(0, len(texts), batch_size):
            batch = texts[i : i + batch_size]
            embeddings = self._model.encode(batch, normalize_embeddings=True)
            all_embeddings.extend(e.tolist() for e in embeddings)
        return all_embeddings

    def embed_report(self, report: Dict[str, Any]) -> List[float]:
        """
        Генерирует embedding для отчёта анализа.

        Комбинирует ключевые поля отчёта в один документ.

        Args:
            report: Словарь с данными отчёта

        Returns:
            Вектор embedding
        """
        parts = []

        if report.get("client_name"):
            parts.append(f"Клиент: {report['client_name']}")
        if report.get("inn"):
            parts.append(f"ИНН: {report['inn']}")
        if report.get("summary"):
            parts.append(f"Резюме: {report['summary']}")

        # Findings
        findings = report.get("findings") or report.get("report", {}).get("findings", [])
        if findings:
            if isinstance(findings, list):
                parts.append("Выводы: " + "; ".join(str(f) for f in findings[:10]))
            else:
                parts.append(f"Выводы: {findings}")

        # Risk
        risk = report.get("risk_assessment") or report.get("report", {}).get("risk_assessment", {})
        if isinstance(risk, dict):
            risk_score = risk.get("overall_score") or risk.get("score")
            risk_level = risk.get("level") or risk.get("risk_level")
            if risk_score is not None:
                parts.append(f"Уровень риска: {risk_score}/100")
            if risk_level:
                parts.append(f"Категория: {risk_level}")

        doc_text = "\n".join(parts) if parts else "Пустой отчёт"
        return self.embed_text(doc_text)

    @property
    def is_loaded(self) -> bool:
        """Загружена ли модель."""
        return self._model is not None

    @property
    def model_name(self) -> Optional[str]:
        """Имя загруженной модели."""
        return self._model_name


def get_embedding_service() -> EmbeddingService:
    """Получить singleton экземпляр EmbeddingService."""
    return EmbeddingService.get_instance()
