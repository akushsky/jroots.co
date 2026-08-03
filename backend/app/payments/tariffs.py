import uuid
from dataclasses import dataclass
from decimal import Decimal


@dataclass(frozen=True)
class Tariff:
    code: str
    title: str
    amount_usd: Decimal
    kind: str  # "one_time" | "subscription" | "reservation"
    grant_searches: int
    grant_scans: int


TARIFFS: dict[str, Tariff] = {
    # «Дело» — разовый пакет: 25 поисков + 10 сканов.
    "delo": Tariff(
        code="delo",
        title="Дело",
        amount_usd=Decimal("25.00"),
        kind="one_time",
        grant_searches=25,
        grant_scans=10,
    ),
    # «Исследователь» — подписка $15/мес: 30 сканов/мес, поиски fair-use.
    "researcher": Tariff(
        code="researcher",
        title="Исследователь",
        amount_usd=Decimal("15.00"),
        kind="subscription",
        grant_searches=0,
        grant_scans=30,
    ),
    # Допродажа: пакет из 10 сканов.
    "scans_pack": Tariff(
        code="scans_pack",
        title="Пакет сканов",
        amount_usd=Decimal("5.00"),
        kind="one_time",
        grant_searches=0,
        grant_scans=10,
    ),
    # Pay-per-result: резерв под разблокировку записи.
    # Кредиты не начисляются — фиксируем только факт оплаты
    # (journal-запись с нулевыми дельтами), логика резерва отдельно.
    "ppr": Tariff(
        code="ppr",
        title="Разблокировка записи",
        amount_usd=Decimal("3.00"),
        kind="reservation",
        grant_searches=0,
        grant_scans=0,
    ),
}


def make_order_id(user_id: int, tariff_code: str, *, with_nonce: bool = True) -> str:
    """order_id format: "{user_id}:{tariff}" (optionally ":{nonce}")."""
    base = f"{user_id}:{tariff_code}"
    if with_nonce:
        return f"{base}:{uuid.uuid4().hex[:12]}"
    return base


def parse_order_id(order_id: str) -> tuple[int, str]:
    parts = order_id.split(":")
    if len(parts) < 2:
        raise ValueError(f"Malformed order_id: {order_id!r}")
    try:
        user_id = int(parts[0])
    except ValueError:
        raise ValueError(f"Malformed order_id (bad user id): {order_id!r}") from None
    tariff_code = parts[1]
    if tariff_code not in TARIFFS:
        raise ValueError(f"Unknown tariff in order_id: {order_id!r}")
    return user_id, tariff_code
