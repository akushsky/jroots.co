"""Idempotent admin seed used by entrypoint after migrations."""

from __future__ import annotations

import asyncio
import logging
import secrets
from datetime import datetime, timedelta, timezone

from sqlalchemy import select

from app.config import get_settings
from app.database import AsyncSessionLocal
from app.models import User
from app.models.billing import Subscription
from app.services import credits
from app.services.auth import hash_password

logger = logging.getLogger("jroots")

# Enough for invite-only beta testing without Polar webhooks.
_BETA_SEARCHES = 100
_BETA_SCANS = 20


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
            await db.flush()
            logger.info("Bootstrap admin created: %s", email)
        else:
            changed = False
            if not user.is_admin:
                user.is_admin = True
                changed = True
            if not user.is_verified:
                user.is_verified = True
                changed = True
            if changed:
                logger.info("Bootstrap admin promoted: %s", email)
            else:
                logger.info("Bootstrap admin already present: %s", email)

        sub = (
            await db.execute(
                select(Subscription).where(
                    Subscription.user_id == user.id, Subscription.status == "active"
                )
            )
        ).scalar_one_or_none()
        if sub is None:
            db.add(
                Subscription(
                    user_id=user.id,
                    status="active",
                    provider="manual",
                    provider_sub_id="bootstrap-admin",
                    current_period_end=datetime.now(timezone.utc).replace(tzinfo=None)
                    + timedelta(days=365),
                )
            )
            logger.info("Bootstrap admin subscription granted: %s", email)

        grant = await credits.grant(
            db,
            user.id,
            searches=_BETA_SEARCHES,
            scans=_BETA_SCANS,
            reason="bootstrap_admin",
            ref_id="bootstrap-admin",
        )
        if grant.get("granted"):
            logger.info(
                "Bootstrap admin credits granted: %s searches=%s scans=%s",
                email,
                _BETA_SEARCHES,
                _BETA_SCANS,
            )

        await db.commit()


def main() -> None:
    asyncio.run(ensure_bootstrap_admin())


if __name__ == "__main__":
    main()
