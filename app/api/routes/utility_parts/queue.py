"""
P1-2: Мониторинг очередей RabbitMQ.

Endpoints для получения статистики и health check очередей.
"""

import time
from typing import Any, Dict

from fastapi import HTTPException

from app.api.routes.utility import utility_router
from app.config import settings
from app.utility.logging_client import logger


@utility_router.get("/queue/stats")
async def get_queue_stats() -> Dict[str, Any]:
    """
    P1-2: Получить статистику очередей RabbitMQ.
    
    Returns:
        Статистика по всем очередям (длина, consumers, rate)
    """
    try:
        import httpx
        
        # RabbitMQ Management API
        mgmt_url = settings.queue.amqp_url.replace("amqp://", "http://").replace(":5672", ":15672")
        
        # Credentials из docker-compose (в production нужно из env)
        auth = ("admin", "admin123")
        
        async with httpx.AsyncClient(timeout=5.0) as client:
            # Список очередей
            resp = await client.get(f"{mgmt_url}/api/queues/%2f", auth=auth)
            resp.raise_for_status()
            queues = resp.json()
            
            stats = {}
            for queue in queues:
                name = queue["name"]
                message_stats = queue.get("message_stats", {})
                
                stats[name] = {
                    "messages": queue.get("messages", 0),
                    "messages_ready": queue.get("messages_ready", 0),
                    "messages_unacknowledged": queue.get("messages_unacknowledged", 0),
                    "consumers": queue.get("consumers", 0),
                    "state": queue.get("state", "unknown"),
                    "rate": {
                        "publish": message_stats.get("publish_details", {}).get("rate", 0),
                        "deliver": message_stats.get("deliver_details", {}).get("rate", 0),
                    }
                }
            
            return {
                "status": "ok",
                "timestamp": time.time(),
                "queues": stats,
                "total_messages": sum(q["messages"] for q in stats.values()),
                "total_consumers": sum(q["consumers"] for q in stats.values()),
            }
            
    except Exception as e:
        logger.error(f"Failed to fetch RabbitMQ stats: {e}", component="rabbitmq_monitor")
        return {
            "status": "error",
            "error": str(e),
            "queues": {},
        }


@utility_router.get("/queue/health")
async def check_queue_health() -> Dict[str, Any]:
    """
    P1-2: Health check для очередей RabbitMQ.
    
    Алерты:
    - Очередь > 100 сообщений
    - Нет consumers
    - DLQ > 10 сообщений
    """
    stats = await get_queue_stats()
    
    if stats["status"] == "error":
        raise HTTPException(
            status_code=503,
            detail="Cannot connect to RabbitMQ Management API"
        )
    
    alerts = []
    
    for name, queue_stats in stats["queues"].items():
        # Проверка длины очереди
        if queue_stats["messages"] > 100:
            alerts.append({
                "severity": "warning",
                "queue": name,
                "reason": f"Queue has {queue_stats['messages']} messages (threshold: 100)"
            })
        
        # Проверка consumers
        if queue_stats["consumers"] == 0 and queue_stats["messages"] > 0:
            alerts.append({
                "severity": "critical",
                "queue": name,
                "reason": "No consumers but queue has messages"
            })
        
        # Проверка DLQ
        if name.startswith("dlq.") and queue_stats["messages"] > 10:
            alerts.append({
                "severity": "critical",
                "queue": name,
                "reason": f"DLQ has {queue_stats['messages']} failed messages (threshold: 10)"
            })
    
    return {
        "status": "healthy" if not alerts else "degraded",
        "alerts": alerts,
        "total_queues": len(stats["queues"]),
        "total_messages": stats["total_messages"],
        "total_consumers": stats.get("total_consumers", 0),
        "timestamp": stats["timestamp"],
    }

