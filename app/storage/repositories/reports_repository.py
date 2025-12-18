"""
Reports Repository - управление отчетами по клиентам.

Работает с reports space, предоставляя API для:
- Создания отчетов с TTL 30 дней
- Поиска отчетов по ИНН
- Фильтрации по уровню риска
- Автоматической очистки старых отчетов
"""

import time
import uuid
from datetime import datetime
from typing import Any, Dict, List, Optional

from app.storage.repositories import BaseRepository
from app.utility.logging_client import logger

# TTL для отчетов: 30 дней
REPORT_TTL_DAYS = 30
REPORT_TTL_SECONDS = REPORT_TTL_DAYS * 24 * 60 * 60  # 2592000 секунд


class ReportsRepository(BaseRepository[Dict[str, Any]]):
    """
    Repository для reports space.
    
    Управляет отчетами по анализу клиентов с автоматическим
    истечением через 30 дней.
    """
    
    def __init__(self, tarantool_client):
        super().__init__(tarantool_client)
        self.space_name = "reports"
    
    async def get(self, report_id: str) -> Optional[Dict[str, Any]]:
        """
        Получить отчет по ID.
        
        Args:
            report_id: Уникальный ID отчета
            
        Returns:
            Отчет или None если не найден/просрочен
        """
        try:
            # Используем persistent методы т.к. reports в своем space
            key = f"report:{report_id}"
            result = await self.client.get_persistent(key)
            
            if result is None:
                return None
            
            # Проверка expires_at
            if isinstance(result, dict) and "expires_at" in result:
                if result["expires_at"] < time.time():
                    # Просрочен, удаляем
                    await self.delete(report_id)
                    logger.debug(
                        f"Report expired and deleted: {report_id}",
                        component="reports_repo"
                    )
                    return None
            
            return result
            
        except Exception as e:
            logger.error(
                f"Report get error for {report_id}: {e}",
                component="reports_repo"
            )
            return None
    
    async def create(self, data: Dict[str, Any]) -> str:
        """
        Создать новый отчет.
        
        Args:
            data: Данные отчета, должны содержать:
                - inn: str
                - client_name: str
                - report_data: dict (полный отчет)
                - risk_level: str (optional, извлекается из report_data)
                - risk_score: int (optional, извлекается из report_data)
                
        Returns:
            report_id - уникальный ID созданного отчета
        """
        report_id = str(uuid.uuid4())
        now = time.time()
        expires_at = now + REPORT_TTL_SECONDS
        
        inn = data.get("inn", "")
        client_name = data.get("client_name", "")
        report_data = data.get("report_data", {})
        
        # Извлекаем risk info из report_data если не передано явно
        risk_assessment = report_data.get("risk_assessment", {})
        risk_level = data.get("risk_level") or risk_assessment.get("level", "unknown")
        risk_score = data.get("risk_score")
        if risk_score is None:
            risk_score = risk_assessment.get("score", 0)
        
        report_record = {
            "report_id": report_id,
            "inn": inn,
            "client_name": client_name,
            "report_data": report_data,
            "created_at": now,
            "expires_at": expires_at,
            "risk_level": risk_level,
            "risk_score": int(risk_score) if risk_score else 0,
        }
        
        try:
            # Сохраняем в persistent с ключом report:{id}
            key = f"report:{report_id}"
            await self.client.set_persistent(key, report_record)
            
            logger.structured(
                "info",
                "report_created",
                component="reports_repo",
                report_id=report_id,
                client_name=client_name[:30],
                risk_level=risk_level,
                ttl_days=REPORT_TTL_DAYS,
            )
            
            return report_id
            
        except Exception as e:
            logger.error(
                f"Report create error: {e}",
                component="reports_repo"
            )
            raise
    
    async def create_from_workflow_result(
        self,
        workflow_result: Dict[str, Any]
    ) -> str:
        """
        Создать отчет из результата workflow.
        
        Удобный метод для сохранения результата client_workflow.
        
        Args:
            workflow_result: Результат run_client_analysis_streaming или batch
                Должен содержать: client_name, inn, report, status
                
        Returns:
            report_id
        """
        report_data = workflow_result.get("report", {})
        
        if not report_data:
            raise ValueError("No report data in workflow result")
        
        return await self.create({
            "inn": workflow_result.get("inn", ""),
            "client_name": workflow_result.get("client_name", ""),
            "report_data": report_data,
        })
    
    async def update(self, report_id: str, data: Dict[str, Any]) -> bool:
        """
        Обновить существующий отчет.
        
        Args:
            report_id: ID отчета
            data: Новые данные (частичное обновление)
            
        Returns:
            True если обновлено
        """
        try:
            existing = await self.get(report_id)
            if not existing:
                logger.warning(
                    f"Report not found for update: {report_id}",
                    component="reports_repo"
                )
                return False
            
            # Обновляем поля
            existing.update(data)
            
            # Сохраняем обратно
            key = f"report:{report_id}"
            await self.client.set_persistent(key, existing)
            
            logger.debug(
                f"Report updated: {report_id}",
                component="reports_repo"
            )
            return True
            
        except Exception as e:
            logger.error(
                f"Report update error for {report_id}: {e}",
                component="reports_repo"
            )
            return False
    
    async def delete(self, report_id: str) -> bool:
        """
        Удалить отчет.
        
        Args:
            report_id: ID отчета
            
        Returns:
            True если удалено
        """
        try:
            key = f"report:{report_id}"
            await self.client.delete_persistent(key)
            
            logger.debug(
                f"Report deleted: {report_id}",
                component="reports_repo"
            )
            return True
            
        except Exception as e:
            logger.error(
                f"Report delete error for {report_id}: {e}",
                component="reports_repo"
            )
            return False
    
    async def list(
        self,
        limit: int = 50,
        offset: int = 0
    ) -> List[Dict[str, Any]]:
        """
        Получить список отчетов (пагинация).
        
        Сортировка: по created_at DESC (новые первые).
        
        Args:
            limit: Максимальное количество
            offset: Смещение
            
        Returns:
            Список отчетов
        """
        # TODO: Implement через прямое обращение к Tarantool
        # Нужно использовать created_idx индекс
        logger.warning(
            "Reports list() not fully implemented yet",
            component="reports_repo"
        )
        return []
    
    async def get_reports_by_inn(
        self,
        inn: str,
        limit: int = 50
    ) -> List[Dict[str, Any]]:
        """
        Получить все отчеты по ИНН.
        
        Args:
            inn: ИНН клиента
            limit: Максимальное количество
            
        Returns:
            Список отчетов для данного ИНН
        """
        # TODO: Implement через прямое обращение к Tarantool
        # Нужно использовать inn_idx индекс
        logger.debug(
            f"Get reports by INN: {inn}",
            component="reports_repo"
        )
        return []
    
    async def get_reports_by_risk_level(
        self,
        risk_level: str,
        limit: int = 50
    ) -> List[Dict[str, Any]]:
        """
        Получить отчеты по уровню риска.
        
        Args:
            risk_level: "low" | "medium" | "high" | "critical"
            limit: Максимальное количество
            
        Returns:
            Список отчетов с указанным уровнем риска
        """
        # TODO: Implement через прямое обращение к Tarantool
        # Нужно использовать risk_idx индекс
        logger.debug(
            f"Get reports by risk level: {risk_level}",
            component="reports_repo"
        )
        return []
    
    async def search_reports(
        self,
        filters: Optional[Dict[str, Any]] = None,
        limit: int = 50
    ) -> List[Dict[str, Any]]:
        """
        Поиск отчетов с фильтрами.
        
        Args:
            filters: Фильтры:
                - inn: str
                - client_name: str (partial match)
                - risk_level: str
                - min_risk_score: int
                - max_risk_score: int
                - date_from: timestamp
                - date_to: timestamp
            limit: Максимальное количество
            
        Returns:
            Список отчетов, соответствующих фильтрам
        """
        # TODO: Implement сложный поиск
        logger.debug(
            f"Search reports with filters: {filters}",
            component="reports_repo"
        )
        return []
    
    async def cleanup_expired(self) -> int:
        """
        Очистка просроченных отчетов.
        
        Note: Автоматически выполняется фоновой задачей в Tarantool.
        
        Returns:
            Количество удаленных отчетов
        """
        logger.info(
            "Cleanup expired reports (runs automatically in Tarantool)",
            component="reports_repo"
        )
        # Cleanup выполняется в init.lua автоматически
        return 0
    
    async def count(self) -> int:
        """
        Получить общее количество отчетов.
        
        Returns:
            Количество отчетов в space
        """
        # TODO: Implement через Tarantool box.space.reports:len()
        return 0
    
    async def get_stats(self) -> Dict[str, Any]:
        """
        Получить статистику по отчетам.
        
        Returns:
            Статистика: total, by_risk_level, avg_risk_score, etc.
        """
        return {
            "total": await self.count(),
            "ttl_days": REPORT_TTL_DAYS,
            "by_risk_level": {
                "low": 0,
                "medium": 0,
                "high": 0,
                "critical": 0,
            },
            "avg_risk_score": 0,
        }


__all__ = ["ReportsRepository", "REPORT_TTL_DAYS", "REPORT_TTL_SECONDS"]
