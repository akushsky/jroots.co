from sqlalchemy import Column, Integer, String, Text, ForeignKey, DateTime, Boolean, func, LargeBinary
from sqlalchemy.orm import relationship, declarative_base

Base = declarative_base()


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True)
    username = Column(String, unique=True, nullable=False)
    email = Column(String, nullable=False)
    hashed_password = Column(String, nullable=False)

    is_admin = Column(Boolean, default=False)
    is_verified = Column(Boolean, default=False)
    is_subscribed = Column(Boolean, default=False)


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
    image_data = Column(LargeBinary, nullable=False)
    thumbnail_data = Column(LargeBinary)
    sha512_hash = Column(String, nullable=False, unique=True)
    created_at = Column(DateTime, server_default=func.now())

    source = relationship("ImageSource")


class SearchObject(Base):
    __tablename__ = "search_objects"

    id = Column(Integer, primary_key=True, index=True)
    text_content = Column(Text, nullable=False)
    image_id = Column(Integer, ForeignKey("images.id", ondelete="SET NULL"))
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())

    image = relationship("Image")


class AdminEvent(Base):
    __tablename__ = "admin_events"

    id = Column(Integer, primary_key=True, index=True)
    object_id = Column(Integer, ForeignKey("search_objects.id", ondelete="SET NULL"))
    message = Column(Text, nullable=False)
    created_at = Column(DateTime, server_default=func.now())
    is_resolved = Column(Boolean, default=False)

    object = relationship("SearchObject")
