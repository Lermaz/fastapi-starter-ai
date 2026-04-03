"""Refresh httpOnly cookie + CSRF when AUTH_REFRESH_COOKIE_ENABLED is on."""

from __future__ import annotations

import os

import pytest
from fastapi.testclient import TestClient

from app.core.config import Settings
from app.main import create_app
from tests.helpers import API_V1_PREFIX, bearer_headers, login_form, register_user


@pytest.fixture
def cookie_auth_client() -> TestClient:
    app = create_app(
        Settings(
            environment="development",
            jwt_secret_key=os.environ["JWT_SECRET_KEY"],
            database_url=os.environ["DATABASE_URL"],
            auth_refresh_cookie_enabled=True,
            auth_cookie_secure=False,
        )
    )
    with TestClient(app) as client:
        yield client


def test_login_sets_cookie_and_csrf(cookie_auth_client: TestClient) -> None:
    register_user(cookie_auth_client, email="cookieuser@test.dev", password="password1")
    response = login_form(cookie_auth_client, email="cookieuser@test.dev", password="password1")
    assert response.status_code == 200
    body = response.json()
    assert body["refresh_token"] is None
    assert body.get("csrf_token")
    assert "refresh_token=" in (response.headers.get("set-cookie") or "").lower()


def test_refresh_with_cookie_requires_csrf_header(cookie_auth_client: TestClient) -> None:
    register_user(cookie_auth_client, email="csrf@test.dev", password="password1")
    login_r = login_form(cookie_auth_client, email="csrf@test.dev", password="password1")
    assert login_r.status_code == 200
    csrf = login_r.json()["csrf_token"]

    bad = cookie_auth_client.post(f"{API_V1_PREFIX}/auth/refresh")
    assert bad.status_code == 403

    ok = cookie_auth_client.post(
        f"{API_V1_PREFIX}/auth/refresh",
        headers={"X-CSRF-Token": csrf},
    )
    assert ok.status_code == 200
    assert ok.json()["refresh_token"] is None


def test_logout_with_refresh_cookie_requires_csrf(cookie_auth_client: TestClient) -> None:
    register_user(cookie_auth_client, email="logoutcsrf@test.dev", password="password1")
    login_r = login_form(cookie_auth_client, email="logoutcsrf@test.dev", password="password1")
    assert login_r.status_code == 200
    token = login_r.json()["access_token"]
    csrf = login_r.json()["csrf_token"]
    headers = bearer_headers(token)

    bad = cookie_auth_client.post(f"{API_V1_PREFIX}/auth/logout", headers=headers)
    assert bad.status_code == 403

    good = cookie_auth_client.post(
        f"{API_V1_PREFIX}/auth/logout",
        headers={**headers, "X-CSRF-Token": csrf},
    )
    assert good.status_code == 204
