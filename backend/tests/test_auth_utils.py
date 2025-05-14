import pytest
from unittest.mock import patch, MagicMock, AsyncMock
from datetime import timedelta, datetime, timezone
from jose import jwt
from fastapi import HTTPException
from backend import auth
from backend.models import User

# Mock secrets
SECRET_KEY = "testsecret"
ALGORITHM = "HS256"


@patch("backend.auth.SECRET_KEY", SECRET_KEY)
@patch("backend.auth.ALGORITHM", ALGORITHM)
def test_create_access_token():
    user = MagicMock()
    user.email = "test@example.com"
    user.username = "testuser"
    user.is_admin = True
    user.is_verified = True

    expires = timedelta(minutes=30)
    now = datetime.now(timezone.utc)

    token = auth.create_access_token(user, expires_delta=expires)
    decoded = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])

    assert decoded["sub"] == user.email
    assert decoded["username"] == user.username
    assert decoded["is_admin"] is True
    assert decoded["is_verified"] is True

    exp = datetime.fromtimestamp(decoded["exp"], tz=timezone.utc)
    iat = datetime.fromtimestamp(decoded["iat"], tz=timezone.utc)
    assert (exp - iat) == expires


@patch("backend.auth.SECRET_KEY", SECRET_KEY)
@patch("backend.auth.ALGORITHM", ALGORITHM)
def test_generate_and_verify_verification_token():
    token = auth.generate_verification_token("test@example.com")
    email = auth.verify_token(token)
    assert email == "test@example.com"


@patch("backend.auth.SECRET_KEY", SECRET_KEY)
@patch("backend.auth.ALGORITHM", ALGORITHM)
def test_verify_token_invalid():
    bad_token = jwt.encode({}, SECRET_KEY, algorithm=ALGORITHM)
    with pytest.raises(HTTPException):
        auth.verify_token(bad_token)


@patch("backend.auth.requests.post")
def test_verify_hcaptcha_success(mock_post):
    mock_post.return_value.json.return_value = {"success": True}
    assert auth.verify_hcaptcha("valid-token") is True


@patch("backend.auth.requests.post")
def test_verify_hcaptcha_failure(mock_post):
    mock_post.return_value.json.return_value = {"success": False}
    assert auth.verify_hcaptcha("invalid-token") is False


@pytest.mark.asyncio
@patch("backend.auth.jwt.decode")
async def test_get_current_user_optional_found(jwt_decode_mock):
    user_mock = MagicMock(spec=User)
    db_mock = AsyncMock()

    # jwt.decode will return a payload with email
    jwt_decode_mock.return_value = {"sub": "test@example.com"}

    # db.execute() should return mock result with scalar_one_or_none()
    execute_result_mock = MagicMock()
    execute_result_mock.scalar_one_or_none.return_value = user_mock
    db_mock.execute.return_value = execute_result_mock

    token = "fake.jwt.token"

    user = await auth.get_current_user_optional(token=token, db=db_mock)
    assert user is user_mock
    jwt_decode_mock.assert_called_once_with(token, auth.SECRET_KEY, algorithms=[auth.ALGORITHM])
    db_mock.execute.assert_called_once()


@patch("backend.auth.SECRET_KEY", SECRET_KEY)
@patch("backend.auth.ALGORITHM", ALGORITHM)
async def test_get_current_user_optional_invalid_token():
    bad_token = "this.is.invalid"
    user = await auth.get_current_user_optional(token=bad_token, db=AsyncMock())
    assert user is None


@patch("backend.auth.SECRET_KEY", SECRET_KEY)
@patch("backend.auth.ALGORITHM", ALGORITHM)
async def test_get_current_user_optional_no_token():
    user = await auth.get_current_user_optional(token=None, db=AsyncMock())
    assert user is None


def test_verify_and_hash_password():
    raw = "s3cret"
    hashed = auth.hash_password(raw)
    assert auth.verify_password(raw, hashed) is True
