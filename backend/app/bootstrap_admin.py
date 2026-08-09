"""Idempotent admin seed used by entrypoint after migrations."""

from __future__ import annotations

import asyncio
import logging
import secrets

from sqlalchemy import select

from app.config import get_settings
from app.database import AsyncSessionLocal
from app.models import User
from app.services.auth import hash_password

logger = logging.getLogger("jroots")


async def ensure_bootstrap_admin() -> None:
    settings = get_settings()
    email = (settings.bootstrap_admin_email or "").strip().lower()
    if not email:
        return

    username = (settings.bootstrap_admin_username or "").strip() or email.split("@")[0]
    # Admin login uses ADMIN_PASSWORD (see authenticate); DB hash is a placeholder.
    placeholder = hash_password(secrets.token_urlsafe(32))

    async with AsyncSessionLocal() as db:
        result = await db.execute(select(User).where(User.email == email))
        user = result.scalar_one_or_none()
        if user is None:
            user = User(
                username=username,
                email=email,
                hashed_password=placeholder,
                is_admin=True,
                is_verified=True,
            )
            db.add(user)
            await db.commit()
            logger.info("Bootstrap admin created: %s", email)
            return

        changed = False
        if not user.is_admin:
            user.is_admin = True
            changed = True
        if not user.is_verified:
            user.is_verified = True
            changed = True
        if changed:
            await db.commit()
            logger.info("Bootstrap admin promoted: %s", email)
        else:
            logger.info("Bootstrap admin already present: %s", email)


def main() -> None:
    asyncio.run(ensure_bootstrap_admin())


if __name__ == "__main__":
    main()
