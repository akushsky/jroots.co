from unittest.mock import MagicMock

import respx
import httpx

from app.models import Image
from app.services.telegram import send_photo_to_chat, answer_callback_query, edit_message_caption

BOT_BASE = "https://api.telegram.org/bottest-bot-token"


def _make_image(telegram_file_id=None, image_data=b"fakejpeg"):
    img = MagicMock(spec=Image)
    img.telegram_file_id = telegram_file_id
    img.image_data = image_data
    return img


@respx.mock
async def test_send_photo_with_file_id():
    image = _make_image(telegram_file_id="existing_fid")
    route = respx.post(f"{BOT_BASE}/sendPhoto").mock(
        return_value=httpx.Response(200, json={"ok": True})
    )
    resp = await send_photo_to_chat(image, "caption", {"inline_keyboard": []})
    assert route.called
    assert resp.status_code == 200


@respx.mock
async def test_send_photo_with_binary():
    image = _make_image(telegram_file_id=None, image_data=b"\xff\xd8\xff")
    route = respx.post(f"{BOT_BASE}/sendPhoto").mock(
        return_value=httpx.Response(200, json={"ok": True})
    )
    resp = await send_photo_to_chat(image, "caption", {"inline_keyboard": []})
    assert route.called
    assert resp.status_code == 200


@respx.mock
async def test_answer_callback_query():
    route = respx.post(f"{BOT_BASE}/answerCallbackQuery").mock(
        return_value=httpx.Response(200, json={"ok": True})
    )
    await answer_callback_query("qid123")
    assert route.called


@respx.mock
async def test_edit_message_caption():
    route = respx.post(f"{BOT_BASE}/editMessageCaption").mock(
        return_value=httpx.Response(200, json={"ok": True})
    )
    await edit_message_caption(chat_id=1, message_id=2, caption="new cap")
    assert route.called
