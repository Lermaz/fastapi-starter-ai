"""Shared HTTP helpers for API integration tests (not fixtures)."""

from __future__ import annotations

from fastapi.testclient import TestClient

API_V1_PREFIX = "/api/v1"


def register_user(client: TestClient, *, email: str, password: str):
    return client.post(
        f"{API_V1_PREFIX}/auth/register", json={"email": email, "password": password}
    )


def login_form(client: TestClient, *, email: str, password: str):
    return client.post(
        f"{API_V1_PREFIX}/auth/login",
        data={"username": email, "password": password},
    )


def bearer_headers(access_token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {access_token}"}


def error_detail(response_json: dict) -> object:
    return response_json["error"]["detail"]
