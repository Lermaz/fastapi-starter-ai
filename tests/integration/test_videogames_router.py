"""Tests targeting `app/routers/videogames.py` routes."""

from __future__ import annotations

from fastapi.testclient import TestClient

from tests.helpers import API_V1_PREFIX

_VG = f"{API_V1_PREFIX}/videogames"


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
            f"{_VG}", json=_game_payload(title="A", genre="RPG"), headers=admin_headers
        ).status_code
        == 201
    )
    assert (
        client.post(
            f"{_VG}", json=_game_payload(title="B", genre="FPS"), headers=admin_headers
        ).status_code
        == 201
    )

    filtered = client.get(f"{_VG}?genre=RPG", headers=admin_headers)
    assert filtered.status_code == 200
    data = filtered.json()
    assert data["total"] == 1
    assert data["items"][0]["genre"] == "RPG"


def test_list_videogames_filter_by_platform(client: TestClient, admin_headers: dict) -> None:
    assert (
        client.post(
            f"{_VG}",
            json=_game_payload(title="PS5 Game", genre="Action", platform="PS5"),
            headers=admin_headers,
        ).status_code
        == 201
    )
    assert (
        client.post(
            f"{_VG}",
            json=_game_payload(title="PC Game", genre="Action", platform="PC"),
            headers=admin_headers,
        ).status_code
        == 201
    )

    filtered = client.get(f"{_VG}?platform=PS5", headers=admin_headers)
    assert filtered.status_code == 200
    assert filtered.json()["total"] == 1
    assert filtered.json()["items"][0]["platform"] == "PS5"


def test_list_videogames_search_q(client: TestClient, admin_headers: dict) -> None:
    assert (
        client.post(
            f"{_VG}",
            json=_game_payload(title="Elden Ring", genre="RPG"),
            headers=admin_headers,
        ).status_code
        == 201
    )
    assert (
        client.post(
            f"{_VG}",
            json=_game_payload(title="Call of Duty", genre="FPS"),
            headers=admin_headers,
        ).status_code
        == 201
    )
    r = client.get(f"{_VG}?q=elden", headers=admin_headers)
    assert r.status_code == 200
    data = r.json()
    assert data["total"] == 1
    assert "elden" in data["items"][0]["title"].lower()


def test_list_videogames_price_range_and_sort(client: TestClient, admin_headers: dict) -> None:
    for title, price in [("Cheap", "9.99"), ("Mid", "29.99"), ("Premium", "59.99")]:
        assert (
            client.post(
                f"{_VG}",
                json={**_game_payload(title=title, genre="X"), "price": price},
                headers=admin_headers,
            ).status_code
            == 201
        )
    r = client.get(f"{_VG}?min_price=20&max_price=40&sort=price_asc", headers=admin_headers)
    assert r.status_code == 200
    data = r.json()
    assert data["total"] == 1
    assert data["items"][0]["title"] == "Mid"


def test_list_videogames_min_price_gt_max_bad_request(
    client: TestClient, admin_headers: dict
) -> None:
    r = client.get(f"{_VG}?min_price=50&max_price=10", headers=admin_headers)
    assert r.status_code == 400


def test_list_videogames_cursor_pagination(client: TestClient, admin_headers: dict) -> None:
    for idx in range(5):
        assert (
            client.post(
                f"{_VG}",
                json=_game_payload(title=f"C-{idx}", genre="Indie"),
                headers=admin_headers,
            ).status_code
            == 201
        )
    first = client.get(f"{_VG}?limit=2&sort=id_desc", headers=admin_headers)
    assert first.status_code == 200
    b1 = first.json()
    assert b1["total"] == 5
    assert len(b1["items"]) == 2
    assert b1["next_cursor"] is not None

    second = client.get(
        f"{_VG}?limit=2&sort=id_desc&cursor={b1['next_cursor']}",
        headers=admin_headers,
    )
    assert second.status_code == 200
    b2 = second.json()
    assert len(b2["items"]) == 2
    assert b2["next_cursor"] is not None
    ids_page1 = {b1["items"][0]["id"], b1["items"][1]["id"]}
    ids_page2 = {b2["items"][0]["id"], b2["items"][1]["id"]}
    assert ids_page1.isdisjoint(ids_page2)

    third = client.get(
        f"{_VG}?limit=2&sort=id_desc&cursor={b2['next_cursor']}",
        headers=admin_headers,
    )
    assert third.status_code == 200
    b3 = third.json()
    assert len(b3["items"]) == 1
    assert b3["next_cursor"] is None


def test_list_videogames_invalid_cursor(client: TestClient, admin_headers: dict) -> None:
    r = client.get(f"{_VG}?cursor=not-valid-base64!!!", headers=admin_headers)
    assert r.status_code == 400


def test_list_videogames_pagination_offset(client: TestClient, admin_headers: dict) -> None:
    for idx in range(3):
        response = client.post(
            f"{_VG}",
            json=_game_payload(title=f"Title-{idx}", genre="Indie"),
            headers=admin_headers,
        )
        assert response.status_code == 201

    page = client.get(f"{_VG}?limit=1&offset=1", headers=admin_headers)
    assert page.status_code == 200
    body = page.json()
    assert body["total"] == 3
    assert len(body["items"]) == 1


def test_get_videogame_not_found(client: TestClient, admin_headers: dict) -> None:
    response = client.get(f"{_VG}/999999", headers=admin_headers)
    assert response.status_code == 404


def test_patch_videogame_empty_body_bad_request(client: TestClient, admin_headers: dict) -> None:
    create = client.post(
        f"{_VG}",
        json=_game_payload(title="PatchMe", genre="Sim"),
        headers=admin_headers,
    )
    assert create.status_code == 201
    game_id = create.json()["id"]

    patch = client.patch(f"{_VG}/{game_id}", json={}, headers=admin_headers)
    assert patch.status_code == 400


def test_patch_videogame_not_found(client: TestClient, admin_headers: dict) -> None:
    response = client.patch(
        f"{_VG}/999999",
        json={"stock": 1},
        headers=admin_headers,
    )
    assert response.status_code == 404


def test_delete_videogame_not_found(client: TestClient, admin_headers: dict) -> None:
    response = client.delete(f"{_VG}/999999", headers=admin_headers)
    assert response.status_code == 404
