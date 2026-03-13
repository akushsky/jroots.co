from pydantic import BaseModel

from app.schemas.image import ImageSchema


class SearchObjectSchema(BaseModel):
    id: int
    text_content: str
    image: ImageSchema | None = None
    image_id: int | None = None
    thumbnail_url: str | None = None
    similarity_score: int | None = None

    model_config = {"from_attributes": True}


class PaginatedResults(BaseModel):
    items: list[SearchObjectSchema]
    total: int

    model_config = {"from_attributes": True}
