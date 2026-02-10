"""
API v1 sub-application.

Why a sub-app (mount) instead of duplicating routers with a prefix:
- avoids route-name collisions (important for url_for / OpenAPI operationId)
- allows dedicated docs at /api/v1/docs
- keeps legacy (unversioned) endpoints working without advertising them
"""

from fastapi import FastAPI

from app.api.error_handlers import install_error_handlers
from app.api.routes.admin import admin_router
from app.api.routes.audit import audit_router
from app.api.routes.batch import batch_router
from app.config.constants import APP_VERSION
from app.api.routes.agent import agent_router
from app.api.routes.analytics import analytics_router
from app.api.routes.data import data_router
from app.api.routes.export import export_router
from app.api.routes.llm import llm_router
from app.api.routes.rag import rag_router
from app.api.routes.reports import reports_router
from app.api.routes.scheduler import scheduler_router
from app.api.routes.utility import utility_router
from app.api.routes.webhooks import webhooks_router


def create_v1_app() -> FastAPI:
    # NOTE: Business logic lives in routers; this is just composition.
    app = FastAPI(
        title="Multi-Agent Client Analysis System API",
        version=APP_VERSION,
        docs_url="/docs",
        redoc_url=None,
    )

    install_error_handlers(app)

    # Core routers
    app.include_router(agent_router)
    app.include_router(data_router)
    app.include_router(scheduler_router)
    app.include_router(utility_router)

    # New routers (for frontend analytics and history)
    app.include_router(reports_router)
    app.include_router(analytics_router)

    # Export and comparison (Sprint 5)
    app.include_router(export_router)

    # LLM async endpoint
    app.include_router(llm_router)

    # Admin endpoints (protected by ADMIN_TOKEN)
    app.include_router(admin_router)

    # RAG (Retrieval Augmented Generation)
    app.include_router(rag_router)

    # Phase 6: Enterprise features
    app.include_router(batch_router)
    app.include_router(webhooks_router)
    app.include_router(audit_router)

    return app


v1_app = create_v1_app()
