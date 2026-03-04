import io
import json
import logging

import httpx

from app.config import get_settings
from app.models import Image

logger = logging.getLogger("jroots")


async def send_photo_to_chat(
    image: Image,
    caption: str,
    reply_markup: dict,
) -> httpx.Response:
    settings = get_settings()
    url = f"https://api.telegram.org/bot{settings.telegram_bot_token}/sendPhoto"

    async with httpx.AsyncClient(timeout=30.0) as client:
        if image.telegram_file_id:
            json_request = {
                "chat_id": settings.telegram_chat_id,
                "photo": image.telegram_file_id,
                "caption": caption,
                "reply_markup": reply_markup,
            }
            return await client.post(url, json=json_request)
        else:
            serialized_reply_markup = json.dumps(reply_markup)
            payload = {
                "chat_id": settings.telegram_chat_id,
                "caption": caption,
                "reply_markup": serialized_reply_markup,
            }
            files = {"photo": ("image.jpg", io.BytesIO(image.image_data), "image/jpeg")}
            return await client.post(url, data=payload, files=files)


async def answer_callback_query(callback_query_id: str) -> None:
    settings = get_settings()
    async with httpx.AsyncClient(timeout=10.0) as client:
        await client.post(
            f"https://api.telegram.org/bot{settings.telegram_bot_token}/answerCallbackQuery",
            json={"callback_query_id": callback_query_id},
        )


async def edit_message_caption(chat_id: int, message_id: int, caption: str) -> None:
    settings = get_settings()
    async with httpx.AsyncClient(timeout=10.0) as client:
        await client.post(
            f"https://api.telegram.org/bot{settings.telegram_bot_token}/editMessageCaption",
            json={
                "chat_id": chat_id,
                "message_id": message_id,
                "caption": caption,
                "reply_markup": {"inline_keyboard": []},
            },
        )
