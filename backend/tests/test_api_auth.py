from unittest.mock import patch, AsyncMock

from tests.conftest import create_user


async def test_register_success(client, db_session):
    with patch("app.routers.auth.verify_hcaptcha", new_callable=AsyncMock, return_value=True), \
         patch("app.routers.auth.send_email", new_callable=AsyncMock):
        response = await client.post("/api/register", json={
            "username": "newuser",
            "email": "new@example.com",
            "password": "securepass123",
            "captcha_token": "fake-token",
        })
    assert response.status_code == 200


async def test_register_duplicate_email(client, db_session):
    await create_user(db_session, email="dup@example.com")
    with patch("app.routers.auth.verify_hcaptcha", new_callable=AsyncMock, return_value=True), \
         patch("app.routers.auth.send_email", new_callable=AsyncMock):
        response = await client.post("/api/register", json={
            "username": "another",
            "email": "dup@example.com",
            "password": "securepass123",
            "captcha_token": "fake-token",
        })
    assert response.status_code == 400
    assert "already registered" in response.json()["detail"]


async def test_register_captcha_failure(client):
    with patch("app.routers.auth.verify_hcaptcha", new_callable=AsyncMock, return_value=False):
        response = await client.post("/api/register", json={
            "username": "newuser",
            "email": "new@example.com",
            "password": "securepass123",
            "captcha_token": "bad-token",
        })
    assert response.status_code == 400


async def test_login_success(client, db_session):
    await create_user(db_session, email="login@example.com", password="mypassword")
    response = await client.post("/api/login", data={
        "username": "login@example.com",
        "password": "mypassword",
    })
    assert response.status_code == 200
    data = response.json()
    assert "access_token" in data
    assert data["token_type"] == "bearer"


async def test_login_wrong_password(client, db_session):
    await create_user(db_session, email="login@example.com", password="correctpass")
    response = await client.post("/api/login", data={
        "username": "login@example.com",
        "password": "wrongpass",
    })
    assert response.status_code == 400


async def test_login_nonexistent_user(client):
    response = await client.post("/api/login", data={
        "username": "nobody@example.com",
        "password": "anypass",
    })
    assert response.status_code == 400


async def test_login_unverified_user(client, db_session):
    await create_user(db_session, email="unverified@example.com", password="mypass", is_verified=False)
    response = await client.post("/api/login", data={
        "username": "unverified@example.com",
        "password": "mypass",
    })
    assert response.status_code == 403


async def test_verify_success(client, db_session):
    await create_user(db_session, email="verify@example.com", is_verified=False)
    from app.services.auth import generate_verification_token
    token = generate_verification_token("verify@example.com")
    response = await client.get(f"/api/verify?token={token}")
    assert response.status_code == 200


async def test_verify_invalid_token(client):
    response = await client.get("/api/verify?token=invalid-token")
    assert response.status_code == 400
