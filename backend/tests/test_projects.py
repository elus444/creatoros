from fastapi.testclient import TestClient


def test_create_and_list_projects(client: TestClient, auth_headers: dict[str, str]) -> None:
    create_response = client.post(
        "/api/v1/projects",
        json={"name": "Fitness Channel", "niche": "home workouts"},
        headers=auth_headers,
    )
    assert create_response.status_code == 201
    created = create_response.json()
    assert created["name"] == "Fitness Channel"
    assert created["niche"] == "home workouts"

    list_response = client.get("/api/v1/projects", headers=auth_headers)
    assert list_response.status_code == 200
    projects = list_response.json()
    assert len(projects) == 1
    assert projects[0]["id"] == created["id"]


def test_get_project_requires_ownership(client: TestClient) -> None:
    owner_headers = client.post(
        "/api/v1/auth/register",
        json={"email": "owner@example.com", "password": "securepass1"},
    ).json()
    owner_token = owner_headers["access_token"]
    create_response = client.post(
        "/api/v1/projects",
        json={"name": "Owner Project"},
        headers={"Authorization": f"Bearer {owner_token}"},
    )
    project_id = create_response.json()["id"]

    other_token = client.post(
        "/api/v1/auth/register",
        json={"email": "intruder@example.com", "password": "securepass1"},
    ).json()["access_token"]

    response = client.get(
        f"/api/v1/projects/{project_id}",
        headers={"Authorization": f"Bearer {other_token}"},
    )
    assert response.status_code == 404


def test_create_project_requires_auth(client: TestClient) -> None:
    response = client.post("/api/v1/projects", json={"name": "No Auth"})
    assert response.status_code == 401


def test_create_project_rejects_whitespace_only_name(
    client: TestClient, auth_headers: dict[str, str]
) -> None:
    response = client.post(
        "/api/v1/projects", json={"name": "   "}, headers=auth_headers
    )
    assert response.status_code == 422
