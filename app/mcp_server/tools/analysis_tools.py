"""
Analysis tools for client risk assessment.
"""

from typing import Any, Dict

from app.shared.logger import get_logger

# Import canonical schema (avoid duplication)
from app.schemas.requests import ClientAnalysisRequest

logger = get_logger(__name__)


# ============================================================================
# Tool Functions
# ============================================================================


async def run_client_analysis_tool(request: ClientAnalysisRequest) -> Dict[str, Any]:
    """
    Run client analysis workflow in-process.

    Executes the full analysis workflow directly, suitable for
    interactive/synchronous use cases.

    Args:
        request: Validated analysis request

    Returns:
        Analysis results with risk assessment

    Raises:
        Exception: If analysis fails

    Examples:
        >>> result = await run_client_analysis_tool(
        ...     ClientAnalysisRequest(
        ...         client_name="ООО Ромашка",
        ...         inn="7707083893",
        ...         save_report=True
        ...     )
        ... )
    """
    logger.log_action(
        "run_client_analysis_start",
        client_name=request.client_name,
        inn=request.inn,
        session_id=request.session_id,
    )

    try:
        from app.services.app_actions import dispatch_client_analysis

        result = await dispatch_client_analysis(
            client_name=request.client_name,
            inn=request.inn,
            additional_notes=request.additional_notes,
            save_report=request.save_report,
            session_id=request.session_id,
            prefer_queue=False,
        )

        logger.log_action(
            "run_client_analysis_success",
            client_name=request.client_name,
            session_id=request.session_id,
            risk_score=result.get("risk_assessment", {}).get("score"),
        )

        return result

    except Exception as e:
        logger.error(
            "run_client_analysis_failed",
            exc=e,
            client_name=request.client_name,
            session_id=request.session_id,
        )
        raise


async def queue_client_analysis_tool(request: ClientAnalysisRequest) -> Dict[str, Any]:
    """
    Queue client analysis to RabbitMQ.

    Publishes analysis request to message queue for async processing
    by worker. Suitable for high-load scenarios.

    Args:
        request: Validated analysis request

    Returns:
        Queue acknowledgment with task ID

    Raises:
        Exception: If queueing fails

    Examples:
        >>> result = await queue_client_analysis_tool(
        ...     ClientAnalysisRequest(
        ...         client_name="ООО Ромашка",
        ...         inn="7707083893"
        ...     )
        ... )
        >>> result
        {'status': 'queued', 'task_id': 'task-123-456'}
    """
    logger.log_action(
        "queue_client_analysis_start",
        client_name=request.client_name,
        inn=request.inn,
        session_id=request.session_id,
    )

    try:
        from app.services.app_actions import dispatch_client_analysis

        result = await dispatch_client_analysis(
            client_name=request.client_name,
            inn=request.inn,
            additional_notes=request.additional_notes,
            save_report=request.save_report,
            session_id=request.session_id,
            prefer_queue=True,
        )

        logger.log_action(
            "queue_client_analysis_success",
            client_name=request.client_name,
            session_id=request.session_id,
            task_id=result.get("task_id"),
        )

        return result

    except Exception as e:
        logger.error(
            "queue_client_analysis_failed",
            exc=e,
            client_name=request.client_name,
            session_id=request.session_id,
        )
        raise


__all__ = [
    "ClientAnalysisRequest",
    "run_client_analysis_tool",
    "queue_client_analysis_tool",
]
