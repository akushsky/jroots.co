from sqlalchemy import select

from app.bootstrap_admin import ensure_bootstrap_admin
from app.config import get_settings
from app.models import User


async def test_ensure_bootstrap_admin_creates_verified_admin(db_session, monkeypatch):
    get_settings.cache_clear()
    monkeypatch.setenv("BOOTSTRAP_ADMIN_EMAIL", "michael.akushsky@gmail.com")
    monkeypatch.setenv("BOOTSTRAP_ADMIN_USERNAME", "michael")
    get_settings.cache_clear()

    try:
        await ensure_bootstrap_admin()

        result = await db_session.execute(
            select(User).where(User.email == "michael.akushsky@gmail.com")
        )
        user = result.scalar_one()
        assert user.is_admin is True
        assert user.is_verified is True
        assert user.username == "michael"

        # Idempotent: second call does not fail or duplicate.
        await ensure_bootstrap_admin()
        again = await db_session.execute(
            select(User).where(User.email == "michael.akushsky@gmail.com")
        )
        assert len(again.scalars().all()) == 1
    finally:
        monkeypatch.delenv("BOOTSTRAP_ADMIN_EMAIL", raising=False)
        monkeypatch.delenv("BOOTSTRAP_ADMIN_USERNAME", raising=False)
        get_settings.cache_clear()


async def test_ensure_bootstrap_admin_promotes_existing(db_session, monkeypatch):
    from tests.conftest import create_user

    await create_user(
        db_session,
        email="michael.akushsky@gmail.com",
        username="old",
        is_admin=False,
    )
    # create_user leaves is_verified True by default in conftest — force False.
    result = await db_session.execute(
        select(User).where(User.email == "michael.akushsky@gmail.com")
    )
    user = result.scalar_one()
    user.is_verified = False
    await db_session.commit()

    get_settings.cache_clear()
    monkeypatch.setenv("BOOTSTRAP_ADMIN_EMAIL", "michael.akushsky@gmail.com")
    get_settings.cache_clear()
    try:
        await ensure_bootstrap_admin()
        await db_session.refresh(user)
        assert user.is_admin is True
        assert user.is_verified is True
    finally:
        monkeypatch.delenv("BOOTSTRAP_ADMIN_EMAIL", raising=False)
        get_settings.cache_clear()
