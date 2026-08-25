"""Focused error-handling tests for the auth endpoints.

Complements test_auth.py's happy-path flow with the specific failure
shapes callers rely on (status codes, detail text, WWW-Authenticate).
"""

from fastapi.testclient import TestClient


def test_register_with_invalid_email(client: TestClient) -> None:
    response = client.post(
        "/api/v1/auth/register",
        json={"email": "not-an-email", "password": "securepass1"},
    )
    assert response.status_code == 422
    assert "detail" in response.json()


def test_register_with_short_password(client: TestClient) -> None:
    response = client.post(
        "/api/v1/auth/register",
        json={"email": "shortpass@example.com", "password": "short"},
    )
    assert response.status_code == 422
    assert "detail" in response.json()


def test_register_duplicate_email(client: TestClient) -> None:
    email = "dupe@example.com"
    payload = {"email": email, "password": "securepass1", "full_name": "Dupe One"}

    first = client.post("/api/v1/auth/register", json=payload)
    assert first.status_code == 201

    second = client.post(
        "/api/v1/auth/register",
        json={**payload, "full_name": "Dupe Two"},
    )
    assert second.status_code == 409
    assert "already exists" in second.json()["detail"].lower()


def test_login_with_invalid_email_format(client: TestClient) -> None:
    response = client.post(
        "/api/v1/auth/login",
        json={"email": "not-an-email", "password": "whatever"},
    )
    assert response.status_code == 422
    assert "detail" in response.json()


def test_login_with_nonexistent_user(client: TestClient) -> None:
    response = client.post(
        "/api/v1/auth/login",
        json={"email": "nobody@example.com", "password": "securepass1"},
    )
    assert response.status_code == 401
    assert response.json()["detail"] == "Invalid email or password."


def test_me_without_token(client: TestClient) -> None:
    response = client.get("/api/v1/auth/me")
    assert response.status_code == 401
    assert "WWW-Authenticate" in response.headers
    assert response.headers["WWW-Authenticate"] == "Bearer"


def test_me_with_malformed_token(client: TestClient) -> None:
    response = client.get(
        "/api/v1/auth/me",
        headers={"Authorization": "Bearer invalid.token.here"},
    )
    assert response.status_code == 401
    assert "WWW-Authenticate" in response.headers
    assert "detail" in response.json()


def test_me_with_wrong_scheme(client: TestClient) -> None:
    response = client.get(
        "/api/v1/auth/me",
        headers={"Authorization": "Basic invalid.token.here"},
    )
    assert response.status_code == 401


def test_logout_without_token_is_a_no_op(client: TestClient) -> None:
    response = client.post("/api/v1/auth/logout")
    assert response.status_code == 200
    assert response.json()["message"] == "Logged out."
