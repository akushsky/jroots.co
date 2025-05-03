import pytest
import respx
import httpx
import certifi
from unittest.mock import patch, AsyncMock

from backend.resend_service import send_email


@respx.mock
async def test_send_email_success():
    route = respx.post("https://api.resend.com/emails").mock(
        return_value=httpx.Response(200, json={"message": "Email sent"})
    )

    result = await send_email("test@example.com", "Test Subject", "<p>Hello</p>")

    assert route.called
    assert result == {"message": "Email sent"}


@respx.mock
async def test_send_email_failure_raises_exception():
    respx.post("https://api.resend.com/emails").mock(
        return_value=httpx.Response(400, text="Bad Request")
    )

    with pytest.raises(Exception) as exc_info:
        await send_email("test@example.com", "Test Subject", "<p>Hello</p>")

    assert "Failed to send email" in str(exc_info.value)


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


async def test_send_email_uses_certifi_in_production():
    mock_response = AsyncMock()
    mock_response.__aenter__.return_value.post.return_value = httpx.Response(
        200, json={"message": "Secure email sent"}
    )

    with patch("backend.resend_service.ENVIRONMENT", "production"), \
            patch("backend.resend_service.httpx.AsyncClient", return_value=mock_response) as mock_client_class:
        result = await send_email("secure@example.com", "Secure Subject", "<p>Secure</p>")

        args, kwargs = mock_client_class.call_args
        assert kwargs["verify"] == certifi.where()
        assert result == {"message": "Secure email sent"}
