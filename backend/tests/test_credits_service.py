import pytest
from sqlalchemy import select

from app.models import Credit, CreditTransaction
from app.services.credits import (
    InsufficientCredits,
    charge,
    get_balance,
    grant,
    grant_signup_bonus,
)
from tests.conftest import create_user


async def _journal(db_session, user_id):
    result = await db_session.execute(
        select(CreditTransaction).where(CreditTransaction.user_id == user_id)
    )
    return result.scalars().all()


async def test_get_balance_no_row_returns_zeros(db_session):
    user = await create_user(db_session)
    balance = await get_balance(db_session, user.id)
    assert balance == {"searches_left": 0, "scans_left": 0}
    # must not create a credits row as a side effect
    row = await db_session.get(Credit, user.id)
    assert row is None


async def test_signup_bonus_granted_once(db_session):
    user = await create_user(db_session)

    first = await grant_signup_bonus(db_session, user.id)
    assert first["granted"] is True
    assert first["searches_left"] == 5
    assert first["scans_left"] == 1

    second = await grant_signup_bonus(db_session, user.id)
    assert second["granted"] is False
    assert second["searches_left"] == 5
    assert second["scans_left"] == 1

    journal = await _journal(db_session, user.id)
    assert len(journal) == 1
    assert journal[0].reason == "signup_bonus"
    assert journal[0].ref_id == str(user.id)
    assert journal[0].delta_searches == 5
    assert journal[0].delta_scans == 1


async def test_grant_purchase_idempotent_by_ref_id(db_session):
    user = await create_user(db_session)

    first = await grant(
        db_session, user.id, searches=10, scans=2, reason="purchase", ref_id="pay-123"
    )
    assert first["granted"] is True
    assert first["searches_left"] == 10
    assert first["scans_left"] == 2

    second = await grant(
        db_session, user.id, searches=10, scans=2, reason="purchase", ref_id="pay-123"
    )
    assert second["granted"] is False
    assert second["searches_left"] == 10
    assert second["scans_left"] == 2

    journal = await _journal(db_session, user.id)
    assert len(journal) == 1


async def test_grant_without_ref_id_always_applies(db_session):
    user = await create_user(db_session)

    await grant(db_session, user.id, searches=3, reason="admin")
    result = await grant(db_session, user.id, searches=3, reason="admin")
    assert result["granted"] is True
    assert result["searches_left"] == 6

    journal = await _journal(db_session, user.id)
    assert len(journal) == 2


async def test_grant_accumulates_on_existing_row(db_session):
    user = await create_user(db_session)

    await grant(
        db_session, user.id, searches=5, scans=1, reason="purchase", ref_id="p1"
    )
    result = await grant(
        db_session, user.id, searches=7, scans=4, reason="purchase", ref_id="p2"
    )
    assert result["searches_left"] == 12
    assert result["scans_left"] == 5


async def test_charge_success_deducts_and_journals(db_session):
    user = await create_user(db_session)
    await grant_signup_bonus(db_session, user.id)

    result = await charge(
        db_session, user.id, searches=1, reason="usage", ref_id="search-42"
    )
    assert result == {"charged": True, "searches_left": 4, "scans_left": 1}

    journal = await _journal(db_session, user.id)
    assert len(journal) == 2
    charge_row = next(t for t in journal if t.reason == "usage")
    assert charge_row.delta_searches == -1
    assert charge_row.delta_scans == 0
    assert charge_row.ref_id == "search-42"


async def test_charge_insufficient_raises_and_leaves_state_untouched(db_session):
    user = await create_user(db_session)
    await grant_signup_bonus(db_session, user.id)

    with pytest.raises(InsufficientCredits):
        await charge(db_session, user.id, searches=6)

    balance = await get_balance(db_session, user.id)
    assert balance == {"searches_left": 5, "scans_left": 1}
    journal = await _journal(db_session, user.id)
    assert len(journal) == 1  # only the signup bonus


async def test_charge_partial_insufficient_is_atomic(db_session):
    user = await create_user(db_session)
    await grant_signup_bonus(db_session, user.id)

    # enough searches, not enough scans -> whole charge must fail
    with pytest.raises(InsufficientCredits):
        await charge(db_session, user.id, searches=3, scans=2)

    balance = await get_balance(db_session, user.id)
    assert balance == {"searches_left": 5, "scans_left": 1}
    journal = await _journal(db_session, user.id)
    assert len(journal) == 1


async def test_charge_without_any_credits_row_raises(db_session):
    user = await create_user(db_session)
    with pytest.raises(InsufficientCredits):
        await charge(db_session, user.id, searches=1)


async def test_charge_scan_consumes_scan_credit(db_session):
    user = await create_user(db_session)
    await grant_signup_bonus(db_session, user.id)

    result = await charge(db_session, user.id, scans=1, reason="usage", ref_id="scan-7")
    assert result["scans_left"] == 0
    assert result["searches_left"] == 5


async def test_grant_negative_amounts_raise_value_error(db_session):
    user = await create_user(db_session)

    with pytest.raises(ValueError):
        await grant(
            db_session, user.id, searches=-10, reason="purchase", ref_id="p-neg"
        )
    with pytest.raises(ValueError):
        await grant(db_session, user.id, scans=-1, reason="admin")

    assert await get_balance(db_session, user.id) == {
        "searches_left": 0,
        "scans_left": 0,
    }
    assert await _journal(db_session, user.id) == []


async def test_charge_negative_amounts_raise_value_error(db_session):
    user = await create_user(db_session)
    await grant_signup_bonus(db_session, user.id)

    with pytest.raises(ValueError):
        await charge(db_session, user.id, searches=-10)
    with pytest.raises(ValueError):
        await charge(db_session, user.id, scans=-5)

    assert await get_balance(db_session, user.id) == {
        "searches_left": 5,
        "scans_left": 1,
    }
    assert len(await _journal(db_session, user.id)) == 1  # only the signup bonus


async def test_charge_zero_is_noop_with_existing_row(db_session):
    user = await create_user(db_session)
    await grant_signup_bonus(db_session, user.id)

    result = await charge(db_session, user.id, searches=0, scans=0)
    assert result == {"charged": True, "searches_left": 5, "scans_left": 1}
    assert len(await _journal(db_session, user.id)) == 1  # journal untouched


async def test_charge_zero_is_noop_without_row(db_session):
    user = await create_user(db_session)

    result = await charge(db_session, user.id, searches=0, scans=0)
    assert result == {"charged": True, "searches_left": 0, "scans_left": 0}
    assert await _journal(db_session, user.id) == []
    assert await db_session.get(Credit, user.id) is None


async def test_grant_conflict_path_ignores_duplicate_after_commit(db_session):
    # sqlite analogue of the concurrent-webhook race: the second grant with the
    # same ref_id goes through ON CONFLICT DO NOTHING and credits nothing.
    user = await create_user(db_session)

    first = await grant(
        db_session, user.id, searches=10, reason="purchase", ref_id="pay-dup"
    )
    await db_session.commit()
    assert first["granted"] is True

    second = await grant(
        db_session, user.id, searches=10, reason="purchase", ref_id="pay-dup"
    )
    await db_session.commit()
    assert second["granted"] is False
    assert second["searches_left"] == 10

    journal = await _journal(db_session, user.id)
    assert len(journal) == 1
