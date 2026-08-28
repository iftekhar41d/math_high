"""Profile read / update for the logged-in student."""

from __future__ import annotations

from tests.test_auth import login, register_and_verify


def _auth_header(client, creds) -> dict:
    token = login(client, creds).json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


def test_student_can_fetch_their_profile(client, fake_email):
    creds = register_and_verify(client, fake_email)
    resp = client.get("/profile", headers=_auth_header(client, creds))
    assert resp.status_code == 200
    body = resp.json()
    assert body["email"] == "ada@example.com"
    assert body["name"] == "Ada Lovelace"
    assert body["year_level"] == 7
    assert body["avatar_url"] is None
    assert body["role"] == "student"


def test_student_can_update_name_avatar_and_year_level(client, fake_email):
    creds = register_and_verify(client, fake_email)
    headers = _auth_header(client, creds)

    resp = client.patch(
        "/profile",
        headers=headers,
        json={
            "name": "Ada, Countess of Lovelace",
            "avatar_url": "/media/avatars/ada.png",
            "year_level": 8,
        },
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["name"] == "Ada, Countess of Lovelace"
    assert body["avatar_url"] == "/media/avatars/ada.png"
    assert body["year_level"] == 8

    # Persisted: a fresh GET sees the change.
    again = client.get("/profile", headers=headers).json()
    assert again["name"] == "Ada, Countess of Lovelace"
    assert again["year_level"] == 8


def test_partial_update_leaves_other_fields_untouched(client, fake_email):
    creds = register_and_verify(client, fake_email)
    headers = _auth_header(client, creds)

    client.patch("/profile", headers=headers, json={"avatar_url": "/media/a.png"})
    resp = client.patch("/profile", headers=headers, json={"name": "Ada L."})
    assert resp.status_code == 200
    body = resp.json()
    assert body["name"] == "Ada L."
    assert body["avatar_url"] == "/media/a.png"  # survived the second patch


def test_profile_requires_authentication(client):
    assert client.get("/profile").status_code == 401
    assert client.patch("/profile", json={"name": "x"}).status_code == 401


def test_profile_rejects_an_out_of_range_year_level(client, fake_email):
    creds = register_and_verify(client, fake_email)
    headers = _auth_header(client, creds)
    assert client.patch("/profile", headers=headers, json={"year_level": 99}).status_code == 422
