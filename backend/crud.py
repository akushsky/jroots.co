import hashlib
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from sqlalchemy.orm import selectinload

from PIL import Image as PILImage, ImageOps
from io import BytesIO

from models import Image, SearchObject


async def save_unique_image(db: AsyncSession,
                            image_path: str,
                            image_key: str,
                            image_source_id: int | None,
                            image_binary: bytes):
    sha512_hash = hashlib.sha512(image_binary).hexdigest()

    existing_image = await db.execute(select(Image).where(Image.sha512_hash == sha512_hash))
    existing = existing_image.scalar_one_or_none()

    if existing:
        return existing  # reuse existing image if binary already exists

    # Open original image and fix orientation
    original_image = PILImage.open(BytesIO(image_binary))
    original_image = ImageOps.exif_transpose(original_image)

    # Create thumbnail
    original_image.thumbnail((200, 200))  # 200px max size
    thumbnail_buffer = BytesIO()
    original_image.save(thumbnail_buffer, format="JPEG")
    thumbnail_binary = thumbnail_buffer.getvalue()

    new_image = Image(
        image_path=image_path,
        image_key=image_key,
        image_source_id=image_source_id,
        image_data=image_binary,
        thumbnail_data=thumbnail_binary,
        sha512_hash=sha512_hash
    )
    db.add(new_image)
    await db.commit()
    await db.refresh(new_image)
    return new_image


async def create_search_object(db: AsyncSession, text_content: str, image_path: str, image_id: int):
    obj = SearchObject(
        text_content=text_content,
        image_path=image_path,
        image_id=image_id
    )
    db.add(obj)
    await db.commit()

    # Reload object explicitly with image relationship
    result = await db.execute(
        select(SearchObject)
        .options(selectinload(SearchObject.image).selectinload(Image.source))
        .where(SearchObject.id == obj.id)
    )
    obj = result.scalar_one()

    return obj


async def fuzzy_search_objects(db: AsyncSession, query: str):
    stmt = (
        select(SearchObject)
        .where(func.similarity(SearchObject.text_content, query) > 0.3)
        .order_by(func.similarity(SearchObject.text_content, query).desc())
        .limit(20)
    )
    result = await db.execute(stmt)
    return result.scalars().all()
