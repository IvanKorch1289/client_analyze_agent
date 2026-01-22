import sys
from pathlib import Path

import pytest
from httpx import ASGITransport, AsyncClient


# Ensure `import app` works when running tests without installing the package.
ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


@pytest.fixture
def async_client():
    """
    Factory fixture for creating AsyncClient with ASGITransport.

    Usage:
        async def test_endpoint(async_client):
            from app.main import app
            async with async_client(app) as client:
                response = await client.get("/endpoint")
    """

    def _make_client(app, base_url: str = "http://test"):
        transport = ASGITransport(app=app)
        return AsyncClient(transport=transport, base_url=base_url)

    return _make_client

