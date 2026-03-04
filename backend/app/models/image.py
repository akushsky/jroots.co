from sqlalchemy import Column, Integer, String, Text, ForeignKey, DateTime, LargeBinary, func
from sqlalchemy.orm import relationship

from app.models.base import Base


class ImageSource(Base):
    __tablename__ = "image_sources"

    id = Column(Integer, primary_key=True, index=True)
    source_name = Column(String, unique=True, nullable=False)
    description = Column(Text)


class Image(Base):
    __tablename__ = "images"

    id = Column(Integer, primary_key=True, index=True)
    image_path = Column(String, nullable=False)
    image_key = Column(String, nullable=False)
    image_source_id = Column(Integer, ForeignKey("image_sources.id", ondelete="SET NULL"))
    telegram_file_id = Column(String, nullable=True)
    image_data = Column(LargeBinary, nullable=False)
    thumbnail_data = Column(LargeBinary)
    sha512_hash = Column(String, nullable=False, unique=True)
    image_file_path = Column(String, nullable=True)
    thumbnail_file_path = Column(String, nullable=True)
    created_at = Column(DateTime, server_default=func.now())

    source = relationship("ImageSource")
