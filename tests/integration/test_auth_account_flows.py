"""Email verification and password reset flows."""

from __future__ import annotations

import logging
import re

import pytest
from fastapi.testclient import TestClient

from app.core.config import settings
from app.main import create_app
from tests.helpers import API_V1_PREFIX, bearer_headers, login_form, register_user

_AUTH = f"{API_V1_PREFIX}/auth"
_TOKEN_RE = re.compile(r"(\d+:[A-Za-z0-9_-]+)")


def _first_token(caplog: pytest.LogCaptureFixture) -> str:
    m = _TOKEN_RE.search(caplog.text)
    assert m is not None, caplog.text
    return m.group(1)


def test_register_default_email_verified(client: TestClient) -> None:
    r = register_user(client, email="verified@test.dev", password="password1")
    assert r.status_code == 201
    assert r.json()["email_verified"] is True


def test_email_verification_required_then_login(caplog: pytest.LogCaptureFixture) -> None:
    cfg = settings.model_copy(update={"auth_require_email_verification": True})
    app = create_app(cfg)
    with caplog.at_level(logging.INFO, logger="app.core.email"):
        with TestClient(app) as client:
            reg = register_user(client, email="needverify@test.dev", password="password1")
            assert reg.status_code == 201
            assert reg.json()["email_verified"] is False
            assert (
                login_form(client, email="needverify@test.dev", password="password1").status_code
                == 403
            )

            token = _first_token(caplog)
            verify = client.post(f"{_AUTH}/verify-email", json={"token": token})
            assert verify.status_code == 200
            assert verify.json()["email_verified"] is True

            login = login_form(client, email="needverify@test.dev", password="password1")
            assert login.status_code == 200


def test_forgot_password_unknown_email_returns_204(client: TestClient) -> None:
    r = client.post(f"{_AUTH}/forgot-password", json={"email": "ghost@test.dev"})
    assert r.status_code == 204


def test_password_reset_invalidates_access_token(
    caplog: pytest.LogCaptureFixture, client: TestClient
) -> None:
    register_user(client, email="resetflow@test.dev", password="oldpass12")
    login_r = login_form(client, email="resetflow@test.dev", password="oldpass12")
    assert login_r.status_code == 200
    old_access = login_r.json()["access_token"]
    old_headers = bearer_headers(old_access)

    with caplog.at_level(logging.INFO, logger="app.core.email"):
        fp = client.post(f"{_AUTH}/forgot-password", json={"email": "resetflow@test.dev"})
    assert fp.status_code == 204
    token = _first_token(caplog)

    rs = client.post(
        f"{_AUTH}/reset-password",
        json={"token": token, "new_password": "newpass12"},
    )
    assert rs.status_code == 204

    me_old = client.get(f"{_AUTH}/me", headers=old_headers)
    assert me_old.status_code == 401

    login_new = login_form(client, email="resetflow@test.dev", password="newpass12")
    assert login_new.status_code == 200
