from unittest.mock import AsyncMock, patch

from app.rate_limit import limiter
from app.services.auth import generate_verification_token
from app.services.credits import get_balance


async def test_register_does_not_grant_bonus(client, db_session):
    limiter.reset()  # /api/register is capped at 5/min per IP across the suite
    with patch(
        "app.routers.auth.verify_hcaptcha", new_callable=AsyncMock, return_value=True
    ), patch("app.routers.auth.send_email", new_callable=AsyncMock):
        response = await client.post(
            "/api/register",
            json={
                "username": "bonususer",
                "email": "bonus@example.com",
                "password": "securepass123",
                "captcha_token": "fake-token",
            },
        )
    assert response.status_code == 200

    from sqlalchemy import select
    from app.models import User

    result = await db_session.execute(
        select(User).where(User.email == "bonus@example.com")
    )
    user = result.scalar_one()
    assert await get_balance(db_session, user.id) == {
        "searches_left": 0,
        "scans_left": 0,
    }


async def test_verify_grants_signup_bonus_once(client, db_session):
    from tests.conftest import create_user

    user = await create_user(
        db_session, email="verify-bonus@example.com", is_verified=False
    )

    token = generate_verification_token("verify-bonus@example.com")
    response = await client.get(f"/api/verify?token={token}")
    assert response.status_code == 200

    balance = await get_balance(db_session, user.id)
    assert balance == {"searches_left": 5, "scans_left": 1}

    # re-verification must not double the bonus
    response = await client.get(f"/api/verify?token={token}")
    assert response.status_code == 200
    balance = await get_balance(db_session, user.id)
    assert balance == {"searches_left": 5, "scans_left": 1}
