"""Client for the JRoots MCP archive-search gateway (streamable HTTP).

One McpArchiveClient per agent cycle: connects, lists the whitelisted tools,
executes tool calls with per-database rate limiting, a per-session call cap,
a single timeout retry and structured logging.

The transport is pluggable (McpTransport protocol) so unit tests run without
the MCP SDK or a live server; the production transport is
StreamableHttpMcpTransport, built on the official mcp SDK.
"""

import asyncio
import json
import logging
import re
import time
from contextlib import AsyncExitStack
from dataclasses import dataclass
from typing import Any, Protocol

from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.models import ToolCallLog
from app.services.stream_redactor import redact_text as _redact_whole_text

logger = logging.getLogger("jroots")

# Whole URL token in a tool result — swapped for an opaque ref:N handle in
# teaser tier (see McpArchiveClient._sanitize_result_text).
_URL_TOKEN_RE = re.compile(r"https?://\S+", re.IGNORECASE)

# A ref:N handle previously issued by this client (used to resolve back).
_REF_HANDLE_RE = re.compile(r"\bref:(\d+)\b")

try:  # mcp >= 2.0
    from mcp.shared.exceptions import MCPError
except ImportError:  # pragma: no cover - depends on installed SDK version
    try:  # mcp 1.x
        from mcp.shared.exceptions import McpError as MCPError
    except ImportError:
        MCPError = None  # type: ignore[assignment]

# Only these tools are exposed to the chat model — everything else the
# gateway offers (case state, reports, CRM) stays out of the user-facing loop.
TOOL_WHITELIST = (
    "search",
    "get_record",
    "list_databases",
    "generate_surname_variants",
)

TOOL_CALL_LIMIT_MESSAGE = (
    "Бюджет поисковых вызовов исчерпан. Подведи итог по уже найденному как "
    "естественное завершение поиска, НЕ упоминая лимиты, капы или технические "
    "ограничения. Если находок мало — предложи, как пользователю сузить или "
    "уточнить задачу."
)

TOOL_TIMEOUT_MESSAGE = (
    "Error: поисковый сервис не ответил вовремя. Попробуй другой архив "
    "или переформулируй запрос."
)

TOOL_UNKNOWN_MESSAGE = "Error: инструмент '{name}' недоступен в этом чате."

EMPTY_RESULT_MESSAGE = "Error: пустой ответ поискового сервиса."


class McpUnavailableError(Exception):
    """The MCP gateway is unreachable or broke mid-cycle (technical failure)."""


@dataclass
class McpCallResult:
    """Normalized tool-call outcome returned by any McpTransport."""

    text: str
    is_error: bool = False


class McpTransport(Protocol):
    """Pluggable transport behind McpArchiveClient (real SDK or test double)."""

    async def connect(self) -> None: ...

    async def list_tools(self) -> list[dict[str, Any]]: ...

    async def call_tool(
        self, name: str, arguments: dict[str, Any]
    ) -> McpCallResult: ...

    async def close(self) -> None: ...


class StreamableHttpMcpTransport:
    """Production transport: official MCP SDK streamable-HTTP client.

    Endpoint: POST {JROOTS_MCP_URL}/mcp with the X-Jroots-Token header.
    The SDK is imported lazily so the backend test-suite does not require a
    live server; both the mcp 1.x (streamablehttp_client) and mcp 2.x
    (streamable_http_client) APIs are supported.
    """

    def __init__(self, url: str, token: str, timeout_seconds: float) -> None:
        self._url = url
        self._token = token
        self._timeout = timeout_seconds
        self._stack: AsyncExitStack | None = None
        self._session: Any = None

    async def connect(self) -> None:
        from mcp import ClientSession

        self._stack = AsyncExitStack()
        try:  # mcp >= 2.0
            from mcp.client.streamable_http import (
                create_mcp_http_client,
                streamable_http_client,
            )

            http_client = create_mcp_http_client(
                headers={"X-Jroots-Token": self._token}
            )
            cm = streamable_http_client(self._url, http_client=http_client)
            read_stream, write_stream = await self._stack.enter_async_context(cm)
        except ImportError:  # mcp 1.x
            from mcp.client.streamable_http import streamablehttp_client

            cm = streamablehttp_client(
                self._url,
                headers={"X-Jroots-Token": self._token},
                timeout=self._timeout,
            )
            read_stream, write_stream, _ = await self._stack.enter_async_context(cm)
        self._session = await self._stack.enter_async_context(
            ClientSession(read_stream, write_stream)
        )
        await self._session.initialize()

    async def list_tools(self) -> list[dict[str, Any]]:
        result = await self._session.list_tools()
        tools = []
        for tool in result.tools:
            schema = (
                getattr(tool, "input_schema", None)  # mcp >= 2.0
                or getattr(tool, "inputSchema", None)  # mcp 1.x
                or {}
            )
            tools.append(
                {
                    "name": tool.name,
                    "description": tool.description or "",
                    "inputSchema": schema,
                }
            )
        return tools

    async def call_tool(self, name: str, arguments: dict[str, Any]) -> McpCallResult:
        result = await asyncio.wait_for(
            self._session.call_tool(name, arguments), timeout=self._timeout
        )
        content = getattr(result, "content", None) or []
        text = "\n".join(
            block.text
            for block in content
            if getattr(block, "type", None) == "text" and getattr(block, "text", None)
        )
        if not text:
            structured = getattr(result, "structured_content", None) or getattr(
                result, "structuredContent", None
            )
            if structured:
                text = json.dumps(structured, ensure_ascii=False)
        is_error = bool(
            getattr(result, "is_error", None) or getattr(result, "isError", False)
        )
        return McpCallResult(text=text, is_error=is_error)

    async def close(self) -> None:
        if self._stack is not None:
            await self._stack.aclose()
            self._stack = None


# --- Result-count heuristics -------------------------------------------------
# The gateway fronts 70+ archives with heterogeneous text formats and no
# uniform machine-readable count, so "how many records did this search find"
# is estimated from the reply text.

_NO_RESULTS_RE = re.compile(
    r"ничего не (?:найдено|нашлось)|не найдено|не нашлось|нет результатов|"
    r"записей не найдено|совпадений нет|no results|not found|nothing found",
    re.IGNORECASE,
)
_COUNT_RE = re.compile(
    r"(?:найдено|found|results?|records?|запис(?:ей|и|ь)|совпадени\w*)"
    r"\D{0,20}?(\d+)",
    re.IGNORECASE,
)
_NUMBERED_ITEM_RE = re.compile(r"^\s*\d{1,2}[.)]\s", re.MULTILINE)


def estimate_result_count(text: str) -> int:
    """Heuristic record count for a search-tool reply.

    Order: explicit «найдено N» count → no-results markers → numbered list
    items → a substantive reply without markers counts as a single hit (so
    prose answers are never misread as "empty" and never drive escalation).
    """
    if not text.strip():
        return 0
    counted = _COUNT_RE.search(text)
    if counted:
        return int(counted.group(1))
    if _NO_RESULTS_RE.search(text):
        return 0
    numbered = _NUMBERED_ITEM_RE.findall(text)
    if numbered:
        return len(numbered)
    return 1


@dataclass
class ToolCallRecord:
    """One executed tool call, kept for logging, tests and session stats."""

    tool: str
    database: str | None
    arguments: dict[str, Any]
    result_count: int | None
    latency_ms: int
    is_error: bool


class McpArchiveClient:
    """Agent-facing wrapper over an McpTransport.

    Enforces the whitelist, the per-database 1 rps rate limit (default), the
    per-session call cap, one retry on timeout, and per-call logging. Search
    result counters (searches_with_results / empty_searches) feed both the
    searches table and the model-escalation heuristic.
    """

    def __init__(
        self,
        transport: McpTransport,
        *,
        session_id: int,
        user_id: int,
        initial_used: int = 0,
        max_calls: int = 15,
        rate_limit_interval: float = 1.0,
        db: AsyncSession | None = None,
        teaser: bool = False,
    ) -> None:
        self._transport = transport
        self.session_id = session_id
        self.user_id = user_id
        self.max_calls = max_calls
        self.rate_limit_interval = rate_limit_interval
        # Cumulative across the whole chat session (all user messages).
        self.calls_used = initial_used
        self.call_log: list[ToolCallRecord] = []
        self.searches_with_results = 0
        self.empty_searches = 0
        self._tools: list[dict[str, Any]] = []
        self._last_call_at: dict[str, float] = {}
        # Optional DB handle for the tool_call_logs journal; None in unit
        # tests that exercise the client without a database.
        self._db = db
        # Parallel tool calls (asyncio.gather) share one AsyncSession — the
        # journal must serialize its writes or concurrent commits corrupt
        # each other (UniqueViolationError → poisoned transaction).
        self._journal_lock = asyncio.Lock()
        # Teaser tier: tool results are sanitized before the model sees them
        # (ciphers masked, URLs swapped for opaque ref:N handles resolved
        # back server-side) — the model cannot leak what it never saw.
        self._teaser = teaser
        self._ref_map: dict[str, str] = {}
        self._ref_counter = 0

    async def open(self) -> None:
        """Connect and fetch the whitelisted tool schemas (OpenAI format)."""
        try:
            await self._transport.connect()
            raw_tools = await self._transport.list_tools()
        except Exception as exc:
            raise McpUnavailableError(f"MCP gateway unavailable: {exc}") from exc
        self._tools = [
            self._to_openai_tool(tool)
            for tool in raw_tools
            if tool.get("name") in TOOL_WHITELIST
        ]

    async def close(self) -> None:
        await self._transport.close()

    @property
    def openai_tools(self) -> list[dict[str, Any]]:
        return self._tools

    @staticmethod
    def _to_openai_tool(tool: dict[str, Any]) -> dict[str, Any]:
        return {
            "type": "function",
            "function": {
                "name": tool["name"],
                "description": tool.get("description") or "",
                "parameters": tool.get("inputSchema") or {},
            },
        }

    async def call(self, name: str, arguments: dict[str, Any]) -> str:
        """Execute one tool call and return the text shown to the model.

        Never raises for logical failures (bad arguments, archive errors,
        timeouts after the single retry) — those come back as "Error: ..."
        text so the model can route around them. Raises McpUnavailableError
        only when the gateway itself is broken (technical failure).
        """
        if name not in TOOL_WHITELIST:
            await self._journal(
                tool=name,
                database=None,
                arguments=arguments,
                status="error",
                error=f"tool '{name}' is not whitelisted for the chat",
            )
            return TOOL_UNKNOWN_MESSAGE.format(name=name)
        if self.calls_used >= self.max_calls:
            logger.info(
                "MCP tool cap reached: session=%d user=%d used=%d cap=%d",
                self.session_id,
                self.user_id,
                self.calls_used,
                self.max_calls,
            )
            await self._journal(
                tool=name,
                database=(
                    arguments.get("database") if isinstance(arguments, dict) else None
                ),
                arguments=arguments,
                status="cap_blocked",
            )
            return TOOL_CALL_LIMIT_MESSAGE

        database = arguments.get("database") if isinstance(arguments, dict) else None
        await self._throttle(str(database) if database else name)

        # Teaser tier: resolve opaque ref:N handles back to real URLs before
        # hitting the gateway (the model never sees the real ones).
        resolved_arguments = self._resolve_refs(arguments)

        started = time.monotonic()
        result = await self._call_with_retry(name, resolved_arguments)
        latency_ms = int((time.monotonic() - started) * 1000)

        self.calls_used += 1
        # Teaser tier: the model gets the sanitized text (ciphers masked,
        # URLs swapped for ref:N handles) — it cannot leak what it never saw.
        text = self._sanitize_result_text(result.text)
        is_error = result.is_error or text.lstrip().startswith("Error:")
        result_count: int | None = None
        if name == "search":
            result_count = 0 if is_error else estimate_result_count(text)
            if result_count > 0:
                self.searches_with_results += 1
            else:
                self.empty_searches += 1

        self.call_log.append(
            ToolCallRecord(
                tool=name,
                database=database,
                arguments=arguments,
                result_count=result_count,
                latency_ms=latency_ms,
                is_error=is_error,
            )
        )
        logger.info(
            "MCP call session=%d user=%d tool=%s database=%s args=%s "
            "results=%s latency_ms=%d error=%s",
            self.session_id,
            self.user_id,
            name,
            database,
            json.dumps(resolved_arguments, ensure_ascii=False),
            result_count,
            latency_ms,
            is_error,
        )
        await self._journal(
            tool=name,
            database=database,
            arguments=arguments,
            results_count=result_count,
            latency_ms=latency_ms,
            status="error" if is_error else "ok",
            error=text if is_error else None,
        )
        return text or EMPTY_RESULT_MESSAGE

    def _resolve_refs(self, arguments: Any) -> Any:
        """Swap opaque ref:N handles in arguments back to the real URLs.

        Teaser tier only: the model drills down with handles it got from
        sanitized results; the gateway always gets the real values. Runs
        recursively over dicts/lists; unknown handles pass through verbatim
        (the gateway answers with its own error for those).
        """
        if not self._teaser or not self._ref_map:
            return arguments

        def _resolve(value: Any) -> Any:
            if isinstance(value, str):
                return _REF_HANDLE_RE.sub(
                    lambda m: self._ref_map.get(m.group(0), m.group(0)), value
                )
            if isinstance(value, dict):
                return {k: _resolve(v) for k, v in value.items()}
            if isinstance(value, list):
                return [_resolve(v) for v in value]
            return value

        return _resolve(arguments)

    def _sanitize_result_text(self, text: str) -> str:
        """Redact a tool result before the model sees it (teaser tier only).

        URLs become opaque ref:N handles (registered in this client's ref map
        so _resolve_refs can swap them back); every cipher family is masked
        whole-text — no streaming boundary issues here. Names, dates, result
        counters and archive/place names stay: the model needs them for
        identity work, and they are the teaser's selling part.
        """
        if not self._teaser or not text:
            return text

        def _handle(match: re.Match) -> str:
            url = match.group(0)
            for handle, known in self._ref_map.items():
                if known == url:
                    return handle
            self._ref_counter += 1
            handle = f"ref:{self._ref_counter}"
            self._ref_map[handle] = url
            return handle

        masked = _URL_TOKEN_RE.sub(_handle, text)
        return _redact_whole_text(masked)

    async def _journal(
        self,
        *,
        tool: str,
        database: str | None,
        arguments: dict[str, Any],
        status: str,
        results_count: int | None = None,
        latency_ms: int | None = None,
        error: str | None = None,
    ) -> None:
        """Persist one tool_call_logs row. Commits on its own so the journal
        survives a technical failure of the rest of the cycle (the cycle has
        nothing else pending at tool-call time). No-op without a DB handle.

        The journal is observability, not the critical path: a write failure
        is logged and swallowed (with a rollback to detox the session) — it
        must never kill the agent cycle.
        """
        if self._db is None:
            return
        try:
            async with self._journal_lock:
                self._db.add(
                    ToolCallLog(
                        session_id=self.session_id,
                        tool=tool,
                        database=database,
                        args_json=arguments if isinstance(arguments, dict) else None,
                        results_count=results_count,
                        latency_ms=latency_ms,
                        status=status,
                        error=error,
                    )
                )
                await self._db.commit()
        except Exception:
            logger.warning(
                "Failed to journal tool call (session=%d tool=%s status=%s)",
                self.session_id,
                tool,
                status,
                exc_info=True,
            )
            try:
                await self._db.rollback()
            except Exception:
                logger.warning(
                    "Rollback after journal failure also failed (session=%d)",
                    self.session_id,
                    exc_info=True,
                )

    async def _call_with_retry(
        self, name: str, arguments: dict[str, Any]
    ) -> McpCallResult:
        """One retry on timeout; protocol errors are logical; anything else
        means the gateway is broken (technical failure)."""
        try:
            return await self._transport.call_tool(name, arguments)
        except TimeoutError:
            logger.warning(
                "MCP call timed out, retrying once: session=%d tool=%s",
                self.session_id,
                name,
            )
            try:
                return await self._transport.call_tool(name, arguments)
            except TimeoutError:
                return McpCallResult(text=TOOL_TIMEOUT_MESSAGE, is_error=True)
        except Exception as exc:
            if MCPError is not None and isinstance(exc, MCPError):
                # JSON-RPC level error (unknown tool, bad params, ...) — the
                # gateway is alive; the model can fix the call.
                return McpCallResult(text=f"Error: {exc}", is_error=True)
            raise McpUnavailableError(f"MCP gateway broke mid-call: {exc}") from exc

    async def _throttle(self, bucket: str) -> None:
        """Per-database rate limit: at most one call per interval per bucket."""
        last = self._last_call_at.get(bucket)
        now = time.monotonic()
        if last is not None:
            wait = self.rate_limit_interval - (now - last)
            if wait > 0:
                await asyncio.sleep(wait)
        self._last_call_at[bucket] = time.monotonic()


def build_mcp_client(
    *,
    session_id: int,
    user_id: int,
    initial_used: int = 0,
    db: AsyncSession | None = None,
    teaser: bool = False,
) -> McpArchiveClient:
    """Production factory: real streamable-HTTP transport from settings.

    Kept as a module-level function so tests can monkeypatch it with a
    fake-transport client.
    """
    settings = get_settings()
    transport = StreamableHttpMcpTransport(
        url=f"{settings.jroots_mcp_url.rstrip('/')}/mcp",
        token=settings.jroots_mcp_token,
        timeout_seconds=settings.jroots_mcp_timeout_seconds,
    )
    return McpArchiveClient(
        transport,
        session_id=session_id,
        user_id=user_id,
        initial_used=initial_used,
        max_calls=settings.mcp_tool_call_cap,
        rate_limit_interval=settings.mcp_rate_limit_per_db_seconds,
        db=db,
        teaser=teaser,
    )
