"""API tests for registration and login, against a real (in-memory) DB."""


def test_register_creates_user(client):
    response = client.post(
        "/auth/register", json={"email": "alice@example.com", "password": "supersecret123"}
    )

    assert response.status_code == 201
    body = response.json()
    assert body["email"] == "alice@example.com"
    assert "id" in body
    assert "password" not in body  # never echo the password back, hashed or not


def test_register_rejects_duplicate_email(client):
    client.post(
        "/auth/register", json={"email": "alice@example.com", "password": "supersecret123"}
    )
    response = client.post(
        "/auth/register", json={"email": "alice@example.com", "password": "differentpass123"}
    )

    assert response.status_code == 409


def test_register_rejects_short_password(client):
    response = client.post(
        "/auth/register", json={"email": "alice@example.com", "password": "short"}
    )

    assert response.status_code == 422  # Pydantic min_length validation


def test_login_returns_token_for_valid_credentials(client):
    client.post(
        "/auth/register", json={"email": "alice@example.com", "password": "supersecret123"}
    )

    response = client.post(
        "/auth/token", data={"username": "alice@example.com", "password": "supersecret123"}
    )

    assert response.status_code == 200
    body = response.json()
    assert body["token_type"] == "bearer"
    assert len(body["access_token"]) > 0


def test_login_rejects_wrong_password(client):
    client.post(
        "/auth/register", json={"email": "alice@example.com", "password": "supersecret123"}
    )

    response = client.post(
        "/auth/token", data={"username": "alice@example.com", "password": "wrongpassword"}
    )

    assert response.status_code == 401


def test_login_rejects_unknown_user(client):
    response = client.post(
        "/auth/token", data={"username": "ghost@example.com", "password": "whatever123"}
    )

    assert response.status_code == 401
