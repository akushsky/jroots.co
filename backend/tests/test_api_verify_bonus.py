from unittest.mock import AsyncMock, patch

from sqlalchemy import func, select

from app.models import CreditTransaction, User
from app.rate_limit import limiter
from app.services.auth import generate_verification_token
from app.services.credits import get_balance
from tests.conftest import create_user


def _register_payload(email, fingerprint=None):
    payload = {
        "username": "user",
        "email": email,
        "password": "securepass123",
        "captcha_token": "fake-token",
    }
    if fingerprint is not None:
        payload["fingerprint"] = fingerprint
    return payload


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

    result = await db_session.execute(
        select(User).where(User.email == "bonus@example.com")
    )
    user = result.scalar_one()
    assert await get_balance(db_session, user.id) == {
        "searches_left": 0,
        "scans_left": 0,
    }


async def test_verify_grants_signup_bonus_once(client, db_session):
    user = await create_user(
        db_session, email="verify-bonus@example.com", is_verified=False
    )

    token = generate_verification_token("verify-bonus@example.com")
    response = await client.get(f"/api/verify?token={token}")
    assert response.status_code == 200
    assert response.json()["free_pool_granted"] is True

    balance = await get_balance(db_session, user.id)
    assert balance == {"searches_left": 5, "scans_left": 1}

    # re-verification must not double the bonus
    response = await client.get(f"/api/verify?token={token}")
    assert response.status_code == 200
    balance = await get_balance(db_session, user.id)
    assert balance == {"searches_left": 5, "scans_left": 1}


async def test_register_stores_fingerprint(client, db_session):
    limiter.reset()
    with patch(
        "app.routers.auth.verify_hcaptcha", new_callable=AsyncMock, return_value=True
    ), patch("app.routers.auth.send_email", new_callable=AsyncMock):
        response = await client.post(
            "/api/register",
            json=_register_payload("fp-store@example.com", fingerprint="fp-abc"),
        )
    assert response.status_code == 200

    user = (
        await db_session.execute(
            select(User).where(User.email == "fp-store@example.com")
        )
    ).scalar_one()
    assert user.fingerprint_hash == "fp-abc"


async def test_fingerprint_first_two_accounts_get_bonus(client, db_session):
    for email in ("fp12-a@example.com", "fp12-b@example.com"):
        user = await create_user(db_session, email=email, is_verified=False)
        user.fingerprint_hash = "fp-shared-12"
        await db_session.commit()

        token = generate_verification_token(email)
        response = await client.get(f"/api/verify?token={token}")
        assert response.status_code == 200
        assert response.json()["free_pool_granted"] is True
        assert await get_balance(db_session, user.id) == {
            "searches_left": 5,
            "scans_left": 1,
        }


async def test_fingerprint_third_account_gets_no_bonus(client, db_session):
    # Create AND verify one account at a time — the anti-abuse rule counts
    # accounts sharing the fingerprint at verify time.
    async def register_and_verify(email):
        user = await create_user(db_session, email=email, is_verified=False)
        user.fingerprint_hash = "fp-shared-3"
        await db_session.commit()
        token = generate_verification_token(email)
        response = await client.get(f"/api/verify?token={token}")
        assert response.status_code == 200
        return user, response.json()

    _, body1 = await register_and_verify("fp3-a@example.com")
    _, body2 = await register_and_verify("fp3-b@example.com")
    third, body3 = await register_and_verify("fp3-c@example.com")

    assert body1["free_pool_granted"] is True
    assert body2["free_pool_granted"] is True
    assert body3["free_pool_granted"] is False

    assert await get_balance(db_session, third.id) == {
        "searches_left": 0,
        "scans_left": 0,
    }
    txns = (
        await db_session.execute(
            select(func.count(CreditTransaction.id)).where(
                CreditTransaction.user_id == third.id
            )
        )
    ).scalar_one()
    assert txns == 0


async def test_rate_limited_code_on_register_flood(client, db_session):
    limiter.reset()
    with patch(
        "app.routers.auth.verify_hcaptcha", new_callable=AsyncMock, return_value=True
    ), patch("app.routers.auth.send_email", new_callable=AsyncMock):
        last = None
        for i in range(6):  # /api/register is limited to 5/minute
            last = await client.post(
                "/api/register",
                json=_register_payload(f"flood-{i}@example.com"),
            )
    assert last.status_code == 429
    detail = last.json()["detail"]
    assert detail["code"] == "rate_limited"
    assert detail["message"]
