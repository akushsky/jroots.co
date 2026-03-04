import logging
from typing import Optional

from fastapi import APIRouter, Depends, Header, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
from starlette.responses import Response

from app.config import get_settings
from app.database import get_db
from app.models import Image, ImagePurchase, User
from app.schemas import AccessRequest, Update
from app.services.auth import get_current_user_optional
from app.services.telegram import answer_callback_query, edit_message_caption, send_photo_to_chat

logger = logging.getLogger("jroots")

router = APIRouter(prefix="/api", tags=["telegram"])


@router.post("/request_access")
async def request_access(
    data: AccessRequest,
    db: AsyncSession = Depends(get_db),
    current_user: Optional[User] = Depends(get_current_user_optional),
):
    settings = get_settings()

    if not current_user or not current_user.is_verified:
        raise HTTPException(status_code=403, detail="Email not verified")

    if not settings.telegram_bot_token or not settings.telegram_chat_id:
        raise HTTPException(status_code=500, detail="Telegram configuration missing.")

    logger.info(
        "User %s requested full access to image with ID %d",
        current_user.email, data.image_id,
    )

    result = await db.execute(
        select(Image).options(selectinload(Image.source)).where(Image.id == data.image_id)
    )
    image = result.scalars().first()
    if not image:
        raise HTTPException(status_code=404, detail="Image not found")

    telegram_line = f"✈️ Telegram: @{current_user.telegram_username}" if current_user.telegram_username else ""
    caption = "\n".join(filter(None, [
        "📨 Новый запрос на доступ",
        f"👤 Пользователь: {current_user.username} ({current_user.email})",
        telegram_line,
        f"💬 Внезапный еврей: {data.search_text_content}",
        f"🖼️ Изображение: {image.image_key}",
        f"📁 Шифр: {image.image_path}",
        f"📚 Источник: {image.source.source_name if image.source else 'Неизвестен'}",
    ]))

    callback_data_approve = f"approve:{image.id}:{current_user.email}"
    callback_data_deny = f"deny:{image.id}:{current_user.email}"

    if len(callback_data_approve.encode("utf-8")) > 64 or len(callback_data_deny.encode("utf-8")) > 64:
        logger.error("Callback data is too long.")
        raise HTTPException(status_code=500, detail="Generated request data is too long for Telegram.")

    reply_markup = {
        "inline_keyboard": [
            [
                {"text": "✅ Разрешить", "callback_data": callback_data_approve},
                {"text": "❌ Отклонить", "callback_data": callback_data_deny},
            ]
        ]
    }

    response = await send_photo_to_chat(image, caption, reply_markup)

    if response.status_code == 200 and not image.telegram_file_id:
        try:
            resp_data = response.json()
            file_id = resp_data["result"]["photo"][-1]["file_id"]
            image.telegram_file_id = file_id
            await db.commit()
            logger.info("Updated image %s with telegram file_id", image.id)
        except (KeyError, IndexError, TypeError):
            logger.exception("Failed to extract file_id from Telegram response")

    if response.status_code != 200:
        raise HTTPException(status_code=500, detail="Не удалось отправить сообщение в Telegram.")

    return {"ok": True}


@router.post("/admin/access")
async def handle_access_decision(
    update: Update,
    db: AsyncSession = Depends(get_db),
    x_telegram_bot_api_secret_token: Optional[str] = Header(default=None),
):
    settings = get_settings()
    if settings.telegram_webhook_secret:
        if x_telegram_bot_api_secret_token != settings.telegram_webhook_secret:
            raise HTTPException(status_code=403, detail="Invalid webhook secret")

    if not update.callback_query:
        return Response(status_code=200)

    callback_query = update.callback_query
    callback_data = callback_query.data
    admin_user = callback_query.from_user

    logger.info("Received callback from %s (%s): %s", admin_user.username, admin_user.id, callback_data)

    await answer_callback_query(callback_query.id)

    try:
        action, image_id_str, user_email = callback_data.split(":", 2)
        image_id = int(image_id_str)
    except (ValueError, IndexError) as e:
        logger.error("Could not parse callback_data: '%s'. Error: %s", callback_data, e)
        return Response(status_code=400)

    if action == "deny":
        logger.info("Denying access for %s to image %d by admin %s", user_email, image_id, admin_user.username)
        new_text = f"❌ ДОСТУП ОТКЛОНЕН для {user_email} (админом @{admin_user.username})"
        await _update_access_request_message(callback_query, new_text)
        return Response(status_code=200)

    if action != "approve":
        logger.error("Unknown action '%s' in callback_data: '%s'", action, callback_data)
        return Response(status_code=400)

    user_result = await db.execute(select(User).where(User.email == user_email))
    user_to_grant_access = user_result.scalars().first()

    if user_to_grant_access is None:
        logger.error("User with email '%s' not found when granting access", user_email)
        return Response(status_code=404)

    existing_purchase_result = await db.execute(
        select(ImagePurchase).where(
            ImagePurchase.user_id == user_to_grant_access.id,
            ImagePurchase.image_id == image_id,
        )
    )
    existing_purchase = existing_purchase_result.scalars().first()

    if existing_purchase:
        logger.info("Image %d already purchased by user %d", image_id, user_to_grant_access.id)
    else:
        new_image_purchase = ImagePurchase(user_id=user_to_grant_access.id, image_id=image_id)
        db.add(new_image_purchase)
        logger.info("Created new ImagePurchase for user %d, image %d", user_to_grant_access.id, image_id)

    try:
        await db.commit()
        logger.info("Access granted for image %d to user '%s'", image_id, user_to_grant_access.email)
    except Exception:
        await db.rollback()
        logger.exception("Database commit failed while granting access")
        raise HTTPException(status_code=500, detail="Failed to save changes.")

    new_text = f"✅ ДОСТУП ПРЕДОСТАВЛЕН для {user_to_grant_access.email} (админом @{admin_user.username})"
    await _update_access_request_message(callback_query, new_text)

    return Response(status_code=200)


async def _update_access_request_message(callback_query, new_text: str):
    if callback_query.message:
        original_caption = callback_query.message.caption or ""
        updated_caption = f"{original_caption}\n\n---\n{new_text}"
        await edit_message_caption(
            callback_query.message.chat.id,
            callback_query.message.message_id,
            updated_caption,
        )
