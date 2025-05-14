import os
from datetime import datetime, timedelta, timezone
from typing import Optional

import requests
from fastapi import HTTPException, Depends, status
from fastapi.security import OAuth2PasswordBearer
from jose import JWTError, jwt
from passlib.context import CryptContext
from sqlalchemy.ext.asyncio import AsyncSession

import database
import models
from logging_middleware import logger
from config import PASSWORD, SECRET_KEY, ALGORITHM
from crud import resolve_user_from_token
from models import User

ACCESS_TOKEN_EXPIRE_MINUTES = 60 * 24

HCAPTCHA_SECRET_KEY = os.getenv("HCAPTCHA_SECRET_KEY", "dev_key")

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
admin_oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/admin/login")
user_oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/login", auto_error=False)

admin = {
    "username": "admin",
    "hashed_password": pwd_context.hash(PASSWORD)
}


def authenticate(user: models.User, username: str, password: str) -> str | None:
    if user is None:
        logger.error("User with email %s not found", username)
        raise HTTPException(status_code=400, detail="Неверный email или пароль")

    if not verify_password(password, admin["hashed_password"] if user.is_admin  else user.hashed_password):
        logger.error("Invalid password for user with email %s", username)
        raise HTTPException(status_code=400, detail="Неверный email или пароль")

    if not user.is_verified:
        raise HTTPException(status_code=403, detail="Email не подтвержден")

    access_token = create_access_token(user)

    logger.info("User %s logged in with email %s", user.username, user.email)
    return access_token


def create_access_token(user: User, expires_delta: timedelta | None = None) -> str:
    to_encode = {
        "sub": user.email,
        "username": user.username,
        "is_admin": user.is_admin,
        "is_verified": user.is_verified,
        "iat": datetime.now(timezone.utc),
        "exp": datetime.now(timezone.utc) + (expires_delta or timedelta(days=1))
    }
    return jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)


async def get_current_admin(
        token: str = Depends(admin_oauth2_scheme),
        db: AsyncSession = Depends(database.get_db)
) -> str | None:
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Invalid credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    admin_user = await resolve_user_from_token(token, db)
    if admin_user is None or not admin_user.is_admin:
        raise credentials_exception
    return admin_user.email


def verify_hcaptcha(token: str) -> bool:
    response = requests.post("https://hcaptcha.com/siteverify", data={
        "response": token,
        "secret": HCAPTCHA_SECRET_KEY
    })
    return response.json().get("success", False)


def generate_verification_token(email: str):
    token = jwt.encode({"email": email}, SECRET_KEY, algorithm=ALGORITHM)
    return token


def verify_token(token: str):
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        email = payload.get("email")
        if email is None:
            raise HTTPException(status_code=400, detail="Invalid token")
        return email
    except JWTError:
        raise HTTPException(status_code=400, detail="Invalid token")


async def get_current_user_optional(
        token: Optional[str] = Depends(user_oauth2_scheme),
        db: AsyncSession = Depends(database.get_db)
) -> Optional[User]:
    return await resolve_user_from_token(token, db)


def verify_password(plain, hashed):
    return pwd_context.verify(plain, hashed)


def hash_password(password):
    return pwd_context.hash(password)
