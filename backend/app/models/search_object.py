from sqlalchemy import Column, Integer, Text, ForeignKey, DateTime, UniqueConstraint, func
from sqlalchemy.orm import relationship

from app.models.base import Base


class SearchObject(Base):
    __tablename__ = "search_objects"

    id = Column(Integer, primary_key=True, index=True)
    text_content = Column(Text, nullable=False)
    price = Column(Integer, nullable=False)
    image_id = Column(Integer, ForeignKey("images.id", ondelete="SET NULL"))
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())

    image = relationship("Image")


class ImagePurchase(Base):
    __tablename__ = "image_purchases"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    image_id = Column(Integer, ForeignKey("images.id", ondelete="CASCADE"), nullable=False, index=True)
    purchased_at = Column(DateTime(timezone=True), server_default=func.now())

    __table_args__ = (UniqueConstraint("user_id", "image_id"),)
