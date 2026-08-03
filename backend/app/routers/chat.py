"""Chat endpoints: sessions + message completions (SSE or JSON).

SSE contract (consumed by the frontend):
  event: token  / data: {"text": "..."}                              — final-answer deltas
  event: step   / data: {"text": "..."}                              — intermediate
                        reasoning block of a round that ended with tool
                        calls (agent mode only, M2)
  event: usage  / data: {"model", "prompt_tokens", "completion_tokens",
                         "session_tokens_total"}
  event: capped / data: {"reason": "token_cap"|"daily_budget"}       — before
                        the graceful-stop message (delivered as token)
  event: paywall / data: {"searches_left": 0}                        — search
                        credits exhausted; the assistant notice follows as a
                        token event (agent mode only, M2)
  event: done   / data: {"session_id", "message_id", "capped",
                         "searches_left"}
  event: error  / data: {"message": "..."}                           — terminal

With JROOTS_MCP_ENABLED=true (default) messages run the agent cycle
(LLM + MCP archive tools); with false the legacy M1 direct-completion path
is used as a kill-switch fallback.
"""

import json
import logging
from collections.abc import AsyncGenerator
from datetime import datetime, timedelta, timezone
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.database import get_db
from app.models import ChatMessage, ChatSession, User
from app.services import credits as credits_service
from app.services import llm_router
from app.services.agent_loop import run_agent_cycle
from app.services.auth import get_current_user
from app.services.prompts import SYSTEM_PROMPT

logger = logging.getLogger("jroots")

router = APIRouter(prefix="/api/chat", tags=["chat"])

_ROLE_USER = "user"
_ROLE_ASSISTANT = "assistant"

LLM_ERROR_MESSAGE = "Ошибка модели, попробуйте ещё раз."


class MessageIn(BaseModel):
    content: str = Field(min_length=1, max_length=20_000)

    @field_validator("content")
    @classmethod
    def _strip_content(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("Сообщение не должно быть пустым")
        return value


def _sse(event: str, data: dict) -> str:
    return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"


async def _searches_left(db: AsyncSession, user_id: int) -> int:
    return (await credits_service.get_balance(db, user_id))["searches_left"]


def _iso(dt: datetime | None) -> str | None:
    """ISO-8601 with explicit UTC offset — naive DB datetimes are UTC."""
    if dt is None:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.isoformat()


def _session_dict(
    session: ChatSession,
    last_message: ChatMessage | None = None,
    title: str | None = None,
) -> dict:
    payload = {
        "id": session.id,
        "is_free": session.is_free,
        "status": session.status,
        "model_main": session.model_main,
        "tokens_used": session.tokens_used,
        "tool_calls": session.tool_calls,
        "created_at": _iso(session.created_at),
        "closed_at": _iso(session.closed_at),
    }
    if title is not None:
        payload["title"] = title
    if last_message is not None:
        payload["last_message"] = _truncate(last_message.content, 200)
    return payload


def _truncate(content: str, limit: int) -> str:
    return content[:limit] + "…" if len(content) > limit else content


def _message_dict(message: ChatMessage, truncate: int | None = None) -> dict:
    content = message.content
    if truncate is not None and len(content) > truncate:
        content = content[:truncate] + "…"
    return {
        "id": message.id,
        "role": message.role,
        "content": content,
        "tokens": message.tokens,
        "created_at": _iso(message.created_at),
    }


async def _get_owned_session(
    db: AsyncSession, session_id: int, user_id: int
) -> ChatSession:
    result = await db.execute(
        select(ChatSession).where(
            ChatSession.id == session_id, ChatSession.user_id == user_id
        )
    )
    session = result.scalar_one_or_none()
    if session is None:
        raise HTTPException(status_code=404, detail="Сессия не найдена")
    return session


def _session_title(first_user_message: ChatMessage | None) -> str:
    """Session list title: first user message (80 chars) or a placeholder."""
    if first_user_message is None:
        return "Новый поиск"
    content = first_user_message.content
    return content[:80] + "…" if len(content) > 80 else content


@router.post("/sessions", status_code=201)
async def create_session(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    settings = get_settings()
    is_free = await llm_router.is_free_user(db, current_user.id)

    if is_free:
        if await llm_router.is_daily_budget_exceeded(db):
            raise HTTPException(
                status_code=429, detail=llm_router.DAILY_BUDGET_EXCEEDED_MESSAGE
            )
        day_ago = datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(days=1)
        recent = await db.execute(
            select(func.count(ChatSession.id)).where(
                ChatSession.user_id == current_user.id,
                ChatSession.is_free.is_(True),
                ChatSession.created_at > day_ago,
            )
        )
        if recent.scalar_one() >= settings.free_sessions_per_day:
            raise HTTPException(
                status_code=429, detail=llm_router.FREE_SESSIONS_LIMIT_MESSAGE
            )

    session = ChatSession(
        user_id=current_user.id,
        is_free=is_free,
        model_main=settings.llm_model_main,
        status="open",
    )
    db.add(session)
    await db.commit()
    await db.refresh(session)
    logger.info(
        "Chat session %d created for user %d (is_free=%s)",
        session.id,
        current_user.id,
        is_free,
    )
    return _session_dict(session)


@router.get("/sessions")
async def list_sessions(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    result = await db.execute(
        select(ChatSession)
        .where(ChatSession.user_id == current_user.id)
        .order_by(ChatSession.created_at.desc())
    )
    sessions = result.scalars().all()

    latest_ids = (
        select(
            ChatMessage.session_id,
            func.max(ChatMessage.id).label("last_id"),
        )
        .group_by(ChatMessage.session_id)
        .subquery()
    )
    messages_result = await db.execute(
        select(ChatMessage).join(latest_ids, ChatMessage.id == latest_ids.c.last_id)
    )
    last_by_session = {m.session_id: m for m in messages_result.scalars().all()}

    first_user_ids = (
        select(
            ChatMessage.session_id,
            func.min(ChatMessage.id).label("first_id"),
        )
        .where(ChatMessage.role == _ROLE_USER)
        .group_by(ChatMessage.session_id)
        .subquery()
    )
    first_result = await db.execute(
        select(ChatMessage).join(
            first_user_ids, ChatMessage.id == first_user_ids.c.first_id
        )
    )
    first_by_session = {m.session_id: m for m in first_result.scalars().all()}

    return [
        _session_dict(
            s,
            last_message=last_by_session.get(s.id),
            title=_session_title(first_by_session.get(s.id)),
        )
        for s in sessions
    ]


@router.get("/sessions/{session_id}")
async def get_session(
    session_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    session = await _get_owned_session(db, session_id, current_user.id)
    result = await db.execute(
        select(ChatMessage)
        .where(ChatMessage.session_id == session.id)
        .order_by(ChatMessage.created_at, ChatMessage.id)
    )
    return {
        **_session_dict(session),
        "messages": [_message_dict(m) for m in result.scalars().all()],
    }


async def _persist_assistant_message(
    db: AsyncSession,
    session: ChatSession,
    content: str,
    prompt_tokens: int,
    completion_tokens: int,
) -> ChatMessage:
    """Save the assistant reply, accumulate session counters and, for free
    sessions, the estimated LLM cost against the daily budget."""
    total = prompt_tokens + completion_tokens
    message = ChatMessage(
        session_id=session.id,
        role=_ROLE_ASSISTANT,
        content=content,
        tokens=total,
    )
    db.add(message)
    session.tokens_used = (session.tokens_used or 0) + total
    # A completed reply (even a capped graceful stop) recovers the session
    # from a previous LLM error.
    session.status = "open"
    if session.is_free:
        await llm_router.record_daily_spend(
            db, llm_router.estimate_cost_usd(prompt_tokens, completion_tokens)
        )
    await db.commit()
    await db.refresh(message)
    return message


async def _build_llm_messages(db: AsyncSession, session: ChatSession) -> list[dict]:
    result = await db.execute(
        select(ChatMessage)
        .where(ChatMessage.session_id == session.id)
        .order_by(ChatMessage.created_at, ChatMessage.id)
    )
    history = [{"role": m.role, "content": m.content} for m in result.scalars().all()]
    return [{"role": "system", "content": SYSTEM_PROMPT}, *history]


async def _stream_reply(
    db: AsyncSession, session: ChatSession
) -> AsyncGenerator[str, None]:
    """SSE stream for one assistant reply, including cap and error paths."""
    if llm_router.is_token_capped(session.tokens_used):
        yield _sse("capped", {"reason": "token_cap"})
        yield _sse("token", {"text": llm_router.GRACEFUL_STOP_MESSAGE})
        message = await _persist_assistant_message(
            db, session, llm_router.GRACEFUL_STOP_MESSAGE, 0, 0
        )
        yield _sse(
            "done",
            {
                "session_id": session.id,
                "message_id": message.id,
                "capped": True,
                "searches_left": await _searches_left(db, session.user_id),
            },
        )
        return

    model = llm_router.select_model({})
    messages = await _build_llm_messages(db, session)
    collected: list[str] = []
    usage = {"prompt_tokens": 0, "completion_tokens": 0}
    try:
        async for item in llm_router.stream_completion(messages, model):
            if item["type"] == "token":
                collected.append(item["text"])
                yield _sse("token", {"text": item["text"]})
            elif item["type"] == "usage":
                usage = item
    except Exception:
        logger.exception("LLM completion failed for session %d", session.id)
        session.status = "error"
        await db.commit()
        yield _sse("error", {"message": LLM_ERROR_MESSAGE})
        return

    message = await _persist_assistant_message(
        db,
        session,
        "".join(collected),
        usage["prompt_tokens"],
        usage["completion_tokens"],
    )
    yield _sse(
        "usage",
        {
            "model": model,
            "prompt_tokens": usage["prompt_tokens"],
            "completion_tokens": usage["completion_tokens"],
            "session_tokens_total": session.tokens_used,
        },
    )
    yield _sse(
        "done",
        {
            "session_id": session.id,
            "message_id": message.id,
            "capped": False,
            "searches_left": await _searches_left(db, session.user_id),
        },
    )


async def _event_stream(
    events: AsyncGenerator[tuple[str, dict[str, Any]], None],
) -> AsyncGenerator[str, None]:
    """Serialize agent-cycle (event, data) pairs into SSE frames."""
    async for event, data in events:
        yield _sse(event, data)


async def _agent_json_reply(
    db: AsyncSession, session: ChatSession, content: str
) -> dict:
    """JSON mode (tests/CLI): drain the agent cycle into one payload."""
    tokens: list[str] = []
    usage: dict | None = None
    done: dict | None = None
    error_message: str | None = None
    capped = False
    paywall = False
    async for event, data in run_agent_cycle(db, session, content):
        if event == "token":
            tokens.append(data["text"])
        elif event == "usage":
            usage = data
        elif event == "done":
            done = data
        elif event == "capped":
            capped = True
        elif event == "paywall":
            paywall = True
        elif event == "error":
            error_message = data["message"]

    if error_message is not None:
        raise HTTPException(status_code=502, detail=error_message)
    assert done is not None  # the cycle always terminates with done or error

    result = await db.execute(
        select(ChatMessage).where(ChatMessage.id == done["message_id"])
    )
    message = result.scalar_one()
    payload: dict[str, Any] = {
        "session_id": session.id,
        "message": _message_dict(message),
        "usage": usage,
        "capped": capped,
        "searches_left": done["searches_left"],
    }
    if paywall:
        payload["paywall"] = True
    return payload


@router.post("/sessions/{session_id}/messages")
async def post_message(
    session_id: int,
    body: MessageIn,
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    session = await _get_owned_session(db, session_id, current_user.id)
    wants_sse = "text/event-stream" in request.headers.get("accept", "")

    # Agent mode (M2): the cycle owns user-message persistence, budget/token
    # caps, paywall, charging and the tool-calling loop.
    if get_settings().jroots_mcp_enabled:
        if wants_sse:
            return StreamingResponse(
                _event_stream(run_agent_cycle(db, session, body.content)),
                media_type="text/event-stream",
            )
        return await _agent_json_reply(db, session, body.content)

    # Persist the user message first so it survives a failed/capped reply.
    db.add(ChatMessage(session_id=session.id, role=_ROLE_USER, content=body.content))
    await db.commit()

    if session.is_free and await llm_router.is_daily_budget_exceeded(db):
        if not wants_sse:
            raise HTTPException(
                status_code=429, detail=llm_router.DAILY_BUDGET_EXCEEDED_MESSAGE
            )

        # SSE: report the cap in-band so the client renders a graceful stop.
        async def budget_stream() -> AsyncGenerator[str, None]:
            yield _sse("capped", {"reason": "daily_budget"})
            yield _sse("token", {"text": llm_router.DAILY_BUDGET_EXCEEDED_MESSAGE})
            message = await _persist_assistant_message(
                db, session, llm_router.DAILY_BUDGET_EXCEEDED_MESSAGE, 0, 0
            )
            yield _sse(
                "done",
                {
                    "session_id": session.id,
                    "message_id": message.id,
                    "capped": True,
                    "searches_left": await _searches_left(db, session.user_id),
                },
            )

        return StreamingResponse(budget_stream(), media_type="text/event-stream")

    if wants_sse:
        return StreamingResponse(
            _stream_reply(db, session), media_type="text/event-stream"
        )

    # JSON mode (tests/CLI): drain the SSE generator and return one payload.
    tokens: list[str] = []
    final: dict = {}
    error_message: str | None = None
    capped = False
    async for frame in _stream_reply(db, session):
        event = frame.split("\n", 1)[0].removeprefix("event: ").strip()
        data = json.loads(frame.split("data: ", 1)[1])
        if event == "token":
            tokens.append(data["text"])
        elif event == "capped":
            capped = True
        elif event == "usage":
            final["usage"] = data
        elif event == "done":
            final["done"] = data
        elif event == "error":
            error_message = data["message"]

    if error_message is not None:
        raise HTTPException(status_code=502, detail=error_message)

    done = final["done"]
    result = await db.execute(
        select(ChatMessage).where(ChatMessage.id == done["message_id"])
    )
    message = result.scalar_one()
    return {
        "session_id": session.id,
        "message": _message_dict(message),
        "usage": final.get("usage"),
        "capped": capped,
    }
