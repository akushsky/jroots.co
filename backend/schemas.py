from pydantic import BaseModel, EmailStr
from datetime import datetime


class ImageSourceSchema(BaseModel):
    id: int
    source_name: str
    description: str | None

    class Config:
        from_attributes = True


class ImageSchema(BaseModel):
    id: int
    image_path: str
    image_key: str
    telegram_file_id: str | None
    source: ImageSourceSchema | None
    sha512_hash: str

    class Config:
        from_attributes = True


class SearchObjectSchema(BaseModel):
    id: int
    text_content: str
    price: int | None
    image: ImageSchema | None
    image_id: int | None = None 
    thumbnail_url: str | None = None
    similarity_score: int | None = None

    class Config:
        from_attributes = True


class AdminEventSchema(BaseModel):
    id: int
    object_id: int | None
    message: str
    created_at: datetime
    is_resolved: bool

    class Config:
        from_attributes = True


class PaginatedResults(BaseModel):
    items: list[SearchObjectSchema]
    total: int

    class Config:
        from_attributes = True


class RegisterRequest(BaseModel):
    username: str
    email: EmailStr
    password: str
    telegram_username: str | None = None
    captcha_token: str

    class Config:
        from_attributes = True


class LoginRequest(BaseModel):
    email: EmailStr
    password: str

    class Config:
        from_attributes = True

class AccessRequest(BaseModel):
    username: str
    email: str
    image_id: int

    class Config:
        from_attributes = True