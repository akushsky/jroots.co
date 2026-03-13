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
    assert "email" in response.json()["detail"].lower()


async def test_register_duplicate_username(client, db_session):
    await create_user(db_session, username="taken")
    with patch("app.routers.auth.verify_hcaptcha", new_callable=AsyncMock, return_value=True), \
         patch("app.routers.auth.send_email", new_callable=AsyncMock):
        response = await client.post("/api/register", json={
            "username": "taken",
            "email": "other@example.com",
            "password": "securepass123",
            "captcha_token": "fake-token",
        })
    assert response.status_code == 400
    assert response.json()["detail"] == "Имя пользователя уже занято"


async def test_register_strips_whitespace(client, db_session):
    with patch("app.routers.auth.verify_hcaptcha", new_callable=AsyncMock, return_value=True), \
         patch("app.routers.auth.send_email", new_callable=AsyncMock):
        response = await client.post("/api/register", json={
            "username": "  spacey  ",
            "email": "spacey@example.com",
            "password": "securepass123",
            "captcha_token": "fake-token",
        })
    assert response.status_code == 200

    from sqlalchemy import select
    from app.models import User
    result = await db_session.execute(select(User).where(User.email == "spacey@example.com"))
    user = result.scalar_one()
    assert user.username == "spacey"


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


async def test_forgot_password_existing_user(client, db_session):
    await create_user(db_session, email="forgot@example.com")
    with patch("app.routers.auth.send_email", new_callable=AsyncMock) as mock_send:
        response = await client.post("/api/forgot-password", json={"email": "forgot@example.com"})
    assert response.status_code == 200
    assert "существует" in response.json()["message"]
    mock_send.assert_called_once()


async def test_forgot_password_unknown_email(client):
    with patch("app.routers.auth.send_email", new_callable=AsyncMock) as mock_send:
        response = await client.post("/api/forgot-password", json={"email": "nobody@example.com"})
    assert response.status_code == 200
    assert "существует" in response.json()["message"]
    mock_send.assert_not_called()


async def test_forgot_password_unverified_user(client, db_session):
    await create_user(db_session, email="unverified@example.com", is_verified=False)
    with patch("app.routers.auth.send_email", new_callable=AsyncMock) as mock_send:
        response = await client.post("/api/forgot-password", json={"email": "unverified@example.com"})
    assert response.status_code == 200
    mock_send.assert_not_called()


async def test_reset_password_success(client, db_session):
    user = await create_user(db_session, email="reset@example.com", password="oldpass")
    from app.services.auth import generate_reset_token
    token = generate_reset_token(user)

    response = await client.post("/api/reset-password", json={
        "token": token,
        "new_password": "newpass123",
    })
    assert response.status_code == 200
    assert "успешно" in response.json()["message"]

    login_response = await client.post("/api/login", data={
        "username": "reset@example.com",
        "password": "newpass123",
    })
    assert login_response.status_code == 200


async def test_reset_password_invalid_token(client):
    response = await client.post("/api/reset-password", json={
        "token": "invalid.token.here",
        "new_password": "newpass123",
    })
    assert response.status_code == 400


async def test_reset_password_already_used(client, db_session):
    user = await create_user(db_session, email="used@example.com", password="oldpass")
    from app.services.auth import generate_reset_token
    token = generate_reset_token(user)

    response1 = await client.post("/api/reset-password", json={
        "token": token,
        "new_password": "newpass123",
    })
    assert response1.status_code == 200

    response2 = await client.post("/api/reset-password", json={
        "token": token,
        "new_password": "anotherpass",
    })
    assert response2.status_code == 400
    assert "уже была использована" in response2.json()["detail"]
