"""LLM routing for the JRoots chat (OpenAI-compatible providers).

Supports Gemini (default) and Moonshot/Kimi via `llm_provider`. Responsibilities:
- streaming completions via the openai SDK against the configured base_url;
- main/escalation model selection;
- per-session token cap with a graceful-stop message;
- free-tier cost accounting against the daily budget;
- the is_free_user helper (payments/subscription aware).
"""

import asyncio
import logging
import random
from collections.abc import AsyncGenerator, AsyncIterator, Mapping
from datetime import date
from decimal import Decimal
from typing import Any

from openai import (
    APIConnectionError,
    APITimeoutError,
    AsyncOpenAI,
    InternalServerError,
    RateLimitError,
)
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

# Transient provider failures worth retrying when ESTABLISHING a stream
# (before the first chunk — retrying mid-stream would duplicate text).
# BadRequestError / AuthenticationError are deliberately absent: those are
# deterministic and a retry would just fail again.
_RETRYABLE_STREAM_ERRORS = (
    APIConnectionError,
    APITimeoutError,
    RateLimitError,
    InternalServerError,
)
_STREAM_ESTABLISH_ATTEMPTS = 3
_RETRY_BACKOFF_BASE_SECONDS = 1.0

_client: AsyncOpenAI | None = None


def _provider_credentials(settings: Any) -> tuple[str, str]:
    """Return (api_key, base_url) for the configured LLM provider."""
    if settings.llm_provider == "moonshot":
        return (
            settings.moonshot_api_key or "not-configured",
            settings.moonshot_base_url,
        )
    return (
        settings.google_api_key or "not-configured",
        settings.gemini_base_url,
    )


def get_llm_client() -> AsyncOpenAI:
    """Process-wide OpenAI-compatible client for the active LLM provider."""
    global _client
    if _client is None:
        settings = get_settings()
        api_key, base_url = _provider_credentials(settings)
        _client = AsyncOpenAI(api_key=api_key, base_url=base_url)
    return _client


def _normalize_extra_content(value: Any) -> Any:
    """Coerce provider-specific tool-call extras (e.g. Gemini thought_signature)
    into plain JSON so they survive the round-trip back into messages."""
    if value is None or isinstance(value, (dict, list, str, int, float, bool)):
        return value
    model_dump = getattr(value, "model_dump", None)
    if callable(model_dump):
        return model_dump()
    if hasattr(value, "__dict__"):
        return {
            key: _normalize_extra_content(item)
            for key, item in vars(value).items()
            if not key.startswith("_")
        }
    return value


def _tool_call_slot_index(
    call: Any, tool_call_slots: dict[int, dict[str, Any]]
) -> int:
    """Resolve the slot key for a streamed tool-call delta.

    OpenAI sends a stable integer `index`. Gemini's OpenAI-compat layer often
    omits it (`index=None`); a new `id` opens a new slot, and id-less continuations
    append to the most recent one — otherwise parallel calls collapse into one.
    """
    index = getattr(call, "index", None)
    if index is not None:
        return int(index)
    if getattr(call, "id", None):
        return len(tool_call_slots)
    if tool_call_slots:
        return max(tool_call_slots)
    return 0


async def _retry_backoff(attempt: int) -> None:
    """Exponential backoff with jitter: 1s, 2s, 4s, ... (+ up to 0.5s)."""
    delay = _RETRY_BACKOFF_BASE_SECONDS * (2**attempt) + random.uniform(0, 0.5)
    await asyncio.sleep(delay)


async def _establish_stream(
    client: AsyncOpenAI, kwargs: dict[str, Any]
) -> tuple[AsyncIterator, Any]:
    """Create the completion stream and pull its first chunk, retrying
    transient provider failures (connection/timeout/429/5xx) up to
    _STREAM_ESTABLISH_ATTEMPTS times with exponential backoff.

    Pulling the first chunk is part of establishment: with stream=True the
    HTTP response (and its error status) only materializes when iteration
    starts. Once this returns, errors must NOT be retried — the stream may
    already have produced text, and a retry would duplicate it.
    """
    for attempt in range(_STREAM_ESTABLISH_ATTEMPTS):
        try:
            stream = await client.chat.completions.create(**kwargs)
            iterator = stream.__aiter__()
            try:
                first_chunk = await iterator.__anext__()
            except StopAsyncIteration:
                first_chunk = None
            return iterator, first_chunk
        except _RETRYABLE_STREAM_ERRORS as exc:
            if attempt == _STREAM_ESTABLISH_ATTEMPTS - 1:
                raise
            logger.warning(
                "LLM stream establishment failed (attempt %d/%d, %s) — retrying",
                attempt + 1,
                _STREAM_ESTABLISH_ATTEMPTS,
                type(exc).__name__,
            )
            await _retry_backoff(attempt)
    raise AssertionError("unreachable")  # the loop always returns or raises


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
    messages: list[dict[str, Any]],
    model: str,
    *,
    max_tokens: int | None = None,
    tools: list[dict[str, Any]] | None = None,
) -> AsyncGenerator[dict[str, Any], None]:
    """Yield {"type": "token", "text": ...} deltas, then a final
    {"type": "usage", "prompt_tokens": N, "completion_tokens": M} item.

    When `tools` is provided (function-calling schemas), tool-call deltas are
    accumulated across chunks and emitted before usage as
    {"type": "tool_calls", "tool_calls": [{"id", "name", "arguments"}]}
    (arguments is the raw JSON string, as streamed by the provider).

    Usage comes from the provider's stream usage chunk (include_usage); if the
    provider omits it, both counters fall back to a chars/4 estimate.
    """
    settings = get_settings()
    client = get_llm_client()
    kwargs: dict[str, Any] = {
        "model": model,
        "messages": messages,
        "stream": True,
        "stream_options": {"include_usage": True},
    }
    if max_tokens is not None:
        kwargs["max_tokens"] = max_tokens
    if tools is not None:
        kwargs["tools"] = tools
    if settings.llm_reasoning_effort:
        kwargs["reasoning_effort"] = settings.llm_reasoning_effort

    stream_iterator, first_chunk = await _establish_stream(client, kwargs)

    collected: list[str] = []
    tool_call_slots: dict[int, dict[str, Any]] = {}
    usage: Any = None

    async def _all_chunks() -> AsyncGenerator[Any, None]:
        if first_chunk is not None:
            yield first_chunk
        async for chunk in stream_iterator:
            yield chunk

    async for chunk in _all_chunks():
        if getattr(chunk, "usage", None):
            usage = chunk.usage
        choices = getattr(chunk, "choices", None) or []
        if not choices:
            continue
        delta = choices[0].delta
        text = getattr(delta, "content", None)
        if text:
            collected.append(text)
            yield {"type": "token", "text": text}
        for call in getattr(delta, "tool_calls", None) or []:
            index = _tool_call_slot_index(call, tool_call_slots)
            slot = tool_call_slots.setdefault(
                index,
                {"id": "", "name": "", "arguments": "", "extra_content": None},
            )
            if getattr(call, "id", None):
                slot["id"] += call.id
            function = getattr(call, "function", None)
            if function is not None:
                if getattr(function, "name", None):
                    slot["name"] += function.name
                if getattr(function, "arguments", None):
                    slot["arguments"] += function.arguments
            # Gemini 3 requires thought_signature echoed on the next turn.
            extra = getattr(call, "extra_content", None)
            if extra is not None:
                slot["extra_content"] = _normalize_extra_content(extra)

    if tool_call_slots:
        emitted: list[dict[str, Any]] = []
        for index in sorted(tool_call_slots):
            slot = tool_call_slots[index]
            entry: dict[str, Any] = {
                "id": slot["id"],
                "name": slot["name"],
                "arguments": slot["arguments"],
            }
            if slot.get("extra_content") is not None:
                entry["extra_content"] = slot["extra_content"]
            emitted.append(entry)
        yield {"type": "tool_calls", "tool_calls": emitted}

    if usage is not None:
        prompt_tokens = int(usage.prompt_tokens or 0)
        completion_tokens = int(usage.completion_tokens or 0)
        # Gemini bills thinking tokens as output but often leaves them out of
        # completion_tokens (total >> prompt + completion). Count them so the
        # session cap and daily budget stay honest.
        total_tokens = getattr(usage, "total_tokens", None)
        if total_tokens is not None:
            completion_tokens = max(completion_tokens, int(total_tokens) - prompt_tokens)
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
