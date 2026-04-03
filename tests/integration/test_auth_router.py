"""Tests targeting `app/routers/auth.py` routes."""

from __future__ import annotations

import asyncio

from fastapi.testclient import TestClient

from app.core.security import hash_password
from app.db.session import async_session
from app.models.user import User, UserRole
from tests.helpers import bearer_headers, login_form, register_user


def _seed_inactive_user() -> None:
    async def run() -> None:
        async with async_session() as session:
            user = User(
                email="inactive@test.dev",
                hashed_password=hash_password("password1"),
                is_active=False,
                role=UserRole.user,
            )
            session.add(user)
            await session.commit()

    asyncio.run(run())


def test_login_inactive_user_forbidden(client: TestClient) -> None:
    _seed_inactive_user()
    response = login_form(client, email="inactive@test.dev", password="password1")
    assert response.status_code == 403
    assert "inactive" in response.json()["detail"].lower()


def test_logout_revokes_access_token(client: TestClient) -> None:
    register_user(client, email="logout@test.dev", password="password1")
    login_response = login_form(client, email="logout@test.dev", password="password1")
    assert login_response.status_code == 200
    headers = bearer_headers(login_response.json()["access_token"])

    logout_response = client.post("/auth/logout", headers=headers)
    assert logout_response.status_code == 204

    me_response = client.get("/auth/me", headers=headers)
    assert me_response.status_code == 401


def test_refresh_invalid_jwt_unauthorized(client: TestClient) -> None:
    # RefreshTokenRequest enforces min_length=20; still not a valid JWT.
    response = client.post("/auth/refresh", json={"refresh_token": "x" * 24})
    assert response.status_code == 401


def test_refresh_with_access_token_wrong_type(client: TestClient) -> None:
    register_user(client, email="wrongtype@test.dev", password="password1")
    login_response = login_form(client, email="wrongtype@test.dev", password="password1")
    access_token = login_response.json()["access_token"]
    response = client.post("/auth/refresh", json={"refresh_token": access_token})
    assert response.status_code == 401
    assert response.json()["detail"] == "Invalid refresh token type"


def test_admin_patch_user_role_ok(client: TestClient, admin_headers: dict) -> None:
    register_response = register_user(client, email="promote@test.dev", password="password1")
    assert register_response.status_code == 201
    user_id = register_response.json()["id"]

    patch_response = client.patch(
        f"/auth/users/{user_id}/role",
        json={"role": "admin"},
        headers=admin_headers,
    )
    assert patch_response.status_code == 200
    body = patch_response.json()
    assert body["role"] == "admin"
    assert body["email"] == "promote@test.dev"


def test_admin_patch_user_role_not_found(client: TestClient, admin_headers: dict) -> None:
    response = client.patch(
        "/auth/users/999999/role",
        json={"role": "admin"},
        headers=admin_headers,
    )
    assert response.status_code == 404
