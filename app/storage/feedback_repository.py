"""
Репозиторий для хранения фидбеков пользователей.

Используется для:
- Сохранения истории фидбеков
- Анализа паттернов недовольства
- Адаптивной доработки промптов
"""

import json
import time
from typing import Any, Dict, List, Optional

from app.utility.logging_client import logger


class FeedbackRepository:
    """Репозиторий для работы с фидбеками пользователей."""

    def __init__(self, connection):
        """
        Инициализация репозитория.

        Args:
            connection: Tarantool connection instance
        """
        self.conn = connection
        self.space_name = "feedbacks"

    async def init_space(self):
        """Инициализировать space для фидбеков, если не существует."""
        try:
            await self.conn.call(
                "box.schema.space.create",
                self.space_name,
                {"if_not_exists": True},
            )

            # Создать индексы
            # primary: feedback_id
            await self.conn.call(
                f"box.space.{self.space_name}:create_index",
                "primary",
                {
                    "parts": [{"field": 1, "type": "string"}],
                    "if_not_exists": True,
                },
            )

            # secondary: report_id для связи с отчетами
            await self.conn.call(
                f"box.space.{self.space_name}:create_index",
                "by_report_id",
                {
                    "parts": [{"field": 2, "type": "string"}],
                    "unique": False,
                    "if_not_exists": True,
                },
            )

            # tertiary: timestamp для сортировки по времени
            await self.conn.call(
                f"box.space.{self.space_name}:create_index",
                "by_timestamp",
                {
                    "parts": [{"field": 8, "type": "number"}],
                    "unique": False,
                    "if_not_exists": True,
                },
            )

            logger.info(
                f"Feedback space '{self.space_name}' initialized",
                component="feedback_repo",
            )

        except Exception as e:
            logger.warning(
                f"Failed to init feedback space (may already exist): {e}",
                component="feedback_repo",
            )

    async def save(self, feedback: Dict[str, Any]) -> str:
        """
        Сохранить фидбек в хранилище.

        Args:
            feedback: Словарь с данными фидбека:
                - feedback_id: str
                - report_id: str
                - rating: str (accurate/partially_accurate/inaccurate)
                - comment: Optional[str]
                - focus_areas: Optional[List[str]]
                - client_name: str
                - inn: str
                - timestamp: float

        Returns:
            feedback_id
        """
        feedback_id = feedback.get("feedback_id", f"fb_{int(time.time() * 1000)}")
        timestamp = feedback.get("timestamp", time.time())

        # Формат кортежа для Tarantool
        # (feedback_id, report_id, rating, comment, focus_areas_json, client_name, inn, timestamp)
        tuple_data = (
            feedback_id,
            feedback.get("report_id", ""),
            feedback.get("rating", ""),
            feedback.get("comment") or "",
            json.dumps(feedback.get("focus_areas", [])),  # JSON строка
            feedback.get("client_name", ""),
            feedback.get("inn", ""),
            timestamp,
        )

        try:
            await self.conn.call(f"box.space.{self.space_name}:insert", tuple_data)
            logger.structured(
                "info",
                "feedback_saved",
                component="feedback_repo",
                feedback_id=feedback_id,
                report_id=feedback.get("report_id"),
                rating=feedback.get("rating"),
            )
            return feedback_id

        except Exception as e:
            logger.error(
                f"Failed to save feedback: {e}",
                component="feedback_repo",
                exc_info=True,
            )
            raise

    async def get_recent_feedbacks(self, limit: int = 10, rating_filter: Optional[str] = None) -> List[Dict[str, Any]]:
        """
        Получить последние N фидбеков.

        Args:
            limit: Количество фидбеков
            rating_filter: Фильтр по рейтингу (inaccurate/partially_accurate)

        Returns:
            Список фидбеков, отсортированных по времени (новые первыми)
        """
        try:
            # Получить все фидбеки через индекс by_timestamp
            result = await self.conn.call(
                f"box.space.{self.space_name}.index.by_timestamp:select",
                {},
                {"limit": limit * 3, "iterator": "REQ"},  # REQ = reverse order
            )

            feedbacks = []
            for row in result[0]:
                feedback_dict = {
                    "feedback_id": row[0],
                    "report_id": row[1],
                    "rating": row[2],
                    "comment": row[3],
                    "focus_areas": (json.loads(row[4]) if row[4] else []),  # Parse JSON string
                    "client_name": row[5],
                    "inn": row[6],
                    "timestamp": row[7],
                }

                # Применить фильтр по рейтингу
                if rating_filter and feedback_dict["rating"] != rating_filter:
                    continue

                feedbacks.append(feedback_dict)

                if len(feedbacks) >= limit:
                    break

            return feedbacks

        except Exception as e:
            logger.error(
                f"Failed to get recent feedbacks: {e}",
                component="feedback_repo",
                exc_info=True,
            )
            return []

    async def get_feedbacks_by_report(self, report_id: str) -> List[Dict[str, Any]]:
        """Получить все фидбеки для конкретного отчета."""
        try:
            result = await self.conn.call(
                f"box.space.{self.space_name}.index.by_report_id:select",
                report_id,
            )

            feedbacks = []
            for row in result[0]:
                feedbacks.append(
                    {
                        "feedback_id": row[0],
                        "report_id": row[1],
                        "rating": row[2],
                        "comment": row[3],
                        "focus_areas": json.loads(row[4]) if row[4] else [],
                        "client_name": row[5],
                        "inn": row[6],
                        "timestamp": row[7],
                    }
                )

            return feedbacks

        except Exception as e:
            logger.error(
                f"Failed to get feedbacks by report: {e}",
                component="feedback_repo",
                exc_info=True,
            )
            return []

    async def analyze_feedback_patterns(self, limit: int = 10) -> Dict[str, Any]:
        """
        Анализировать паттерны в последних фидбеках.

        Returns:
            Dict с агрегированной статистикой:
            - common_issues: List[str] - частые проблемы
            - focus_areas_frequency: Dict[str, int] - частота областей внимания
            - rating_distribution: Dict[str, int] - распределение оценок
            - sample_comments: List[str] - примеры комментариев
        """
        feedbacks = await self.get_recent_feedbacks(limit=limit)

        if not feedbacks:
            return {
                "common_issues": [],
                "focus_areas_frequency": {},
                "rating_distribution": {},
                "sample_comments": [],
            }

        # Анализ паттернов
        focus_areas_freq = {}
        rating_dist = {}
        comments = []

        for fb in feedbacks:
            # Подсчет focus_areas
            for area in fb.get("focus_areas", []):
                focus_areas_freq[area] = focus_areas_freq.get(area, 0) + 1

            # Распределение рейтингов
            rating = fb.get("rating", "")
            rating_dist[rating] = rating_dist.get(rating, 0) + 1

            # Сбор комментариев
            if fb.get("comment"):
                comments.append(fb["comment"])

        # Определить частые проблемы
        common_issues = sorted(focus_areas_freq.items(), key=lambda x: x[1], reverse=True)[:5]

        return {
            "common_issues": [issue[0] for issue in common_issues],
            "focus_areas_frequency": focus_areas_freq,
            "rating_distribution": rating_dist,
            "sample_comments": comments[:5],  # Первые 5 комментариев
        }
