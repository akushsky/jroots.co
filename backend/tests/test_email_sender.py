import pytest
import respx
import httpx

from app.services.email import send_email


@pytest.mark.asyncio
@respx.mock
async def test_send_email_success():
    route = respx.post("https://api.resend.com/emails").mock(
        return_value=httpx.Response(200, json={"message": "Email sent"})
    )

    result = await send_email("test@example.com", "Test Subject", "<p>Hello</p>")

    assert route.called
    assert result == {"message": "Email sent"}


@pytest.mark.asyncio
@respx.mock
async def test_send_email_failure_raises_exception():
    respx.post("https://api.resend.com/emails").mock(
        return_value=httpx.Response(400, text="Bad Request")
    )

    with pytest.raises(RuntimeError, match="Failed to send email"):
        await send_email("test@example.com", "Test Subject", "<p>Hello</p>")


@pytest.mark.asyncio
@respx.mock
async def test_send_email_retry_on_connect_error():
    call_counter = {"count": 0}

    def fail_then_succeed(request):
        call_counter["count"] += 1
        if call_counter["count"] < 3:
            raise httpx.ConnectError("Connection failed", request=request)
        return httpx.Response(200, json={"message": "Success after retry"})

    respx.post("https://api.resend.com/emails").mock(side_effect=fail_then_succeed)

    result = await send_email("test@example.com", "Retry Subject", "<p>Retry</p>")

    assert result == {"message": "Success after retry"}
    assert call_counter["count"] == 3
