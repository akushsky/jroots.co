"""Detach chat agent cycles from the SSE HTTP lifetime.

The producer runs in an asyncio task with its own DB session and publishes
(event, data) pairs onto a queue. The SSE consumer only reads the queue; when
the client disconnects the consumer is cancelled but the producer keeps going
and still persists the assistant reply.
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import AsyncGenerator
from typing import Any

from sqlalchemy import select

from app.database import AsyncSessionLocal
from app.models import ChatSession
from app.services.agent_loop import run_agent_cycle

logger = logging.getLogger("jroots")

GENERIC_ERROR_MESSAGE = "Ошибка, попробуйте ещё раз."
GENERATING_STATUS = "generating"
GENERATING_MESSAGE = "Ответ ещё готовится"

# Strong refs so background tasks are not garbage-collected mid-run.
_active_jobs: dict[int, asyncio.Task[None]] = {}


async def _mark_session_status(session_id: int, status: str) -> None:
    try:
        async with AsyncSessionLocal() as db:
            result = await db.execute(
                select(ChatSession).where(ChatSession.id == session_id)
            )
            session = result.scalar_one_or_none()
            if session is None:
                return
            session.status = status
            await db.commit()
    except Exception:
        logger.exception(
            "Failed to set session %d status=%s after detached agent job",
            session_id,
            status,
        )


async def _run_agent_job(
    session_id: int,
    content: str,
    scan_ids: list[int] | None,
    queue: asyncio.Queue[tuple[str, dict[str, Any]] | None],
) -> None:
    """Drain one agent cycle into `queue`, then send a None sentinel."""
    try:
        async with AsyncSessionLocal() as db:
            result = await db.execute(
                select(ChatSession).where(ChatSession.id == session_id)
            )
            session = result.scalar_one()
            try:
                async for event, data in run_agent_cycle(
                    db, session, content, scan_ids=scan_ids
                ):
                    await queue.put((event, data))
            except Exception:
                logger.exception("Agent cycle crashed for session %d", session_id)
                try:
                    await db.rollback()
                except Exception:
                    logger.exception(
                        "Rollback after agent crash failed for session %d", session_id
                    )
                try:
                    session.status = "error"
                    await db.commit()
                except Exception:
                    logger.exception(
                        "Failed to flag session %d error on job DB session", session_id
                    )
                    await _mark_session_status(session_id, "error")
                await queue.put(("error", {"message": GENERIC_ERROR_MESSAGE}))
            finally:
                try:
                    await db.refresh(session)
                    if session.status == GENERATING_STATUS:
                        session.status = "error"
                        await db.commit()
                except Exception:
                    await _mark_session_status(session_id, "error")
    except Exception:
        logger.exception(
            "Detached agent job failed to open DB for session %d", session_id
        )
        await _mark_session_status(session_id, "error")
        await queue.put(("error", {"message": GENERIC_ERROR_MESSAGE}))
    finally:
        await queue.put(None)


def start_agent_job(
    session_id: int,
    content: str,
    scan_ids: list[int] | None = None,
) -> asyncio.Queue[tuple[str, dict[str, Any]] | None]:
    """Schedule a detached agent cycle; return the event queue for SSE."""
    queue: asyncio.Queue[tuple[str, dict[str, Any]] | None] = asyncio.Queue()
    task = asyncio.create_task(
        _run_agent_job(session_id, content, scan_ids, queue),
        name=f"chat-agent-{session_id}",
    )
    _active_jobs[session_id] = task

    def _clear(done: asyncio.Task[None], sid: int = session_id) -> None:
        _active_jobs.pop(sid, None)
        if done.cancelled():
            return
        exc = done.exception()
        if exc is not None:
            logger.error(
                "Detached agent job for session %d raised: %s", sid, exc, exc_info=exc
            )

    task.add_done_callback(_clear)
    return queue


async def iter_agent_queue(
    queue: asyncio.Queue[tuple[str, dict[str, Any]] | None],
) -> AsyncGenerator[tuple[str, dict[str, Any]], None]:
    """Yield (event, data) from the producer queue until the sentinel.

    CancelledError from the SSE consumer must not cancel the producer — this
    generator intentionally does not hold a task handle to cancel.
    """
    while True:
        item = await queue.get()
        if item is None:
            break
        yield item
