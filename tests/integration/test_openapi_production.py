"""OpenAPI disabled when explicitly configured for production-style apps."""

from __future__ import annotations

import os

import pytest
from fastapi.testclient import TestClient

from app.core.config import Settings
from app.main import create_app


@pytest.mark.filterwarnings("ignore:.*SQLite in production.*")
def test_openapi_routes_disabled_when_configured() -> None:
    # enable_openapi omitted: auto-disabled when environment is production.
    app = create_app(
        Settings(
            environment="production",
            jwt_secret_key="p" * 32,
            database_url=os.environ["DATABASE_URL"],
        )
    )
    with TestClient(app) as client:
        assert client.get("/docs").status_code == 404
        assert client.get("/redoc").status_code == 404
        assert client.get("/openapi.json").status_code == 404
