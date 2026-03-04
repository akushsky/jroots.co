import asyncio
import io
import logging
import os
from typing import Optional

from PIL import Image as PILImage, ImageOps
from fastapi import APIRouter, Depends, Header, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.responses import Response, StreamingResponse

from app.database import get_db
from app.models import Image, User
from app.services.auth import get_current_user_optional
from app.services.image import apply_watermark, generate_etag, user_has_access_to_image

logger = logging.getLogger("jroots")

router = APIRouter(prefix="/api/images", tags=["images"])


def _load_image_bytes(image: Image) -> bytes:
    """Load image bytes from filesystem first, then fall back to database."""
    if image.image_file_path and os.path.exists(image.image_file_path):
        with open(image.image_file_path, "rb") as f:
            return f.read()
    return image.image_data


def _load_thumbnail_bytes(image: Image) -> bytes | None:
    """Load thumbnail bytes from filesystem first, then fall back to database."""
    if image.thumbnail_file_path and os.path.exists(image.thumbnail_file_path):
        with open(image.thumbnail_file_path, "rb") as f:
            return f.read()
    return image.thumbnail_data


@router.get("/{image_id}", response_class=StreamingResponse)
async def get_image(
    image_id: int,
    db: AsyncSession = Depends(get_db),
    if_none_match: str | None = Header(default=None),
    current_user: Optional[User] = Depends(get_current_user_optional),
):
    logger.info(
        "User %s requested image with ID %d",
        current_user.email if current_user else "Anonymous", image_id,
    )
    if not current_user or not current_user.is_verified:
        raise HTTPException(status_code=403, detail="Email not verified")

    image = await db.get(Image, image_id)
    if not image:
        raise HTTPException(status_code=404, detail="Image not found")

    has_access = False
    if current_user:
        if current_user.is_admin:
            has_access = True
        else:
            has_access = await user_has_access_to_image(db, current_user.id, image_id)

    etag = generate_etag(image, has_access)

    if if_none_match == etag:
        return Response(status_code=304)

    image_bytes = await asyncio.to_thread(_load_image_bytes, image)
    original = PILImage.open(io.BytesIO(image_bytes))
    original = ImageOps.exif_transpose(original).convert("RGBA")

    result = original if has_access else await apply_watermark(original)

    if result.mode != "RGB":
        result = result.convert("RGB")

    buffer = io.BytesIO()
    result.save(buffer, format="JPEG")
    buffer.seek(0)

    headers = {
        "ETag": etag,
        "Cache-Control": "max-age=3600, must-revalidate",
    }

    logger.info(
        "Image with path '%s' and key '%s' opened by user %s",
        image.image_path, image.image_key, current_user.email,
    )

    return StreamingResponse(buffer, media_type="image/jpeg", headers=headers)


@router.get("/{image_id}/thumbnail", response_class=StreamingResponse)
async def get_thumbnail(image_id: int, db: AsyncSession = Depends(get_db)):
    image = await db.get(Image, image_id)
    if not image:
        raise HTTPException(status_code=404, detail="Thumbnail not found")

    thumbnail_bytes = await asyncio.to_thread(_load_thumbnail_bytes, image)
    if not thumbnail_bytes:
        raise HTTPException(status_code=404, detail="Thumbnail not found")

    headers = {"Cache-Control": "public, max-age=86400"}
    return StreamingResponse(io.BytesIO(thumbnail_bytes), media_type="image/jpeg", headers=headers)
