"""Lightweight OpenAPI contract checks (regressions in routes or schema generation)."""

from __future__ import annotations

from fastapi.testclient import TestClient

from tests.helpers import API_V1_PREFIX


def test_openapi_json_served(client: TestClient) -> None:
    response = client.get("/openapi.json")
    assert response.status_code == 200
    schema = response.json()
    assert schema.get("openapi", "").startswith("3.")
    assert "paths" in schema and isinstance(schema["paths"], dict)
    paths = schema["paths"]
    assert "/health" in paths
    assert "/ready" in paths
    assert f"{API_V1_PREFIX}/auth/register" in paths
    assert f"{API_V1_PREFIX}/auth/login" in paths
    assert f"{API_V1_PREFIX}/videogames" in paths
    assert "info" in schema
    assert schema["info"].get("title")


def test_swagger_ui_available(client: TestClient) -> None:
    response = client.get("/docs")
    assert response.status_code == 200
    assert "swagger" in response.text.lower() or "openapi" in response.text.lower()
