"""LLM routing for the JRoots chat (Moonshot AI / Kimi, OpenAI-compatible).

Responsibilities:
- streaming completions via the openai SDK against the configured base_url;
- main/escalation model selection;
- per-session token cap with a graceful-stop message;
- free-tier cost accounting against the daily budget;
- the is_free_user helper (payments/subscription aware).
"""

import logging
from collections.abc import AsyncGenerator, Mapping
from datetime import date
from decimal import Decimal
from typing import Any

from openai import AsyncOpenAI
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.models import DailyBudget, Payment, Subscription
from app.services.credits import _dialect_insert

logger = logging.getLogger("jroots")

GRACEFUL_STOP_MESSAGE = (
    "Ваша задача оказалась сложнее обычного, и мы достигли лимита этой "
    "сессии. Промежуточный итог уже в переписке выше — его можно "
    "использовать для дальнейшей работы. Продолжить поиск можно в платном "
    "тарифе: там нет лимита токенов на сессию и доступна более мощная модель."
)

DAILY_BUDGET_EXCEEDED_MESSAGE = (
    "Бесплатный лимит на сегодня исчерпан. Попробуйте завтра — лимит "
    "обновляется ежедневно, — или продолжите без ограничений в платном тарифе."
)

FREE_SESSIONS_LIMIT_MESSAGE = (
    "Бесплатных сессий доступно не больше двух в сутки. Продолжите в одной из "
    "текущих сессий или оформите платный тариф без ограничений."
)

# Rough heuristic when the provider does not return usage: ~4 chars/token.
_CHARS_PER_TOKEN = 4

_client: AsyncOpenAI | None = None


def get_llm_client() -> AsyncOpenAI:
    """Process-wide OpenAI-compatible client for Moonshot AI."""
    global _client
    if _client is None:
        settings = get_settings()
        _client = AsyncOpenAI(
            api_key=settings.moonshot_api_key or "not-configured",
            base_url=settings.moonshot_base_url,
        )
    return _client


def select_model(session_context: Mapping[str, Any] | None = None) -> str:
    """Pick the model for the next completion.

    Default is the main model; escalation flags in the context switch to the
    escalation model: explicit escalate=True, 3+ empty searches in a row, or
    3+ answer generations without progress. Real triggers arrive in M2/M3 —
    for now callers pass an empty context and get the main model.
    """
    settings = get_settings()
    ctx = session_context or {}
    if (
        ctx.get("escalate")
        or (ctx.get("empty_searches") or 0) >= 3
        or (ctx.get("generations") or 0) >= 3
    ):
        return settings.llm_model_escalation
    return settings.llm_model_main


def _estimate_tokens(text: str) -> int:
    return max(1, (len(text) + _CHARS_PER_TOKEN - 1) // _CHARS_PER_TOKEN)


async def stream_completion(
    messages: list[dict[str, str]],
    model: str,
    *,
    max_tokens: int | None = None,
) -> AsyncGenerator[dict[str, Any], None]:
    """Yield {"type": "token", "text": ...} deltas, then a final
    {"type": "usage", "prompt_tokens": N, "completion_tokens": M} item.

    Usage comes from the provider's stream usage chunk (include_usage); if the
    provider omits it, both counters fall back to a chars/4 estimate.
    """
    client = get_llm_client()
    kwargs: dict[str, Any] = {
        "model": model,
        "messages": messages,
        "stream": True,
        "stream_options": {"include_usage": True},
    }
    if max_tokens is not None:
        kwargs["max_tokens"] = max_tokens

    stream = await client.chat.completions.create(**kwargs)

    collected: list[str] = []
    usage: Any = None
    async for chunk in stream:
        if getattr(chunk, "usage", None):
            usage = chunk.usage
        choices = getattr(chunk, "choices", None) or []
        if not choices:
            continue
        text = getattr(choices[0].delta, "content", None)
        if text:
            collected.append(text)
            yield {"type": "token", "text": text}

    if usage is not None:
        prompt_tokens = int(usage.prompt_tokens or 0)
        completion_tokens = int(usage.completion_tokens or 0)
    else:
        prompt_tokens = sum(_estimate_tokens(m.get("content") or "") for m in messages)
        completion_tokens = _estimate_tokens("".join(collected))
    yield {
        "type": "usage",
        "prompt_tokens": prompt_tokens,
        "completion_tokens": completion_tokens,
    }


def is_token_capped(tokens_used: int | None) -> bool:
    """True when the session already burned its per-session token budget."""
    return (tokens_used or 0) >= get_settings().llm_token_cap_per_session


def estimate_cost_usd(prompt_tokens: int, completion_tokens: int) -> Decimal:
    """USD cost of one completion at the configured Kimi prices."""
    settings = get_settings()
    cost = (
        prompt_tokens * settings.llm_price_in_per_1m
        + completion_tokens * settings.llm_price_out_per_1m
    ) / 1_000_000
    return Decimal(str(round(cost, 6)))


async def get_daily_free_spend(db: AsyncSession, day: date | None = None) -> Decimal:
    result = await db.execute(
        select(DailyBudget.free_spend_usd).where(
            DailyBudget.day == (day or date.today())
        )
    )
    row = result.scalar_one_or_none()
    return Decimal(row) if row is not None else Decimal("0")


async def is_daily_budget_exceeded(db: AsyncSession) -> bool:
    spend = await get_daily_free_spend(db)
    return spend >= Decimal(str(get_settings().free_daily_budget_usd))


async def record_daily_spend(
    db: AsyncSession, cost_usd: Decimal, day: date | None = None
) -> None:
    """Upsert today's daily_budget row, adding cost_usd to free_spend_usd.

    Flushes but does not commit — the caller owns the transaction.
    """
    if cost_usd <= 0:
        return
    table = DailyBudget.__table__
    stmt = _dialect_insert(db, table).values(
        day=day or date.today(), free_spend_usd=cost_usd
    )
    stmt = stmt.on_conflict_do_update(
        index_elements=["day"],
        set_={"free_spend_usd": table.c.free_spend_usd + cost_usd},
    )
    await db.execute(stmt)
    await db.flush()


async def is_free_user(db: AsyncSession, user_id: int) -> bool:
    """Free tier = no successful payment and no active subscription."""
    payment = await db.execute(
        select(func.count(Payment.id)).where(
            Payment.user_id == user_id, Payment.status == "succeeded"
        )
    )
    if payment.scalar_one() > 0:
        return False
    subscription = await db.execute(
        select(func.count(Subscription.id)).where(
            Subscription.user_id == user_id, Subscription.status == "active"
        )
    )
    return subscription.scalar_one() == 0
