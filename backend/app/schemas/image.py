from pydantic import BaseModel


class ImageSourceSchema(BaseModel):
    id: int
    source_name: str
    description: str | None = None

    model_config = {"from_attributes": True}


class ImageSchema(BaseModel):
    id: int
    image_path: str
    image_key: str
    telegram_file_id: str | None = None
    source: ImageSourceSchema | None = None
    sha512_hash: str

    model_config = {"from_attributes": True}
