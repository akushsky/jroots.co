import logging

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Payment, Subscription, User
from app.payments.base import NormalizedPaymentEvent
from app.payments.tariffs import TARIFFS
from app.services import credits as credits_service
from app.services.telegram import send_admin_alert

logger = logging.getLogger("jroots")


class UnprocessableEvent(Exception):
    """The webhook is authentic but cannot be applied (unknown user/tariff)."""


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
    if user_id is None:
        raise UnprocessableEvent("Cannot resolve user for payment event")
    user = await db.get(User, user_id)
    if user is None:
        raise UnprocessableEvent(f"User {user_id} not found")

    existing = (
        await db.execute(
            select(Payment).where(
                Payment.provider == event.provider,
                Payment.provider_payment_id == event.provider_payment_id,
            )
        )
    ).scalar_one_or_none()
    if existing is not None:
        logger.info(
            "Duplicate webhook ignored: %s %s",
            event.provider,
            event.provider_payment_id,
        )
        return {
            "processed": False,
            "duplicate": True,
            "payment_id": existing.id,
            "status": existing.status,
        }

    payment = Payment(
        provider=event.provider,
        provider_payment_id=event.provider_payment_id,
        order_id=event.order_id,
        user_id=user.id,
        tariff=event.tariff,
        amount=event.amount,
        currency=event.currency,
        status=event.status,
        raw_payload_json=event.raw,
    )
    db.add(payment)
    await db.flush()

    if event.status == "succeeded":
        tariff = TARIFFS[event.tariff]
        # For the subscription tariff the scan package is granted on the
        # subscription.activated event (provider_sub_id present). Polar also
        # fires checkout.succeeded for the same purchase — that event is
        # recorded as a payment (paid-tier marker) but must not grant, or the
        # scans would be credited twice.
        if tariff.kind != "subscription" or event.provider_sub_id:
            await credits_service.grant(
                db,
                user.id,
                searches=tariff.grant_searches,
                scans=tariff.grant_scans,
                reason="purchase",
                ref_id=str(payment.id),
            )

    if event.provider_sub_id:
        if subscription is None:
            subscription = Subscription(
                user_id=user.id,
                provider=event.provider,
                provider_sub_id=event.provider_sub_id,
            )
            db.add(subscription)
        if event.status == "succeeded":
            subscription.status = "active"
            subscription.current_period_end = event.current_period_end
        elif event.status == "canceled":
            subscription.status = "canceled"

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
