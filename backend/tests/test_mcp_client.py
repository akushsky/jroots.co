import time

import pytest

from app.services.mcp_client import (
    TOOL_CALL_LIMIT_MESSAGE,
    TOOL_TIMEOUT_MESSAGE,
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


async def test_cap_is_cumulative_from_initial_used():
    transport = FakeTransport()
    client = _client(transport, max_calls=15, initial_used=14, rate_limit_interval=0)
    await client.open()

    assert await client.call("list_databases", {}) == "ok"
    assert await client.call("list_databases", {}) == TOOL_CALL_LIMIT_MESSAGE
    assert len(transport.calls) == 1


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
