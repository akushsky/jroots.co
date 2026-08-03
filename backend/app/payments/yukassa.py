import ipaddress
import json
import logging
import uuid
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

API_BASE = "https://api.yookassa.ru"

# Official YuKassa webhook source networks (no request signing exists on
# their side, so the source IP allowlist is the first verification layer).
YUKASSA_WEBHOOK_NETWORKS = tuple(
    ipaddress.ip_network(net)
    for net in (
        "185.71.76.0/27",
        "185.71.77.0/27",
        "77.75.153.0/25",
        "77.75.154.128/25",
        "77.75.156.11/32",
        "77.75.156.35/32",
        "2a02:5180::/32",
    )
)

_STATUS_MAP = {
    "succeeded": "succeeded",
    "canceled": "canceled",
    "pending": "pending",
    "waiting_for_capture": "pending",
}


class YuKassaProvider:
    """YuKassa rail (RU audience).

    Webhooks are unsigned; verification is two-layered:
    1. source IP allowlist (YUKASSA_WEBHOOK_NETWORKS);
    2. mandatory re-verification: GET /v3/payments/{id} with basic auth and
       trust ONLY the API response (status, amount, metadata), never the
       webhook body.
    """

    name = "yukassa"

    async def create_checkout(
        self,
        *,
        user: "User",
        tariff: "Tariff",
        success_url: str,
        cancel_url: str,
    ) -> dict:
        settings = get_settings()
        if not settings.yukassa_shop_id or not settings.yukassa_secret_key:
            raise ProviderError("YuKassa credentials are not configured")
        order_id = make_order_id(user.id, tariff.code)
        # Tariffs are USD-denominated; YuKassa charges in yukassa_currency
        # (RUB by default) converted at the configured rate.
        amount_value = (
            tariff.amount_usd * Decimal(str(settings.yukassa_usd_rate))
        ).quantize(Decimal("0.01"))
        payload = {
            "amount": {
                "value": str(amount_value),
                "currency": settings.yukassa_currency,
            },
            "capture": True,
            "confirmation": {"type": "redirect", "return_url": success_url},
            "description": f"JRoots: {tariff.title} ({tariff.code})",
            "metadata": {"order_id": order_id},
        }
        async with httpx.AsyncClient(timeout=15.0) as client:
            response = await client.post(
                f"{API_BASE}/v3/payments",
                json=payload,
                auth=(settings.yukassa_shop_id, settings.yukassa_secret_key),
                headers={"Idempotence-Key": uuid.uuid4().hex},
            )
        if response.status_code not in (200, 201):
            raise ProviderError(
                f"YuKassa payment creation failed: "
                f"{response.status_code} {response.text[:200]}"
            )
        confirmation = response.json().get("confirmation") or {}
        checkout_url = confirmation.get("confirmation_url")
        if not checkout_url:
            raise ProviderError("YuKassa response missing confirmation_url")
        return {"checkout_url": checkout_url, "order_id": order_id}

    async def verify_and_parse(
        self,
        headers: Mapping[str, str],
        raw_body: bytes,
        *,
        client_ip: str | None = None,
    ) -> NormalizedPaymentEvent:
        self._verify_ip(client_ip)
        try:
            payload = json.loads(raw_body)
        except json.JSONDecodeError as exc:
            raise ValueError("Invalid JSON in YuKassa webhook") from exc
        if not isinstance(payload, dict):
            raise ValueError("YuKassa webhook payload is not an object")
        obj = payload.get("object")
        if not isinstance(obj, dict):
            raise ValueError("YuKassa webhook missing object")
        payment_id = obj.get("id")
        if not payment_id:
            raise ValueError("YuKassa webhook missing object.id")
        # Never trust the body: re-fetch the payment from the API.
        payment = await self._fetch_payment(str(payment_id))
        return self._normalize(payload.get("event", ""), payment, raw=payload)

    def _verify_ip(self, client_ip: str | None) -> None:
        if not client_ip:
            raise SignatureError("Missing client IP for YuKassa webhook")
        try:
            addr = ipaddress.ip_address(client_ip)
        except ValueError:
            raise SignatureError(f"Unparseable client IP: {client_ip!r}") from None
        if not any(addr in net for net in YUKASSA_WEBHOOK_NETWORKS):
            raise SignatureError(f"Foreign YuKassa webhook IP: {client_ip}")

    async def _fetch_payment(self, payment_id: str) -> dict:
        settings = get_settings()
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.get(
                    f"{API_BASE}/v3/payments/{payment_id}",
                    auth=(settings.yukassa_shop_id, settings.yukassa_secret_key),
                )
        except httpx.RequestError as exc:
            raise SignatureError(
                f"YuKassa re-verification request failed: {exc}"
            ) from exc
        if response.status_code != 200:
            raise SignatureError(
                f"YuKassa re-verification failed: {response.status_code}"
            )
        payment = response.json()
        if not isinstance(payment, dict) or payment.get("id") != payment_id:
            raise SignatureError("YuKassa re-verification returned wrong payment")
        return payment

    def _normalize(
        self, event_type: str, payment: dict, raw: dict
    ) -> NormalizedPaymentEvent:
        metadata = payment.get("metadata") or {}
        order_id = metadata.get("order_id")
        user_id, tariff_code = (None, None)
        if order_id:
            user_id, tariff_code = parse_order_id(order_id)
        api_status = payment.get("status", "")
        status = _STATUS_MAP.get(api_status)
        if status is None:
            raise ValueError(f"Unsupported YuKassa payment status: {api_status!r}")
        amount_info = payment.get("amount") or {}
        value = amount_info.get("value")
        return NormalizedPaymentEvent(
            provider=self.name,
            provider_payment_id=str(payment["id"]),
            order_id=order_id,
            user_id=user_id,
            tariff=tariff_code,
            amount=Decimal(str(value)) if value is not None else None,
            currency=amount_info.get("currency"),
            status=status,
            raw=raw,
            event_type=event_type,
        )
