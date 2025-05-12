import hashlib
from typing import Optional

from jose import jwt, JWTError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from PIL import Image as PILImage, ImageOps
from io import BytesIO

from config import SECRET_KEY, ALGORITHM
from models import Image, SearchObject, User, ImagePurchase


async def save_unique_image(db: AsyncSession,
                            image_path: str,
                            image_key: str,
                            image_source_id: int | None,
                            image_binary: bytes):
    sha512_hash = hashlib.sha512(image_binary).hexdigest()

    existing_image = await db.execute(
        select(Image).options(selectinload(Image.source)).where(Image.sha512_hash == sha512_hash))
    existing = existing_image.scalar_one_or_none()

    if existing:
        return existing  # reuse existing image if binary already exists

    # Open original image and fix orientation
    original_image = PILImage.open(BytesIO(image_binary))
    original_image = ImageOps.exif_transpose(original_image)

    # Create thumbnail
    original_image.thumbnail((200, 200))  # 200px max size
    original_image = original_image.convert('RGB')  # Convert to RGB if not already
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

    result = await db.execute(
        select(Image).options(selectinload(Image.source)).where(Image.id == new_image.id)
    )
    new_image = result.scalar_one()

    return new_image


async def create_search_object(db: AsyncSession, text_content: str, price: int, image_id: int):
    obj = SearchObject(
        text_content=text_content,
        price=price,
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


async def resolve_user_from_token(token: Optional[str], db: AsyncSession) -> Optional[User]:
    if not token:
        return None
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        email: str = payload.get("sub")
        if email is None:
            return None
        result = await db.execute(select(User).where(User.email == email))
        return result.scalar_one_or_none()
    except JWTError:
        return None


async def user_has_access_to_image(db: AsyncSession, user_id: int, image_id: int) -> bool:
    result = await db.execute(
        select(ImagePurchase).where(
            ImagePurchase.user_id == user_id,
            ImagePurchase.image_id == image_id
        )
    )
    return result.scalar() is not None
