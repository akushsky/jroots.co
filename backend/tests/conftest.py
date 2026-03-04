import os

os.environ.setdefault("SECRET_KEY", "testsecret")
os.environ.setdefault("ALGORITHM", "HS256")
os.environ.setdefault("ADMIN_PASSWORD", "testadminpassword")
os.environ.setdefault("DATABASE_URL", "sqlite+aiosqlite:///./test.db")
os.environ.setdefault("ENVIRONMENT", "test")
os.environ.setdefault("MEDIA_PATH", "/tmp/jroots_test_media")

import pytest
from unittest.mock import MagicMock

from app.models import User


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
