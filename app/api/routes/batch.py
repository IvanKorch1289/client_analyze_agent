"""
Batch analysis API endpoints (Phase 6).

Allows submitting multiple clients for analysis in a single request.
Results are returned as a summary with individual statuses.
"""

import uuid
from typing import Any, Dict, List

from fastapi import APIRouter, Depends

from app.schemas.requests import BatchAnalysisRequest
from app.shared.audit_trail import audit_log
from app.shared.toolkit.auth import Permission, require_permission
from app.shared.toolkit.logging import logger

batch_router = APIRouter(prefix="/batch", tags=["Batch"])


@batch_router.post(
    "/analyze",
    dependencies=[Depends(require_permission(Permission.ANALYSIS_BATCH))],
)
async def batch_analyze(
    request: BatchAnalysisRequest,
    role: str = Depends(require_permission(Permission.ANALYSIS_BATCH)),
) -> Dict[str, Any]:
    """
    Submit multiple clients for analysis.

    Each client is processed independently. Results include per-client status.
    Optional webhook_url receives a POST when all analyses complete.

    Args:
        request: Batch analysis request with list of clients (1-100).

    Returns:
        Batch job summary with individual task IDs.
    """
    batch_id = str(uuid.uuid4())[:12]

    audit_log.record(
        action="batch.create",
        role=role,
        details={
            "batch_id": batch_id,
            "client_count": len(request.clients),
            "webhook_url": request.webhook_url,
        },
    )

    results: List[Dict[str, Any]] = []

    for i, client_data in enumerate(request.clients):
        task_id = f"{batch_id}-{i}"
        client_name = client_data.get("client_name", "")
        inn = client_data.get("inn", "")

        try:
            from app.services.analysis_executor import execute_client_analysis

            result = await execute_client_analysis(
                client_name=client_name,
                inn=inn,
                additional_notes=client_data.get("additional_notes", ""),
                save_report=request.save_reports,
            )

            results.append(
                {
                    "task_id": task_id,
                    "client_name": client_name,
                    "inn": inn,
                    "status": "completed",
                    "report_id": (result.get("report_id") if isinstance(result, dict) else None),
                }
            )

        except Exception as e:
            logger.error(
                f"Batch analysis failed for client {i}: {e}",
                component="batch_api",
                exc_info=True,
            )
            results.append(
                {
                    "task_id": task_id,
                    "client_name": client_name,
                    "inn": inn,
                    "status": "failed",
                    "error": str(e),
                }
            )

    # Dispatch webhook if configured
    if request.webhook_url:
        try:
            from app.shared.webhooks import webhook_manager

            await webhook_manager.dispatch(
                "batch.completed",
                {
                    "batch_id": batch_id,
                    "total": len(results),
                    "completed": sum(1 for r in results if r["status"] == "completed"),
                    "failed": sum(1 for r in results if r["status"] == "failed"),
                },
            )
        except Exception as e:
            logger.warning(f"Webhook dispatch failed: {e}", component="batch_api")

    completed = sum(1 for r in results if r["status"] == "completed")

    audit_log.record(
        action="batch.completed",
        role=role,
        details={
            "batch_id": batch_id,
            "total": len(results),
            "completed": completed,
            "failed": len(results) - completed,
        },
    )

    return {
        "status": "success",
        "batch_id": batch_id,
        "total": len(results),
        "completed": completed,
        "failed": len(results) - completed,
        "results": results,
    }


__all__ = ["batch_router"]
