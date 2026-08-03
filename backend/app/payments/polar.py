import base64
import hashlib
import hmac
import json
import logging
import time
from datetime import datetime
from decimal import Decimal
from typing import TYPE_CHECKING, Any, Mapping

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

# Standard Webhooks spec: reject events with a timestamp too far from now.
SIGNATURE_TOLERANCE_SECONDS = 300


class PolarProvider:
    """Polar (Merchant of Record) rail.

    Sandbox base URL: https://api.sandbox.polar.sh (POLAR_SANDBOX=true).
    Webhooks follow the Standard Webhooks spec: svix-id / svix-timestamp /
    svix-signature headers, HMAC-SHA256 over "{id}.{timestamp}.{raw_body}"
    with the base64-decoded webhook secret (whsec_ prefix stripped).
    """

    name = "polar"

    def _api_base(self) -> str:
        settings = get_settings()
        if settings.polar_sandbox:
            return "https://api.sandbox.polar.sh"
        return "https://api.polar.sh"

    def _product_id_for(self, tariff_code: str) -> str:
        settings = get_settings()
        product_ids = {
            "delo": settings.polar_product_id_delo,
            "researcher": settings.polar_product_id_researcher,
            "scans_pack": settings.polar_product_id_scans_pack,
            "ppr": settings.polar_product_id_ppr,
        }
        product_id = product_ids.get(tariff_code, "")
        if not product_id:
            raise ProviderError(
                f"Polar product id is not configured for tariff {tariff_code!r}"
            )
        return product_id

    async def create_checkout(
        self,
        *,
        user: "User",
        tariff: "Tariff",
        success_url: str,
        cancel_url: str,
    ) -> dict:
        settings = get_settings()
        order_id = make_order_id(user.id, tariff.code)
        payload = {
            "products": [self._product_id_for(tariff.code)],
            "success_url": success_url,
            "cancel_url": cancel_url,
            "metadata": {"order_id": order_id},
        }
        async with httpx.AsyncClient(timeout=15.0) as client:
            response = await client.post(
                f"{self._api_base()}/v1/checkouts",
                json=payload,
                headers={"Authorization": f"Bearer {settings.polar_api_key}"},
            )
        if response.status_code not in (200, 201):
            raise ProviderError(
                f"Polar checkout creation failed: "
                f"{response.status_code} {response.text[:200]}"
            )
        checkout_url = response.json().get("url")
        if not checkout_url:
            raise ProviderError("Polar checkout response missing url")
        return {"checkout_url": checkout_url, "order_id": order_id}

    async def verify_and_parse(
        self,
        headers: Mapping[str, str],
        raw_body: bytes,
        *,
        client_ip: str | None = None,
    ) -> NormalizedPaymentEvent:
        self._verify_signature(headers, raw_body)
        try:
            payload = json.loads(raw_body)
        except json.JSONDecodeError as exc:
            raise ValueError("Invalid JSON in Polar webhook") from exc
        if not isinstance(payload, dict):
            raise ValueError("Polar webhook payload is not an object")
        event_type = payload.get("type", "")
        data = payload.get("data")
        if not isinstance(data, dict):
            raise ValueError("Polar webhook payload missing data object")
        if event_type == "checkout.succeeded":
            return self._normalize_checkout(data, payload)
        if event_type in ("subscription.created", "subscription.canceled"):
            return self._normalize_subscription(event_type, data, payload)
        raise ValueError(f"Unsupported Polar event type: {event_type!r}")

    def _verify_signature(self, headers: Mapping[str, str], raw_body: bytes) -> None:
        settings = get_settings()
        secret = settings.polar_webhook_secret
        if not secret:
            raise SignatureError("Polar webhook secret is not configured")
        msg_id = headers.get("svix-id")
        timestamp = headers.get("svix-timestamp")
        signature_header = headers.get("svix-signature")
        if not msg_id or not timestamp or not signature_header:
            raise SignatureError("Missing svix signature headers")
        try:
            ts = int(timestamp)
        except ValueError:
            raise SignatureError("Invalid svix timestamp") from None
        if abs(time.time() - ts) > SIGNATURE_TOLERANCE_SECONDS:
            raise SignatureError("Stale svix timestamp")
        if secret.startswith("whsec_"):
            secret = secret[len("whsec_") :]
        try:
            key = base64.b64decode(secret)
        except ValueError:
            raise SignatureError("Invalid webhook secret encoding") from None
        signed_content = msg_id.encode() + b"." + timestamp.encode() + b"." + raw_body
        expected = base64.b64encode(
            hmac.new(key, signed_content, hashlib.sha256).digest()
        ).decode()
        # Header format: "v1,<sig1> v1,<sig2> ..." (multiple during rotation).
        signatures = [
            part.split(",", 1)[1]
            for part in signature_header.split(" ")
            if part.startswith("v1,")
        ]
        if not any(hmac.compare_digest(expected, sig) for sig in signatures):
            raise SignatureError("Polar signature mismatch")

    @staticmethod
    def _require(data: dict, key: str) -> Any:
        value = data.get(key)
        if value is None:
            raise ValueError(f"Polar payload missing {key!r}")
        return value

    def _normalize_checkout(self, data: dict, raw: dict) -> NormalizedPaymentEvent:
        metadata = data.get("metadata") or {}
        order_id = metadata.get("order_id")
        if not order_id:
            raise ValueError("Polar checkout payload has no metadata.order_id")
        user_id, tariff_code = parse_order_id(order_id)
        amount_cents = data.get("amount")
        return NormalizedPaymentEvent(
            provider=self.name,
            provider_payment_id=str(self._require(data, "id")),
            order_id=order_id,
            user_id=user_id,
            tariff=tariff_code,
            amount=(
                Decimal(str(amount_cents)) / 100 if amount_cents is not None else None
            ),
            currency=(data.get("currency") or "").upper() or None,
            status="succeeded",
            raw=raw,
            event_type="checkout.succeeded",
        )

    def _normalize_subscription(
        self, event_type: str, data: dict, raw: dict
    ) -> NormalizedPaymentEvent:
        metadata = data.get("metadata") or {}
        order_id = metadata.get("order_id")
        user_id, tariff_code = (None, None)
        if order_id:
            user_id, tariff_code = parse_order_id(order_id)
        sub_id = str(self._require(data, "id"))
        created = event_type == "subscription.created"
        period_end_raw = data.get("current_period_end")
        period_end = (
            datetime.fromisoformat(period_end_raw.replace("Z", "+00:00"))
            if period_end_raw
            else None
        )
        amount_cents = data.get("amount")
        return NormalizedPaymentEvent(
            provider=self.name,
            provider_payment_id=f"{sub_id}:{'created' if created else 'canceled'}",
            order_id=order_id,
            user_id=user_id,
            tariff=tariff_code,
            amount=(
                Decimal(str(amount_cents)) / 100 if amount_cents is not None else None
            ),
            currency=(data.get("currency") or "").upper() or None,
            status="succeeded" if created else "canceled",
            raw=raw,
            provider_sub_id=sub_id,
            current_period_end=period_end,
            event_type=event_type,
        )
