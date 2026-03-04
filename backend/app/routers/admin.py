import logging
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
from starlette import status

from app.config import get_settings
from app.database import get_db
from app.models import SearchObject, Image, ImageSource, User
from app.schemas import SearchObjectSchema, PaginatedResults, ImageSchema, ImageSourceSchema
from app.services.auth import get_current_admin
from app.services.image import save_unique_image, create_search_object

logger = logging.getLogger("jroots")

router = APIRouter(prefix="/api/admin", tags=["admin"])


@router.post("/images", response_model=ImageSchema)
async def create_image(
    image_path: str = Form(...),
    image_key: str = Form(...),
    image_source_id: Optional[int] = Form(None),
    image_file: UploadFile = File(...),
    image_file_sha512: str = Form(...),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_admin),
):
    existing = await db.scalar(
        select(Image)
        .options(selectinload(Image.source))
        .where(Image.sha512_hash == image_file_sha512)
    )
    if existing:
        return existing

    image_binary = await image_file.read()
    max_bytes = get_settings().max_upload_size_mb * 1024 * 1024
    if len(image_binary) > max_bytes:
        raise HTTPException(status_code=413, detail="File too large")
    return await save_unique_image(db, image_path, image_key, image_source_id, image_binary)


@router.post("/objects", response_model=SearchObjectSchema)
async def create_object(
    text_content: str = Form(...),
    price: int = Form(...),
    image_path: Optional[str] = Form(None),
    image_key: Optional[str] = Form(None),
    image_source_id: Optional[int] = Form(None),
    image_file: Optional[UploadFile] = File(None),
    image_file_sha512: Optional[str] = Form(None),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_admin),
):
    has_existing_image = image_file_sha512 is not None
    has_new_image_data = image_path is not None and image_key is not None

    if not has_existing_image and not has_new_image_data:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="You must provide either 'image_file_sha512' OR both 'image_path' and 'image_key'.",
        )

    if has_new_image_data and not image_file:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="'image_file' is required when providing 'image_path' and 'image_key' without 'image_file_sha512'.",
        )

    image = await create_image(
        image_path, image_key, image_source_id, image_file, image_file_sha512, db, user,
    )
    return await create_search_object(db, text_content, price, image.id)


@router.get("/objects", response_model=PaginatedResults)
async def list_objects(
    skip: int = 0,
    limit: int = 20,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_admin),
):
    limit = min(limit, 100)
    total = await db.scalar(select(func.count()).select_from(SearchObject))

    result = await db.execute(
        select(SearchObject)
        .options(selectinload(SearchObject.image).selectinload(Image.source))
        .offset(skip)
        .limit(limit)
        .order_by(SearchObject.created_at.desc())
    )

    objects = result.scalars().all()
    objects_with_urls = []

    for obj in objects:
        obj_data = SearchObjectSchema.model_validate(obj)
        if obj.image:
            obj_data.image_id = obj.image.id
            obj_data.thumbnail_url = f"/api/images/{obj.image.id}/thumbnail"
        objects_with_urls.append(obj_data)

    return {"items": objects_with_urls, "total": total}


@router.put("/objects/{object_id}", response_model=SearchObjectSchema)
async def update_object(
    object_id: int,
    text_content: str = Form(...),
    price: int = Form(...),
    image_path: str = Form(...),
    image_key: str = Form(...),
    image_source_id: int | None = Form(None),
    image_file: UploadFile | None = File(None),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_admin),
):
    obj = await db.get(SearchObject, object_id)
    if not obj:
        raise HTTPException(status_code=404, detail="Object not found")

    obj.text_content = text_content
    obj.price = price

    if image_file:
        image_binary = await image_file.read()
        image = await save_unique_image(db, image_path, image_key, image_source_id, image_binary)
        obj.image_id = image.id

    await db.commit()
    await db.refresh(obj, attribute_names=["image"])

    if obj.image:
        await db.refresh(obj.image, attribute_names=["source"])

    return obj


@router.delete("/objects/{object_id}")
async def delete_object(
    object_id: int,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_admin),
):
    obj = await db.get(SearchObject, object_id)
    if not obj:
        raise HTTPException(status_code=404, detail="Object not found")
    await db.delete(obj)
    await db.commit()
    return {"status": "deleted", "object_id": object_id}


@router.get("/image-sources", response_model=list[ImageSourceSchema])
async def list_image_sources(
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_admin),
):
    result = await db.execute(select(ImageSource))
    return result.scalars().all()
