from app.services.credits import grant_signup_bonus
from tests.conftest import auth_header, create_user


async def test_get_credits_requires_auth(client):
    response = await client.get("/api/credits")
    assert response.status_code == 401


async def test_get_credits_zero_balance(client, db_session):
    user = await create_user(db_session, email="credits-zero@example.com")
    response = await client.get("/api/credits", headers=auth_header(user))
    assert response.status_code == 200
    assert response.json() == {"searches_left": 0, "scans_left": 0}


async def test_get_credits_reflects_balance(client, db_session):
    user = await create_user(db_session, email="credits-full@example.com")
    await grant_signup_bonus(db_session, user.id)
    await db_session.commit()

    response = await client.get("/api/credits", headers=auth_header(user))
    assert response.status_code == 200
    assert response.json() == {"searches_left": 5, "scans_left": 1}
