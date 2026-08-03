import hashlib
import hmac
import json
import logging
from decimal import Decimal
from typing import TYPE_CHECKING, Mapping

import httpx

from app.config import get_settings
from app.payments.base import (
    NormalizedPaymentEvent,
    ProviderError,
    SignatureError,
)
from app.payments.tariffs import make_order_id, parse_order_id

if TYPE_CHECKING:
    from app.models import User
    from app.payments.tariffs import Tariff

logger = logging.getLogger("jroots")

API_BASE = "https://api.nowpayments.io"

_STATUS_MAP = {
    "finished": "succeeded",
    "partially_paid": "partially_paid",
    "failed": "failed",
    "expired": "failed",
    "refunded": "failed",
    "waiting": "pending",
    "confirming": "pending",
    "confirmed": "pending",
    "sending": "pending",
}


class NowPaymentsProvider:
    """NOWPayments crypto rail.

    Checkout via POST /v1/invoice. IPN signature: x-nowpayments-sig header,
    HMAC-SHA512(ipn_secret, canonical_json) where canonical_json is the
    payload re-serialized with sorted keys, separators=(',', ':'),
    ensure_ascii=False.
    """

    name = "nowpayments"

    async def create_checkout(
        self,
        *,
        user: "User",
        tariff: "Tariff",
        success_url: str,
        cancel_url: str,
    ) -> dict:
        settings = get_settings()
        if not settings.nowpayments_api_key:
            raise ProviderError("NOWPayments API key is not configured")
        # NOWPayments order_id per spec: "{user_id}:{tariff}".
        order_id = make_order_id(user.id, tariff.code, with_nonce=False)
        payload = {
            "price_amount": float(tariff.amount_usd),
            "price_currency": "usd",
            "order_id": order_id,
            "ipn_callback_url": (
                f"{settings.public_base_url}/api/webhooks/nowpayments"
            ),
            "success_url": success_url,
            "cancel_url": cancel_url,
        }
        async with httpx.AsyncClient(timeout=15.0) as client:
            response = await client.post(
                f"{API_BASE}/v1/invoice",
                json=payload,
                headers={"x-api-key": settings.nowpayments_api_key},
            )
        if response.status_code not in (200, 201):
            raise ProviderError(
                f"NOWPayments invoice creation failed: "
                f"{response.status_code} {response.text[:200]}"
            )
        invoice_url = response.json().get("invoice_url")
        if not invoice_url:
            raise ProviderError("NOWPayments invoice response missing invoice_url")
        return {"checkout_url": invoice_url, "order_id": order_id}

    async def verify_and_parse(
        self,
        headers: Mapping[str, str],
        raw_body: bytes,
        *,
        client_ip: str | None = None,
    ) -> NormalizedPaymentEvent:
        try:
            payload = json.loads(raw_body)
        except json.JSONDecodeError as exc:
            raise ValueError("Invalid JSON in NOWPayments webhook") from exc
        if not isinstance(payload, dict):
            raise ValueError("NOWPayments webhook payload is not an object")
        self._verify_signature(headers, payload)
        return self._normalize(payload)

    def _verify_signature(self, headers: Mapping[str, str], payload: dict) -> None:
        settings = get_settings()
        secret = settings.nowpayments_ipn_secret
        if not secret:
            raise SignatureError("NOWPayments IPN secret is not configured")
        provided = headers.get("x-nowpayments-sig")
        if not provided:
            raise SignatureError("Missing x-nowpayments-sig header")
        canonical = json.dumps(
            payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False
        )
        expected = hmac.new(
            secret.encode(), canonical.encode("utf-8"), hashlib.sha512
        ).hexdigest()
        if not hmac.compare_digest(expected, provided.strip().lower()):
            raise SignatureError("NOWPayments signature mismatch")

    def _normalize(self, payload: dict) -> NormalizedPaymentEvent:
        payment_id = payload.get("payment_id")
        if payment_id is None:
            raise ValueError("NOWPayments payload missing payment_id")
        order_id = payload.get("order_id") or ""
        user_id, tariff_code = parse_order_id(order_id)
        payment_status = payload.get("payment_status", "")
        status = _STATUS_MAP.get(payment_status)
        if status is None:
            raise ValueError(
                f"Unsupported NOWPayments payment_status: {payment_status!r}"
            )
        price_amount = payload.get("price_amount")
        price_currency = payload.get("price_currency")
        return NormalizedPaymentEvent(
            provider=self.name,
            provider_payment_id=str(payment_id),
            order_id=order_id,
            user_id=user_id,
            tariff=tariff_code,
            amount=Decimal(str(price_amount)) if price_amount is not None else None,
            currency=str(price_currency).upper() if price_currency else None,
            status=status,
            raw=payload,
            event_type=payment_status,
        )
