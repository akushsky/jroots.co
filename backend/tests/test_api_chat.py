import json
from datetime import date
from decimal import Decimal
from types import SimpleNamespace

import pytest
from sqlalchemy import select

from app.config import get_settings
from app.models import ChatMessage, ChatSession, DailyBudget, Payment
from app.services import llm_router
from tests.conftest import auth_header, create_user


def _chunk(text=None, usage=None):
    delta = SimpleNamespace(content=text)
    choices = [SimpleNamespace(delta=delta)] if text else []
    return SimpleNamespace(choices=choices, usage=usage)


class _FakeCompletions:
    def __init__(self, chunks=None, error=None):
        self._chunks = chunks or []
        self._error = error

    async def create(self, **kwargs):
        if self._error is not None:
            raise self._error

        async def gen():
            for chunk in self._chunks:
                yield chunk

        return gen()


class _FakeClient:
    def __init__(self, chunks=None, error=None):
        self.chat = SimpleNamespace(completions=_FakeCompletions(chunks, error))


@pytest.fixture
def fake_llm(monkeypatch):
    def install(texts=("Привет", " ответ"), usage=(10, 5), error=None):
        chunks = [_chunk(t) for t in texts]
        if usage is not None:
            chunks.append(
                _chunk(
                    usage=SimpleNamespace(
                        prompt_tokens=usage[0], completion_tokens=usage[1]
                    )
                )
            )
        client = _FakeClient(chunks, error)
        monkeypatch.setattr(llm_router, "_client", client)
        return client

    yield install
    monkeypatch.setattr(llm_router, "_client", None)


def _parse_sse(body: str):
    """Parse an SSE body into an ordered list of (event, data) pairs."""
    frames = []
    for block in body.strip().split("\n\n"):
        event = data = None
        for line in block.splitlines():
            if line.startswith("event: "):
                event = line[len("event: ") :]
            elif line.startswith("data: "):
                data = json.loads(line[len("data: ") :])
        frames.append((event, data))
    return frames


async def _create_session(client, user):
    response = await client.post("/api/chat/sessions", headers=auth_header(user))
    assert response.status_code == 201
    return response.json()


async def test_create_session_free_flag(client, db_session):
    user = await create_user(db_session, email="chat-free@example.com")
    payload = await _create_session(client, user)
    assert payload["is_free"] is True
    assert payload["status"] == "open"
    assert payload["model_main"] == get_settings().llm_model_main
    assert payload["tokens_used"] == 0


async def test_create_session_paid_user(client, db_session):
    user = await create_user(db_session, email="chat-paid@example.com")
    db_session.add(
        Payment(
            provider="stripe",
            provider_payment_id="pay-1",
            user_id=user.id,
            status="succeeded",
        )
    )
    await db_session.commit()
    payload = await _create_session(client, user)
    assert payload["is_free"] is False


async def test_create_session_requires_auth(client):
    response = await client.post("/api/chat/sessions")
    assert response.status_code == 401


async def test_free_session_rate_limit(client, db_session):
    user = await create_user(db_session, email="chat-limit@example.com")
    await _create_session(client, user)
    await _create_session(client, user)

    response = await client.post("/api/chat/sessions", headers=auth_header(user))
    assert response.status_code == 429
    assert "сессий" in response.json()["detail"].lower()


async def test_daily_budget_blocks_session_create(client, db_session):
    user = await create_user(db_session, email="chat-budget@example.com")
    db_session.add(DailyBudget(day=date.today(), free_spend_usd=Decimal("999.0")))
    await db_session.commit()

    response = await client.post("/api/chat/sessions", headers=auth_header(user))
    assert response.status_code == 429
    assert "лимит" in response.json()["detail"].lower()


async def test_message_json_happy_path(client, db_session, fake_llm):
    fake_llm(texts=("Найдено", " две записи"), usage=(10, 5))
    user = await create_user(db_session, email="chat-msg@example.com")
    session = await _create_session(client, user)

    response = await client.post(
        f"/api/chat/sessions/{session['id']}/messages",
        json={"content": "Ищу Кацнельсона в Клинцах"},
        headers=auth_header(user),
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["capped"] is False
    assert payload["message"]["role"] == "assistant"
    assert payload["message"]["content"] == "Найдено две записи"
    assert payload["message"]["tokens"] == 15
    assert payload["usage"]["model"] == get_settings().llm_model_main
    assert payload["usage"]["session_tokens_total"] == 15

    result = await db_session.execute(
        select(ChatSession).where(ChatSession.id == session["id"])
    )
    assert result.scalar_one().tokens_used == 15

    messages = (
        (
            await db_session.execute(
                select(ChatMessage)
                .where(ChatMessage.session_id == session["id"])
                .order_by(ChatMessage.id)
            )
        )
        .scalars()
        .all()
    )
    assert [m.role for m in messages] == ["user", "assistant"]
    assert messages[0].content == "Ищу Кацнельсона в Клинцах"


async def test_message_sse_contract(client, db_session, fake_llm):
    fake_llm(texts=("Раз", " два"), usage=(8, 4))
    user = await create_user(db_session, email="chat-sse@example.com")
    session = await _create_session(client, user)

    response = await client.post(
        f"/api/chat/sessions/{session['id']}/messages",
        json={"content": "привет"},
        headers={**auth_header(user), "Accept": "text/event-stream"},
    )
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/event-stream")

    frames = _parse_sse(response.text)
    events = [event for event, _ in frames]
    assert events == ["token", "token", "usage", "done"]

    assert frames[0][1] == {"text": "Раз"}
    assert frames[1][1] == {"text": " два"}

    usage = frames[2][1]
    assert usage["model"] == get_settings().llm_model_main
    assert usage["prompt_tokens"] == 8
    assert usage["completion_tokens"] == 4
    assert usage["session_tokens_total"] == 12

    done = frames[3][1]
    assert done["session_id"] == session["id"]
    assert done["capped"] is False
    result = await db_session.execute(
        select(ChatMessage).where(ChatMessage.id == done["message_id"])
    )
    assert result.scalar_one().content == "Раз два"


async def test_token_cap_graceful_stop(client, db_session, fake_llm, monkeypatch):
    settings = get_settings()
    monkeypatch.setattr(settings, "llm_token_cap_per_session", 100)
    user = await create_user(db_session, email="chat-cap@example.com")
    session = await _create_session(client, user)
    db_session.add(ChatMessage(session_id=session["id"], role="user", content="old"))
    capped_session = (
        await db_session.execute(
            select(ChatSession).where(ChatSession.id == session["id"])
        )
    ).scalar_one()
    capped_session.tokens_used = 150
    await db_session.commit()

    response = await client.post(
        f"/api/chat/sessions/{session['id']}/messages",
        json={"content": "продолжаем"},
        headers={**auth_header(user), "Accept": "text/event-stream"},
    )
    frames = _parse_sse(response.text)
    events = [event for event, _ in frames]
    assert events == ["capped", "token", "done"]
    assert frames[0][1] == {"reason": "token_cap"}
    assert frames[1][1]["text"] == llm_router.GRACEFUL_STOP_MESSAGE
    assert frames[2][1]["capped"] is True

    # The graceful-stop reply is persisted as the assistant message.
    messages = (
        (
            await db_session.execute(
                select(ChatMessage).where(
                    ChatMessage.session_id == session["id"],
                    ChatMessage.role == "assistant",
                )
            )
        )
        .scalars()
        .all()
    )
    assert messages[-1].content == llm_router.GRACEFUL_STOP_MESSAGE


async def test_token_cap_json_mode_returns_capped(
    client, db_session, fake_llm, monkeypatch
):
    settings = get_settings()
    monkeypatch.setattr(settings, "llm_token_cap_per_session", 100)
    user = await create_user(db_session, email="chat-cap-json@example.com")
    session = await _create_session(client, user)
    capped_session = (
        await db_session.execute(
            select(ChatSession).where(ChatSession.id == session["id"])
        )
    ).scalar_one()
    capped_session.tokens_used = 150
    await db_session.commit()

    response = await client.post(
        f"/api/chat/sessions/{session['id']}/messages",
        json={"content": "продолжаем"},
        headers=auth_header(user),
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["capped"] is True
    assert payload["message"]["content"] == llm_router.GRACEFUL_STOP_MESSAGE


async def test_foreign_session_is_404(client, db_session, fake_llm):
    fake_llm()
    owner = await create_user(db_session, email="chat-owner@example.com")
    other = await create_user(db_session, email="chat-other@example.com")
    session = await _create_session(client, owner)

    for response in (
        await client.get(
            f"/api/chat/sessions/{session['id']}", headers=auth_header(other)
        ),
        await client.post(
            f"/api/chat/sessions/{session['id']}/messages",
            json={"content": "чужое"},
            headers=auth_header(other),
        ),
    ):
        assert response.status_code == 404


async def test_llm_error_emits_error_event(client, db_session, fake_llm):
    fake_llm(error=RuntimeError("timeout to https://api.moonshot.ai/v1 req-123"))
    user = await create_user(db_session, email="chat-err@example.com")
    session = await _create_session(client, user)

    response = await client.post(
        f"/api/chat/sessions/{session['id']}/messages",
        json={"content": "привет"},
        headers={**auth_header(user), "Accept": "text/event-stream"},
    )
    frames = _parse_sse(response.text)
    assert frames[-1][0] == "error"
    # Static client-facing message — no provider internals (URLs, request ids).
    assert frames[-1][1] == {"message": "Ошибка модели, попробуйте ещё раз."}

    result = await db_session.execute(
        select(ChatSession).where(ChatSession.id == session["id"])
    )
    assert result.scalar_one().status == "error"


async def test_session_recovers_to_open_after_error(client, db_session, fake_llm):
    user = await create_user(db_session, email="chat-recover@example.com")
    session = await _create_session(client, user)

    fake_llm(error=RuntimeError("boom"))
    response = await client.post(
        f"/api/chat/sessions/{session['id']}/messages",
        json={"content": "привет"},
        headers={**auth_header(user), "Accept": "text/event-stream"},
    )
    assert _parse_sse(response.text)[-1][0] == "error"

    fake_llm(texts=("всё работает",), usage=(3, 2), error=None)
    response = await client.post(
        f"/api/chat/sessions/{session['id']}/messages",
        json={"content": "ещё раз"},
        headers=auth_header(user),
    )
    assert response.status_code == 200
    assert response.json()["capped"] is False

    result = await db_session.execute(
        select(ChatSession).where(ChatSession.id == session["id"])
    )
    assert result.scalar_one().status == "open"


async def test_daily_budget_sse_uses_budget_message(client, db_session, fake_llm):
    fake_llm()
    user = await create_user(db_session, email="chat-budget-sse@example.com")
    session = await _create_session(client, user)
    # Budget exhausts between session creation and the next message.
    db_session.add(DailyBudget(day=date.today(), free_spend_usd=Decimal("999.0")))
    await db_session.commit()

    response = await client.post(
        f"/api/chat/sessions/{session['id']}/messages",
        json={"content": "привет"},
        headers={**auth_header(user), "Accept": "text/event-stream"},
    )
    frames = _parse_sse(response.text)
    assert [event for event, _ in frames] == ["capped", "token", "done"]
    assert frames[0][1] == {"reason": "daily_budget"}
    assert frames[1][1]["text"] == llm_router.DAILY_BUDGET_EXCEEDED_MESSAGE
    assert frames[1][1]["text"] != llm_router.GRACEFUL_STOP_MESSAGE
    assert frames[2][1]["capped"] is True


async def test_llm_error_json_mode_returns_502(client, db_session, fake_llm):
    fake_llm(error=RuntimeError("boom"))
    user = await create_user(db_session, email="chat-err-json@example.com")
    session = await _create_session(client, user)

    response = await client.post(
        f"/api/chat/sessions/{session['id']}/messages",
        json={"content": "привет"},
        headers=auth_header(user),
    )
    assert response.status_code == 502


async def test_free_session_spend_recorded(client, db_session, fake_llm):
    fake_llm(texts=("ответ",), usage=(1_000_000, 500_000))
    user = await create_user(db_session, email="chat-spend@example.com")
    session = await _create_session(client, user)

    response = await client.post(
        f"/api/chat/sessions/{session['id']}/messages",
        json={"content": "привет"},
        headers=auth_header(user),
    )
    assert response.status_code == 200

    result = await db_session.execute(
        select(DailyBudget).where(DailyBudget.day == date.today())
    )
    spend = result.scalar_one().free_spend_usd
    # 1M in * 0.95 + 0.5M out * 4.0 = 2.95 USD
    assert spend == Decimal("2.95")


async def test_paid_session_does_not_touch_budget(client, db_session, fake_llm):
    fake_llm(texts=("ответ",), usage=(1000, 500))
    user = await create_user(db_session, email="chat-nospend@example.com")
    db_session.add(
        Payment(
            provider="stripe",
            provider_payment_id="pay-2",
            user_id=user.id,
            status="succeeded",
        )
    )
    await db_session.commit()
    session = await _create_session(client, user)

    response = await client.post(
        f"/api/chat/sessions/{session['id']}/messages",
        json={"content": "привет"},
        headers=auth_header(user),
    )
    assert response.status_code == 200
    assert await llm_router.get_daily_free_spend(db_session) == Decimal("0")


async def test_get_session_with_messages(client, db_session, fake_llm):
    fake_llm(texts=("ответ",), usage=(3, 2))
    user = await create_user(db_session, email="chat-get@example.com")
    session = await _create_session(client, user)
    await client.post(
        f"/api/chat/sessions/{session['id']}/messages",
        json={"content": "привет"},
        headers=auth_header(user),
    )

    response = await client.get(
        f"/api/chat/sessions/{session['id']}", headers=auth_header(user)
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["id"] == session["id"]
    assert [m["role"] for m in payload["messages"]] == ["user", "assistant"]


async def test_list_sessions_returns_last_message(client, db_session, fake_llm):
    fake_llm(texts=("последний ответ",), usage=(3, 2))
    user = await create_user(db_session, email="chat-list@example.com")
    session = await _create_session(client, user)
    await client.post(
        f"/api/chat/sessions/{session['id']}/messages",
        json={"content": "привет"},
        headers=auth_header(user),
    )

    response = await client.get("/api/chat/sessions", headers=auth_header(user))
    assert response.status_code == 200
    sessions = response.json()
    assert len(sessions) == 1
    assert sessions[0]["id"] == session["id"]
    assert sessions[0]["status"] == "open"
    assert sessions[0]["model_main"] == get_settings().llm_model_main
    # last_message is a plain string (frontend calls .trim() on it).
    assert sessions[0]["last_message"] == "последний ответ"
    assert sessions[0]["title"] == "привет"


async def test_whitespace_only_message_rejected(client, db_session, fake_llm):
    fake_llm()
    user = await create_user(db_session, email="chat-blank@example.com")
    session = await _create_session(client, user)

    response = await client.post(
        f"/api/chat/sessions/{session['id']}/messages",
        json={"content": "   \n\t  "},
        headers=auth_header(user),
    )
    assert response.status_code == 422

    # Nothing was persisted for the rejected message.
    messages = (
        (
            await db_session.execute(
                select(ChatMessage).where(ChatMessage.session_id == session["id"])
            )
        )
        .scalars()
        .all()
    )
    assert messages == []


async def test_message_content_is_stripped(client, db_session, fake_llm):
    fake_llm(texts=("ответ",), usage=(3, 2))
    user = await create_user(db_session, email="chat-strip@example.com")
    session = await _create_session(client, user)

    response = await client.post(
        f"/api/chat/sessions/{session['id']}/messages",
        json={"content": "  привет  "},
        headers=auth_header(user),
    )
    assert response.status_code == 200
    result = await db_session.execute(
        select(ChatMessage).where(
            ChatMessage.session_id == session["id"], ChatMessage.role == "user"
        )
    )
    assert result.scalar_one().content == "привет"


async def test_list_sessions_title_from_first_user_message(
    client, db_session, fake_llm
):
    fake_llm(texts=("ответ",), usage=(3, 2))
    user = await create_user(db_session, email="chat-title@example.com")
    session = await _create_session(client, user)
    long_question = "Ищу метрики " + "очень " * 30 + "длинный запрос"
    await client.post(
        f"/api/chat/sessions/{session['id']}/messages",
        json={"content": long_question},
        headers=auth_header(user),
    )
    await client.post(
        f"/api/chat/sessions/{session['id']}/messages",
        json={"content": "второе сообщение"},
        headers=auth_header(user),
    )

    sessions = (
        await client.get("/api/chat/sessions", headers=auth_header(user))
    ).json()
    title = sessions[0]["title"]
    # First user message, truncated to 80 chars + ellipsis.
    assert title == long_question[:80] + "…"


async def test_list_sessions_title_default_without_messages(client, db_session):
    user = await create_user(db_session, email="chat-notitle@example.com")
    await _create_session(client, user)

    sessions = (
        await client.get("/api/chat/sessions", headers=auth_header(user))
    ).json()
    assert sessions[0]["title"] == "Новый поиск"


async def test_timestamps_carry_utc_offset(client, db_session, fake_llm):
    fake_llm(texts=("ответ",), usage=(3, 2))
    user = await create_user(db_session, email="chat-tz@example.com")
    session = await _create_session(client, user)
    assert session["created_at"].endswith("+00:00")

    response = await client.post(
        f"/api/chat/sessions/{session['id']}/messages",
        json={"content": "привет"},
        headers=auth_header(user),
    )
    assert response.json()["message"]["created_at"].endswith("+00:00")

    payload = (
        await client.get(
            f"/api/chat/sessions/{session['id']}", headers=auth_header(user)
        )
    ).json()
    assert payload["created_at"].endswith("+00:00")
    for message in payload["messages"]:
        assert message["created_at"].endswith("+00:00")
