"""
API v1 sub-application.

Why a sub-app (mount) instead of duplicating routers with a prefix:
- avoids route-name collisions (important for url_for / OpenAPI operationId)
- allows dedicated docs at /api/v1/docs
- keeps legacy (unversioned) endpoints working without advertising them
"""

from fastapi import FastAPI

from app.api.routes.agent import agent_router
from app.api.routes.data import data_router
from app.api.routes.scheduler import scheduler_router
from app.api.routes.utility import utility_router


def create_v1_app() -> FastAPI:
    # NOTE: Business logic lives in routers; this is just composition.
    app = FastAPI(
        title="Multi-Agent Client Analysis System API",
        version="1.0.0",
        docs_url="/docs",
        redoc_url=None,
    )

    app.include_router(agent_router)
    app.include_router(data_router)
    app.include_router(scheduler_router)
    app.include_router(utility_router)
    return app


v1_app = create_v1_app()

