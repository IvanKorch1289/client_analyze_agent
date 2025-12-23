"""
Analysis tools for client risk assessment.
"""

from typing import Any, Dict, Optional

from pydantic import BaseModel, Field, field_validator

from app.shared.logger import get_logger
from app.shared.security import sanitize_for_llm, validate_inn

logger = get_logger(__name__)


# ============================================================================
# Request Models
# ============================================================================


class ClientAnalysisRequest(BaseModel):
    """Request for client analysis."""

    client_name: str = Field(..., max_length=200, description="Client/company name")
    inn: str = Field(default="", description="Company INN (optional)")
    additional_notes: str = Field(
        default="",
        max_length=5000,
        description="Additional notes from user",
    )
    save_report: bool = Field(default=True, description="Save report to database")
    session_id: Optional[str] = Field(default=None, description="Session ID for tracking")

    @field_validator("client_name")
    @classmethod
    def validate_client_name(cls, v: str) -> str:
        """Validate and sanitize client name."""
        return sanitize_for_llm(v, max_length=200, strict=False)

    @field_validator("inn")
    @classmethod
    def validate_inn_field(cls, v: str) -> str:
        """Validate INN format."""
        if v:
            is_valid, error = validate_inn(v)
            if not is_valid:
                raise ValueError(error)
        return v.strip()

    @field_validator("additional_notes")
    @classmethod
    def validate_notes(cls, v: str) -> str:
        """Validate and sanitize additional notes."""
        if v:
            return sanitize_for_llm(v, max_length=5000, strict=False)
        return ""


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
