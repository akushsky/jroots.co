from app.payments.base import (
    NormalizedPaymentEvent,
    PaymentProvider,
    ProviderError,
    SignatureError,
)
from app.payments.nowpayments import NowPaymentsProvider
from app.payments.polar import PolarProvider
from app.payments.tariffs import TARIFFS, Tariff
from app.payments.yukassa import YuKassaProvider

_PROVIDERS: dict[str, PaymentProvider] = {
    "polar": PolarProvider(),
    "nowpayments": NowPaymentsProvider(),
    "yukassa": YuKassaProvider(),
}


def get_provider(name: str) -> PaymentProvider | None:
    return _PROVIDERS.get(name)


__all__ = [
    "NormalizedPaymentEvent",
    "PaymentProvider",
    "ProviderError",
    "SignatureError",
    "TARIFFS",
    "Tariff",
    "get_provider",
]
