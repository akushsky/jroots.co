import io
import traceback
from os import getenv
from typing import Optional

import httpx
from PIL import Image, ImageOps
from fastapi import FastAPI, Depends, HTTPException, status, UploadFile, File, Form, BackgroundTasks, Header
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy import select, func, or_, text
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
from starlette.responses import StreamingResponse, Response

import auth
import crud
import database
import image_utils
import models
import schemas
from logging_config import setup_logging, construct_logger
from logging_middleware import LoggingMiddleware
from resend_service import send_email

if __name__ == "__main__":
    import uvicorn

    uvicorn.run("backend.main:app", host="0.0.0.0", port=8000, reload=True)

setup_logging()
logger = construct_logger("jroots")

app = FastAPI()

origins = getenv("CORS_ORIGINS", "*").split(",")
FRONTEND_URL = getenv("FRONTEND_URL", "http://localhost:5173")

TELEGRAM_BOT_TOKEN = getenv("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = getenv("TELEGRAM_CHAT_ID")

# noinspection PyTypeChecker
app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# noinspection PyTypeChecker
app.add_middleware(LoggingMiddleware)


@app.on_event("startup")
async def startup():
    async with database.engine.begin() as conn:
        await conn.run_sync(models.Base.metadata.create_all)


@app.get("/api/search", response_model=schemas.PaginatedResults)
async def search(q: str, skip: int = 0, limit: int = 20,
                 db: AsyncSession = Depends(database.get_db),
                 current_user: Optional[models.User] = Depends(auth.get_current_user_optional)):
    like_query = f"%{q}%"

    similarity_conditions = [
        func.similarity(models.SearchObject.text_content, q) > 0.3,
        func.similarity(models.Image.image_key, q) > 0.3,
        func.similarity(models.Image.image_path, q) > 0.3,
    ]

    filter_conditions = or_(
        models.SearchObject.text_content.ilike(like_query),
        models.Image.image_key.ilike(like_query),
        models.Image.image_path.ilike(like_query),
        *similarity_conditions
    )

    total = await db.scalar(
        select(func.count(models.SearchObject.id))
        .join(models.Image)
        .where(filter_conditions)
    )

    results = await db.execute(
        select(models.SearchObject,
               func.greatest(*[func.similarity(models.SearchObject.text_content, q),
                               func.similarity(models.Image.image_key, q),
                               func.similarity(models.Image.image_path, q)])
               .label("relevance"))
        .join(models.Image)
        .options(selectinload(models.SearchObject.image).selectinload(models.Image.source))
        .where(filter_conditions)
        .order_by(text("relevance DESC"))
        .offset(skip)
        .limit(limit)
    )

    search_objects = results.all()
    objects_with_urls = []

    logger.info("Found %d objects for query '%s' and user '%s'", len(search_objects), q,
                current_user.email if current_user else "Anonymous")

    # Retrieve images from found, purchased by user
    if current_user and current_user.is_verified:
        result = await db.execute(
            select(models.ImagePurchase)
            .where(models.ImagePurchase.user_id == current_user.id,
                    models.ImagePurchase.image_id.in_([obj.image.id for obj, _ in search_objects if obj.image]))
        )
        purchased_images = {purchase.image_id for purchase in result.scalars().all()}
        logger.info("User %s has purchased images: %s", current_user.email, purchased_images)
    else:
        purchased_images = set()


    for obj, score in search_objects:
        obj_data = schemas.SearchObjectSchema.model_validate(obj, from_attributes=True)
        if obj.image:
            obj_data.image_id = obj.image.id
            obj_data.thumbnail_url = f"/api/images/{obj.image.id}/thumbnail"
            if not current_user or (not current_user.is_admin and obj.image.id not in purchased_images):
                obj_data.image.image_path = "********"
        obj_data.price = obj.price
        obj_data.similarity_score = round(score * 100)
        objects_with_urls.append(obj_data)

    return {"items": objects_with_urls, "total": total}


@app.post("/api/admin/images", response_model=schemas.ImageSchema)
async def create_image(image_path: str = Form(...), image_key: str = Form(...),
                       image_source_id: Optional[int] = Form(None), image_file: UploadFile = File(...),
                       image_file_sha512: str = Form(...),
                       db: AsyncSession = Depends(database.get_db),
                       user=Depends(auth.get_current_admin)):
    existing = await db.scalar(
        select(models.Image).options(selectinload(models.Image.source))
        .where(models.Image.sha512_hash == image_file_sha512)
    )
    if existing:
        return existing

    image_binary = await image_file.read()
    return await crud.save_unique_image(db, image_path, image_key, image_source_id, image_binary)


@app.post("/api/admin/objects", response_model=schemas.SearchObjectSchema)
async def create_object(text_content: str = Form(...),
                        price: int = Form(...), image_path: str = Form(...),
                        image_key: str = Form(...), image_source_id: Optional[int] = Form(None),
                        image_file: Optional[UploadFile] = File(None),
                        image_file_sha512: Optional[str] = Form(None),
                        db: AsyncSession = Depends(database.get_db),
                        user=Depends(auth.get_current_admin)):
    image = await create_image(image_path, image_key, image_source_id, image_file, image_file_sha512, db, user)
    return await crud.create_search_object(db, text_content, price, image.id)


@app.get("/api/admin/objects", response_model=schemas.PaginatedResults)
async def list_objects(skip: int = 0, limit: int = 20,
                       db: AsyncSession = Depends(database.get_db),
                       user=Depends(auth.get_current_admin)):
    total = await db.scalar(select(func.count()).select_from(models.SearchObject))

    result = await db.execute(
        select(models.SearchObject)
        .options(selectinload(models.SearchObject.image).selectinload(models.Image.source))
        .offset(skip).limit(limit)
        .order_by(models.SearchObject.created_at.desc())
    )

    objects = result.scalars().all()
    objects_with_urls = []

    for obj in objects:
        obj_data = schemas.SearchObjectSchema.model_validate(obj)
        if obj.image:
            obj_data.image_id = obj.image.id
            obj_data.thumbnail_url = f"/api/images/{obj.image.id}/thumbnail"
        objects_with_urls.append(obj_data)

    return {"items": objects_with_urls, "total": total}


@app.put("/api/admin/objects/{object_id}", response_model=schemas.SearchObjectSchema)
async def update_object(
        object_id: int,
        text_content: str = Form(...),
        price: int = Form(...),
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

    # Update valuable fields
    obj.text_content = text_content
    obj.price = price

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
async def get_image(
        image_id: int,
        db: AsyncSession = Depends(database.get_db),
        if_none_match: str | None = Header(default=None),
        current_user: Optional[models.User] = Depends(auth.get_current_user_optional)):
    logger.info("User %s requested image with ID %d", current_user.email if current_user else "Anonymous", image_id)
    if not current_user or not current_user.is_verified:
        raise HTTPException(status_code=403, detail="Email not verified")

    # Fetch image from the database
    image = await db.get(models.Image, image_id)
    if not image:
        raise HTTPException(status_code=404, detail="Image not found")

    # Determine access
    has_access = False
    if current_user:
        if current_user.is_admin:
            has_access = True
        else:
            has_access = await crud.user_has_access_to_image(db, current_user.id, image_id)
        logger.info("User %s has access to image %d: %s", current_user.email, image_id, has_access)

    # Generate ETag
    etag = await image_utils.generate_etag(image, has_access)

    # Handle If-None-Match (client-side cache validation)
    if if_none_match == etag:
        return Response(status_code=304)

    # Load image data
    original = Image.open(io.BytesIO(image.image_data))
    original = ImageOps.exif_transpose(original).convert("RGBA")

    # Apply watermark if a user does not have access
    # Prepare image data
    result = original if has_access else await image_utils.apply_watermark(original)

    # Convert to RGB if not already
    if result.mode != "RGB":
        result = result.convert("RGB")

    # Save image to buffer
    buffer = io.BytesIO()
    result.save(buffer, format="JPEG")
    buffer.seek(0)

    # Build response with headers
    headers = {
        "ETag": etag,
        "Cache-Control": "max-age=3600, must-revalidate",  # Cache for 1 hour
    }

    logger.info("Image with path '%s' and key '%s' opened by user %s",
                image.image_path, image.image_key, current_user.email)

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


@app.post("/api/register")
async def register_user(
        data: schemas.RegisterRequest,
        db: AsyncSession = Depends(database.get_db),
        background_tasks: BackgroundTasks = BackgroundTasks()):
    # Check if user already exists
    existing_user = await db.execute(select(models.User).where(models.User.email == data.email))
    if existing_user.scalar_one_or_none():
        raise HTTPException(status_code=400, detail="Email already registered")

    verification_token = auth.generate_verification_token(str(data.email))
    verification_url = f"{FRONTEND_URL}/verify?token={verification_token}"

    hashed_pw = auth.hash_password(data.password)
    user = models.User(
        username=data.username,
        email=data.email,
        hashed_password=hashed_pw,
        telegram_username=data.telegram_username,
        is_verified=False
    )

    db.add(user)
    await db.commit()

    logger.info("User %s registered with email %s", data.username, data.email)

    html = f"""
    <h1>Подтвердите регистрацию</h1>
    <p>Здравствуйте, {data.username}!</p>
    <p>Пожалуйста, подтвердите ваш email, перейдя по ссылке ниже:</p>
    <a href="{verification_url}">Подтвердить Email</a>
    """
    background_tasks.add_task(send_email,
                              to_email=str(data.email),
                              subject="Подтверждение регистрации",
                              html_content=html
                              )

    return {"message": "Регистрация прошла успешно. Пожалуйста, проверьте вашу почту для подтверждения."}


@app.get("/api/verify")
async def verify_user(token: str, db: AsyncSession = Depends(database.get_db)):
    email = auth.verify_token(token)

    result = await db.execute(select(models.User).where(models.User.email == email))
    user = result.scalar_one_or_none()
    if user is None:
        raise HTTPException(status_code=404, detail="User not found")

    user.is_verified = True
    await db.commit()

    logger.info("User %s verified their email %s", user.username, user.email)

    return {"message": "User verified successfully"}


@app.post("/api/login")
async def login_user(
        form_data: OAuth2PasswordRequestForm = Depends(),
        db: AsyncSession = Depends(database.get_db)
):
    result = await db.execute(select(models.User).where(models.User.email == form_data.username))
    user = result.scalar_one_or_none()
    access_token = auth.authenticate(user, form_data.username, form_data.password)
    return {"access_token": access_token, "token_type": "bearer"}


@app.post("/api/request_access")
async def request_access(
        data: schemas.AccessRequest,
        db: AsyncSession = Depends(database.get_db),
        background_tasks: BackgroundTasks = BackgroundTasks(),
        current_user: Optional[models.User] = Depends(auth.get_current_user_optional)):
    logger.info("User %s requested full access to image with ID %d",
                current_user.email if current_user else "Anonymous", data.image_id)

    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        raise HTTPException(status_code=500, detail="Telegram configuration missing.")

    if not current_user or not current_user.is_verified:
        raise HTTPException(status_code=403, detail="Email not verified")

    # Fetch image from the database
    result = await db.execute(
        select(models.Image).options(selectinload(models.Image.source)).where(models.Image.id == data.image_id)
    )
    image = result.scalars().first()
    if not image:
        raise HTTPException(status_code=404, detail="Image not found")

    telegram_line = f"✈️ Telegram: @{current_user.telegram_username}" if current_user.telegram_username else ""
    caption = "\n".join(filter(None, [
        f"📨 Новый запрос на доступ\n",
        f"👤 Пользователь: {data.username} ({data.email})\n",
        telegram_line,
        f"🖼️ Изображение: {image.image_key}\n",
        f"📁 Шифр: {image.image_path}\n",
        f"📚 Источник: {image.source.source_name if image.source else 'Неизвестен'}",
    ]))

    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendPhoto"

    async with httpx.AsyncClient(verify=False) as client:
        if image.telegram_file_id:
            json = {
                "chat_id": TELEGRAM_CHAT_ID,
                "photo": image.telegram_file_id,
                "caption": caption,
            }
            response = await client.post(url, json=json)
            logger.info("User %s sent image %s to Telegram chat %s using existing file_id", current_user.email,
                        image.id, TELEGRAM_CHAT_ID)
        else:
            payload = {
                "chat_id": TELEGRAM_CHAT_ID,
                "caption": caption,
            }
            files = {
                "photo": ("image.jpg", io.BytesIO(image.image_data), "image/jpeg")
            }
            response = await client.post(url, data=payload, files=files)
            logger.info("User %s sent image %s to Telegram chat %s", current_user.email, image.id,
                        TELEGRAM_CHAT_ID)
            # Save file_id for future use
            if response.status_code == 200:
                data = response.json()
                try:
                    file_id = data["result"]["photo"][-1]["file_id"]  # Highest resolution
                    image.telegram_file_id = file_id
                    await db.commit()
                    logger.info("User %s updated image %s with telegram id", current_user.email, image.id)
                except Exception:
                    logger.error(traceback.format_exc())
                    pass

    if response.status_code != 200:
        raise HTTPException(status_code=500, detail="Не удалось отправить сообщение в Telegram.")

    return {"ok": True}
