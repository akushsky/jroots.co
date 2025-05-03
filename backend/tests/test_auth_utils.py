import pytest
from unittest.mock import patch, MagicMock, AsyncMock
from datetime import timedelta
from jose import jwt
from fastapi import HTTPException
from backend import auth

# Mock secrets
SECRET_KEY = "testsecret"
ALGORITHM = "HS256"


@patch("backend.auth.SECRET_KEY", SECRET_KEY)
@patch("backend.auth.ALGORITHM", ALGORITHM)
def test_create_access_token_and_verify():
    token = auth.create_access_token({"sub": "admin"}, timedelta(minutes=5))
    payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
    assert payload["sub"] == "admin"
    assert "exp" in payload


@patch("backend.auth.pwd_context.verify", return_value=True)
def test_authenticate_admin_success(mock_verify):
    result = auth.authenticate_admin("admin", "fake_password")
    assert result == {"username": "admin"}


@patch("backend.auth.pwd_context.verify", return_value=False)
def test_authenticate_admin_invalid_password(mock_verify):
    result = auth.authenticate_admin("admin", "wrong")
    assert result is False


def test_authenticate_admin_invalid_username():
    result = auth.authenticate_admin("notadmin", "whatever")
    assert result is False


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


@patch("backend.auth.SECRET_KEY", SECRET_KEY)
@patch("backend.auth.ALGORITHM", ALGORITHM)
async def test_get_current_user_optional_found():
    user_mock = MagicMock()

    # Mock result of db.execute()h
    execute_result_mock = MagicMock()
    execute_result_mock.scalar_one_or_none.return_value = user_mock

    db_mock = AsyncMock()
    db_mock.execute.return_value = execute_result_mock  # <-- await db.execute() will return this

    token = jwt.encode({"sub": "test@example.com"}, SECRET_KEY, algorithm=ALGORITHM)

    user = await auth.get_current_user_optional(token=token, db=db_mock)
    assert user is user_mock


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
