import asyncio
import base64
import hashlib
import hmac
import logging
import os
from io import BytesIO

import PIL
from PIL import Image as PILImage, ImageDraw, ImageFont, ImageOps
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.config import get_settings
from app.models import Image, ImagePurchase, SearchObject

logger = logging.getLogger("jroots")


def _apply_watermark_sync(original: PILImage.Image) -> PILImage.Image:
    watermark = PIL.Image.new("RGBA", original.size, (255, 255, 255, 0))

    font_size = max(original.width // 20, 30)
    font_path = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"
    try:
        font = ImageFont.truetype(font_path, font_size)
    except OSError:
        font = ImageFont.load_default()

    watermark_text = "JRoots.co"
    opacity = 150

    single_watermark = PIL.Image.new(
        "RGBA", (font_size * len(watermark_text), font_size + 10), (255, 255, 255, 0)
    )
    single_draw = ImageDraw.Draw(single_watermark)
    single_draw.text((0, 0), watermark_text, font=font, fill=(255, 255, 255, opacity))

    angle = 30
    rotated_watermark = single_watermark.rotate(angle, expand=True)

    spacing_x = rotated_watermark.width
    spacing_y = rotated_watermark.height // 2

    for x in range(-rotated_watermark.width, original.width + rotated_watermark.width, spacing_x):
        for y in range(-rotated_watermark.height, original.height + rotated_watermark.height, spacing_y):
            watermark.alpha_composite(rotated_watermark, (x, y))

    watermarked = PIL.Image.alpha_composite(original, watermark).convert("RGB")
    return watermarked


async def apply_watermark(original: PILImage.Image) -> PILImage.Image:
    return await asyncio.to_thread(_apply_watermark_sync, original)


def generate_etag(image: Image, has_access: bool) -> str:
    settings = get_settings()
    access_key = "full" if has_access else "watermarked"
    payload = f"{access_key}-{image.sha512_hash}"
    signature = hmac.new(settings.secret_key.encode(), payload.encode(), hashlib.sha256).digest()
    return base64.urlsafe_b64encode(signature).decode()


def _create_thumbnail_sync(image_binary: bytes) -> bytes:
    original_image = PILImage.open(BytesIO(image_binary))
    original_image = ImageOps.exif_transpose(original_image)
    original_image.thumbnail((200, 200))
    original_image = original_image.convert("RGB")
    thumbnail_buffer = BytesIO()
    original_image.save(thumbnail_buffer, format="JPEG")
    return thumbnail_buffer.getvalue()


def _save_to_disk(media_path: str, sha512_hash: str, image_binary: bytes, thumbnail_binary: bytes) -> tuple[str, str]:
    os.makedirs(media_path, exist_ok=True)
    image_file_path = os.path.join(media_path, f"{sha512_hash}.jpg")
    thumbnail_file_path = os.path.join(media_path, f"{sha512_hash}_thumb.jpg")
    with open(image_file_path, "wb") as f:
        f.write(image_binary)
    with open(thumbnail_file_path, "wb") as f:
        f.write(thumbnail_binary)
    return image_file_path, thumbnail_file_path


async def save_unique_image(
    db: AsyncSession,
    image_path: str,
    image_key: str,
    image_source_id: int | None,
    image_binary: bytes,
) -> Image:
    sha512_hash = hashlib.sha512(image_binary).hexdigest()

    existing_image = await db.execute(
        select(Image).options(selectinload(Image.source)).where(Image.sha512_hash == sha512_hash)
    )
    existing = existing_image.scalar_one_or_none()
    if existing:
        return existing

    thumbnail_binary = await asyncio.to_thread(_create_thumbnail_sync, image_binary)

    settings = get_settings()
    image_file_path, thumbnail_file_path = await asyncio.to_thread(
        _save_to_disk, settings.media_path, sha512_hash, image_binary, thumbnail_binary,
    )

    new_image = Image(
        image_path=image_path,
        image_key=image_key,
        image_source_id=image_source_id,
        image_data=image_binary,
        thumbnail_data=thumbnail_binary,
        sha512_hash=sha512_hash,
        image_file_path=image_file_path,
        thumbnail_file_path=thumbnail_file_path,
    )
    db.add(new_image)
    await db.commit()

    result = await db.execute(
        select(Image).options(selectinload(Image.source)).where(Image.id == new_image.id)
    )
    return result.scalar_one()


async def create_search_object(db: AsyncSession, text_content: str, price: int, image_id: int) -> SearchObject:
    obj = SearchObject(text_content=text_content, price=price, image_id=image_id)
    db.add(obj)
    await db.commit()

    result = await db.execute(
        select(SearchObject)
        .options(selectinload(SearchObject.image).selectinload(Image.source))
        .where(SearchObject.id == obj.id)
    )
    return result.scalar_one()


async def user_has_access_to_image(db: AsyncSession, user_id: int, image_id: int) -> bool:
    result = await db.execute(
        select(ImagePurchase).where(
            ImagePurchase.user_id == user_id,
            ImagePurchase.image_id == image_id,
        )
    )
    return result.scalars().first() is not None
