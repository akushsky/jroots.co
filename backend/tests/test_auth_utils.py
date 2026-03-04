import pytest
from unittest.mock import MagicMock, AsyncMock
from datetime import timedelta, datetime, timezone

from jose import jwt
from fastapi import HTTPException

from app.services.auth import (
    create_access_token,
    generate_verification_token,
    hash_password,
    resolve_user_from_token,
    verify_hcaptcha,
    verify_password,
    verify_token,
)
from app.config import get_settings
from app.models import User

settings = get_settings()


def test_create_access_token():
    user = MagicMock(spec=User)
    user.email = "test@example.com"
    user.username = "testuser"
    user.is_admin = True
    user.is_verified = True

    expires = timedelta(minutes=30)

    token = create_access_token(user, expires_delta=expires)
    decoded = jwt.decode(token, settings.secret_key, algorithms=[settings.algorithm])

    assert decoded["sub"] == user.email
    assert decoded["username"] == user.username
    assert decoded["is_admin"] is True
    assert decoded["is_verified"] is True

    exp = datetime.fromtimestamp(decoded["exp"], tz=timezone.utc)
    iat = datetime.fromtimestamp(decoded["iat"], tz=timezone.utc)
    assert (exp - iat) == expires


def test_generate_and_verify_verification_token():
    token = generate_verification_token("test@example.com")
    email = verify_token(token)
    assert email == "test@example.com"


def test_verify_token_invalid():
    bad_token = jwt.encode({}, settings.secret_key, algorithm=settings.algorithm)
    with pytest.raises(HTTPException):
        verify_token(bad_token)


@pytest.mark.asyncio
async def test_verify_hcaptcha_no_key_configured():
    result = await verify_hcaptcha("any-token")
    assert result is True


@pytest.mark.asyncio
async def test_resolve_user_from_token_no_token():
    db = AsyncMock()
    user = await resolve_user_from_token(None, db)
    assert user is None


@pytest.mark.asyncio
async def test_resolve_user_from_token_invalid():
    db = AsyncMock()
    user = await resolve_user_from_token("bad.token.here", db)
    assert user is None


@pytest.mark.asyncio
async def test_resolve_user_from_token_valid():
    mock_user = MagicMock(spec=User)
    db = AsyncMock()
    execute_result = MagicMock()
    execute_result.scalar_one_or_none.return_value = mock_user
    db.execute.return_value = execute_result

    token = jwt.encode(
        {"sub": "test@example.com"},
        settings.secret_key,
        algorithm=settings.algorithm,
    )

    user = await resolve_user_from_token(token, db)
    assert user is mock_user


def test_verify_and_hash_password():
    raw = "s3cret"
    hashed = hash_password(raw)
    assert verify_password(raw, hashed) is True
    assert verify_password("wrong", hashed) is False
