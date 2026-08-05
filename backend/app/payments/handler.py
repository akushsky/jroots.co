import logging

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Payment, Subscription, User
from app.payments.base import NormalizedPaymentEvent
from app.payments.tariffs import TARIFFS
from app.services import credits as credits_service
from app.services.telegram import send_admin_alert

logger = logging.getLogger("jroots")

# Statuses after which a payment never changes again. Anything else
# ("pending", "partially_paid") may still transition on the same
# provider_payment_id — e.g. NOWPayments delivers waiting → confirming →
# finished as separate webhooks for one payment, YuKassa pending → succeeded.
TERMINAL_STATUSES = frozenset({"succeeded", "failed", "canceled"})


class UnprocessableEvent(Exception):
    """The webhook is authentic but cannot be applied (unknown user/tariff)."""


async def _find_payment(
    db: AsyncSession, event: NormalizedPaymentEvent
) -> Payment | None:
    return (
        await db.execute(
            select(Payment).where(
                Payment.provider == event.provider,
                Payment.provider_payment_id == event.provider_payment_id,
            )
        )
    ).scalar_one_or_none()


async def _insert_payment(
    db: AsyncSession, event: NormalizedPaymentEvent, user_id: int
) -> Payment | None:
    """Insert the payment row inside a savepoint.

    Returns None when a concurrent delivery of the same webhook won the
    insert race — the caller then re-reads the winner's row instead of
    propagating a 500 to the provider.
    """
    payment = Payment(
        provider=event.provider,
        provider_payment_id=event.provider_payment_id,
        order_id=event.order_id,
        user_id=user_id,
        tariff=event.tariff,
        amount=event.amount,
        currency=event.currency,
        status=event.status,
        raw_payload_json=event.raw,
    )
    try:
        async with db.begin_nested():
            db.add(payment)
            await db.flush()
    except IntegrityError:
        logger.info(
            "Concurrent webhook insert race on %s %s",
            event.provider,
            event.provider_payment_id,
        )
        return None
    return payment


async def _maybe_grant(
    db: AsyncSession, event: NormalizedPaymentEvent, payment: Payment
) -> bool:
    """Grant the tariff package for a succeeded event.

    Idempotent even when called twice for the same payment: the credit
    journal is unique on (user_id, reason='purchase', ref_id=payment.id).
    For the subscription tariff the package is granted only on the
    subscription-activation event (provider_sub_id present) — Polar also
    fires checkout.succeeded for the same purchase, and granting there too
    would double-credit.
    """
    if event.status != "succeeded":
        return False
    tariff = TARIFFS.get(payment.tariff or "")
    if tariff is None:
        raise UnprocessableEvent(
            f"Succeeded event with unknown tariff: {payment.tariff!r}"
        )
    if tariff.kind == "subscription" and not event.provider_sub_id:
        return False
    result = await credits_service.grant(
        db,
        payment.user_id,
        searches=tariff.grant_searches,
        scans=tariff.grant_scans,
        reason="purchase",
        ref_id=str(payment.id),
    )
    return result["granted"]


async def _apply_subscription(
    db: AsyncSession,
    event: NormalizedPaymentEvent,
    user_id: int,
    subscription: Subscription | None,
) -> None:
    if not event.provider_sub_id:
        return
    if subscription is None:
        subscription = Subscription(
            user_id=user_id,
            provider=event.provider,
            provider_sub_id=event.provider_sub_id,
        )
        db.add(subscription)
    if event.status == "succeeded":
        subscription.status = "active"
        subscription.current_period_end = event.current_period_end
    elif event.status == "canceled":
        subscription.status = "canceled"


async def _apply_to_existing(
    db: AsyncSession,
    payment: Payment,
    event: NormalizedPaymentEvent,
    subscription: Subscription | None,
) -> dict:
    """Handle an event for an already-recorded provider_payment_id.

    A redelivery of what was already applied (terminal status, or the same
    status again) is an honest no-op duplicate. A status progression
    (pending/partially_paid → succeeded/failed/canceled) updates the row and
    runs the grant that the earlier non-terminal delivery postponed.
    """
    if payment.status in TERMINAL_STATUSES or payment.status == event.status:
        logger.info(
            "Duplicate webhook ignored: %s %s (status=%s)",
            event.provider,
            event.provider_payment_id,
            payment.status,
        )
        return {
            "processed": False,
            "duplicate": True,
            "payment_id": payment.id,
            "status": payment.status,
        }

    previous_status = payment.status
    payment.status = event.status
    payment.raw_payload_json = event.raw
    if event.amount is not None:
        payment.amount = event.amount
    if event.currency:
        payment.currency = event.currency
    if event.order_id:
        payment.order_id = event.order_id
    if event.tariff:
        payment.tariff = event.tariff

    await _maybe_grant(db, event, payment)
    await _apply_subscription(db, event, payment.user_id, subscription)
    await db.commit()
    await _alert_admin(event, payment)
    logger.info(
        "Payment %d transitioned %s -> %s",
        payment.id,
        previous_status,
        event.status,
    )
    return {
        "processed": True,
        "duplicate": False,
        "payment_id": payment.id,
        "status": event.status,
        "previous_status": previous_status,
    }


async def process_payment_event(
    db: AsyncSession, event: NormalizedPaymentEvent
) -> dict:
    """Apply a normalized payment event in a single transaction.

    Idempotent on (provider, provider_payment_id): a redelivered webhook is a
    no-op and still returns 200 to the caller. Credits are granted only for
    status "succeeded", with reason="purchase" and ref_id=str(payment.id) —
    the journal's (user_id, reason, ref_id) uniqueness is a second layer of
    double-grant protection on top of webhook dedupe.
    """
    if event.status == "succeeded" and event.tariff not in TARIFFS:
        raise UnprocessableEvent(
            f"Succeeded event with unknown tariff: {event.tariff!r}"
        )

    subscription = None
    if event.provider_sub_id:
        subscription = (
            await db.execute(
                select(Subscription).where(
                    Subscription.provider == event.provider,
                    Subscription.provider_sub_id == event.provider_sub_id,
                )
            )
        ).scalar_one_or_none()

    user_id = event.user_id
    if user_id is None and subscription is not None:
        user_id = subscription.user_id

    existing = await _find_payment(db, event)
    if existing is not None:
        return await _apply_to_existing(db, existing, event, subscription)

    if user_id is None:
        raise UnprocessableEvent("Cannot resolve user for payment event")
    user = await db.get(User, user_id)
    if user is None:
        raise UnprocessableEvent(f"User {user_id} not found")

    payment = await _insert_payment(db, event, user.id)
    if payment is None:
        # Lost the insert race with a concurrent delivery of the same webhook.
        existing = await _find_payment(db, event)
        if existing is None:
            # The winner has not committed yet; its own request completes the
            # job — answer as a duplicate so the provider stops retrying.
            return {
                "processed": False,
                "duplicate": True,
                "payment_id": None,
                "status": event.status,
            }
        return await _apply_to_existing(db, existing, event, subscription)

    await _maybe_grant(db, event, payment)
    await _apply_subscription(db, event, user.id, subscription)
    await db.commit()
    await _alert_admin(event, payment)
    return {
        "processed": True,
        "duplicate": False,
        "payment_id": payment.id,
        "status": event.status,
    }


async def _alert_admin(event: NormalizedPaymentEvent, payment: Payment) -> None:
    amount = (
        f"{event.amount} {event.currency}"
        if event.amount is not None
        else "сумма неизвестна"
    )
    note = (
        " (частичная оплата — требуется ручной возврат)"
        if event.status == "partially_paid"
        else ""
    )
    await send_admin_alert(
        f"💳 Платёж {event.provider}: {amount}{note}\n"
        f"Пользователь: #{payment.user_id}, тариф: {event.tariff or '-'}, "
        f"статус: {event.status}"
    )
