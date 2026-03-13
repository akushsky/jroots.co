import logging
from typing import Optional

from fastapi import APIRouter, Depends
from sqlalchemy import select, func, or_, text, cast, Float
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.config import get_settings
from app.database import get_db
from app.models import SearchObject, Image, ImagePurchase, User
from app.schemas import SearchObjectSchema, PaginatedResults
from app.services.auth import get_current_user_optional

logger = logging.getLogger("jroots")

router = APIRouter(prefix="/api", tags=["search"])

WORD_SIMILARITY_THRESHOLD = 0.2
SIMILARITY_THRESHOLD = 0.3


@router.get("/search", response_model=PaginatedResults)
async def search(
    q: str,
    skip: int = 0,
    limit: int = 20,  # capped at 100 below
    db: AsyncSession = Depends(get_db),
    current_user: Optional[User] = Depends(get_current_user_optional),
):
    limit = min(limit, 100)
    like_query = f"%{q}%"
    max_lev_distance = min(3, max(1, len(q) // 2))
    q_len = max(len(q), 1)

    word_sim = func.word_similarity(q, SearchObject.text_content)
    key_sim = func.similarity(Image.image_key, q)
    path_sim = func.similarity(Image.image_path, q)
    lev_dist = func.best_word_levenshtein(SearchObject.text_content, q)

    filter_conditions = or_(
        SearchObject.text_content.ilike(like_query),
        Image.image_key.ilike(like_query),
        Image.image_path.ilike(like_query),
        word_sim > WORD_SIMILARITY_THRESHOLD,
        key_sim > SIMILARITY_THRESHOLD,
        path_sim > SIMILARITY_THRESHOLD,
        lev_dist <= max_lev_distance,
    )

    total = await db.scalar(
        select(func.count(SearchObject.id)).join(Image).where(filter_conditions)
    )

    lev_score = 1.0 - cast(lev_dist, Float) / q_len
    relevance = func.greatest(word_sim, key_sim, path_sim, lev_score).label("relevance")

    results = await db.execute(
        select(SearchObject, relevance)
        .join(Image)
        .options(selectinload(SearchObject.image).selectinload(Image.source))
        .where(filter_conditions)
        .order_by(text("relevance DESC"), SearchObject.id.asc())
        .offset(skip)
        .limit(limit)
    )

    search_objects = results.all()
    objects_with_urls = []

    logger.info(
        "Found %d objects for query '%s' and user '%s'",
        len(search_objects), q, current_user.email if current_user else "Anonymous",
    )

    purchased_images: set[int] = set()
    if current_user and current_user.is_verified:
        result = await db.execute(
            select(ImagePurchase).where(
                ImagePurchase.user_id == current_user.id,
                ImagePurchase.image_id.in_([obj.image.id for obj, _ in search_objects if obj.image]),
            )
        )
        purchased_images = {purchase.image_id for purchase in result.scalars().all()}

    for obj, score in search_objects:
        obj_data = SearchObjectSchema.model_validate(obj, from_attributes=True)
        if obj.image:
            obj_data.image_id = obj.image.id
            cdn = get_settings().cdn_base
            obj_data.thumbnail_url = f"{cdn}/api/images/{obj.image.id}/thumbnail"
            if not current_user or (not current_user.is_admin and obj.image.id not in purchased_images):
                obj_data.image.image_path = "********"
        obj_data.similarity_score = round(score * 100)
        objects_with_urls.append(obj_data)

    return {"items": objects_with_urls, "total": total}
