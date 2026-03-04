import os

os.environ.setdefault("SECRET_KEY", "testsecret")
os.environ.setdefault("ALGORITHM", "HS256")
os.environ.setdefault("ADMIN_PASSWORD", "testadminpassword")
os.environ.setdefault("DATABASE_URL", "sqlite+aiosqlite:///./test.db")
os.environ.setdefault("ENVIRONMENT", "test")
os.environ.setdefault("MEDIA_PATH", "/tmp/jroots_test_media")
os.environ.setdefault("TELEGRAM_BOT_TOKEN", "test-bot-token")
os.environ.setdefault("TELEGRAM_CHAT_ID", "12345")

import hashlib
import io
from unittest.mock import MagicMock

import pytest
from httpx import ASGITransport, AsyncClient
from PIL import Image as PILImage
from sqlalchemy import event

from app.database import AsyncSessionLocal, engine, get_db
from app.main import app
from app.models import User, Image, SearchObject
from app.models.base import Base
from app.services.auth import hash_password, create_access_token


@event.listens_for(engine.sync_engine, "connect")
def _register_sqlite_functions(dbapi_conn, connection_record):
    dbapi_conn.create_function(
        "similarity", 2,
        lambda a, b: 1.0 if a and b and b.lower() in a.lower() else 0.0,
    )
    dbapi_conn.create_function("greatest", -1, lambda *args: max(args) if args else 0.0)


@pytest.fixture(autouse=True)
async def setup_db():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield
    async with AsyncSessionLocal() as session:
        for table in reversed(Base.metadata.sorted_tables):
            await session.execute(table.delete())
        await session.commit()


@pytest.fixture
async def db_session():
    async with AsyncSessionLocal() as session:
        yield session


@pytest.fixture
async def client(db_session):
    async def override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = override_get_db
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        yield c
    app.dependency_overrides.clear()


# --- Helpers ---

def make_test_image_bytes(width=100, height=100, color="red"):
    img = PILImage.new("RGB", (width, height), color=color)
    buf = io.BytesIO()
    img.save(buf, format="JPEG")
    return buf.getvalue()


async def create_user(
    db, *, username="testuser", email="test@example.com",
    password="testpass123", is_admin=False, is_verified=True,
    telegram_username=None,
):
    user = User(
        username=username, email=email,
        hashed_password=hash_password(password),
        is_admin=is_admin, is_verified=is_verified,
        telegram_username=telegram_username,
    )
    db.add(user)
    await db.commit()
    await db.refresh(user)
    return user


async def create_image_record(db, image_bytes=None, image_path="test/path", image_key="test-key"):
    if image_bytes is None:
        image_bytes = make_test_image_bytes()
    sha512 = hashlib.sha512(image_bytes).hexdigest()
    thumb = PILImage.open(io.BytesIO(image_bytes))
    thumb.thumbnail((200, 200))
    buf = io.BytesIO()
    thumb.save(buf, format="JPEG")
    image = Image(
        image_path=image_path, image_key=image_key,
        image_data=image_bytes, thumbnail_data=buf.getvalue(),
        sha512_hash=sha512,
    )
    db.add(image)
    await db.commit()
    await db.refresh(image)
    return image


async def create_search_obj(db, text_content="test search text", price=100, image_id=None):
    obj = SearchObject(text_content=text_content, price=price, image_id=image_id)
    db.add(obj)
    await db.commit()
    await db.refresh(obj)
    return obj


def auth_header(user):
    token = create_access_token(user)
    return {"Authorization": f"Bearer {token}"}


# --- Legacy mock fixtures (used by existing unit tests) ---

@pytest.fixture
def mock_user() -> MagicMock:
    user = MagicMock(spec=User)
    user.email = "test@example.com"
    user.username = "testuser"
    user.is_admin = False
    user.is_verified = True
    user.id = 1
    return user


@pytest.fixture
def mock_admin() -> MagicMock:
    user = MagicMock(spec=User)
    user.email = "admin@example.com"
    user.username = "admin"
    user.is_admin = True
    user.is_verified = True
    user.id = 99
    return user
