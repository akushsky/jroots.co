import logging

import certifi
import httpx
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

    async with httpx.AsyncClient(verify=certifi.where(), timeout=10.0) as client:
        response = await client.post("https://api.resend.com/emails", json=payload, headers=headers)

    if response.status_code != 200:
        raise RuntimeError(f"Failed to send email: {response.status_code} {response.text}")

    return response.json()
