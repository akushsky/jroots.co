from datetime import date
from decimal import Decimal
from types import SimpleNamespace

import httpx
import openai
import pytest
from sqlalchemy import select

from app.config import get_settings
from app.models import DailyBudget, Payment, Subscription
from app.services import llm_router


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
def fake_client(monkeypatch):
    def install(chunks=None, error=None):
        client = _FakeClient(chunks, error)
        monkeypatch.setattr(llm_router, "_client", client)
        return client

    yield install
    monkeypatch.setattr(llm_router, "_client", None)


async def _collect(gen):
    return [item async for item in gen]


def test_select_model_defaults_to_main():
    assert llm_router.select_model({}) == get_settings().llm_model_main
    assert llm_router.select_model(None) == get_settings().llm_model_main


def test_select_model_escalation_flags():
    settings = get_settings()
    assert llm_router.select_model({"escalate": True}) == settings.llm_model_escalation
    assert (
        llm_router.select_model({"empty_searches": 3}) == settings.llm_model_escalation
    )
    assert llm_router.select_model({"generations": 5}) == settings.llm_model_escalation
    assert (
        llm_router.select_model({"empty_searches": 2, "generations": 1})
        == settings.llm_model_main
    )


def test_is_token_capped(monkeypatch):
    settings = get_settings()
    monkeypatch.setattr(settings, "llm_token_cap_per_session", 1000)
    assert not llm_router.is_token_capped(999)
    assert llm_router.is_token_capped(1000)
    assert llm_router.is_token_capped(1500)
    assert not llm_router.is_token_capped(None)


def test_estimate_cost_usd():
    settings = get_settings()
    cost = llm_router.estimate_cost_usd(1_000_000, 1_000_000)
    expected = Decimal(
        str(round(settings.llm_price_in_per_1m + settings.llm_price_out_per_1m, 6))
    )
    assert cost == expected
    assert llm_router.estimate_cost_usd(0, 0) == Decimal("0.0")


async def test_stream_completion_yields_tokens_and_usage(fake_client):
    fake_client(
        [
            _chunk("Шалом"),
            _chunk(", мир"),
            _chunk(usage=SimpleNamespace(prompt_tokens=12, completion_tokens=7)),
        ]
    )
    items = await _collect(
        llm_router.stream_completion([{"role": "user", "content": "hi"}], "kimi-k2.6")
    )
    assert items[0] == {"type": "token", "text": "Шалом"}
    assert items[1] == {"type": "token", "text": ", мир"}
    assert items[-1] == {"type": "usage", "prompt_tokens": 12, "completion_tokens": 7}


async def test_stream_completion_estimates_usage_when_missing(fake_client):
    fake_client([_chunk("ответ")])
    items = await _collect(
        llm_router.stream_completion(
            [{"role": "user", "content": "вопрос"}], "kimi-k2.6"
        )
    )
    usage = items[-1]
    assert usage["type"] == "usage"
    assert usage["prompt_tokens"] >= 1
    assert usage["completion_tokens"] >= 1


async def test_stream_completion_propagates_errors(fake_client):
    fake_client(error=RuntimeError("boom"))
    with pytest.raises(RuntimeError):
        await _collect(
            llm_router.stream_completion([{"role": "user", "content": "x"}], "m")
        )


async def test_is_free_user(db_session):
    assert await llm_router.is_free_user(db_session, 1) is True

    db_session.add(
        Payment(
            provider="stripe",
            provider_payment_id="p-failed",
            user_id=1,
            status="failed",
        )
    )
    await db_session.commit()
    assert await llm_router.is_free_user(db_session, 1) is True

    db_session.add(
        Payment(
            provider="stripe",
            provider_payment_id="p-ok",
            user_id=1,
            status="succeeded",
        )
    )
    await db_session.commit()
    assert await llm_router.is_free_user(db_session, 1) is False

    db_session.add(Subscription(user_id=2, provider="stripe", status="active"))
    await db_session.commit()
    assert await llm_router.is_free_user(db_session, 2) is False

    db_session.add(Subscription(user_id=3, provider="stripe", status="canceled"))
    await db_session.commit()
    assert await llm_router.is_free_user(db_session, 3) is True


async def test_record_daily_spend_upserts_and_accumulates(db_session):
    today = date.today()
    await llm_router.record_daily_spend(db_session, Decimal("1.5"))
    await llm_router.record_daily_spend(db_session, Decimal("2.25"))
    await db_session.commit()

    result = await db_session.execute(
        select(DailyBudget).where(DailyBudget.day == today)
    )
    row = result.scalar_one()
    assert row.free_spend_usd == Decimal("3.75")

    assert await llm_router.get_daily_free_spend(db_session) == Decimal("3.75")


async def test_record_daily_spend_ignores_nonpositive(db_session):
    await llm_router.record_daily_spend(db_session, Decimal("0"))
    await db_session.commit()
    assert await llm_router.get_daily_free_spend(db_session) == Decimal("0")


async def test_is_daily_budget_exceeded(db_session, monkeypatch):
    settings = get_settings()
    monkeypatch.setattr(settings, "free_daily_budget_usd", 10.0)
    assert await llm_router.is_daily_budget_exceeded(db_session) is False

    await llm_router.record_daily_spend(db_session, Decimal("10.0"))
    await db_session.commit()
    assert await llm_router.is_daily_budget_exceeded(db_session) is True


# --- Stream-establishment retry ----------------------------------------------


def _http_request():
    return httpx.Request("POST", "https://api.moonshot.ai/v1/chat/completions")


def _conn_error():
    return openai.APIConnectionError(request=_http_request())


def _rate_limit_error():
    return openai.RateLimitError(
        "rate limited",
        response=httpx.Response(429, request=_http_request()),
        body=None,
    )


def _bad_request_error():
    return openai.BadRequestError(
        "bad request",
        response=httpx.Response(400, request=_http_request()),
        body=None,
    )


class _RetryScriptedCompletions:
    """create() consumes scripted entries: an exception to raise, a chunk
    list to stream, or (chunks, error) to fail mid-stream."""

    def __init__(self, script):
        self._script = list(script)
        self.calls = 0

    async def create(self, **kwargs):
        self.calls += 1
        item = self._script.pop(0)
        if isinstance(item, Exception):
            raise item
        chunks, mid_error = item if isinstance(item, tuple) else (item, None)

        async def gen():
            for chunk in chunks:
                yield chunk
            if mid_error is not None:
                raise mid_error

        return gen()


@pytest.fixture
def scripted_client(monkeypatch):
    def install(script):
        client = SimpleNamespace(
            chat=SimpleNamespace(completions=_RetryScriptedCompletions(script))
        )
        monkeypatch.setattr(llm_router, "_client", client)
        return client

    yield install
    monkeypatch.setattr(llm_router, "_client", None)


@pytest.fixture
def no_backoff(monkeypatch):
    calls = []

    async def _noop(attempt):
        calls.append(attempt)

    monkeypatch.setattr(llm_router, "_retry_backoff", _noop)
    return calls


async def test_stream_establishment_retries_connection_errors(
    scripted_client, no_backoff
):
    client = scripted_client([_conn_error(), _conn_error(), [_chunk("ок")]])
    items = await _collect(
        llm_router.stream_completion([{"role": "user", "content": "hi"}], "m")
    )
    assert items[0] == {"type": "token", "text": "ок"}
    assert client.chat.completions.calls == 3
    assert no_backoff == [0, 1]  # backoff after attempt 1 and 2


async def test_stream_establishment_gives_up_after_max_attempts(
    scripted_client, no_backoff
):
    client = scripted_client([_conn_error(), _conn_error(), _conn_error()])
    with pytest.raises(openai.APIConnectionError):
        await _collect(
            llm_router.stream_completion([{"role": "user", "content": "hi"}], "m")
        )
    assert client.chat.completions.calls == 3
    assert no_backoff == [0, 1]


async def test_stream_establishment_retries_rate_limit(scripted_client, no_backoff):
    client = scripted_client([_rate_limit_error(), [_chunk("ок")]])
    items = await _collect(
        llm_router.stream_completion([{"role": "user", "content": "hi"}], "m")
    )
    assert items[0] == {"type": "token", "text": "ок"}
    assert client.chat.completions.calls == 2


async def test_bad_request_is_not_retried(scripted_client, no_backoff):
    client = scripted_client([_bad_request_error(), [_chunk("ок")]])
    with pytest.raises(openai.BadRequestError):
        await _collect(
            llm_router.stream_completion([{"role": "user", "content": "hi"}], "m")
        )
    assert client.chat.completions.calls == 1
    assert no_backoff == []


async def test_error_after_first_chunk_is_not_retried(scripted_client, no_backoff):
    # The stream established and produced a token — a later failure must
    # propagate without retry (a retry would duplicate the emitted text).
    mid_stream_failure = ([_chunk("начало")], _conn_error())
    client = scripted_client([mid_stream_failure])
    with pytest.raises(openai.APIConnectionError):
        await _collect(
            llm_router.stream_completion([{"role": "user", "content": "hi"}], "m")
        )
    assert client.chat.completions.calls == 1
    assert no_backoff == []


# --- Gemini OpenAI-compat quirks ---------------------------------------------


def _tool_delta(index, call_id=None, name=None, arguments=None, extra_content=None):
    return SimpleNamespace(
        index=index,
        id=call_id,
        function=SimpleNamespace(name=name, arguments=arguments),
        extra_content=extra_content,
    )


def _tool_chunk(tool_calls, usage=None):
    delta = SimpleNamespace(content=None, tool_calls=tool_calls)
    return SimpleNamespace(choices=[SimpleNamespace(delta=delta)], usage=usage)


def _clear_model_env(monkeypatch):
    """conftest hard-sets model/price for suite stability — drop them here."""
    for key in (
        "LLM_MODEL_MAIN",
        "LLM_MODEL_ESCALATION",
        "LLM_PRICE_IN_PER_1M",
        "LLM_PRICE_OUT_PER_1M",
        "LLM_PROVIDER",
    ):
        monkeypatch.delenv(key, raising=False)


def test_provider_profile_fills_gemini_defaults(monkeypatch):
    from app.config import Settings

    _clear_model_env(monkeypatch)
    settings = Settings(
        secret_key="x",
        admin_password="x",
        database_url="sqlite+aiosqlite:///:memory:",
        llm_provider="gemini",
    )
    assert settings.llm_model_main == "gemini-3.1-pro-preview"
    assert settings.llm_model_escalation == "gemini-3.1-pro-preview"
    assert settings.llm_price_in_per_1m == 2.0
    assert settings.llm_price_out_per_1m == 12.0


def test_provider_profile_fills_moonshot_defaults(monkeypatch):
    from app.config import Settings

    _clear_model_env(monkeypatch)
    settings = Settings(
        secret_key="x",
        admin_password="x",
        database_url="sqlite+aiosqlite:///:memory:",
        llm_provider="moonshot",
    )
    assert settings.llm_model_main == "kimi-k2.6"
    assert settings.llm_model_escalation == "kimi-k3"
    assert settings.llm_price_in_per_1m == 0.95


def test_provider_profile_keeps_explicit_model_override(monkeypatch):
    from app.config import Settings

    _clear_model_env(monkeypatch)
    settings = Settings(
        secret_key="x",
        admin_password="x",
        database_url="sqlite+aiosqlite:///:memory:",
        llm_provider="gemini",
        llm_model_main="custom-model",
    )
    assert settings.llm_model_main == "custom-model"
    assert settings.llm_model_escalation == "gemini-3.1-pro-preview"


def test_get_llm_client_uses_gemini_credentials(monkeypatch):
    monkeypatch.setattr(llm_router, "_client", None)
    settings = get_settings()
    monkeypatch.setattr(settings, "llm_provider", "gemini")
    monkeypatch.setattr(settings, "google_api_key", "gemini-key")
    monkeypatch.setattr(
        settings, "gemini_base_url", "https://example.com/v1beta/openai/"
    )
    client = llm_router.get_llm_client()
    assert client.api_key == "gemini-key"
    assert "example.com/v1beta/openai" in str(client.base_url)
    monkeypatch.setattr(llm_router, "_client", None)


def test_get_llm_client_uses_moonshot_credentials(monkeypatch):
    monkeypatch.setattr(llm_router, "_client", None)
    settings = get_settings()
    monkeypatch.setattr(settings, "llm_provider", "moonshot")
    monkeypatch.setattr(settings, "moonshot_api_key", "moon-key")
    monkeypatch.setattr(settings, "moonshot_base_url", "https://api.moonshot.ai/v1")
    client = llm_router.get_llm_client()
    assert client.api_key == "moon-key"
    assert "api.moonshot.ai" in str(client.base_url)
    monkeypatch.setattr(llm_router, "_client", None)


async def test_stream_completion_splits_parallel_calls_when_index_none(fake_client):
    """Gemini omits tool-call index — two id'd deltas must not collapse."""
    fake_client(
        [
            _tool_chunk(
                [
                    _tool_delta(
                        None,
                        "call_a",
                        "search",
                        '{"database":"gabo"}',
                        extra_content={"google": {"thought_signature": "sig-a"}},
                    )
                ]
            ),
            _tool_chunk(
                [
                    _tool_delta(
                        None,
                        "call_b",
                        "search",
                        '{"database":"dako"}',
                        extra_content={"google": {"thought_signature": "sig-b"}},
                    )
                ]
            ),
            _chunk(
                usage=SimpleNamespace(
                    prompt_tokens=10, completion_tokens=4, total_tokens=14
                )
            ),
        ]
    )
    items = await _collect(
        llm_router.stream_completion([{"role": "user", "content": "hi"}], "m", tools=[])
    )
    tool_event = next(item for item in items if item["type"] == "tool_calls")
    assert len(tool_event["tool_calls"]) == 2
    assert tool_event["tool_calls"][0]["id"] == "call_a"
    assert tool_event["tool_calls"][1]["id"] == "call_b"
    assert tool_event["tool_calls"][0]["extra_content"] == {
        "google": {"thought_signature": "sig-a"}
    }
    assert tool_event["tool_calls"][1]["extra_content"] == {
        "google": {"thought_signature": "sig-b"}
    }


async def test_stream_completion_counts_thinking_tokens_in_usage(fake_client):
    """Gemini: total >> prompt+completion because thinking is billed as output."""
    fake_client(
        [
            _chunk("ok"),
            _chunk(
                usage=SimpleNamespace(
                    prompt_tokens=87, completion_tokens=33, total_tokens=536
                )
            ),
        ]
    )
    items = await _collect(
        llm_router.stream_completion([{"role": "user", "content": "hi"}], "m")
    )
    usage = items[-1]
    assert usage["prompt_tokens"] == 87
    assert usage["completion_tokens"] == 536 - 87


async def test_stream_completion_passes_reasoning_effort(monkeypatch):
    settings = get_settings()
    monkeypatch.setattr(settings, "llm_reasoning_effort", "low")
    captured = {}

    class _Spy:
        async def create(self, **kwargs):
            captured.update(kwargs)

            async def gen():
                yield _chunk("ok")

            return gen()

    monkeypatch.setattr(
        llm_router,
        "_client",
        SimpleNamespace(chat=SimpleNamespace(completions=_Spy())),
    )
    await _collect(
        llm_router.stream_completion([{"role": "user", "content": "hi"}], "m")
    )
    assert captured.get("reasoning_effort") == "low"
    monkeypatch.setattr(llm_router, "_client", None)
