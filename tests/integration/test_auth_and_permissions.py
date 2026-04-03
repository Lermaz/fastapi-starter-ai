from __future__ import annotations

import time

from fastapi.testclient import TestClient

from tests.helpers import API_V1_PREFIX, login_form, register_user


def test_register_creates_user_with_role_user(client: TestClient) -> None:
    response = register_user(client, email="newbie@test.dev", password="password1")
    assert response.status_code == 201
    data = response.json()
    assert data["email"] == "newbie@test.dev"
    assert data["role"] == "user"
    assert data["is_active"] is True


def test_register_duplicate_email_conflict(client: TestClient) -> None:
    register_user(client, email="dup@test.dev", password="password1")
    response = register_user(client, email="dup@test.dev", password="password2")
    assert response.status_code == 409


def test_login_returns_bearer_tokens(client: TestClient) -> None:
    register_user(client, email="login@test.dev", password="password1")
    response = login_form(client, email="login@test.dev", password="password1")
    assert response.status_code == 200
    data = response.json()
    assert data["token_type"] == "bearer"
    assert "access_token" in data and "refresh_token" in data
    assert len(data["access_token"]) > 20


def test_login_invalid_password_unauthorized(client: TestClient) -> None:
    register_user(client, email="badlogin@test.dev", password="correctpass")
    response = login_form(client, email="badlogin@test.dev", password="wrongpass")
    assert response.status_code == 401


def test_me_without_token_unauthorized(client: TestClient) -> None:
    response = client.get(f"{API_V1_PREFIX}/auth/me")
    assert response.status_code == 401


def test_me_with_token_ok(client: TestClient, regular_user: tuple) -> None:
    _, _, headers = regular_user
    response = client.get(f"{API_V1_PREFIX}/auth/me", headers=headers)
    assert response.status_code == 200
    assert response.json()["email"] == "regular@test.dev"


def test_regular_user_cannot_create_videogame(client: TestClient, regular_user: tuple) -> None:
    _, _, headers = regular_user
    payload = {
        "title": "Test Game",
        "genre": "RPG",
        "platform": "PC",
        "price": "59.99",
        "stock": 5,
    }
    response = client.post(f"{API_V1_PREFIX}/videogames", json=payload, headers=headers)
    assert response.status_code == 403


def test_regular_user_cannot_change_roles(client: TestClient, regular_user: tuple) -> None:
    _, _, headers = regular_user
    response = client.patch(
        f"{API_V1_PREFIX}/auth/users/1/role",
        json={"role": "admin"},
        headers=headers,
    )
    assert response.status_code == 403


def test_regular_user_can_list_videogames_empty(client: TestClient, regular_user: tuple) -> None:
    _, _, headers = regular_user
    response = client.get(f"{API_V1_PREFIX}/videogames", headers=headers)
    assert response.status_code == 200
    data = response.json()
    assert data["total"] == 0
    assert data["items"] == []


def test_admin_videogame_crud_flow(client: TestClient, admin_headers: dict) -> None:
    create_payload = {
        "title": "Hollow Knight",
        "genre": "Metroidvania",
        "platform": "PC",
        "price": "19.99",
        "stock": 10,
    }
    create_response = client.post(
        f"{API_V1_PREFIX}/videogames", json=create_payload, headers=admin_headers
    )
    assert create_response.status_code == 201, create_response.text
    created = create_response.json()
    game_id = created["id"]
    assert created["title"] == "Hollow Knight"

    list_response = client.get(f"{API_V1_PREFIX}/videogames", headers=admin_headers)
    assert list_response.status_code == 200
    assert list_response.json()["total"] == 1

    get_response = client.get(f"{API_V1_PREFIX}/videogames/{game_id}", headers=admin_headers)
    assert get_response.status_code == 200
    assert get_response.json()["stock"] == 10

    patch_response = client.patch(
        f"{API_V1_PREFIX}/videogames/{game_id}",
        json={"stock": 3},
        headers=admin_headers,
    )
    assert patch_response.status_code == 200
    assert patch_response.json()["stock"] == 3

    delete_response = client.delete(f"{API_V1_PREFIX}/videogames/{game_id}", headers=admin_headers)
    assert delete_response.status_code == 204

    missing = client.get(f"{API_V1_PREFIX}/videogames/{game_id}", headers=admin_headers)
    assert missing.status_code == 404


def test_refresh_token_returns_new_pair(client: TestClient) -> None:
    register_user(client, email="refresh@test.dev", password="password1")
    login_response = login_form(client, email="refresh@test.dev", password="password1")
    assert login_response.status_code == 200
    old_refresh = login_response.json()["refresh_token"]

    # JWT `exp` is second-resolution; wait so refresh mints a distinct token string.
    time.sleep(1.1)

    refresh_response = client.post(
        f"{API_V1_PREFIX}/auth/refresh",
        json={"refresh_token": old_refresh},
    )
    assert refresh_response.status_code == 200
    new_pair = refresh_response.json()
    assert new_pair["refresh_token"] != old_refresh
    assert len(new_pair["access_token"]) > 20

    stale = client.post(f"{API_V1_PREFIX}/auth/refresh", json={"refresh_token": old_refresh})
    assert stale.status_code == 401
