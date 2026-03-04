import pytest
from unittest.mock import MagicMock, AsyncMock

from fastapi import HTTPException

from app.models import User
from app.services.auth import authenticate, get_current_admin, get_current_user_optional, create_access_token


def _make_user(email="u@example.com", username="user", is_admin=False, is_verified=True, password_hash="$2b$12$x"):
    user = MagicMock(spec=User)
    user.email = email
    user.username = username
    user.is_admin = is_admin
    user.is_verified = is_verified
    user.hashed_password = password_hash
    user.id = 1
    return user


def test_authenticate_none_user():
    with pytest.raises(HTTPException) as exc:
        authenticate(None, "nobody@test.com", "pass")
    assert exc.value.status_code == 400


def test_authenticate_wrong_password():
    from app.services.auth import hash_password
    user = _make_user(password_hash=hash_password("correct"))
    with pytest.raises(HTTPException) as exc:
        authenticate(user, user.email, "wrong")
    assert exc.value.status_code == 400


def test_authenticate_unverified():
    from app.services.auth import hash_password
    user = _make_user(is_verified=False, password_hash=hash_password("pass"))
    with pytest.raises(HTTPException) as exc:
        authenticate(user, user.email, "pass")
    assert exc.value.status_code == 403


def test_authenticate_success():
    from app.services.auth import hash_password
    user = _make_user(password_hash=hash_password("pass"))
    token = authenticate(user, user.email, "pass")
    assert isinstance(token, str)
    assert len(token) > 0


async def test_get_current_admin_valid():
    from app.services.auth import hash_password
    admin = _make_user(is_admin=True, password_hash=hash_password("p"))
    token = create_access_token(admin)

    db = AsyncMock()
    execute_result = MagicMock()
    execute_result.scalar_one_or_none.return_value = admin
    db.execute.return_value = execute_result

    result = await get_current_admin(token=token, db=db)
    assert result is admin


async def test_get_current_admin_non_admin():
    user = _make_user(is_admin=False)
    token = create_access_token(user)

    db = AsyncMock()
    execute_result = MagicMock()
    execute_result.scalar_one_or_none.return_value = user
    db.execute.return_value = execute_result

    with pytest.raises(HTTPException) as exc:
        await get_current_admin(token=token, db=db)
    assert exc.value.status_code == 401


async def test_get_current_admin_invalid_token():
    db = AsyncMock()
    with pytest.raises(HTTPException) as exc:
        await get_current_admin(token="bad.token.here", db=db)
    assert exc.value.status_code == 401


async def test_get_current_user_optional_none():
    db = AsyncMock()
    result = await get_current_user_optional(token=None, db=db)
    assert result is None


async def test_get_current_user_optional_valid():
    user = _make_user()
    token = create_access_token(user)

    db = AsyncMock()
    execute_result = MagicMock()
    execute_result.scalar_one_or_none.return_value = user
    db.execute.return_value = execute_result

    result = await get_current_user_optional(token=token, db=db)
    assert result is user
