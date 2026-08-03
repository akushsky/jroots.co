from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from typing import TYPE_CHECKING, Any, Mapping, Protocol

if TYPE_CHECKING:
    from app.models import User
    from app.payments.tariffs import Tariff


class SignatureError(Exception):
    """Webhook authenticity could not be verified.

    Bad signature, foreign source IP, or a failed re-verification call to the
    provider's API. Mapped to HTTP 401 by the webhook route.
    """


class ProviderError(Exception):
    """Upstream provider API call failed (checkout creation, re-verification)."""


@dataclass
class NormalizedPaymentEvent:
    provider: str
    provider_payment_id: str
    order_id: str | None
    user_id: int | None
    tariff: str | None
    amount: Decimal | None
    currency: str | None
    # Internal status vocabulary:
    # "succeeded" | "partially_paid" | "pending" | "failed" | "canceled"
    status: str
    raw: dict[str, Any]
    # Subscription-specific (only for subscription.* events):
    provider_sub_id: str | None = None
    current_period_end: datetime | None = None
    event_type: str = ""


class PaymentProvider(Protocol):
    name: str

    async def create_checkout(
        self,
        *,
        user: "User",
        tariff: "Tariff",
        success_url: str,
        cancel_url: str,
    ) -> dict:
        """Create a checkout/invoice with the provider.

        Returns {"checkout_url": str, "order_id": str}.
        """
        ...

    async def verify_and_parse(
        self,
        headers: Mapping[str, str],
        raw_body: bytes,
        *,
        client_ip: str | None = None,
    ) -> NormalizedPaymentEvent:
        """Verify webhook authenticity and normalize the payload.

        Raises SignatureError when verification fails, ValueError when the
        payload is malformed.
        """
        ...
