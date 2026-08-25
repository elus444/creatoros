from fastapi.testclient import TestClient


def test_register_login_me_logout_flow(client: TestClient) -> None:
    register_response = client.post(
        "/api/v1/auth/register",
        json={
            "email": "alex@example.com",
            "password": "securepass1",
            "full_name": "Alex Creator",
        },
    )
    assert register_response.status_code == 201
    register_data = register_response.json()
    assert register_data["token_type"] == "bearer"
    assert register_data["user"]["email"] == "alex@example.com"
    token = register_data["access_token"]

    me_response = client.get(
        "/api/v1/auth/me",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert me_response.status_code == 200
    me_data = me_response.json()
    assert me_data["full_name"] == "Alex Creator"
    assert me_data["access_token"]
    assert me_data["access_token"] != token

    slid_me = client.get(
        "/api/v1/auth/me",
        headers={"Authorization": f"Bearer {me_data['access_token']}"},
    )
    assert slid_me.status_code == 200
    assert slid_me.json()["email"] == "alex@example.com"

    login_response = client.post(
        "/api/v1/auth/login",
        json={"email": "alex@example.com", "password": "securepass1"},
    )
    assert login_response.status_code == 200
    login_token = login_response.json()["access_token"]

    logout_response = client.post(
        "/api/v1/auth/logout",
        headers={"Authorization": f"Bearer {login_token}"},
    )
    assert logout_response.status_code == 200

    revoked_me = client.get(
        "/api/v1/auth/me",
        headers={"Authorization": f"Bearer {login_token}"},
    )
    assert revoked_me.status_code == 401


def test_invalid_credentials(client: TestClient) -> None:
    client.post(
        "/api/v1/auth/register",
        json={"email": "sam@example.com", "password": "securepass1"},
    )
    response = client.post(
        "/api/v1/auth/login",
        json={"email": "sam@example.com", "password": "wrong-password"},
    )
    assert response.status_code == 401
    assert response.json()["detail"] == "Invalid email or password."


def test_protected_route_requires_auth(client: TestClient) -> None:
    response = client.get("/api/v1/auth/me")
    assert response.status_code == 401
