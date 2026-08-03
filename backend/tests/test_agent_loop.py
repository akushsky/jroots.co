"""End-to-end agent-cycle tests: HTTP API + mocked MCP transport + mocked LLM."""

from types import SimpleNamespace

import pytest
from sqlalchemy import select

from app.config import get_settings
from app.models import (
    ChatMessage,
    ChatSession,
    Credit,
    CreditTransaction,
    Payment,
    Search,
)
from app.services import llm_router
from app.services import mcp_client as mcp_client_module
from app.services.agent_loop import (
    LLM_ERROR_MESSAGE,
    MCP_ERROR_MESSAGE,
    PAYWALL_MESSAGE,
)
from app.services.mcp_client import (
    TOOL_CALL_LIMIT_MESSAGE,
    McpArchiveClient,
    McpCallResult,
)
from tests.conftest import auth_header, create_user
from tests.test_api_chat import _parse_sse
from tests.test_mcp_client import FakeTransport


def _chunk(text=None, usage=None, tool_calls=None):
    delta = SimpleNamespace(content=text, tool_calls=tool_calls)
    choices = [SimpleNamespace(delta=delta)] if (text or tool_calls) else []
    return SimpleNamespace(choices=choices, usage=usage)


def _tc(index, call_id=None, name=None, arguments=None):
    return SimpleNamespace(
        index=index,
        id=call_id,
        function=SimpleNamespace(name=name, arguments=arguments),
    )


def _usage(prompt, completion):
    return SimpleNamespace(prompt_tokens=prompt, completion_tokens=completion)


def _tool_round(call_id, name, argument_parts, usage=(100, 20)):
    """One LLM round that ends in a tool call (args streamed in chunks)."""
    chunks = []
    for i, part in enumerate(argument_parts):
        chunks.append(
            _chunk(
                tool_calls=[
                    _tc(0, call_id if i == 0 else None, name if i == 0 else None, part)
                ]
            )
        )
    chunks.append(_chunk(usage=_usage(*usage)))
    return chunks


class _ScriptedCompletions:
    """OpenAI-client double: each create() consumes the next scripted round."""

    def __init__(self, scripts):
        self._scripts = list(scripts)
        self.calls = []

    async def create(self, **kwargs):
        self.calls.append(kwargs)
        script = self._scripts.pop(0)
        if isinstance(script, Exception):
            raise script

        async def gen():
            for chunk in script:
                yield chunk

        return gen()


class _ScriptedClient:
    def __init__(self, scripts):
        self.chat = SimpleNamespace(completions=_ScriptedCompletions(scripts))


@pytest.fixture
def agent_mode(monkeypatch):
    settings = get_settings()
    monkeypatch.setattr(settings, "jroots_mcp_enabled", True)
    return settings


@pytest.fixture
def fake_llm(monkeypatch):
    def install(scripts):
        client = _ScriptedClient(scripts)
        monkeypatch.setattr(llm_router, "_client", client)
        return client

    yield install
    monkeypatch.setattr(llm_router, "_client", None)


@pytest.fixture
def fake_mcp(monkeypatch):
    """Swap build_mcp_client for a real McpArchiveClient over FakeTransport."""

    def install(transport, max_calls=15):
        holder = {}

        def factory(*, session_id, user_id, initial_used=0):
            client = McpArchiveClient(
                transport,
                session_id=session_id,
                user_id=user_id,
                initial_used=initial_used,
                max_calls=max_calls,
                rate_limit_interval=0,
            )
            holder["client"] = client
            return client

        monkeypatch.setattr(mcp_client_module, "build_mcp_client", factory)
        return holder

    return install


async def _create_session(client, user):
    response = await client.post("/api/chat/sessions", headers=auth_header(user))
    assert response.status_code == 201
    return response.json()


async def _give_credits(db_session, user, searches=5):
    db_session.add(Credit(user_id=user.id, searches_left=searches, scans_left=0))
    await db_session.commit()


async def _post_sse(client, user, session_id, content):
    response = await client.post(
        f"/api/chat/sessions/{session_id}/messages",
        json={"content": content},
        headers={**auth_header(user), "Accept": "text/event-stream"},
    )
    assert response.status_code == 200
    return _parse_sse(response.text)


async def _searches(db_session, session_id):
    result = await db_session.execute(
        select(Search).where(Search.session_id == session_id)
    )
    return result.scalars().all()


async def _session_row(db_session, session_id):
    result = await db_session.execute(
        select(ChatSession).where(ChatSession.id == session_id)
    )
    return result.scalar_one()


async def test_agent_full_cycle_charges_one_search(
    client, db_session, agent_mode, fake_llm, fake_mcp
):
    transport = FakeTransport(
        script=[
            McpCallResult(
                text="Найдено 2 записи:\n1. Метрическая книга, Клинцы, 1890\n"
                "2. Ревизская сказка, 1858"
            )
        ]
    )
    holder = fake_mcp(transport)
    llm_client = fake_llm(
        [
            _tool_round(
                "call_1",
                "search",
                ['{"database": "gabo", ', '"last_name": "Фалькович"}'],
                usage=(100, 20),
            ),
            [
                _chunk("Нашёл две записи"),
                _chunk(" по Клинцам."),
                _chunk(usage=_usage(200, 30)),
            ],
        ]
    )
    user = await create_user(db_session, email="agent-full@example.com")
    await _give_credits(db_session, user, searches=5)
    session = await _create_session(client, user)

    frames = await _post_sse(
        client, user, session["id"], "Ищу Шмуила Фальковича в Клинцах"
    )
    events = [event for event, _ in frames]
    # The teaser redactor emits text with a one-word lag + a flushed tail,
    # so the two LLM deltas arrive as three token events.
    assert events == ["token", "token", "token", "usage", "done"]
    streamed = "".join(data["text"] for event, data in frames if event == "token")
    assert streamed == "Нашёл две записи по Клинцам."

    usage = frames[3][1]
    assert usage["prompt_tokens"] == 300
    assert usage["completion_tokens"] == 50
    assert usage["session_tokens_total"] == 350

    done = frames[4][1]
    assert done["capped"] is False
    assert done["searches_left"] == 4

    # The search was journaled and charged.
    rows = await _searches(db_session, session["id"])
    assert len(rows) == 1
    row = rows[0]
    assert row.charged is True
    assert row.results_count == 1
    assert row.query_summary == "Ищу Шмуила Фальковича в Клинцах"

    credit = (
        await db_session.execute(select(Credit).where(Credit.user_id == user.id))
    ).scalar_one()
    assert credit.searches_left == 4

    txn = (
        await db_session.execute(
            select(CreditTransaction).where(CreditTransaction.user_id == user.id)
        )
    ).scalar_one()
    assert txn.delta_searches == -1
    assert txn.reason == "usage"
    assert txn.ref_id == f"search:{row.id}"

    session_row = await _session_row(db_session, session["id"])
    assert session_row.tool_calls == 1
    assert session_row.status == "open"

    # The tool schema went to the model; the tool result went back to it.
    first_call = llm_client.chat.completions.calls[0]
    tool_names = [t["function"]["name"] for t in first_call["tools"]]
    assert tool_names == [
        "search",
        "get_record",
        "list_databases",
        "generate_surname_variants",
    ]
    second_call = llm_client.chat.completions.calls[1]
    tool_messages = [m for m in second_call["messages"] if m["role"] == "tool"]
    assert len(tool_messages) == 1
    assert tool_messages[0]["tool_call_id"] == "call_1"
    assert "Метрическая книга" in tool_messages[0]["content"]

    # The transport saw the reassembled JSON arguments.
    assert transport.calls[0][0] == "search"
    assert transport.calls[0][1] == {"database": "gabo", "last_name": "Фалькович"}
    assert holder["client"].calls_used == 1


async def test_agent_mcp_unavailable_is_error_and_not_charged(
    client, db_session, agent_mode, fake_llm, fake_mcp
):
    transport = FakeTransport(connect_error=ConnectionError("refused"))
    fake_mcp(transport)
    llm_client = fake_llm([])
    user = await create_user(db_session, email="agent-down@example.com")
    await _give_credits(db_session, user, searches=5)
    session = await _create_session(client, user)

    frames = await _post_sse(client, user, session["id"], "привет")
    assert frames[-1] == ("error", {"message": MCP_ERROR_MESSAGE})

    # LLM was never called, credit untouched, nothing journaled.
    assert llm_client.chat.completions.calls == []
    credit = (
        await db_session.execute(select(Credit).where(Credit.user_id == user.id))
    ).scalar_one()
    assert credit.searches_left == 5
    assert await _searches(db_session, session["id"]) == []

    session_row = await _session_row(db_session, session["id"])
    assert session_row.status == "error"
    # The user message survived the failure.
    roles = [
        m.role
        for m in (
            await db_session.execute(
                select(ChatMessage).where(ChatMessage.session_id == session["id"])
            )
        )
        .scalars()
        .all()
    ]
    assert roles == ["user"]


async def test_agent_llm_failure_mid_cycle_is_error_and_not_charged(
    client, db_session, agent_mode, fake_llm, fake_mcp
):
    transport = FakeTransport(script=[McpCallResult(text="Найдено 1 запись")])
    fake_mcp(transport)
    fake_llm(
        [
            _tool_round("call_1", "search", ['{"database": "gabo"}']),
            RuntimeError("boom"),
        ]
    )
    user = await create_user(db_session, email="agent-llmerr@example.com")
    await _give_credits(db_session, user, searches=5)
    session = await _create_session(client, user)

    frames = await _post_sse(client, user, session["id"], "ищем")
    assert frames[-1] == ("error", {"message": LLM_ERROR_MESSAGE})

    credit = (
        await db_session.execute(select(Credit).where(Credit.user_id == user.id))
    ).scalar_one()
    assert credit.searches_left == 5
    assert await _searches(db_session, session["id"]) == []

    session_row = await _session_row(db_session, session["id"])
    assert session_row.status == "error"
    # The one executed tool call is still accounted for.
    assert session_row.tool_calls == 1


async def test_agent_paywall_when_no_credits(
    client, db_session, agent_mode, fake_llm, fake_mcp
):
    transport = FakeTransport()
    holder = fake_mcp(transport)
    llm_client = fake_llm([])
    user = await create_user(db_session, email="agent-paywall@example.com")
    await _give_credits(db_session, user, searches=0)
    session = await _create_session(client, user)

    frames = await _post_sse(client, user, session["id"], "ищу прадеда")
    events = [event for event, _ in frames]
    assert events == ["paywall", "token", "done"]
    assert frames[0][1] == {"searches_left": 0}
    assert frames[1][1]["text"] == PAYWALL_MESSAGE
    assert frames[2][1]["searches_left"] == 0

    # Neither the LLM nor the MCP client was touched.
    assert llm_client.chat.completions.calls == []
    assert holder == {}
    assert await _searches(db_session, session["id"]) == []

    # The paywall notice is persisted as the assistant reply.
    message = (
        await db_session.execute(
            select(ChatMessage).where(
                ChatMessage.session_id == session["id"],
                ChatMessage.role == "assistant",
            )
        )
    ).scalar_one()
    assert message.content == PAYWALL_MESSAGE


async def test_agent_teaser_stream_is_redacted(
    client, db_session, agent_mode, fake_llm, fake_mcp
):
    transport = FakeTransport(script=[McpCallResult(text="Найдено 1 запись")])
    fake_mcp(transport)
    fake_llm(
        [
            _tool_round("call_1", "search", ['{"database": "gabo"}']),
            [
                _chunk("Найдена запись: ф. "),
                _chunk("585 оп. 1 д"),
                _chunk(". 23, "),
                _chunk("https://arc"),
                _chunk("hive.ru/r/1 "),
                _chunk("конец"),
                _chunk(usage=_usage(50, 25)),
            ],
        ]
    )
    user = await create_user(db_session, email="agent-teaser@example.com")
    await _give_credits(db_session, user, searches=5)
    session = await _create_session(client, user)

    frames = await _post_sse(client, user, session["id"], "ищу")
    streamed = "".join(data["text"] for event, data in frames if event == "token")
    for leaked in ("585", "оп. 1", "д. 23", "https", "hive.ru"):
        assert leaked not in streamed
    assert "конец" in streamed
    assert "Найдена запись: " in streamed

    # The persisted reply is redacted too — otherwise GET /sessions would
    # leak the cipher on reload.
    message = (
        await db_session.execute(
            select(ChatMessage).where(
                ChatMessage.session_id == session["id"],
                ChatMessage.role == "assistant",
            )
        )
    ).scalar_one()
    assert "585" not in message.content
    assert "hive.ru" not in message.content
    assert "конец" in message.content


async def test_agent_full_tier_stream_is_not_redacted(
    client, db_session, agent_mode, fake_llm, fake_mcp
):
    transport = FakeTransport(script=[McpCallResult(text="Найдено 1 запись")])
    fake_mcp(transport)
    fake_llm(
        [
            _tool_round("call_1", "search", ['{"database": "gabo"}']),
            [
                _chunk("Запись ф. 585 оп. 1 д. 23, "),
                _chunk("https://archive.ru/r/1"),
                _chunk(usage=_usage(50, 25)),
            ],
        ]
    )
    user = await create_user(db_session, email="agent-paid@example.com")
    db_session.add(
        Payment(
            provider="stripe",
            provider_payment_id="pay-agent-1",
            user_id=user.id,
            status="succeeded",
        )
    )
    await db_session.commit()
    await _give_credits(db_session, user, searches=5)
    session = await _create_session(client, user)
    assert session["is_free"] is False

    frames = await _post_sse(client, user, session["id"], "ищу")
    streamed = "".join(data["text"] for event, data in frames if event == "token")
    assert "ф. 585 оп. 1 д. 23" in streamed
    assert "https://archive.ru/r/1" in streamed


async def test_agent_empty_searches_escalate_model(
    client, db_session, agent_mode, fake_llm, fake_mcp
):
    transport = FakeTransport(
        script=[
            McpCallResult(text="Ничего не найдено."),
            McpCallResult(text="Ничего не найдено."),
            McpCallResult(text="Ничего не найдено."),
        ]
    )
    fake_mcp(transport)
    llm_client = fake_llm(
        [
            _tool_round("c1", "search", ['{"database": "gabo", "last_name": "А"}']),
            _tool_round("c2", "search", ['{"database": "dako", "last_name": "А"}']),
            _tool_round("c3", "search", ['{"database": "niab", "last_name": "А"}']),
            [_chunk("Ничего не нашлось."), _chunk(usage=_usage(10, 5))],
        ]
    )
    user = await create_user(db_session, email="agent-esc@example.com")
    await _give_credits(db_session, user, searches=5)
    session = await _create_session(client, user)

    frames = await _post_sse(client, user, session["id"], "ищу Аграновича")
    assert frames[-1][0] == "done"

    settings = get_settings()
    models = [call["model"] for call in llm_client.chat.completions.calls]
    assert models[:3] == [settings.llm_model_main] * 3
    # Three empty searches escalated the fourth round.
    assert models[3] == settings.llm_model_escalation


async def test_agent_nothing_found_is_still_charged(
    client, db_session, agent_mode, fake_llm, fake_mcp
):
    transport = FakeTransport(script=[McpCallResult(text="Ничего не найдено.")])
    fake_mcp(transport)
    fake_llm(
        [
            _tool_round("c1", "search", ['{"database": "gabo"}']),
            [_chunk("К сожалению, ничего не нашлось."), _chunk(usage=_usage(10, 5))],
        ]
    )
    user = await create_user(db_session, email="agent-empty@example.com")
    await _give_credits(db_session, user, searches=5)
    session = await _create_session(client, user)

    frames = await _post_sse(client, user, session["id"], "ищу")
    assert frames[-1][1]["searches_left"] == 4

    rows = await _searches(db_session, session["id"])
    assert len(rows) == 1
    assert rows[0].charged is True
    assert rows[0].results_count == 0


async def test_agent_tool_cap_message_reaches_model(
    client, db_session, agent_mode, fake_llm, fake_mcp
):
    transport = FakeTransport(script=[McpCallResult(text="Найдено 1 запись")])
    fake_mcp(transport, max_calls=1)
    llm_client = fake_llm(
        [
            _tool_round("c1", "search", ['{"database": "gabo"}']),
            _tool_round("c2", "search", ['{"database": "dako"}']),
            [_chunk("Итог по найденному."), _chunk(usage=_usage(10, 5))],
        ]
    )
    user = await create_user(db_session, email="agent-cap@example.com")
    await _give_credits(db_session, user, searches=5)
    session = await _create_session(client, user)

    frames = await _post_sse(client, user, session["id"], "ищу")
    assert frames[-1][0] == "done"

    # The second search was capped before reaching the gateway...
    assert len(transport.calls) == 1
    # ...and the model saw the limit message as the tool result.
    final_round = llm_client.chat.completions.calls[2]
    tool_messages = [m for m in final_round["messages"] if m["role"] == "tool"]
    assert tool_messages[-1]["content"] == TOOL_CALL_LIMIT_MESSAGE


async def test_agent_json_mode_full_cycle(
    client, db_session, agent_mode, fake_llm, fake_mcp
):
    transport = FakeTransport(script=[McpCallResult(text="Найдено 1 запись")])
    fake_mcp(transport)
    fake_llm(
        [
            _tool_round("c1", "search", ['{"database": "gabo"}']),
            [_chunk("Ответ"), _chunk(usage=_usage(10, 5))],
        ]
    )
    user = await create_user(db_session, email="agent-json@example.com")
    await _give_credits(db_session, user, searches=5)
    session = await _create_session(client, user)

    response = await client.post(
        f"/api/chat/sessions/{session['id']}/messages",
        json={"content": "ищу"},
        headers=auth_header(user),
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["capped"] is False
    assert payload["searches_left"] == 4
    assert payload["message"]["content"] == "Ответ"
    # Tool round (100+20) + answer round (10+5).
    assert payload["usage"]["session_tokens_total"] == 135


async def test_legacy_done_carries_searches_left(client, db_session, fake_llm):
    # Legacy fallback path (JROOTS_MCP_ENABLED=false from conftest).
    fake_llm(
        [
            [
                _chunk("ответ"),
                _chunk(usage=_usage(3, 2)),
            ]
        ]
    )
    user = await create_user(db_session, email="agent-legacy@example.com")
    await _give_credits(db_session, user, searches=7)
    session = await _create_session(client, user)

    frames = await _post_sse(client, user, session["id"], "привет")
    done = frames[-1]
    assert done[0] == "done"
    assert done[1]["searches_left"] == 7


async def test_agent_cycle_without_tool_calls_is_free(
    client, db_session, agent_mode, fake_llm, fake_mcp
):
    # The model answers directly (clarifying question, small talk) — no real
    # MCP work, so no charge and no searches row.
    transport = FakeTransport()
    fake_mcp(transport)
    fake_llm(
        [
            [
                _chunk("Уточните год рождения деда."),
                _chunk(usage=_usage(10, 5)),
            ]
        ]
    )
    user = await create_user(db_session, email="agent-chat@example.com")
    await _give_credits(db_session, user, searches=5)
    session = await _create_session(client, user)

    frames = await _post_sse(client, user, session["id"], "ищу деда")
    events = [event for event, _ in frames]
    assert events[-2:] == ["usage", "done"]
    streamed = "".join(data["text"] for event, data in frames if event == "token")
    assert streamed == "Уточните год рождения деда."
    assert frames[-1][1]["searches_left"] == 5

    # Balance and journal untouched; the gateway never saw a call.
    assert transport.calls == []
    assert await _searches(db_session, session["id"]) == []
    credit = (
        await db_session.execute(select(Credit).where(Credit.user_id == user.id))
    ).scalar_one()
    assert credit.searches_left == 5
    txns = (
        (
            await db_session.execute(
                select(CreditTransaction).where(CreditTransaction.user_id == user.id)
            )
        )
        .scalars()
        .all()
    )
    assert txns == []

    # The assistant reply is still persisted.
    message = (
        await db_session.execute(
            select(ChatMessage).where(
                ChatMessage.session_id == session["id"],
                ChatMessage.role == "assistant",
            )
        )
    ).scalar_one()
    assert message.content == "Уточните год рождения деда."
