"""Pytest setup: force test DATABASE_URL and JWT before the app builds its engine."""

from __future__ import annotations

import asyncio
import os
import tempfile
import uuid
from collections.abc import Generator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import delete

# Must run before importing app.db.session (engine is created at import time).
_test_db_path = Path(tempfile.gettempdir()) / f"fastapi-cursor-pytest-{uuid.uuid4().hex}.sqlite"
_test_db_path.unlink(missing_ok=True)
os.environ["DATABASE_URL"] = f"sqlite+aiosqlite:///{_test_db_path.as_posix()}"
os.environ["JWT_SECRET_KEY"] = "pytest-jwt-secret-key-not-for-production"

from app.core.security import hash_password
from app.db.session import Base, async_session, engine
from app.main import app
from app.models.user import User, UserRole
from app.models.videogame import Videogame


@pytest.fixture(scope="session", autouse=True)
def _create_schema() -> Generator[None, None, None]:
    async def run() -> None:
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)

    asyncio.run(run())
    yield
    asyncio.run(engine.dispose())
    _test_db_path.unlink(missing_ok=True)


@pytest.fixture(autouse=True)
def _truncate_tables() -> Generator[None, None, None]:
    yield

    async def truncate() -> None:
        async with async_session() as session:
            await session.execute(delete(Videogame))
            await session.execute(delete(User))
            await session.commit()

    asyncio.run(truncate())


@pytest.fixture
def client() -> Generator[TestClient, None, None]:
    with TestClient(app) as test_client:
        yield test_client


def register_user(client: TestClient, *, email: str, password: str):
    return client.post("/auth/register", json={"email": email, "password": password})


def login_form(client: TestClient, *, email: str, password: str):
    return client.post(
        "/auth/login",
        data={"username": email, "password": password},
    )


def bearer_headers(access_token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {access_token}"}


@pytest.fixture
def regular_user(client: TestClient) -> tuple[str, str, dict[str, str]]:
    email = "regular@test.dev"
    password = "regular12"
    register_response = register_user(client, email=email, password=password)
    assert register_response.status_code == 201, register_response.text
    body = register_response.json()
    assert body["role"] == "user"

    login_response = login_form(client, email=email, password=password)
    assert login_response.status_code == 200, login_response.text
    token = login_response.json()["access_token"]
    return email, password, bearer_headers(token)


@pytest.fixture
def admin_headers(client: TestClient) -> dict[str, str]:
    email = "admin@test.dev"
    password = "adminpass12"

    async def insert_admin() -> None:
        async with async_session() as session:
            user = User(
                email=email,
                hashed_password=hash_password(password),
                is_active=True,
                role=UserRole.admin,
            )
            session.add(user)
            await session.commit()

    asyncio.run(insert_admin())
    login_response = login_form(client, email=email, password=password)
    assert login_response.status_code == 200, login_response.text
    return bearer_headers(login_response.json()["access_token"])
