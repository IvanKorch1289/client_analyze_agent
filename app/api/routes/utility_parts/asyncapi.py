from __future__ import annotations

import json
from typing import Any, Dict

from fastapi import Request
from fastapi.responses import HTMLResponse

from app.api.compat import is_versioned_request
from app.api.routes.utility import utility_router


@utility_router.get("/asyncapi.json")
async def get_asyncapi_spec(request: Request) -> Dict[str, Any]:
    """
    AsyncAPI спецификация очередей (RabbitMQ/FastStream).
    """
    try:
        from faststream.specification import AsyncAPI

        from app.messaging.broker import broker

        spec = AsyncAPI(broker, title="Client Analysis Messaging", version="1.0.0").to_specification()
        return json.loads(spec.to_json())
    except Exception as e:
        if is_versioned_request(request):
            raise
        return {"status": "error", "message": str(e)}


@utility_router.get("/asyncapi")
async def get_asyncapi_html() -> HTMLResponse:
    """HTML-представление AsyncAPI."""
    from faststream.specification import (
        AsyncAPI,
    )
    from faststream.specification import (
        get_asyncapi_html as _get_asyncapi_html,
    )

    from app.messaging.broker import broker

    spec = AsyncAPI(broker, title="Client Analysis Messaging", version="1.0.0").to_specification()
    html = _get_asyncapi_html(spec)
    return HTMLResponse(content=html)
