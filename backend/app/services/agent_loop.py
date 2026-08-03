"""Agent cycle for the JRoots chat: LLM + MCP archive tools.

run_agent_cycle() drives the tool-calling loop for one user message and
yields (event, data) pairs that the router serializes into SSE frames.
Event contract (M1 events plus the paywall addition):

  token   {"text": ...}        — final-answer deltas (cipher/URL-redacted
                                 for the teaser tier; the model itself sees
                                 full data)
  step    {"text": ...}        — intermediate reasoning block of a round
                                 that ended with tool calls (one event per
                                 round; persisted wrapped in <steps>...</steps>
                                 so the frontend can re-render the split)
  usage   {"model", "prompt_tokens", "completion_tokens",
           "session_tokens_total"}
  capped  {"reason": "token_cap"|"daily_budget"}
  paywall {"searches_left": 0} — search credits exhausted (frontend renders
                                 the upgrade offer; the assistant message is
                                 delivered afterwards as a token event)
  done    {"session_id", "message_id", "capped", "searches_left"}
  error   {"message": ...}     — terminal technical failure (LLM error or
                                 MCP gateway unavailable); never charged

Charging model: a completed cycle with at least one real MCP tool call
costs one search credit, including a well-founded "nothing found" answer
(the archive work was still done). A cycle without tool calls (small talk,
clarifying questions) is free — no charge and no searches row. Technical
failures are never charged.
"""

import asyncio
import json
import logging
import re
from collections.abc import AsyncGenerator
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import ChatMessage, ChatSession, Search
from app.services import credits, llm_router
from app.services import mcp_client as mcp_client_module
from app.services.credits import InsufficientCredits
from app.services.mcp_client import McpArchiveClient, McpUnavailableError
from app.services.prompts import SYSTEM_PROMPT
from app.services.stream_redactor import StreamRedactor

logger = logging.getLogger("jroots")

# Hard bound on LLM rounds per user message — a model that keeps requesting
# tools after the call cap must not spin forever.
MAX_AGENT_ROUNDS = 12

PAYWALL_MESSAGE = (
    "Бесплатные поиски закончились. Оформите платный тариф, чтобы продолжить "
    "поиск по архивам без ограничений."
)

MCP_ERROR_MESSAGE = (
    "Поисковый сервис временно недоступен. Попробуйте ещё раз через пару минут."
)

LLM_ERROR_MESSAGE = "Ошибка модели, попробуйте ещё раз."

# «пра» prefixes before дед/баб: each one is a generation beyond grandparents.
_GENERATION_RE = re.compile(r"(пра+)(?:дед|баб)", re.IGNORECASE)


def estimate_generations(text: str) -> int:
    """'How deep is the ask' heuristic for model escalation: прадед=1,
    прапрадед=2, ... — the longest «пра» chain mentioned in the request."""
    generations = 0
    for match in _GENERATION_RE.finditer(text):
        generations = max(generations, len(match.group(1)))
    return generations


async def run_agent_cycle(
    db: AsyncSession,
    session: ChatSession,
    user_content: str,
    *,
    mcp_client: McpArchiveClient | None = None,
) -> AsyncGenerator[tuple[str, dict[str, Any]], None]:
    """Run one full agent turn for a user message, yielding SSE events."""

    # 1. Persist the user message so it survives capped/error replies.
    db.add(ChatMessage(session_id=session.id, role="user", content=user_content))
    await db.commit()

    # 2. Free-tier daily budget → graceful in-band stop (mirrors the M1 path).
    if session.is_free and await llm_router.is_daily_budget_exceeded(db):
        yield "capped", {"reason": "daily_budget"}
        yield "token", {"text": llm_router.DAILY_BUDGET_EXCEEDED_MESSAGE}
        message = await _persist_reply(
            db, session, llm_router.DAILY_BUDGET_EXCEEDED_MESSAGE, 0, 0, 0
        )
        yield "done", await _done_payload(db, session, message, capped=True)
        return

    # 3. Per-session token cap → graceful stop.
    if llm_router.is_token_capped(session.tokens_used):
        yield "capped", {"reason": "token_cap"}
        yield "token", {"text": llm_router.GRACEFUL_STOP_MESSAGE}
        message = await _persist_reply(
            db, session, llm_router.GRACEFUL_STOP_MESSAGE, 0, 0, 0
        )
        yield "done", await _done_payload(db, session, message, capped=True)
        return

    # 4. Credit pre-check: no searches left → paywall without burning LLM
    # tokens on an answer the user would not be charged for anyway.
    balance = await credits.get_balance(db, session.user_id)
    if balance["searches_left"] < 1:
        async for event in _paywall_events(db, session):
            yield event
        return

    initial_tool_calls = session.tool_calls or 0
    client = mcp_client or mcp_client_module.build_mcp_client(
        session_id=session.id,
        user_id=session.user_id,
        initial_used=initial_tool_calls,
        db=db,
    )

    try:
        try:
            await client.open()
        except McpUnavailableError:
            logger.exception("MCP unavailable for session %d", session.id)
            await _mark_technical_error(db, session)
            yield "error", {"message": MCP_ERROR_MESSAGE}
            return

        # Teaser tier: the outgoing stream is redacted; the model still sees
        # full tool results so it can iterate on the search.
        redactor = StreamRedactor() if session.is_free else None
        messages = await _build_messages(db, session)
        visible_parts: list[str] = []
        usage = {"prompt_tokens": 0, "completion_tokens": 0}
        model = llm_router.select_model({})
        generations = estimate_generations(user_content)

        try:
            for _round in range(MAX_AGENT_ROUNDS):
                model = llm_router.select_model(
                    {
                        "empty_searches": client.empty_searches,
                        "generations": generations,
                    }
                )
                round_raw: list[str] = []
                round_visible: list[str] = []
                tool_calls: list[dict[str, str]] = []
                async for item in llm_router.stream_completion(
                    messages, model, tools=client.openai_tools
                ):
                    if item["type"] == "token":
                        round_raw.append(item["text"])
                        out = (
                            redactor.feed(item["text"])
                            if redactor is not None
                            else item["text"]
                        )
                        round_visible.append(out)
                    elif item["type"] == "tool_calls":
                        tool_calls = item["tool_calls"]
                    elif item["type"] == "usage":
                        usage["prompt_tokens"] += item["prompt_tokens"]
                        usage["completion_tokens"] += item["completion_tokens"]
                if redactor is not None:
                    # Patterns never span completion rounds — release the
                    # held-back tail into THIS round's output.
                    round_visible.append(redactor.flush())

                # The event type is decided by how the round ended, so the
                # round's text is buffered until its stream completes:
                # - ended with tool calls → intermediate reasoning, one
                #   `step` event, persisted wrapped in <steps>...</steps>;
                # - no tool calls → the final answer, `token` events with
                #   the original delta granularity.
                if not tool_calls:
                    visible_parts.extend(round_visible)
                    for out in round_visible:
                        if out:
                            yield "token", {"text": out}
                    break

                step_text = "".join(round_visible)
                if step_text:
                    yield "step", {"text": step_text}
                    visible_parts.append(f"<steps>{step_text}</steps>")
                messages.append(_assistant_tool_message(round_raw, tool_calls))
                tool_messages = await _execute_tools(client, tool_calls)
                messages.extend(tool_messages)
            else:
                logger.warning(
                    "Agent hit the round cap (%d) in session %d",
                    MAX_AGENT_ROUNDS,
                    session.id,
                )
        except McpUnavailableError:
            logger.exception("MCP failed mid-cycle, session %d", session.id)
            await _mark_technical_error(db, session, client, initial_tool_calls)
            yield "error", {"message": MCP_ERROR_MESSAGE}
            return
        except Exception:
            logger.exception("LLM completion failed for session %d", session.id)
            await _mark_technical_error(db, session, client, initial_tool_calls)
            yield "error", {"message": LLM_ERROR_MESSAGE}
            return
    finally:
        await client.close()

    final_text = "".join(visible_parts)
    tool_calls_delta = client.calls_used - initial_tool_calls

    # 5. Successful cycle. A cycle without real MCP work (small talk,
    # clarifying answers) is free: no search journal row, no charge.
    searches_left = balance["searches_left"]
    if tool_calls_delta > 0:
        search_row = Search(
            session_id=session.id,
            user_id=session.user_id,
            charged=False,
            query_summary=user_content[:200],
            results_count=client.searches_with_results,
        )
        db.add(search_row)
        await db.flush()
        try:
            charge_result = await credits.charge(
                db,
                session.user_id,
                searches=1,
                reason="usage",
                ref_id=f"search:{search_row.id}",
            )
            search_row.charged = True
            searches_left = charge_result["searches_left"]
        except InsufficientCredits:
            # The balance raced to zero after the pre-check. The answer is
            # already streamed and stays free; surface the paywall on top.
            logger.warning(
                "Charge raced to zero for user %d (search %d) — not charged",
                session.user_id,
                search_row.id,
            )
            await _persist_reply(
                db,
                session,
                final_text,
                usage["prompt_tokens"],
                usage["completion_tokens"],
                tool_calls_delta,
            )
            async for event in _paywall_events(db, session):
                yield event
            return

    message = await _persist_reply(
        db,
        session,
        final_text,
        usage["prompt_tokens"],
        usage["completion_tokens"],
        tool_calls_delta,
    )
    yield "usage", {
        "model": model,
        "prompt_tokens": usage["prompt_tokens"],
        "completion_tokens": usage["completion_tokens"],
        "session_tokens_total": session.tokens_used,
    }
    yield "done", {
        "session_id": session.id,
        "message_id": message.id,
        "capped": False,
        "searches_left": searches_left,
    }


def _assistant_tool_message(
    round_text: list[str], tool_calls: list[dict[str, str]]
) -> dict[str, Any]:
    """OpenAI-format assistant message carrying the requested tool calls."""
    return {
        "role": "assistant",
        "content": "".join(round_text) or None,
        "tool_calls": [
            {
                "id": call["id"] or f"call_{index}",
                "type": "function",
                "function": {"name": call["name"], "arguments": call["arguments"]},
            }
            for index, call in enumerate(tool_calls)
        ],
    }


async def _execute_tools(
    client: McpArchiveClient, tool_calls: list[dict[str, str]]
) -> list[dict[str, Any]]:
    """Run the requested tool calls (independent ones in parallel) and
    return the OpenAI-format tool result messages."""
    results = await asyncio.gather(
        *(_execute_one_tool(client, call) for call in tool_calls),
        return_exceptions=True,
    )
    tool_messages: list[dict[str, Any]] = []
    for result in results:
        if isinstance(result, McpUnavailableError):
            raise result
        if isinstance(result, Exception):
            raise result
        tool_messages.append(result)
    return tool_messages


async def _execute_one_tool(
    client: McpArchiveClient, call: dict[str, str]
) -> dict[str, Any]:
    call_id = call["id"]
    try:
        arguments = json.loads(call["arguments"] or "{}")
        if not isinstance(arguments, dict):
            raise ValueError("tool arguments must be a JSON object")
    except (json.JSONDecodeError, ValueError):
        logger.warning(
            "Invalid tool arguments from model: tool=%s arguments=%r",
            call["name"],
            call["arguments"],
        )
        return {
            "role": "tool",
            "tool_call_id": call_id,
            "content": "Error: невалидные аргументы инструмента "
            "(ожидается JSON-объект).",
        }
    text = await client.call(call["name"], arguments)
    return {"role": "tool", "tool_call_id": call_id, "content": text}


async def _paywall_events(
    db: AsyncSession, session: ChatSession
) -> AsyncGenerator[tuple[str, dict[str, Any]], None]:
    """Paywall terminal flow: paywall event + persisted assistant notice."""
    yield "paywall", {"searches_left": 0}
    yield "token", {"text": PAYWALL_MESSAGE}
    message = await _persist_reply(db, session, PAYWALL_MESSAGE, 0, 0, 0)
    yield "done", {
        "session_id": session.id,
        "message_id": message.id,
        "capped": False,
        "searches_left": 0,
    }


async def _build_messages(db: AsyncSession, session: ChatSession) -> list[dict]:
    """System prompt + persisted conversation (user/assistant only)."""
    result = await db.execute(
        select(ChatMessage)
        .where(ChatMessage.session_id == session.id)
        .order_by(ChatMessage.created_at, ChatMessage.id)
    )
    history = [
        {"role": m.role, "content": m.content}
        for m in result.scalars().all()
        if m.role in ("user", "assistant")
    ]
    return [{"role": "system", "content": SYSTEM_PROMPT}, *history]


async def _persist_reply(
    db: AsyncSession,
    session: ChatSession,
    content: str,
    prompt_tokens: int,
    completion_tokens: int,
    tool_calls_delta: int,
) -> ChatMessage:
    """Save the assistant reply and accumulate the session counters
    (tokens, tool calls, free-tier daily LLM spend)."""
    total = prompt_tokens + completion_tokens
    message = ChatMessage(
        session_id=session.id,
        role="assistant",
        content=content,
        tokens=total,
    )
    db.add(message)
    session.tokens_used = (session.tokens_used or 0) + total
    session.tool_calls = (session.tool_calls or 0) + tool_calls_delta
    # A completed reply (even a capped graceful stop) recovers the session
    # from a previous error.
    session.status = "open"
    if session.is_free and total > 0:
        await llm_router.record_daily_spend(
            db, llm_router.estimate_cost_usd(prompt_tokens, completion_tokens)
        )
    await db.commit()
    await db.refresh(message)
    return message


async def _mark_technical_error(
    db: AsyncSession,
    session: ChatSession,
    client: McpArchiveClient | None = None,
    initial_tool_calls: int = 0,
) -> None:
    """Technical failure: flag the session, keep executed tool calls counted,
    and never touch credits."""
    session.status = "error"
    if client is not None:
        session.tool_calls = (session.tool_calls or 0) + (
            client.calls_used - initial_tool_calls
        )
    await db.commit()


async def _done_payload(
    db: AsyncSession, session: ChatSession, message: ChatMessage, *, capped: bool
) -> dict[str, Any]:
    searches_left = (await credits.get_balance(db, session.user_id))["searches_left"]
    return {
        "session_id": session.id,
        "message_id": message.id,
        "capped": capped,
        "searches_left": searches_left,
    }
