import time

import pytest

from app.services.mcp_client import (
    TOOL_CALL_LIMIT_MESSAGE,
    TOOL_TIMEOUT_MESSAGE,
    TRUNCATED_RESULT_MARKER,
    McpArchiveClient,
    McpCallResult,
    McpUnavailableError,
    estimate_result_count,
)

TOOLS = [
    {"name": "search", "description": "поиск", "inputSchema": {"type": "object"}},
    {"name": "get_record", "description": "запись", "inputSchema": {"type": "object"}},
    {
        "name": "list_databases",
        "description": "базы",
        "inputSchema": {"type": "object"},
    },
    {
        "name": "generate_surname_variants",
        "description": "варианты",
        "inputSchema": {"type": "object"},
    },
    # Not whitelisted for the chat.
    {"name": "update_case", "description": "кейс", "inputSchema": {"type": "object"}},
]


class FakeTransport:
    """McpTransport double: scripted results, recorded call timestamps."""

    def __init__(self, tools=None, script=None, connect_error=None):
        self._tools = TOOLS if tools is None else tools
        self._script = list(script) if script else []
        self._connect_error = connect_error
        self.calls = []  # (name, arguments, monotonic_ts)
        self.connected = False
        self.closed = False

    async def connect(self):
        if self._connect_error is not None:
            raise self._connect_error
        self.connected = True

    async def list_tools(self):
        return self._tools

    async def call_tool(self, name, arguments):
        self.calls.append((name, arguments, time.monotonic()))
        item = self._script.pop(0) if self._script else McpCallResult(text="ok")
        if isinstance(item, Exception):
            raise item
        return item

    async def close(self):
        self.closed = True


def _client(transport, **kwargs):
    return McpArchiveClient(transport, session_id=1, user_id=2, **kwargs)


async def test_open_maps_whitelisted_tools_to_openai_format():
    transport = FakeTransport()
    client = _client(transport)
    await client.open()

    assert transport.connected is True
    names = [tool["function"]["name"] for tool in client.openai_tools]
    assert names == [
        "search",
        "get_record",
        "list_databases",
        "generate_surname_variants",
    ]
    for tool in client.openai_tools:
        assert tool["type"] == "function"
        assert tool["function"]["parameters"] == {"type": "object"}
        assert tool["function"]["description"]


async def test_teaser_sanitizes_result_urls_and_ciphers():
    """Teaser tier: the model never sees real URLs or ciphers."""
    transport = FakeTransport(
        script=[
            McpCallResult(
                text=(
                    "Найдено: Клебанов Мордух Копелевич, 1913-1991, Самара.\n"
                    "URL: https://toldot.com/life/cemetery/graves_97636.html\n"
                    "Шифр: ЦДІАК/W/1164/1/423, фонд 1164 опись 1 дело 415"
                )
            ),
        ]
    )
    client = _client(transport, teaser=True)
    await client.open()
    text = await client.call(
        "search", {"database": "toldot_cemetery", "last_name": "Клебанов"}
    )

    assert "toldot.com" not in text
    assert "1164" not in text
    assert "Клебанов Мордух Копелевич" in text  # names stay (identity work)
    assert "ref:1" in text


async def test_teaser_resolves_ref_handle_back_to_url():
    """get_record with a ref:N handle goes to the gateway with the real URL."""
    transport = FakeTransport(
        script=[
            McpCallResult(
                text="Запись: https://toldot.com/life/cemetery/graves_97636.html"
            ),
            McpCallResult(text="Полная запись о Клебанове"),
        ]
    )
    client = _client(transport, teaser=True)
    await client.open()
    result_text = await client.call("search", {"database": "toldot_cemetery"})
    assert "ref:1" in result_text

    await client.call(
        "get_record", {"database": "toldot_cemetery", "record_id": "ref:1"}
    )

    last_call = transport.calls[-1]
    assert (
        last_call[1]["record_id"]
        == "https://toldot.com/life/cemetery/graves_97636.html"
    )


async def test_teaser_refs_resolve_inside_extras():
    """Ref handles nested in extras/dicts resolve recursively."""
    transport = FakeTransport(
        script=[
            McpCallResult(
                text="Form Action: https://www.jewishgen.org/databases/jgdetail_2.php"
            ),
            McpCallResult(text="Записи коллекции"),
        ]
    )
    client = _client(transport, teaser=True)
    await client.open()
    await client.call("search", {"database": "jewishgen"})
    await client.call(
        "get_record",
        {
            "database": "jewishgen",
            "record_id": "detail",
            "extras": {"form_action": "ref:1", "form_params": {"srch1": "Goldberg"}},
        },
    )

    extras = transport.calls[-1][1]["extras"]
    assert extras["form_action"] == "https://www.jewishgen.org/databases/jgdetail_2.php"
    assert extras["form_params"] == {"srch1": "Goldberg"}


async def test_full_tier_passes_results_untouched():
    """Full tier: no sanitization, no ref handles."""
    transport = FakeTransport(
        script=[
            McpCallResult(text="URL: https://toldot.com/x.html шифр ЦДІАК/W/1164/1/423")
        ]
    )
    client = _client(transport, teaser=False)
    await client.open()
    text = await client.call("search", {"database": "toldot_cemetery"})

    assert "https://toldot.com/x.html" in text
    assert "1164" in text


async def test_open_connect_failure_raises_unavailable():
    client = _client(FakeTransport(connect_error=ConnectionError("refused")))
    with pytest.raises(McpUnavailableError):
        await client.open()


async def test_call_cap_returns_limit_message_and_stops_transport():
    transport = FakeTransport()
    client = _client(transport, max_calls=2, rate_limit_interval=0)
    await client.open()

    assert await client.call("list_databases", {}) == "ok"
    assert await client.call("list_databases", {}) == "ok"
    limited = await client.call("search", {"database": "gabo"})
    assert limited == TOOL_CALL_LIMIT_MESSAGE
    # The capped call never reached the gateway.
    assert len(transport.calls) == 2


async def test_cap_is_per_cycle_despite_initial_used():
    """initial_used only seeds the journal counter; the cap is per cycle."""
    transport = FakeTransport()
    client = _client(transport, max_calls=2, initial_used=14, rate_limit_interval=0)
    await client.open()

    assert await client.call("list_databases", {}) == "ok"
    assert await client.call("list_databases", {}) == "ok"
    assert await client.call("list_databases", {}) == TOOL_CALL_LIMIT_MESSAGE
    assert len(transport.calls) == 2


async def test_cap_resets_on_next_cycle():
    """Turn 1 exhausts the cap; turn 2 (new client seeded with the cumulative
    counter) gets a full fresh cap."""
    transport1 = FakeTransport()
    client1 = _client(transport1, max_calls=2, rate_limit_interval=0)
    await client1.open()
    assert await client1.call("list_databases", {}) == "ok"
    assert await client1.call("list_databases", {}) == "ok"
    assert await client1.call("list_databases", {}) == TOOL_CALL_LIMIT_MESSAGE
    assert len(transport1.calls) == 2

    transport2 = FakeTransport()
    client2 = _client(
        transport2, max_calls=2, initial_used=client1.calls_used, rate_limit_interval=0
    )
    await client2.open()
    assert await client2.call("list_databases", {}) == "ok"
    assert await client2.call("list_databases", {}) == "ok"
    assert await client2.call("list_databases", {}) == TOOL_CALL_LIMIT_MESSAGE
    assert len(transport2.calls) == 2
    # Cumulative counter kept running for the journal's per-cycle delta.
    assert client2.calls_used == 4


async def test_non_whitelisted_tool_never_reaches_transport():
    transport = FakeTransport()
    client = _client(transport, rate_limit_interval=0)
    await client.open()

    result = await client.call("update_case", {"case_id": "x"})
    assert "недоступен" in result
    assert transport.calls == []


async def test_rate_limit_one_rps_per_database():
    transport = FakeTransport()
    client = _client(transport, rate_limit_interval=0.05)
    await client.open()

    await client.call("search", {"database": "gabo", "last_name": "А"})
    await client.call("search", {"database": "gabo", "last_name": "Б"})
    # Different database: no throttling against the first bucket.
    await client.call("search", {"database": "dako", "last_name": "В"})

    _, _, t1 = transport.calls[0]
    _, _, t2 = transport.calls[1]
    _, _, t3 = transport.calls[2]
    assert t2 - t1 >= 0.045
    assert t3 - t2 < 0.05


async def test_timeout_is_retried_once_and_recovers():
    transport = FakeTransport(script=[TimeoutError(), McpCallResult(text="ok")])
    client = _client(transport, rate_limit_interval=0)
    await client.open()

    assert await client.call("list_databases", {}) == "ok"
    assert len(transport.calls) == 2


async def test_double_timeout_returns_error_text_without_raising():
    transport = FakeTransport(script=[TimeoutError(), TimeoutError()])
    client = _client(transport, rate_limit_interval=0)
    await client.open()

    result = await client.call("list_databases", {})
    assert result == TOOL_TIMEOUT_MESSAGE
    assert len(transport.calls) == 2
    assert client.call_log[0].is_error is True


async def test_unexpected_transport_error_is_technical():
    transport = FakeTransport(script=[ConnectionError("reset by peer")])
    client = _client(transport, rate_limit_interval=0)
    await client.open()

    with pytest.raises(McpUnavailableError):
        await client.call("search", {"database": "gabo"})


async def test_search_counters_and_call_log():
    transport = FakeTransport(
        script=[
            McpCallResult(
                text="Найдено 3 записи:\n1. Метрика\n2. Ревизия\n3. Перепись"
            ),
            McpCallResult(text="Ничего не найдено по вашему запросу."),
            McpCallResult(text="Error: Database 'gaboo' is unknown."),
        ]
    )
    client = _client(transport, rate_limit_interval=0)
    await client.open()

    await client.call("search", {"database": "gabo", "last_name": "Фалькович"})
    await client.call("search", {"database": "gabo", "last_name": "Фалкович"})
    await client.call("search", {"database": "gaboo", "last_name": "Фалькович"})

    assert client.searches_with_results == 1
    assert client.empty_searches == 2  # empty reply and the gateway error
    assert client.calls_used == 3

    first, second, third = client.call_log
    assert first.result_count == 3
    assert first.database == "gabo"
    assert first.arguments["last_name"] == "Фалькович"
    assert first.latency_ms >= 0
    assert first.is_error is False
    assert second.result_count == 0
    assert third.is_error is True
    assert third.result_count == 0


class FlakyDb:
    """AsyncSession double whose commit fails a given number of times."""

    def __init__(self, fail_commits=1):
        self.added = []
        self.commits = 0
        self.rollbacks = 0
        self._fail = fail_commits

    def add(self, obj):
        self.added.append(obj)

    async def commit(self):
        self.commits += 1
        if self.commits <= self._fail:
            raise RuntimeError("UniqueViolationError: duplicate key value")

    async def rollback(self):
        self.rollbacks += 1


async def test_journal_failure_does_not_kill_the_call():
    db = FlakyDb(fail_commits=1)
    transport = FakeTransport()
    client = McpArchiveClient(
        transport, session_id=1, user_id=2, rate_limit_interval=0, db=db
    )
    await client.open()

    # The journal write blows up — the tool call itself still succeeds and
    # the poisoned transaction is rolled back.
    assert await client.call("list_databases", {}) == "ok"
    assert db.rollbacks == 1

    # The client keeps working afterwards.
    assert await client.call("list_databases", {}) == "ok"
    assert client.calls_used == 2


async def test_journal_cap_blocked_failure_does_not_kill_the_call():
    db = FlakyDb(fail_commits=10)  # every journal write fails
    transport = FakeTransport()
    client = McpArchiveClient(
        transport, session_id=1, user_id=2, max_calls=1, rate_limit_interval=0, db=db
    )
    await client.open()

    assert await client.call("list_databases", {}) == "ok"
    assert await client.call("search", {"database": "gabo"}) == TOOL_CALL_LIMIT_MESSAGE
    assert db.rollbacks == 2


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("", 0),
        ("   ", 0),
        ("Найдено 5 записей", 5),
        ("Найдено 0 записей", 0),
        ("Ничего не найдено", 0),
        ("По запросу ничего не нашлось", 0),
        ("No results found", 0),
        ("1. Первая\n2. Вторая\n3. Третья", 3),
        ("Метрическая книга синагоги Клинцов, 1890, сплошным текстом", 1),
    ],
)
def test_estimate_result_count(text, expected):
    assert estimate_result_count(text) == expected


class RecordingDb(FlakyDb):
    """Journal sink that never fails (fail_commits=0)."""

    def __init__(self):
        super().__init__(fail_commits=0)


async def test_truncates_long_result_and_journals_result_chars():
    long_body = "Найдено 40 записей\n" + ("запись подробная\n" * 2000)
    assert len(long_body) > 8000
    db = RecordingDb()
    transport = FakeTransport(script=[McpCallResult(text=long_body)])
    client = McpArchiveClient(
        transport,
        session_id=1,
        user_id=2,
        rate_limit_interval=0,
        result_max_chars=8000,
        db=db,
    )
    await client.open()
    text = await client.call(
        "search", {"database": "gabo", "last_name": "Фалькович"}
    )

    assert "выдача обрезана сервером" in text
    assert f"показано 8000 из {len(long_body)}" in text
    assert text.startswith(long_body[:8000])
    assert TRUNCATED_RESULT_MARKER.format(kept=8000, total=len(long_body)) in text

    row = db.added[-1]
    assert row.result_chars == len(text)
    assert row.status == "ok"
    assert row.results_count is not None


async def test_short_result_is_not_truncated():
    body = "Найдено 2 записи: Фалькович"
    transport = FakeTransport(script=[McpCallResult(text=body)])
    client = _client(transport, result_max_chars=8000, rate_limit_interval=0)
    await client.open()
    text = await client.call("search", {"database": "gabo"})
    assert text == body
    assert "обрезана" not in text


async def test_teaser_ref_handles_built_from_truncated_text():
    """URLs past the truncate cut never become ref handles — model can't see them."""
    head = "URL: https://toldot.com/life/cemetery/graves_1.html\n"
    # Second URL sits after the budget so it must not be registered.
    long_body = head + ("x" * 9000) + "\nURL: https://toldot.com/tail.html"
    transport = FakeTransport(
        script=[
            McpCallResult(text=long_body),
            McpCallResult(text="ok"),
        ]
    )
    client = _client(
        transport, teaser=True, result_max_chars=200, rate_limit_interval=0
    )
    await client.open()
    text = await client.call("search", {"database": "toldot_cemetery"})
    assert "ref:1" in text
    assert "toldot.com" not in text
    assert "обрезана" in text
    # Only the head URL was registered.
    assert client._ref_map == {
        "ref:1": "https://toldot.com/life/cemetery/graves_1.html"
    }
    await client.call(
        "get_record", {"database": "toldot_cemetery", "record_id": "ref:1"}
    )
    assert (
        transport.calls[-1][1]["record_id"]
        == "https://toldot.com/life/cemetery/graves_1.html"
    )


async def test_cap_blocked_journals_without_result_chars():
    db = RecordingDb()
    transport = FakeTransport()
    client = McpArchiveClient(
        transport,
        session_id=1,
        user_id=2,
        max_calls=0,
        rate_limit_interval=0,
        db=db,
    )
    await client.open()
    assert await client.call("search", {"database": "gabo"}) == TOOL_CALL_LIMIT_MESSAGE
    row = db.added[-1]
    assert row.status == "cap_blocked"
    assert row.result_chars is None
