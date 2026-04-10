import logging

import certifi
import httpx
import sentry_sdk
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_fixed

from app.config import get_settings

logger = logging.getLogger("jroots")


@retry(
    stop=stop_after_attempt(3),
    wait=wait_fixed(1),
    retry=retry_if_exception_type((httpx.ConnectError, httpx.ReadTimeout, httpx.RequestError)),
)
async def send_email(to_email: str, subject: str, html_content: str):
    settings = get_settings()
    headers = {
        "Authorization": f"Bearer {settings.resend_api_key}",
        "Content-Type": "application/json",
    }
    payload = {
        "from": "JRoots <noreply@jroots.co>",
        "to": [to_email],
        "subject": subject,
        "html": html_content,
    }

    try:
        async with httpx.AsyncClient(verify=certifi.where(), timeout=10.0) as client:
            response = await client.post("https://api.resend.com/emails", json=payload, headers=headers)

        if response.status_code != 200:
            error_msg = f"Resend API error: {response.status_code} {response.text}"
            logger.error("Failed to send email to %s: %s", to_email, error_msg)
            sentry_sdk.capture_message(error_msg, level="error")
            await _notify_telegram(f"Email delivery failed to {to_email}: {response.status_code}")
            raise RuntimeError(error_msg)

        logger.info("Email sent to %s: %s", to_email, subject)
        return response.json()

    except httpx.RequestError as exc:
        logger.error("Network error sending email to %s: %s", to_email, exc)
        sentry_sdk.capture_exception(exc)
        raise


async def _notify_telegram(message: str):
    """Best-effort alert to admin Telegram chat."""
    settings = get_settings()
    if not settings.telegram_bot_token or not settings.telegram_chat_id:
        return
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            await client.post(
                f"https://api.telegram.org/bot{settings.telegram_bot_token}/sendMessage",
                json={"chat_id": settings.telegram_chat_id, "text": f"⚠️ {message}"},
            )
    except Exception:
        pass  # alert is best-effort, don't fail the caller
