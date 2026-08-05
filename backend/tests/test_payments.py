import asyncio
import base64
import hashlib
import hmac
import json
import time
from decimal import Decimal

import httpx
import pytest
import respx
from sqlalchemy import func, select

from app.config import get_settings
from app.database import AsyncSessionLocal
from app.models import CreditTransaction, Payment, Subscription
from app.payments import handler as payments_handler
from app.payments.base import NormalizedPaymentEvent
from app.services.credits import get_balance
from tests.conftest import auth_header, create_user

POLAR_SECRET_RAW = b"test-polar-webhook-secret"
POLAR_SECRET = "whsec_" + base64.b64encode(POLAR_SECRET_RAW).decode()
NOWPAYMENTS_SECRET = "test-nowpayments-ipn-secret"
YUKASSA_SHOP_ID = "123456"
YUKASSA_SECRET = "test_yukassa_secret"
YUKASSA_IP = "185.71.76.10"


@pytest.fixture
def payment_settings(monkeypatch):
    settings = get_settings()
    monkeypatch.setattr(settings, "polar_api_key", "polar_test_key")
    monkeypatch.setattr(settings, "polar_webhook_secret", POLAR_SECRET)
    monkeypatch.setattr(settings, "polar_sandbox", True)
    monkeypatch.setattr(settings, "polar_product_id_delo", "prod_delo")
    monkeypatch.setattr(settings, "polar_product_id_researcher", "prod_researcher")
    monkeypatch.setattr(settings, "polar_product_id_scans_pack", "prod_scans")
    monkeypatch.setattr(settings, "polar_product_id_ppr", "prod_ppr")
    monkeypatch.setattr(settings, "nowpayments_api_key", "np_test_key")
    monkeypatch.setattr(settings, "nowpayments_ipn_secret", NOWPAYMENTS_SECRET)
    monkeypatch.setattr(settings, "yukassa_shop_id", YUKASSA_SHOP_ID)
    monkeypatch.setattr(settings, "yukassa_secret_key", YUKASSA_SECRET)
    monkeypatch.setattr(settings, "public_base_url", "https://test.jroots.co")
    return settings


@pytest.fixture(autouse=True)
def admin_alerts(monkeypatch):
    calls = []

    async def fake_alert(text):
        calls.append(text)

    monkeypatch.setattr("app.payments.handler.send_admin_alert", fake_alert)
    return calls


# --- Payload / signature helpers ---


def polar_checkout_payload(order_id, checkout_id="ch_1", amount=2500):
    return {
        "type": "checkout.succeeded",
        "data": {
            "id": checkout_id,
            "status": "succeeded",
            "amount": amount,
            "currency": "usd",
            "metadata": {"order_id": order_id},
        },
    }


def polar_signed_request(payload, msg_id="msg_1"):
    body = json.dumps(payload).encode()
    ts = str(int(time.time()))
    signed = msg_id.encode() + b"." + ts.encode() + b"." + body
    sig = base64.b64encode(
        hmac.new(POLAR_SECRET_RAW, signed, hashlib.sha256).digest()
    ).decode()
    headers = {
        "svix-id": msg_id,
        "svix-timestamp": ts,
        "svix-signature": f"v1,{sig}",
    }
    return body, headers


def nowpayments_payload(order_id, payment_status="finished", payment_id=5550001):
    return {
        "payment_id": payment_id,
        "payment_status": payment_status,
        "order_id": order_id,
        "price_amount": 5.0,
        "price_currency": "usd",
        "pay_amount": 0.00012,
        "pay_currency": "btc",
    }


def nowpayments_signed_request(payload):
    canonical = json.dumps(
        payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False
    )
    sig = hmac.new(
        NOWPAYMENTS_SECRET.encode(), canonical.encode("utf-8"), hashlib.sha512
    ).hexdigest()
    return json.dumps(payload).encode(), {"x-nowpayments-sig": sig}


async def payment_count(db, user_id=None):
    query = select(func.count(Payment.id))
    if user_id is not None:
        query = query.where(Payment.user_id == user_id)
    return (await db.execute(query)).scalar_one()


async def transaction_count(db, user_id):
    return (
        await db.execute(
            select(func.count(CreditTransaction.id)).where(
                CreditTransaction.user_id == user_id
            )
        )
    ).scalar_one()


# --- Polar ---


async def test_polar_checkout_succeeded_grants_delo(
    client, db_session, payment_settings
):
    user = await create_user(db_session, email="polar-delo@example.com")
    order_id = f"{user.id}:delo:abc123"
    body, headers = polar_signed_request(polar_checkout_payload(order_id))

    response = await client.post("/api/webhooks/polar", content=body, headers=headers)

    assert response.status_code == 200
    assert response.json()["processed"] is True
    assert await get_balance(db_session, user.id) == {
        "searches_left": 25,
        "scans_left": 10,
    }
    payment = (
        await db_session.execute(select(Payment).where(Payment.user_id == user.id))
    ).scalar_one()
    assert payment.provider == "polar"
    assert payment.provider_payment_id == "ch_1"
    assert payment.status == "succeeded"
    assert payment.tariff == "delo"
    assert str(payment.amount) == "25.00"
    assert payment.currency == "USD"


async def test_polar_invalid_signature_rejected(client, db_session, payment_settings):
    user = await create_user(db_session, email="polar-badsig@example.com")
    order_id = f"{user.id}:delo:abc123"
    body = json.dumps(polar_checkout_payload(order_id)).encode()
    ts = str(int(time.time()))
    headers = {
        "svix-id": "msg_1",
        "svix-timestamp": ts,
        "svix-signature": "v1,forgedsignature",
    }

    response = await client.post("/api/webhooks/polar", content=body, headers=headers)

    assert response.status_code == 401
    assert await get_balance(db_session, user.id) == {
        "searches_left": 0,
        "scans_left": 0,
    }
    assert await payment_count(db_session) == 0


async def test_polar_duplicate_delivery_grants_once(
    client, db_session, payment_settings
):
    user = await create_user(db_session, email="polar-dupe@example.com")
    order_id = f"{user.id}:delo:abc123"
    payload = polar_checkout_payload(order_id)

    body, headers = polar_signed_request(payload)
    first = await client.post("/api/webhooks/polar", content=body, headers=headers)
    body, headers = polar_signed_request(payload)
    second = await client.post("/api/webhooks/polar", content=body, headers=headers)

    assert first.status_code == 200
    assert second.status_code == 200
    assert second.json()["duplicate"] is True
    assert await get_balance(db_session, user.id) == {
        "searches_left": 25,
        "scans_left": 10,
    }
    assert await payment_count(db_session, user.id) == 1
    assert await transaction_count(db_session, user.id) == 1


async def test_polar_subscription_created_activates_researcher(
    client, db_session, payment_settings
):
    user = await create_user(db_session, email="polar-sub@example.com")
    order_id = f"{user.id}:researcher:xyz789"
    payload = {
        "type": "subscription.created",
        "data": {
            "id": "sub_1",
            "status": "active",
            "amount": 1500,
            "currency": "usd",
            "current_period_end": "2026-09-04T00:00:00Z",
            "metadata": {"order_id": order_id},
        },
    }
    body, headers = polar_signed_request(payload)

    response = await client.post("/api/webhooks/polar", content=body, headers=headers)

    assert response.status_code == 200
    balance = await get_balance(db_session, user.id)
    assert balance == {"searches_left": 0, "scans_left": 30}
    subscription = (
        await db_session.execute(
            select(Subscription).where(Subscription.user_id == user.id)
        )
    ).scalar_one()
    assert subscription.provider == "polar"
    assert subscription.provider_sub_id == "sub_1"
    assert subscription.status == "active"
    assert subscription.current_period_end is not None


async def test_polar_subscription_duplicate_no_double_grant(
    client, db_session, payment_settings
):
    user = await create_user(db_session, email="polar-subdupe@example.com")
    payload = {
        "type": "subscription.created",
        "data": {
            "id": "sub_1",
            "status": "active",
            "current_period_end": "2026-09-04T00:00:00Z",
            "metadata": {"order_id": f"{user.id}:researcher:xyz789"},
        },
    }

    body, headers = polar_signed_request(payload)
    await client.post("/api/webhooks/polar", content=body, headers=headers)
    body, headers = polar_signed_request(payload)
    second = await client.post("/api/webhooks/polar", content=body, headers=headers)

    assert second.status_code == 200
    assert second.json()["duplicate"] is True
    assert (await get_balance(db_session, user.id))["scans_left"] == 30
    assert await transaction_count(db_session, user.id) == 1
    assert (
        await db_session.execute(select(func.count(Subscription.id)))
    ).scalar_one() == 1


async def test_polar_subscription_checkout_then_activation_single_grant(
    client, db_session, payment_settings
):
    """Polar fires checkout.succeeded AND subscription.created for one purchase.

    The checkout event records the payment (paid tier) but the scan package is
    granted exactly once — on subscription activation.
    """
    user = await create_user(db_session, email="polar-subboth@example.com")
    order_id = f"{user.id}:researcher:xyz789"

    body, headers = polar_signed_request(
        polar_checkout_payload(order_id, checkout_id="ch_sub", amount=1500)
    )
    checkout_resp = await client.post(
        "/api/webhooks/polar", content=body, headers=headers
    )
    body, headers = polar_signed_request(
        {
            "type": "subscription.created",
            "data": {
                "id": "sub_1",
                "status": "active",
                "current_period_end": "2026-09-04T00:00:00Z",
                "metadata": {"order_id": order_id},
            },
        }
    )
    sub_resp = await client.post("/api/webhooks/polar", content=body, headers=headers)

    assert checkout_resp.status_code == 200
    assert sub_resp.status_code == 200
    assert (await get_balance(db_session, user.id))["scans_left"] == 30
    assert await transaction_count(db_session, user.id) == 1
    assert await payment_count(db_session, user.id) == 2


async def test_polar_subscription_canceled(client, db_session, payment_settings):
    user = await create_user(db_session, email="polar-subcancel@example.com")
    order_id = f"{user.id}:researcher:xyz789"
    body, headers = polar_signed_request(
        {
            "type": "subscription.created",
            "data": {
                "id": "sub_1",
                "status": "active",
                "current_period_end": "2026-09-04T00:00:00Z",
                "metadata": {"order_id": order_id},
            },
        }
    )
    await client.post("/api/webhooks/polar", content=body, headers=headers)

    # Cancellation without metadata — user resolves via the subscription row.
    body, headers = polar_signed_request(
        {
            "type": "subscription.canceled",
            "data": {"id": "sub_1", "status": "canceled"},
        }
    )
    response = await client.post("/api/webhooks/polar", content=body, headers=headers)

    assert response.status_code == 200
    subscription = (
        await db_session.execute(
            select(Subscription).where(Subscription.user_id == user.id)
        )
    ).scalar_one()
    assert subscription.status == "canceled"
    # No additional credits on cancellation.
    assert (await get_balance(db_session, user.id))["scans_left"] == 30


async def test_polar_stale_timestamp_rejected(client, db_session, payment_settings):
    user = await create_user(db_session, email="polar-stale@example.com")
    order_id = f"{user.id}:delo:abc123"
    body = json.dumps(polar_checkout_payload(order_id)).encode()
    ts = str(int(time.time()) - 3600)
    signed = b"msg_1." + ts.encode() + b"." + body
    sig = base64.b64encode(
        hmac.new(POLAR_SECRET_RAW, signed, hashlib.sha256).digest()
    ).decode()
    headers = {
        "svix-id": "msg_1",
        "svix-timestamp": ts,
        "svix-signature": f"v1,{sig}",
    }

    response = await client.post("/api/webhooks/polar", content=body, headers=headers)

    assert response.status_code == 401
    assert await payment_count(db_session) == 0


async def test_polar_ppr_succeeded_records_payment_without_credits(
    client, db_session, payment_settings
):
    user = await create_user(db_session, email="polar-ppr@example.com")
    order_id = f"{user.id}:ppr:rsv001"
    body, headers = polar_signed_request(
        polar_checkout_payload(order_id, checkout_id="ch_ppr", amount=300)
    )

    response = await client.post("/api/webhooks/polar", content=body, headers=headers)

    assert response.status_code == 200
    payment = (
        await db_session.execute(select(Payment).where(Payment.user_id == user.id))
    ).scalar_one()
    assert payment.status == "succeeded"
    assert payment.tariff == "ppr"
    # Reservation logic is separate; the purchase is journaled with zero deltas.
    transaction = (
        await db_session.execute(
            select(CreditTransaction).where(CreditTransaction.user_id == user.id)
        )
    ).scalar_one()
    assert transaction.reason == "purchase"
    assert transaction.ref_id == str(payment.id)
    assert transaction.delta_searches == 0
    assert transaction.delta_scans == 0
    assert await get_balance(db_session, user.id) == {
        "searches_left": 0,
        "scans_left": 0,
    }


# --- NOWPayments ---


async def test_nowpayments_finished_grants_scans_pack(
    client, db_session, payment_settings
):
    user = await create_user(db_session, email="np-scans@example.com")
    order_id = f"{user.id}:scans_pack"
    body, headers = nowpayments_signed_request(nowpayments_payload(order_id))

    response = await client.post(
        "/api/webhooks/nowpayments", content=body, headers=headers
    )

    assert response.status_code == 200
    assert await get_balance(db_session, user.id) == {
        "searches_left": 0,
        "scans_left": 10,
    }
    payment = (
        await db_session.execute(select(Payment).where(Payment.user_id == user.id))
    ).scalar_one()
    assert payment.provider == "nowpayments"
    assert payment.provider_payment_id == "5550001"
    assert payment.status == "succeeded"


async def test_nowpayments_invalid_signature_rejected(
    client, db_session, payment_settings
):
    user = await create_user(db_session, email="np-badsig@example.com")
    order_id = f"{user.id}:scans_pack"
    body = json.dumps(nowpayments_payload(order_id)).encode()
    headers = {"x-nowpayments-sig": "0" * 128}

    response = await client.post(
        "/api/webhooks/nowpayments", content=body, headers=headers
    )

    assert response.status_code == 401
    assert await get_balance(db_session, user.id) == {
        "searches_left": 0,
        "scans_left": 0,
    }
    assert await payment_count(db_session) == 0


async def test_nowpayments_partially_paid_recorded_without_grant(
    client, db_session, payment_settings, admin_alerts
):
    user = await create_user(db_session, email="np-partial@example.com")
    order_id = f"{user.id}:scans_pack"
    body, headers = nowpayments_signed_request(
        nowpayments_payload(order_id, payment_status="partially_paid")
    )

    response = await client.post(
        "/api/webhooks/nowpayments", content=body, headers=headers
    )

    assert response.status_code == 200
    payment = (
        await db_session.execute(select(Payment).where(Payment.user_id == user.id))
    ).scalar_one()
    assert payment.status == "partially_paid"
    assert await get_balance(db_session, user.id) == {
        "searches_left": 0,
        "scans_left": 0,
    }
    assert admin_alerts, "partial payment must alert the admin"
    assert "частичная оплата" in admin_alerts[-1]


async def test_nowpayments_duplicate_delivery_grants_once(
    client, db_session, payment_settings
):
    user = await create_user(db_session, email="np-dupe@example.com")
    order_id = f"{user.id}:scans_pack"
    payload = nowpayments_payload(order_id)

    body, headers = nowpayments_signed_request(payload)
    first = await client.post(
        "/api/webhooks/nowpayments", content=body, headers=headers
    )
    body, headers = nowpayments_signed_request(payload)
    second = await client.post(
        "/api/webhooks/nowpayments", content=body, headers=headers
    )

    assert first.status_code == 200
    assert second.status_code == 200
    assert second.json()["duplicate"] is True
    assert (await get_balance(db_session, user.id))["scans_left"] == 10
    assert await payment_count(db_session, user.id) == 1
    assert await transaction_count(db_session, user.id) == 1


# --- YuKassa ---


def yukassa_webhook_payload(payment_id="pay_1", order_id="1:delo:q1"):
    return {
        "type": "notification",
        "event": "payment.succeeded",
        "object": {
            "id": payment_id,
            "status": "succeeded",
            "amount": {"value": "2250.00", "currency": "RUB"},
            "metadata": {"order_id": order_id},
        },
    }


def yukassa_api_payment(payment_id, order_id, status="succeeded"):
    return {
        "id": payment_id,
        "status": status,
        "amount": {"value": "2250.00", "currency": "RUB"},
        "metadata": {"order_id": order_id},
    }


async def test_yukassa_foreign_ip_rejected(client, db_session, payment_settings):
    user = await create_user(db_session, email="yk-badip@example.com")
    body = json.dumps(yukassa_webhook_payload(order_id=f"{user.id}:delo:q1")).encode()

    with respx.mock:
        response = await client.post(
            "/api/webhooks/yukassa",
            content=body,
            headers={"x-forwarded-for": "8.8.8.8"},
        )

    assert response.status_code == 401
    assert respx.calls.call_count == 0, "no re-verification call for foreign IPs"
    assert await get_balance(db_session, user.id) == {
        "searches_left": 0,
        "scans_left": 0,
    }
    assert await payment_count(db_session) == 0


async def test_yukassa_succeeded_grants_after_api_recheck(
    client, db_session, payment_settings
):
    user = await create_user(db_session, email="yk-ok@example.com")
    order_id = f"{user.id}:delo:q1"
    body = json.dumps(yukassa_webhook_payload(order_id=order_id)).encode()

    with respx.mock:
        route = respx.get("https://api.yookassa.ru/v3/payments/pay_1").mock(
            return_value=httpx.Response(
                200, json=yukassa_api_payment("pay_1", order_id)
            )
        )
        response = await client.post(
            "/api/webhooks/yukassa",
            content=body,
            headers={"x-forwarded-for": YUKASSA_IP},
        )

    assert response.status_code == 200
    assert route.called
    assert await get_balance(db_session, user.id) == {
        "searches_left": 25,
        "scans_left": 10,
    }
    payment = (
        await db_session.execute(select(Payment).where(Payment.user_id == user.id))
    ).scalar_one()
    assert payment.provider == "yukassa"
    assert payment.status == "succeeded"
    assert payment.currency == "RUB"


async def test_yukassa_body_not_trusted_api_says_pending(
    client, db_session, payment_settings
):
    """Webhook body claims success, but the API re-check says pending:
    the payment is recorded as pending and nothing is granted."""
    user = await create_user(db_session, email="yk-pending@example.com")
    order_id = f"{user.id}:delo:q1"
    body = json.dumps(yukassa_webhook_payload(order_id=order_id)).encode()

    with respx.mock:
        respx.get("https://api.yookassa.ru/v3/payments/pay_1").mock(
            return_value=httpx.Response(
                200, json=yukassa_api_payment("pay_1", order_id, status="pending")
            )
        )
        response = await client.post(
            "/api/webhooks/yukassa",
            content=body,
            headers={"x-forwarded-for": YUKASSA_IP},
        )

    assert response.status_code == 200
    payment = (
        await db_session.execute(select(Payment).where(Payment.user_id == user.id))
    ).scalar_one()
    assert payment.status == "pending"
    assert await get_balance(db_session, user.id) == {
        "searches_left": 0,
        "scans_left": 0,
    }


async def test_yukassa_api_recheck_failure_rejected(
    client, db_session, payment_settings
):
    user = await create_user(db_session, email="yk-norecheck@example.com")
    order_id = f"{user.id}:delo:q1"
    body = json.dumps(yukassa_webhook_payload(order_id=order_id)).encode()

    with respx.mock:
        respx.get("https://api.yookassa.ru/v3/payments/pay_1").mock(
            return_value=httpx.Response(404, json={"code": "not_found"})
        )
        response = await client.post(
            "/api/webhooks/yukassa",
            content=body,
            headers={"x-forwarded-for": YUKASSA_IP},
        )

    assert response.status_code == 401
    assert await payment_count(db_session) == 0


# --- Checkout endpoint ---


async def test_checkout_creates_polar_link(client, db_session, payment_settings):
    user = await create_user(db_session, email="checkout-polar@example.com")

    with respx.mock:
        route = respx.post("https://api.sandbox.polar.sh/v1/checkouts").mock(
            return_value=httpx.Response(
                201, json={"id": "ch_new", "url": "https://pay.polar.test/ch_new"}
            )
        )
        response = await client.post(
            "/api/payments/checkout",
            json={"tariff": "delo"},
            headers=auth_header(user),
        )

    assert response.status_code == 200
    data = response.json()
    assert data["checkout_url"] == "https://pay.polar.test/ch_new"
    assert data["order_id"].startswith(f"{user.id}:delo:")
    assert route.called
    sent = json.loads(route.calls[0].request.content)
    assert sent["products"] == ["prod_delo"]
    assert sent["metadata"]["order_id"] == data["order_id"]


async def test_checkout_requires_auth(client, payment_settings):
    response = await client.post("/api/payments/checkout", json={"tariff": "delo"})
    assert response.status_code == 401


async def test_checkout_unknown_tariff(client, db_session, payment_settings):
    user = await create_user(db_session, email="checkout-badtariff@example.com")
    response = await client.post(
        "/api/payments/checkout",
        json={"tariff": "gold_platinum"},
        headers=auth_header(user),
    )
    assert response.status_code == 400


async def test_checkout_subscription_rejected_for_non_polar(
    client, db_session, payment_settings
):
    user = await create_user(db_session, email="checkout-sub-yk@example.com")
    response = await client.post(
        "/api/payments/checkout",
        json={"tariff": "researcher", "provider": "yukassa"},
        headers=auth_header(user),
    )
    assert response.status_code == 400


async def test_checkout_creates_yukassa_link_with_rub_amount(
    client, db_session, payment_settings
):
    user = await create_user(db_session, email="checkout-yk@example.com")

    with respx.mock:
        route = respx.post("https://api.yookassa.ru/v3/payments").mock(
            return_value=httpx.Response(
                200,
                json={
                    "id": "pay_new",
                    "status": "pending",
                    "confirmation": {
                        "type": "redirect",
                        "confirmation_url": "https://yookassa.test/pay_new",
                    },
                },
            )
        )
        response = await client.post(
            "/api/payments/checkout",
            json={"tariff": "delo", "provider": "yukassa"},
            headers=auth_header(user),
        )

    assert response.status_code == 200
    data = response.json()
    assert data["checkout_url"] == "https://yookassa.test/pay_new"
    assert data["order_id"].startswith(f"{user.id}:delo:")
    sent = json.loads(route.calls[0].request.content)
    # $25 at the default 90.0 RUB/USD rate.
    assert sent["amount"] == {"value": "2250.00", "currency": "RUB"}
    assert sent["metadata"]["order_id"] == data["order_id"]


async def test_webhook_unknown_provider_404(client, payment_settings):
    response = await client.post("/api/webhooks/something", content=b"{}")
    assert response.status_code == 404


async def test_webhook_malformed_payload_400(client, db_session, payment_settings):
    body = b"not json at all"
    ts = str(int(time.time()))
    signed = b"msg_1." + ts.encode() + b"." + body
    sig = base64.b64encode(
        hmac.new(POLAR_SECRET_RAW, signed, hashlib.sha256).digest()
    ).decode()
    headers = {
        "svix-id": "msg_1",
        "svix-timestamp": ts,
        "svix-signature": f"v1,{sig}",
    }
    response = await client.post("/api/webhooks/polar", content=body, headers=headers)
    assert response.status_code == 400


# --- Status progression on the same provider_payment_id ---


async def test_nowpayments_waiting_then_finished_grants_once(
    client, db_session, payment_settings
):
    """NOWPayments delivers waiting → confirming → finished for one payment.
    The finished event must transition the pending row and grant exactly once.
    """
    user = await create_user(db_session, email="np-progress@example.com")
    order_id = f"{user.id}:scans_pack"

    body, headers = nowpayments_signed_request(
        nowpayments_payload(order_id, payment_status="waiting")
    )
    first = await client.post(
        "/api/webhooks/nowpayments", content=body, headers=headers
    )
    assert first.status_code == 200
    assert await get_balance(db_session, user.id) == {
        "searches_left": 0,
        "scans_left": 0,
    }

    body, headers = nowpayments_signed_request(
        nowpayments_payload(order_id, payment_status="finished")
    )
    second = await client.post(
        "/api/webhooks/nowpayments", content=body, headers=headers
    )
    assert second.status_code == 200
    assert second.json()["processed"] is True
    assert second.json()["duplicate"] is False

    assert await get_balance(db_session, user.id) == {
        "searches_left": 0,
        "scans_left": 10,
    }
    assert await payment_count(db_session, user.id) == 1
    payment = (
        await db_session.execute(select(Payment).where(Payment.user_id == user.id))
    ).scalar_one()
    assert payment.status == "succeeded"
    assert await transaction_count(db_session, user.id) == 1

    # A redelivered finished event is a no-op duplicate — no second grant.
    body, headers = nowpayments_signed_request(
        nowpayments_payload(order_id, payment_status="finished")
    )
    third = await client.post(
        "/api/webhooks/nowpayments", content=body, headers=headers
    )
    assert third.status_code == 200
    assert third.json()["duplicate"] is True
    assert (await get_balance(db_session, user.id))["scans_left"] == 10
    assert await transaction_count(db_session, user.id) == 1


async def test_yukassa_pending_then_succeeded_grants(
    client, db_session, payment_settings
):
    """YuKassa pending → succeeded on the same payment id (re-check decides)."""
    user = await create_user(db_session, email="yk-progress@example.com")
    order_id = f"{user.id}:delo:q1"
    body = json.dumps(yukassa_webhook_payload(order_id=order_id)).encode()

    with respx.mock:
        route = respx.get("https://api.yookassa.ru/v3/payments/pay_1").mock(
            side_effect=[
                httpx.Response(
                    200, json=yukassa_api_payment("pay_1", order_id, status="pending")
                ),
                httpx.Response(
                    200,
                    json=yukassa_api_payment("pay_1", order_id, status="succeeded"),
                ),
            ]
        )
        first = await client.post(
            "/api/webhooks/yukassa",
            content=body,
            headers={"x-forwarded-for": YUKASSA_IP},
        )
        assert first.status_code == 200
        assert await get_balance(db_session, user.id) == {
            "searches_left": 0,
            "scans_left": 0,
        }

        second = await client.post(
            "/api/webhooks/yukassa",
            content=body,
            headers={"x-forwarded-for": YUKASSA_IP},
        )

    assert second.status_code == 200
    assert second.json()["processed"] is True
    assert route.call_count == 2
    assert await get_balance(db_session, user.id) == {
        "searches_left": 25,
        "scans_left": 10,
    }
    assert await payment_count(db_session, user.id) == 1
    payment = (
        await db_session.execute(select(Payment).where(Payment.user_id == user.id))
    ).scalar_one()
    assert payment.status == "succeeded"
    assert await transaction_count(db_session, user.id) == 1


# --- Concurrent duplicate deliveries ---


def _np_event(user_id, payment_id="5550009"):
    return NormalizedPaymentEvent(
        provider="nowpayments",
        provider_payment_id=payment_id,
        order_id=f"{user_id}:scans_pack",
        user_id=user_id,
        tariff="scans_pack",
        amount=Decimal("5.00"),
        currency="USD",
        status="succeeded",
        raw={"payment_id": payment_id, "payment_status": "finished"},
        event_type="finished",
    )


async def test_concurrent_same_webhook_single_grant_no_errors(
    db_session, payment_settings
):
    """Two simultaneous deliveries of the same webhook on independent
    sessions: no exception (i.e. no 500 at the route), exactly one grant."""
    user = await create_user(db_session, email="np-race@example.com")
    event = _np_event(user.id)

    async def call():
        async with AsyncSessionLocal() as session:
            return await payments_handler.process_payment_event(session, event)

    results = await asyncio.gather(call(), call())

    assert sum(1 for r in results if r["processed"]) == 1
    assert sum(1 for r in results if r["duplicate"]) == 1
    assert (await get_balance(db_session, user.id))["scans_left"] == 10
    assert await payment_count(db_session, user.id) == 1
    assert await transaction_count(db_session, user.id) == 1


async def test_insert_race_falls_back_to_duplicate(
    db_session, payment_settings, monkeypatch
):
    """Deterministic insert-race: the loser's dedupe SELECT ran before the
    winner committed, so its INSERT hits the unique constraint — it must
    re-read the winner's row and answer duplicate instead of failing."""
    user = await create_user(db_session, email="np-race2@example.com")
    winner = Payment(
        provider="nowpayments",
        provider_payment_id="5550010",
        order_id=f"{user.id}:scans_pack",
        user_id=user.id,
        tariff="scans_pack",
        amount=Decimal("5.00"),
        currency="USD",
        status="succeeded",
        raw_payload_json={},
    )
    db_session.add(winner)
    await db_session.commit()

    real_find = payments_handler._find_payment
    calls = 0

    async def stale_find(db, event):
        nonlocal calls
        calls += 1
        if calls == 1:
            return None  # raced: dedupe ran before the winner committed
        return await real_find(db, event)

    monkeypatch.setattr(payments_handler, "_find_payment", stale_find)

    result = await payments_handler.process_payment_event(
        db_session, _np_event(user.id, payment_id="5550010")
    )

    assert result["duplicate"] is True
    assert result["payment_id"] == winner.id
    # The loser must not grant — the winner row is already terminal.
    assert await transaction_count(db_session, user.id) == 0
