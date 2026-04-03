"""Shared HTTP helpers for API integration tests (not fixtures)."""

from __future__ import annotations

from fastapi.testclient import TestClient


def register_user(client: TestClient, *, email: str, password: str):
    return client.post("/auth/register", json={"email": email, "password": password})


def login_form(client: TestClient, *, email: str, password: str):
    return client.post(
        "/auth/login",
        data={"username": email, "password": password},
    )


def bearer_headers(access_token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {access_token}"}
