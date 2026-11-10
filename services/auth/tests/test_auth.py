from datetime import datetime, timedelta, timezone

import jwt

from app.config import settings

CREDS = {"email": "me@example.com", "password": "password123"}


def register(client, **overrides):
    return client.post("/auth/register", json={**CREDS, **overrides})


def login(client, **overrides):
    return client.post("/auth/login", json={**CREDS, **overrides})


def test_health_checks_the_database(client):
    assert client.get("/health").json() == {
        "status": "ok",
        "service": "auth",
        "database": "ok",
    }


def test_register_returns_the_user_without_secrets(client):
    response = register(client)
    assert response.status_code == 201
    body = response.json()
    assert body["email"] == "me@example.com"
    assert "password" not in body and "password_hash" not in body


def test_email_is_case_insensitive(client):
    assert register(client, email="Me@Example.com").status_code == 201
    assert login(client, email="ME@EXAMPLE.COM").status_code == 200
    assert register(client).status_code == 409


def test_duplicate_email_is_rejected(client):
    register(client)
    response = register(client)
    assert response.status_code == 409
    assert "already registered" in response.json()["detail"]


def test_short_password_is_rejected(client):
    response = register(client, password="short")
    assert response.status_code == 422
    assert "at least 8" in response.json()["detail"][0]["msg"]


def test_overlong_password_is_rejected(client):
    assert register(client, password="x" * 73).status_code == 422


def test_invalid_email_is_rejected(client):
    assert register(client, email="not-an-email").status_code == 422


def test_login_returns_a_token_for_the_right_user(client):
    user_id = register(client).json()["id"]
    response = login(client)
    assert response.status_code == 200
    claims = jwt.decode(
        response.json()["access_token"], settings.jwt_secret, algorithms=["HS256"]
    )
    assert claims["sub"] == str(user_id)


def test_wrong_password_and_unknown_email_look_the_same(client):
    register(client)
    wrong = login(client, password="wrong-password")
    unknown = login(client, email="nobody@example.com")
    assert wrong.status_code == unknown.status_code == 401
    assert wrong.json() == unknown.json()


def test_me_returns_the_logged_in_user(client):
    register(client)
    token = login(client).json()["access_token"]
    response = client.get("/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert response.status_code == 200
    assert response.json()["email"] == "me@example.com"


def test_me_without_a_token_is_401(client):
    assert client.get("/auth/me").status_code == 401


def test_me_with_a_garbage_token_is_401(client):
    response = client.get("/auth/me", headers={"Authorization": "Bearer nonsense"})
    assert response.status_code == 401


def test_me_with_an_expired_token_is_401(client):
    user_id = register(client).json()["id"]
    expired = jwt.encode(
        {"sub": str(user_id), "exp": datetime.now(timezone.utc) - timedelta(minutes=1)},
        settings.jwt_secret,
        algorithm="HS256",
    )
    response = client.get("/auth/me", headers={"Authorization": f"Bearer {expired}"})
    assert response.status_code == 401


def test_me_with_a_token_signed_by_someone_else_is_401(client):
    user_id = register(client).json()["id"]
    forged = jwt.encode(
        {"sub": str(user_id), "exp": datetime.now(timezone.utc) + timedelta(hours=1)},
        "a-different-secret-that-is-long-enough-123",
        algorithm="HS256",
    )
    response = client.get("/auth/me", headers={"Authorization": f"Bearer {forged}"})
    assert response.status_code == 401
