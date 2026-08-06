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
    ToolCallLog,
)
from app.services import agent_loop as agent_loop_module
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

        def factory(*, session_id, user_id, initial_used=0, db=None, teaser=False):
            client = McpArchiveClient(
                transport,
                session_id=session_id,
                user_id=user_id,
                initial_used=initial_used,
                max_calls=max_calls,
                rate_limit_interval=0,
                db=db,
                teaser=teaser,
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
                _chunk("https://archive.ru/r/1 "),
                _chunk("![скан записи](https://archive.ru/img/1.jpg)"),
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
    # Paid tier: inline images from tool results stay inline.
    assert "![скан записи](https://archive.ru/img/1.jpg)" in streamed


async def test_agent_teaser_redacts_inline_images(
    client, db_session, agent_mode, fake_llm, fake_mcp
):
    transport = FakeTransport(script=[McpCallResult(text="Найдено 1 запись")])
    fake_mcp(transport)
    fake_llm(
        [
            _tool_round("call_1", "search", ['{"database": "gabo"}']),
            [
                _chunk("Фото могилы: ![скан](https://tol"),
                _chunk("dot.ru/x.jpg)"),
                _chunk(usage=_usage(50, 25)),
            ],
        ]
    )
    user = await create_user(db_session, email="agent-teaser-img@example.com")
    await _give_credits(db_session, user, searches=5)
    session = await _create_session(client, user)

    frames = await _post_sse(client, user, session["id"], "ищу")
    streamed = "".join(data["text"] for event, data in frames if event == "token")
    assert "toldot" not in streamed
    assert "скан" not in streamed  # the alt text is cut with the construct
    assert "🖼 🔒" in streamed
    assert "Фото могилы: " in streamed

    message = (
        await db_session.execute(
            select(ChatMessage).where(
                ChatMessage.session_id == session["id"],
                ChatMessage.role == "assistant",
            )
        )
    ).scalar_one()
    assert "toldot" not in message.content
    assert "🖼 🔒" in message.content


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
    # The persisted reply carries the machine-facing searchlog appendix.
    assert payload["message"]["content"].startswith("Ответ")
    assert "<searchlog>" in payload["message"]["content"]
    assert "search(gabo)" in payload["message"]["content"]
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


async def test_agent_intermediate_rounds_emit_step_events(
    client, db_session, agent_mode, fake_llm, fake_mcp
):
    transport = FakeTransport(
        script=[
            McpCallResult(text="Найдено 1 запись"),
            McpCallResult(text="Найдено 1 запись"),
        ]
    )
    fake_mcp(transport)
    fake_llm(
        [
            [
                _chunk("Сначала посмотрю базы."),
                _chunk(tool_calls=[_tc(0, "c1", "search", '{"database": "gabo"}')]),
                _chunk(usage=_usage(10, 5)),
            ],
            [
                _chunk("Теперь ищу в ГАБО."),
                _chunk(tool_calls=[_tc(0, "c2", "search", '{"database": "dako"}')]),
                _chunk(usage=_usage(10, 5)),
            ],
            [
                _chunk("Нашёл запись."),
                _chunk(usage=_usage(10, 5)),
            ],
        ]
    )
    user = await create_user(db_session, email="agent-steps@example.com")
    await _give_credits(db_session, user, searches=5)
    session = await _create_session(client, user)

    frames = await _post_sse(client, user, session["id"], "ищу захоронение деда")
    events = [event for event, _ in frames]
    # Reasoning of the tool-calling rounds is `step`; the final answer is `token`.
    assert events == ["step", "step", "token", "token", "usage", "done"]
    assert frames[0][1] == {"text": "Сначала посмотрю базы."}
    assert frames[1][1] == {"text": "Теперь ищу в ГАБО."}
    streamed = "".join(data["text"] for event, data in frames if event == "token")
    assert streamed == "Нашёл запись."
    assert frames[-1][1]["searches_left"] == 4

    # One assistant message, steps marked up for history re-rendering, with
    # the searchlog appendix at the end.
    message = (
        await db_session.execute(
            select(ChatMessage).where(
                ChatMessage.session_id == session["id"],
                ChatMessage.role == "assistant",
            )
        )
    ).scalar_one()
    assert message.content.startswith(
        "<steps>Сначала посмотрю базы.</steps>"
        "<steps>Теперь ищу в ГАБО.</steps>"
        "Нашёл запись."
    )
    assert "<searchlog>" in message.content

    rows = await _searches(db_session, session["id"])
    assert len(rows) == 1
    assert rows[0].charged is True
    assert rows[0].results_count == 2


async def test_agent_cap_instruction_never_leaks_to_user(
    client, db_session, agent_mode, fake_llm, fake_mcp
):
    transport = FakeTransport(script=[McpCallResult(text="Найдено 1 запись")])
    fake_mcp(transport, max_calls=1)
    llm_client = fake_llm(
        [
            _tool_round("c1", "search", ['{"database": "gabo"}']),
            _tool_round("c2", "search", ['{"database": "dako"}']),
            [
                _chunk("По вашей семье нашлась метрическая запись из Клинцов, "),
                _chunk("фамилия записана как Фалькович."),
                _chunk(usage=_usage(10, 5)),
            ],
        ]
    )
    user = await create_user(db_session, email="agent-capleak@example.com")
    await _give_credits(db_session, user, searches=5)
    session = await _create_session(client, user)

    frames = await _post_sse(client, user, session["id"], "ищу")
    # Everything the user saw — neither the cap wording nor any mention of
    # technical limits may leak into the visible stream.
    visible = "".join(
        data["text"] for event, data in frames if event in ("token", "step")
    ).lower()
    for leak in ("лимит", "кап", "ограничен", "бюджет", "вызов"):
        assert leak not in visible

    # The model, however, received the instruction to summarize naturally.
    final_round = llm_client.chat.completions.calls[2]
    tool_messages = [m for m in final_round["messages"] if m["role"] == "tool"]
    instruction = tool_messages[-1]["content"]
    assert instruction == TOOL_CALL_LIMIT_MESSAGE
    assert "НЕ упоминая лимиты" in instruction
    assert "естественное завершение" in instruction

    assert frames[-1][0] == "done"
    assert frames[-1][1]["searches_left"] == 4


async def _tool_call_rows(db_session, session_id):
    result = await db_session.execute(
        select(ToolCallLog)
        .where(ToolCallLog.session_id == session_id)
        .order_by(ToolCallLog.id)
    )
    return result.scalars().all()


async def test_agent_tool_calls_are_journaled(
    client, db_session, agent_mode, fake_llm, fake_mcp
):
    transport = FakeTransport(
        script=[McpCallResult(text="Найдено 2 записи:\n1. Метрика\n2. Ревизия")]
    )
    fake_mcp(transport)
    fake_llm(
        [
            _tool_round(
                "c1", "search", ['{"database": "gabo", "last_name": "Фалькович"}']
            ),
            [_chunk("Нашёл."), _chunk(usage=_usage(10, 5))],
        ]
    )
    user = await create_user(db_session, email="agent-journal@example.com")
    await _give_credits(db_session, user, searches=5)
    session = await _create_session(client, user)

    frames = await _post_sse(client, user, session["id"], "ищу Фальковича")
    assert frames[-1][0] == "done"

    rows = await _tool_call_rows(db_session, session["id"])
    assert len(rows) == 1
    row = rows[0]
    assert row.tool == "search"
    assert row.database == "gabo"
    assert row.args_json == {"database": "gabo", "last_name": "Фалькович"}
    assert row.results_count == 2
    assert row.latency_ms is not None and row.latency_ms >= 0
    assert row.status == "ok"
    assert row.error is None

    # The same journal is exposed over the debug endpoint.
    response = await client.get(
        f"/api/chat/sessions/{session['id']}/tool-calls",
        headers=auth_header(user),
    )
    assert response.status_code == 200
    payload = response.json()
    assert len(payload) == 1
    assert payload[0]["tool"] == "search"
    assert payload[0]["args"] == {"database": "gabo", "last_name": "Фалькович"}
    assert payload[0]["results_count"] == 2
    assert payload[0]["status"] == "ok"
    assert payload[0]["created_at"].endswith("+00:00")


async def test_agent_error_call_is_journaled(
    client, db_session, agent_mode, fake_llm, fake_mcp
):
    transport = FakeTransport(
        script=[McpCallResult(text="Error: Database 'gaboo' is unknown.")]
    )
    fake_mcp(transport)
    fake_llm(
        [
            _tool_round("c1", "search", ['{"database": "gaboo"}']),
            [_chunk("Не удалось проверить этот архив."), _chunk(usage=_usage(10, 5))],
        ]
    )
    user = await create_user(db_session, email="agent-jerr@example.com")
    await _give_credits(db_session, user, searches=5)
    session = await _create_session(client, user)

    frames = await _post_sse(client, user, session["id"], "ищу")
    assert frames[-1][0] == "done"

    rows = await _tool_call_rows(db_session, session["id"])
    assert len(rows) == 1
    assert rows[0].status == "error"
    assert "unknown" in rows[0].error
    assert rows[0].results_count == 0


async def test_agent_cap_blocked_call_is_journaled(
    client, db_session, agent_mode, fake_llm, fake_mcp
):
    transport = FakeTransport(script=[McpCallResult(text="Найдено 1 запись")])
    fake_mcp(transport, max_calls=1)
    fake_llm(
        [
            _tool_round("c1", "search", ['{"database": "gabo"}']),
            _tool_round("c2", "search", ['{"database": "dako"}']),
            [_chunk("Итог."), _chunk(usage=_usage(10, 5))],
        ]
    )
    user = await create_user(db_session, email="agent-jcap@example.com")
    await _give_credits(db_session, user, searches=5)
    session = await _create_session(client, user)

    frames = await _post_sse(client, user, session["id"], "ищу")
    assert frames[-1][0] == "done"

    rows = await _tool_call_rows(db_session, session["id"])
    assert [row.status for row in rows] == ["ok", "cap_blocked"]
    blocked = rows[1]
    assert blocked.tool == "search"
    assert blocked.database == "dako"
    assert blocked.args_json == {"database": "dako"}
    assert blocked.latency_ms is None
    assert blocked.results_count is None


async def test_tool_calls_endpoint_is_owner_only(
    client, db_session, agent_mode, fake_llm, fake_mcp
):
    transport = FakeTransport(script=[McpCallResult(text="Найдено 1 запись")])
    fake_mcp(transport)
    fake_llm(
        [
            _tool_round("c1", "search", ['{"database": "gabo"}']),
            [_chunk("Ответ."), _chunk(usage=_usage(10, 5))],
        ]
    )
    owner = await create_user(db_session, email="agent-jowner@example.com")
    other = await create_user(db_session, email="agent-jother@example.com")
    await _give_credits(db_session, owner, searches=5)
    session = await _create_session(client, owner)
    await _post_sse(client, owner, session["id"], "ищу")

    # Anonymous: 401; another user: 404 (same as the session itself).
    response = await client.get(f"/api/chat/sessions/{session['id']}/tool-calls")
    assert response.status_code == 401
    response = await client.get(
        f"/api/chat/sessions/{session['id']}/tool-calls",
        headers=auth_header(other),
    )
    assert response.status_code == 404
    response = await client.get(
        f"/api/chat/sessions/{session['id']}/tool-calls",
        headers=auth_header(owner),
    )
    assert response.status_code == 200
    assert len(response.json()) == 1


async def test_agent_cycle_crash_emits_error_event_not_silent_eof(
    client, db_session, agent_mode, fake_llm, fake_mcp, monkeypatch
):
    """Any exception escaping the cycle (e.g. a poisoned DB transaction)
    must surface as a terminal error event, not a silently closed stream."""

    async def boom(*args, **kwargs):
        raise RuntimeError("PendingRollbackError: transaction was poisoned")

    monkeypatch.setattr(agent_loop_module.credits, "get_balance", boom)
    transport = FakeTransport()
    fake_mcp(transport)
    llm_client = fake_llm([])
    user = await create_user(db_session, email="agent-crash@example.com")
    user_id = user.id  # the crash path rolls back the shared session,
    # expiring every ORM object attached to it
    await _give_credits(db_session, user, searches=5)
    session = await _create_session(client, user)

    frames = await _post_sse(client, user, session["id"], "ищу")
    assert frames[-1] == ("error", {"message": "Ошибка, попробуйте ещё раз."})

    # The LLM was never reached, the credit is untouched, the session is
    # flagged error — and the user message still survived.
    assert llm_client.chat.completions.calls == []
    credit = (
        await db_session.execute(select(Credit).where(Credit.user_id == user_id))
    ).scalar_one()
    assert credit.searches_left == 5
    session_row = await _session_row(db_session, session["id"])
    assert session_row.status == "error"


async def test_agent_second_cycle_sees_searchlog_of_first(
    client, db_session, agent_mode, fake_llm, fake_mcp
):
    transport = FakeTransport(
        script=[
            McpCallResult(text="Найдено 53 записи по Фалькович"),
            McpCallResult(text="Найдено 15 записей по Фалькович"),
        ]
    )
    fake_mcp(transport)
    llm_client = fake_llm(
        [
            # Cycle 1: search jewishgen, then answer.
            _tool_round(
                "c1",
                "search",
                ['{"database": "jewishgen", "last_name": "Фалькович"}'],
            ),
            [_chunk("Нашёл 53 записи."), _chunk(usage=_usage(10, 5))],
            # Cycle 2: search rtr_foundation, then answer.
            _tool_round(
                "c2",
                "search",
                ['{"database": "rtr_foundation", "last_name": "Фалькович"}'],
            ),
            [_chunk("И ещё 15 записей."), _chunk(usage=_usage(10, 5))],
        ]
    )
    user = await create_user(db_session, email="agent-searchlog@example.com")
    await _give_credits(db_session, user, searches=5)
    session = await _create_session(client, user)

    frames1 = await _post_sse(client, user, session["id"], "ищу Фальковича")
    # The searchlog is persisted but never streamed.
    streamed1 = "".join(data["text"] for event, data in frames1 if event == "token")
    assert "<searchlog>" not in streamed1

    await _post_sse(client, user, session["id"], "а покажи подробнее")

    # The first call of cycle 2 sees the cycle-1 assistant reply, searchlog
    # included, via the persisted history.
    cycle2_first_call = llm_client.chat.completions.calls[2]
    assistant_replies = [
        m["content"] for m in cycle2_first_call["messages"] if m["role"] == "assistant"
    ]
    assert any("<searchlog>" in content for content in assistant_replies)
    searchlog_reply = next(c for c in assistant_replies if "<searchlog>" in c)
    assert "search(jewishgen: Фалькович) → 53 результатов" in searchlog_reply

    # The cycle-2 reply accumulates both calls in its own searchlog.
    messages = (
        (
            await db_session.execute(
                select(ChatMessage)
                .where(
                    ChatMessage.session_id == session["id"],
                    ChatMessage.role == "assistant",
                )
                .order_by(ChatMessage.id)
            )
        )
        .scalars()
        .all()
    )
    second_reply = messages[-1].content
    assert "search(jewishgen: Фалькович) → 53 результатов" in second_reply
    assert "search(rtr_foundation: Фалькович) → 15 результатов" in second_reply


_RECORDS_BLOCK = (
    '[{"type": "metric_book", "place": "Клинцы", "period": "1890-1895", '
    '"names": ["Шмуил Фалькович"], "archive": "ГАБО", '
    '"cipher": "ф.585 оп.1 д.12", "url": "https://archive.example/r/1"}]'
)


async def _assistant_content(db_session, session_id):
    message = (
        await db_session.execute(
            select(ChatMessage).where(
                ChatMessage.session_id == session_id,
                ChatMessage.role == "assistant",
            )
        )
    ).scalar_one()
    return message.content


async def test_agent_teaser_records_block_server_rendered(
    client, db_session, agent_mode, fake_llm, fake_mcp
):
    transport = FakeTransport(script=[McpCallResult(text="Найдено 1 запись")])
    fake_mcp(transport)
    fake_llm(
        [
            _tool_round("c1", "search", ['{"database": "gabo"}']),
            [
                _chunk("Итог:\n"),
                _chunk("```rec"),
                _chunk("ords\n"),
                _chunk(_RECORDS_BLOCK[:40]),
                _chunk(_RECORDS_BLOCK[40:]),
                _chunk("\n```\n"),
                _chunk("Подробности выше."),
                _chunk(usage=_usage(10, 5)),
            ],
        ]
    )
    user = await create_user(db_session, email="agent-rec-teaser@example.com")
    await _give_credits(db_session, user, searches=5)
    session = await _create_session(client, user)

    frames = await _post_sse(client, user, session["id"], "ищу")
    streamed = "".join(data["text"] for event, data in frames if event == "token")

    # Server-rendered teaser table: masked names, lock — no raw JSON, no
    # cipher, no URL, neither in the stream nor in the persisted reply.
    for text in (streamed, await _assistant_content(db_session, session["id"])):
        assert "Шмуи…" in text
        assert "Фалькович" not in text
        assert "585" not in text
        assert "archive.example" not in text
        assert "```records" not in text
        assert '"cipher"' not in text
        assert "🔒 доступно в полной версии" in text
        assert "| Тип | Место | Период | Имена | Запись |" in text
    assert "Итог:" in streamed
    assert "Подробности выше." in streamed


async def test_agent_full_records_block_renders_everything(
    client, db_session, agent_mode, fake_llm, fake_mcp
):
    transport = FakeTransport(script=[McpCallResult(text="Найдено 1 запись")])
    fake_mcp(transport)
    fake_llm(
        [
            _tool_round("c1", "search", ['{"database": "gabo"}']),
            [
                _chunk("```records\n"),
                _chunk(_RECORDS_BLOCK),
                _chunk("\n```"),
                _chunk(usage=_usage(10, 5)),
            ],
        ]
    )
    user = await create_user(db_session, email="agent-rec-full@example.com")
    db_session.add(
        Payment(
            provider="stripe",
            provider_payment_id="pay-rec-1",
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
    assert "Шмуил Фалькович" in streamed
    assert "ф.585 оп.1 д.12" in streamed
    assert "[открыть](https://archive.example/r/1)" in streamed
    assert "```records" not in streamed  # the fence itself is replaced


async def test_agent_teaser_broken_records_block_dropped(
    client, db_session, agent_mode, fake_llm, fake_mcp
):
    transport = FakeTransport(script=[McpCallResult(text="Найдено 1 запись")])
    fake_mcp(transport)
    fake_llm(
        [
            _tool_round("c1", "search", ['{"database": "gabo"}']),
            [
                _chunk("До блока.\n"),
                _chunk("```records\n"),
                _chunk('[{"cipher": "ф.585'),
                _chunk(usage=_usage(10, 5)),
            ],
        ]
    )
    user = await create_user(db_session, email="agent-rec-broken@example.com")
    await _give_credits(db_session, user, searches=5)
    session = await _create_session(client, user)

    frames = await _post_sse(client, user, session["id"], "ищу")
    streamed = "".join(data["text"] for event, data in frames if event == "token")
    # Unterminated block with broken JSON: dropped silently, prose survives.
    assert "585" not in streamed
    assert "cipher" not in streamed
    assert "```" not in streamed
    assert "До блока." in streamed

    persisted = await _assistant_content(db_session, session["id"])
    assert "585" not in persisted
    assert "```" not in persisted


async def test_agent_teaser_prose_without_block_still_clean(
    client, db_session, agent_mode, fake_llm, fake_mcp
):
    # The model ignored the records-block instruction and put sensitive data
    # straight into prose — the redactor still covers ciphers and URLs.
    transport = FakeTransport(script=[McpCallResult(text="Найдено 1 запись")])
    fake_mcp(transport)
    fake_llm(
        [
            _tool_round("c1", "search", ['{"database": "gabo"}']),
            [
                _chunk("Запись ЦДІАК/W/1164/1/423 и ф. 585 оп. 1 д. 23, "),
                _chunk("https://archive.example/r/1"),
                _chunk(usage=_usage(10, 5)),
            ],
        ]
    )
    user = await create_user(db_session, email="agent-rec-prose@example.com")
    await _give_credits(db_session, user, searches=5)
    session = await _create_session(client, user)

    frames = await _post_sse(client, user, session["id"], "ищу")
    streamed = "".join(data["text"] for event, data in frames if event == "token")
    assert "1164" not in streamed
    assert "ЦДІАК" not in streamed
    assert "585" not in streamed
    assert "archive.example" not in streamed
