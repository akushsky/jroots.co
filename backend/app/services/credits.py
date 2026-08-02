import logging

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Credit, CreditTransaction

logger = logging.getLogger("jroots")

SIGNUP_BONUS_SEARCHES = 5
SIGNUP_BONUS_SCANS = 1


class InsufficientCredits(Exception):
    def __init__(self, user_id: int, searches: int, scans: int):
        self.user_id = user_id
        self.searches = searches
        self.scans = scans
        super().__init__(
            f"User {user_id} has insufficient credits for charge "
            f"(searches={searches}, scans={scans})"
        )


def _balance_dict(credit: Credit | None) -> dict:
    if credit is None:
        return {"searches_left": 0, "scans_left": 0}
    return {"searches_left": credit.searches_left, "scans_left": credit.scans_left}


def _validate_amounts(searches: int, scans: int) -> None:
    if searches < 0 or scans < 0:
        raise ValueError(
            f"Credit amounts must be non-negative (searches={searches}, scans={scans})"
        )


async def get_balance(session: AsyncSession, user_id: int) -> dict:
    result = await session.execute(select(Credit).where(Credit.user_id == user_id))
    return _balance_dict(result.scalar_one_or_none())


def _dialect_insert(session: AsyncSession, table):
    dialect = session.bind.dialect.name if session.bind is not None else ""
    if dialect == "postgresql":
        from sqlalchemy.dialects.postgresql import insert

        return insert(table)
    if dialect == "sqlite":
        from sqlalchemy.dialects.sqlite import insert

        return insert(table)
    raise RuntimeError(f"Unsupported database dialect for credits upsert: {dialect!r}")


async def _add_to_balance(
    session: AsyncSession, user_id: int, delta_searches: int, delta_scans: int
) -> None:
    """Atomically increment the balance, creating the credits row if missing."""
    table = Credit.__table__
    stmt = _dialect_insert(session, table).values(
        user_id=user_id, searches_left=delta_searches, scans_left=delta_scans
    )
    stmt = stmt.on_conflict_do_update(
        index_elements=["user_id"],
        set_={
            "searches_left": table.c.searches_left + delta_searches,
            "scans_left": table.c.scans_left + delta_scans,
        },
    )
    await session.execute(stmt)


async def _insert_journal(
    session: AsyncSession,
    user_id: int,
    delta_searches: int,
    delta_scans: int,
    reason: str,
    ref_id: str | None,
    *,
    ignore_conflicts: bool,
) -> bool:
    """Insert a journal row. With ignore_conflicts, a duplicate
    (user_id, reason, ref_id) inserts nothing and returns False."""
    table = CreditTransaction.__table__
    stmt = _dialect_insert(session, table).values(
        user_id=user_id,
        delta_searches=delta_searches,
        delta_scans=delta_scans,
        reason=reason,
        ref_id=ref_id,
    )
    if ignore_conflicts:
        stmt = stmt.on_conflict_do_nothing().returning(table.c.id)
        row = (await session.execute(stmt)).one_or_none()
        return row is not None
    await session.execute(stmt)
    return True


async def grant(
    session: AsyncSession,
    user_id: int,
    *,
    searches: int = 0,
    scans: int = 0,
    reason: str,
    ref_id: str | None = None,
) -> dict:
    """Atomically idempotent credit grant.

    When ref_id is provided, the journal row is inserted with
    ON CONFLICT DO NOTHING against (user_id, reason, ref_id); the balance is
    credited only when the journal row was actually inserted, so concurrent or
    retried grants (payment webhooks, bonus hooks) can never double-credit.
    Flushes but does not commit — the caller owns the transaction.
    """
    _validate_amounts(searches, scans)

    if ref_id is not None:
        inserted = await _insert_journal(
            session, user_id, searches, scans, reason, ref_id, ignore_conflicts=True
        )
        if not inserted:
            logger.info(
                "Duplicate credit grant ignored for user %d (reason=%s, ref_id=%s)",
                user_id,
                reason,
                ref_id,
            )
            return {"granted": False, **await get_balance(session, user_id)}
    else:
        await _insert_journal(
            session, user_id, searches, scans, reason, ref_id, ignore_conflicts=False
        )

    await _add_to_balance(session, user_id, searches, scans)
    await session.flush()
    logger.info(
        "Granted credits to user %d: searches=%+d, scans=%+d (reason=%s, ref_id=%s)",
        user_id,
        searches,
        scans,
        reason,
        ref_id,
    )
    return {"granted": True, **await get_balance(session, user_id)}


async def charge(
    session: AsyncSession,
    user_id: int,
    *,
    searches: int = 0,
    scans: int = 0,
    reason: str = "usage",
    ref_id: str | None = None,
) -> dict:
    """Atomically deduct credits; raises InsufficientCredits when the balance
    cannot cover the charge. Journal row is written in the same transaction.
    A zero charge is a no-op (no journal row). Flushes but does not commit —
    the caller owns the transaction.
    """
    _validate_amounts(searches, scans)

    if searches == 0 and scans == 0:
        return {"charged": True, **await get_balance(session, user_id)}

    result = await session.execute(
        update(Credit)
        .where(
            Credit.user_id == user_id,
            Credit.searches_left >= searches,
            Credit.scans_left >= scans,
        )
        .values(
            searches_left=Credit.searches_left - searches,
            scans_left=Credit.scans_left - scans,
        )
        .returning(Credit.searches_left, Credit.scans_left)
    )
    row = result.one_or_none()
    if row is None:
        raise InsufficientCredits(user_id, searches, scans)

    session.add(
        CreditTransaction(
            user_id=user_id,
            delta_searches=-searches,
            delta_scans=-scans,
            reason=reason,
            ref_id=ref_id,
        )
    )
    await session.flush()
    logger.info(
        "Charged user %d: searches=-%d, scans=-%d (reason=%s, ref_id=%s)",
        user_id,
        searches,
        scans,
        reason,
        ref_id,
    )
    return {
        "charged": True,
        "searches_left": row.searches_left,
        "scans_left": row.scans_left,
    }


async def grant_signup_bonus(session: AsyncSession, user_id: int) -> dict:
    """One-time welcome package: 5 searches + 1 scan per user."""
    return await grant(
        session,
        user_id,
        searches=SIGNUP_BONUS_SEARCHES,
        scans=SIGNUP_BONUS_SCANS,
        reason="signup_bonus",
        ref_id=str(user_id),
    )
