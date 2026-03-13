import logging
from datetime import datetime, timedelta, timezone
from typing import Optional

import httpx
from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from jose import JWTError, jwt
from passlib.context import CryptContext
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.database import get_db
from app.models import User

logger = logging.getLogger("jroots")

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
admin_oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/login")
user_oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/login", auto_error=False)


def verify_password(plain: str, hashed: str) -> bool:
    return pwd_context.verify(plain, hashed)


def hash_password(password: str) -> str:
    return pwd_context.hash(password)


def _get_admin_hashed_password() -> str:
    settings = get_settings()
    return pwd_context.hash(settings.admin_password)


def authenticate(user: User | None, username: str, password: str) -> str:
    if user is None:
        logger.error("User with email %s not found", username)
        raise HTTPException(status_code=400, detail="Неверный email или пароль")

    expected_hash = _get_admin_hashed_password() if user.is_admin else user.hashed_password
    if not verify_password(password, expected_hash):
        logger.error("Invalid password for user with email %s", username)
        raise HTTPException(status_code=400, detail="Неверный email или пароль")

    if not user.is_verified:
        raise HTTPException(status_code=403, detail="Email не подтвержден")

    access_token = create_access_token(user)
    logger.info("User %s logged in with email %s", user.username, user.email)
    return access_token


def create_access_token(user: User, expires_delta: timedelta | None = None) -> str:
    settings = get_settings()
    to_encode = {
        "sub": user.email,
        "username": user.username,
        "is_admin": user.is_admin,
        "is_verified": user.is_verified,
        "iat": datetime.now(timezone.utc),
        "exp": datetime.now(timezone.utc) + (
            expires_delta or timedelta(minutes=settings.access_token_expire_minutes)
        ),
    }
    return jwt.encode(to_encode, settings.secret_key, algorithm=settings.algorithm)


def generate_verification_token(email: str) -> str:
    settings = get_settings()
    return jwt.encode({"email": email}, settings.secret_key, algorithm=settings.algorithm)


def verify_token(token: str) -> str:
    settings = get_settings()
    try:
        payload = jwt.decode(token, settings.secret_key, algorithms=[settings.algorithm])
        email = payload.get("email")
        if email is None:
            raise HTTPException(status_code=400, detail="Invalid token")
        return email
    except JWTError:
        raise HTTPException(status_code=400, detail="Invalid token")


RESET_TOKEN_EXPIRE_MINUTES = 60


def generate_reset_token(user: User) -> str:
    settings = get_settings()
    payload = {
        "email": user.email,
        "hash_prefix": user.hashed_password[:16],
        "purpose": "reset",
        "exp": datetime.now(timezone.utc) + timedelta(minutes=RESET_TOKEN_EXPIRE_MINUTES),
    }
    return jwt.encode(payload, settings.secret_key, algorithm=settings.algorithm)


def verify_reset_token(token: str) -> tuple[str, str]:
    settings = get_settings()
    try:
        payload = jwt.decode(token, settings.secret_key, algorithms=[settings.algorithm])
        email = payload.get("email")
        hash_prefix = payload.get("hash_prefix")
        if not email or not hash_prefix or payload.get("purpose") != "reset":
            raise HTTPException(status_code=400, detail="Недействительная ссылка для сброса пароля")
        return email, hash_prefix
    except JWTError:
        raise HTTPException(status_code=400, detail="Ссылка для сброса пароля истекла или недействительна")


async def resolve_user_from_token(token: Optional[str], db: AsyncSession) -> Optional[User]:
    if not token:
        return None
    settings = get_settings()
    try:
        payload = jwt.decode(token, settings.secret_key, algorithms=[settings.algorithm])
        email: str = payload.get("sub")
        if email is None:
            return None
        result = await db.execute(select(User).where(User.email == email))
        return result.scalar_one_or_none()
    except JWTError:
        return None


async def get_current_admin(
    token: str = Depends(admin_oauth2_scheme),
    db: AsyncSession = Depends(get_db),
) -> User:
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Invalid credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    admin_user = await resolve_user_from_token(token, db)
    if admin_user is None or not admin_user.is_admin:
        raise credentials_exception
    return admin_user


async def get_current_user_optional(
    token: Optional[str] = Depends(user_oauth2_scheme),
    db: AsyncSession = Depends(get_db),
) -> Optional[User]:
    return await resolve_user_from_token(token, db)


async def verify_hcaptcha(token: str) -> bool:
    settings = get_settings()
    if not settings.hcaptcha_secret_key:
        logger.warning("hCaptcha secret key not configured, skipping verification")
        return True
    async with httpx.AsyncClient(timeout=10.0) as client:
        response = await client.post(
            "https://hcaptcha.com/siteverify",
            data={"response": token, "secret": settings.hcaptcha_secret_key},
        )
    return response.json().get("success", False)
