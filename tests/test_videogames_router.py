"""Tests targeting `app/routers/videogames.py` routes."""

from __future__ import annotations

from fastapi.testclient import TestClient


def _game_payload(*, title: str, genre: str, platform: str = "PC") -> dict:
    return {
        "title": title,
        "genre": genre,
        "platform": platform,
        "price": "49.99",
        "stock": 5,
    }


def test_list_videogames_filter_by_genre(client: TestClient, admin_headers: dict) -> None:
    assert (
        client.post(
            "/videogames", json=_game_payload(title="A", genre="RPG"), headers=admin_headers
        ).status_code
        == 201
    )
    assert (
        client.post(
            "/videogames", json=_game_payload(title="B", genre="FPS"), headers=admin_headers
        ).status_code
        == 201
    )

    filtered = client.get("/videogames?genre=RPG", headers=admin_headers)
    assert filtered.status_code == 200
    data = filtered.json()
    assert data["total"] == 1
    assert data["items"][0]["genre"] == "RPG"


def test_list_videogames_filter_by_platform(client: TestClient, admin_headers: dict) -> None:
    assert (
        client.post(
            "/videogames",
            json=_game_payload(title="PS5 Game", genre="Action", platform="PS5"),
            headers=admin_headers,
        ).status_code
        == 201
    )
    assert (
        client.post(
            "/videogames",
            json=_game_payload(title="PC Game", genre="Action", platform="PC"),
            headers=admin_headers,
        ).status_code
        == 201
    )

    filtered = client.get("/videogames?platform=PS5", headers=admin_headers)
    assert filtered.status_code == 200
    assert filtered.json()["total"] == 1
    assert filtered.json()["items"][0]["platform"] == "PS5"


def test_list_videogames_pagination_offset(client: TestClient, admin_headers: dict) -> None:
    for idx in range(3):
        response = client.post(
            "/videogames",
            json=_game_payload(title=f"Title-{idx}", genre="Indie"),
            headers=admin_headers,
        )
        assert response.status_code == 201

    page = client.get("/videogames?limit=1&offset=1", headers=admin_headers)
    assert page.status_code == 200
    body = page.json()
    assert body["total"] == 3
    assert len(body["items"]) == 1


def test_get_videogame_not_found(client: TestClient, admin_headers: dict) -> None:
    response = client.get("/videogames/999999", headers=admin_headers)
    assert response.status_code == 404


def test_patch_videogame_empty_body_bad_request(client: TestClient, admin_headers: dict) -> None:
    create = client.post(
        "/videogames",
        json=_game_payload(title="PatchMe", genre="Sim"),
        headers=admin_headers,
    )
    assert create.status_code == 201
    game_id = create.json()["id"]

    patch = client.patch(f"/videogames/{game_id}", json={}, headers=admin_headers)
    assert patch.status_code == 400


def test_patch_videogame_not_found(client: TestClient, admin_headers: dict) -> None:
    response = client.patch(
        "/videogames/999999",
        json={"stock": 1},
        headers=admin_headers,
    )
    assert response.status_code == 404


def test_delete_videogame_not_found(client: TestClient, admin_headers: dict) -> None:
    response = client.delete("/videogames/999999", headers=admin_headers)
    assert response.status_code == 404
