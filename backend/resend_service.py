import os

import certifi
import httpx
from tenacity import retry, stop_after_attempt, wait_fixed, retry_if_exception_type

RESEND_API_KEY = os.getenv("RESEND_API_KEY", "dev_key")
ENVIRONMENT = os.getenv("ENVIRONMENT", "development")

MAX_RETRIES = 3
RETRY_DELAY_SECONDS = 1

# Retry config: up to 3 attempts with 1-second delay, only for connection/read errors
@retry(
    stop=stop_after_attempt(3),
    wait=wait_fixed(1),
    retry=retry_if_exception_type((httpx.ConnectError, httpx.ReadTimeout, httpx.RequestError)),
)
async def send_email(to_email: str, subject: str, html_content: str):
    headers = {
        "Authorization": f"Bearer {RESEND_API_KEY}",
        "Content-Type": "application/json"
    }
    payload = {
        "from": "JRoots <noreply@jroots.co>",
        "to": [to_email],
        "subject": subject,
        "html": html_content
    }

    verify_ssl = False if ENVIRONMENT == "development" else certifi.where()

    async with httpx.AsyncClient(verify=verify_ssl, timeout=10.0) as client:
        response = await client.post("https://api.resend.com/emails", json=payload, headers=headers)

    if response.status_code != 200:
        raise Exception(f"Failed to send email: {response.status_code} {response.text}")

    return response.json()