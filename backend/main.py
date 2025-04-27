import io
from os import getenv
from typing import Optional

from PIL import Image, ImageFont, ImageDraw, ImageOps
from fastapi import FastAPI, Depends, HTTPException, status, UploadFile, File, Form
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy import select, func, or_, text
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
from starlette.responses import StreamingResponse

import auth
import crud
import database
import models
import schemas

app = FastAPI()

origins = getenv("CORS_ORIGINS", "*").split(",")

# noinspection PyTypeChecker
app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("startup")
async def startup():
    async with database.engine.begin() as conn:
        await conn.run_sync(models.Base.metadata.create_all)


@app.get("/api/search", response_model=schemas.PaginatedResults)
async def search(q: str,
                 skip: int = 0,
                 limit: int = 20,
                 db: AsyncSession = Depends(database.get_db)
                 ):
    like_query = f"%{q}%"

    total_stmt = (
        select(func.count(models.SearchObject.id))
        .join(models.Image, models.SearchObject.image_id == models.Image.id)
        .where(
            or_(
                models.SearchObject.text_content.ilike(like_query),
                models.Image.image_key.ilike(like_query),
                models.Image.image_path.ilike(like_query),
                func.similarity(models.SearchObject.text_content, q) > 0.3,
                func.similarity(models.Image.image_key, q) > 0.3,
                func.similarity(models.Image.image_path, q) > 0.3,
            )
        )
    )
    total = await db.scalar(total_stmt)

    results = await db.execute(
        select(models.SearchObject,
               func.greatest(
                   func.similarity(models.SearchObject.text_content, q),
                   func.similarity(models.Image.image_key, q),
                   func.similarity(models.Image.image_path, q),
               ).label("relevance")
               )
        .join(models.Image, models.SearchObject.image_id == models.Image.id)
        .options(selectinload(models.SearchObject.image).selectinload(models.Image.source))
        .where(
            or_(
                models.SearchObject.text_content.ilike(like_query),
                models.Image.image_key.ilike(like_query),
                models.Image.image_path.ilike(like_query),
                func.similarity(models.SearchObject.text_content, q) > 0.3,
                func.similarity(models.Image.image_key, q) > 0.3,
                func.similarity(models.Image.image_path, q) > 0.3,
            )
        )
        .order_by(text("relevance DESC"))
        .offset(skip)
        .limit(limit)
    )

    search_objects = results.all()

    objects_with_urls = []
    for obj, score in search_objects:
        obj_data = schemas.SearchObjectSchema.model_validate(obj, from_attributes=True)
        if obj.image:
            obj_data.image_url = f"/api/images/{obj.image.id}"
            obj_data.thumbnail_url = f"/api/images/{obj.image.id}/thumbnail"
        obj_data.similarity_score = round(score * 100)
        objects_with_urls.append(obj_data)

    return {"items": objects_with_urls, "total": total}


@app.post("/api/admin/login")
async def admin_login(form_data: OAuth2PasswordRequestForm = Depends()):
    user = auth.authenticate_user(form_data.username, form_data.password)
    if not user:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Incorrect credentials")
    token = auth.create_access_token({"sub": user["username"]})
    return {"access_token": token, "token_type": "bearer"}


@app.post("/api/admin/images", response_model=schemas.ImageSchema)
async def create_image(
        image_path: str = Form(...),
        image_key: str = Form(...),
        image_source_id: int | None = Form(None),
        image_file: UploadFile = File(...),
        image_file_sha512: str = Form(...),
        db: AsyncSession = Depends(database.get_db),
        user=Depends(auth.get_current_admin)
):
    # Check if the image already exists
    existing_image = await db.execute(
        select(models.Image).options(selectinload(models.Image.source)).where(
            models.Image.sha512_hash == image_file_sha512
        )
    )
    existing = existing_image.scalar_one_or_none()
    if existing:
        # If it exists, reuse the existing image
        return existing

    # If it doesn't exist, save the new image
    image_binary = await image_file.read()
    image = await crud.save_unique_image(db, image_path, image_key, image_source_id, image_binary)
    return image


@app.post("/api/admin/objects", response_model=schemas.SearchObjectSchema)
async def create_object(
        text_content: str = Form(...),
        image_path: str = Form(None),
        image_key: str = Form(None),
        image_source_id: int | None = Form(None),
        image_file: Optional[UploadFile] = File(None),
        image_file_sha512: Optional[str] = Form(None),
        db: AsyncSession = Depends(database.get_db),
        user=Depends(auth.get_current_admin)
):
    image = await create_image(image_path, image_key, image_source_id, image_file, image_file_sha512, db, user)

    search_obj = await crud.create_search_object(db, text_content, image.id)
    return search_obj


@app.get("/api/admin/objects", response_model=schemas.PaginatedResults)
async def list_objects(
        skip: int = 0,
        limit: int = 20,
        db: AsyncSession = Depends(database.get_db),
        user=Depends(auth.get_current_admin)
):
    total_stmt = select(func.count()).select_from(models.SearchObject)
    total = await db.scalar(total_stmt)

    result = await db.execute(
        select(models.SearchObject)
        .options(selectinload(models.SearchObject.image).selectinload(models.Image.source))
        .offset(skip)
        .limit(limit)
        .order_by(models.SearchObject.created_at.desc())
    )
    objects = result.scalars().all()

    # Dynamically add image URLs
    objects_with_urls = []
    for obj in objects:
        obj_data = schemas.SearchObjectSchema.model_validate(obj)
        if obj.image:
            obj_data.image_url = f"/api/images/{obj.image.id}"
            obj_data.thumbnail_url = f"/api/images/{obj.image.id}/thumbnail"
        objects_with_urls.append(obj_data)

    return {"items": objects_with_urls, "total": total}


@app.put("/api/admin/objects/{object_id}", response_model=schemas.SearchObjectSchema)
async def update_object(
        object_id: int,
        text_content: str = Form(...),
        image_path: str = Form(...),
        image_key: str = Form(...),
        image_source_id: int | None = Form(None),
        image_file: UploadFile | None = File(None),
        db: AsyncSession = Depends(database.get_db),
        user=Depends(auth.get_current_admin)
):
    obj = await db.get(models.SearchObject, object_id)
    if not obj:
        raise HTTPException(status_code=404, detail="Object not found")

    obj.text_content = text_content

    if image_file:
        image_binary = await image_file.read()
        image = await crud.save_unique_image(db, image_path, image_key, image_source_id, image_binary)
        obj.image_id = image.id

    await db.commit()

    # Load relationships explicitly
    await db.refresh(obj, attribute_names=['image'])

    # And eager-load the image’s source relationship too:
    if obj.image:
        await db.refresh(obj.image, attribute_names=['source'])

    return obj


@app.delete("/api/admin/objects/{object_id}")
async def delete_object(object_id: int, db: AsyncSession = Depends(database.get_db),
                        user=Depends(auth.get_current_admin)):
    obj = await db.get(models.SearchObject, object_id)
    if not obj:
        raise HTTPException(status_code=404, detail="Object not found")
    await db.delete(obj)
    await db.commit()
    return {"status": "deleted", "object_id": object_id}


@app.get("/api/admin/events", response_model=list[schemas.AdminEventSchema])
async def get_events(db: AsyncSession = Depends(database.get_db), user=Depends(auth.get_current_admin)):
    result = await db.execute(select(models.AdminEvent).order_by(models.AdminEvent.created_at.desc()))
    return result.scalars().all()


@app.put("/api/admin/events/{id}/resolve")
async def resolve_event(id: int, db: AsyncSession = Depends(database.get_db), user=Depends(auth.get_current_admin)):
    event = await db.get(models.AdminEvent, id)
    if not event:
        raise HTTPException(status_code=404, detail="Event not found")
    event.is_resolved = True
    await db.commit()
    return {"status": "resolved"}


@app.get("/api/images/{image_id}", response_class=StreamingResponse)
async def get_image(image_id: int, db: AsyncSession = Depends(database.get_db)):
    image = await db.get(models.Image, image_id)
    if not image:
        raise HTTPException(status_code=404, detail="Image not found")

    original = Image.open(io.BytesIO(image.image_data))
    original = ImageOps.exif_transpose(original).convert("RGBA")

    watermark = Image.new("RGBA", original.size, (255, 255, 255, 0))

    # Font setup
    font_size = max(original.width // 15, 40)
    font_path = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"
    try:
        font = ImageFont.truetype(font_path, font_size)
    except:
        font = ImageFont.load_default()

    watermark_text = "JRoots.co"
    opacity = 90  # More visible watermark

    # Create a single watermark image (rotated)
    single_watermark = Image.new("RGBA", (font_size * len(watermark_text), font_size), (255, 255, 255, 0))
    single_draw = ImageDraw.Draw(single_watermark)
    single_draw.text((0, 0), watermark_text, font=font, fill=(255, 255, 255, opacity))

    # Rotate watermark
    angle = 30  # degrees
    rotated_watermark = single_watermark.rotate(angle, expand=True)

    # Tiled watermark placement
    spacing_x, spacing_y = rotated_watermark.width + 100, rotated_watermark.height + 100
    for x in range(-rotated_watermark.width, original.width + rotated_watermark.width, spacing_x):
        for y in range(-rotated_watermark.height, original.height + rotated_watermark.height, spacing_y):
            watermark.alpha_composite(rotated_watermark, (x, y))

    # Combine watermark with the original image
    watermarked = Image.alpha_composite(original, watermark).convert("RGB")

    buffer = io.BytesIO()
    watermarked.save(buffer, format="JPEG")
    buffer.seek(0)

    headers = {"Cache-Control": "public, max-age=86400"}  # cache for 1 day
    return StreamingResponse(buffer, media_type="image/jpeg", headers=headers)


@app.get("/api/admin/image-sources", response_model=list[schemas.ImageSourceSchema])
async def list_image_sources(db: AsyncSession = Depends(database.get_db)):
    result = await db.execute(select(models.ImageSource))
    return result.scalars().all()


@app.get("/api/images/{image_id}/thumbnail", response_class=StreamingResponse)
async def get_thumbnail(image_id: int, db: AsyncSession = Depends(database.get_db)):
    image = await db.get(models.Image, image_id)
    if not image or not image.thumbnail_data:
        raise HTTPException(status_code=404, detail="Thumbnail not found")

    headers = {"Cache-Control": "public, max-age=86400"}  # cache for 1 day
    return StreamingResponse(io.BytesIO(image.thumbnail_data), media_type="image/jpeg", headers=headers)
