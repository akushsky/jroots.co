import logging

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Request
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.database import get_db
from app.models import User
from app.schemas import RegisterRequest, ForgotPasswordRequest, ResetPasswordRequest
from app.services.auth import (
    authenticate,
    generate_reset_token,
    generate_verification_token,
    hash_password,
    verify_hcaptcha,
    verify_reset_token,
    verify_token,
)
from app.rate_limit import limiter
from app.services.email import send_email

logger = logging.getLogger("jroots")

router = APIRouter(prefix="/api", tags=["auth"])


@router.post("/register")
@limiter.limit("5/minute")
async def register_user(
    request: Request,
    data: RegisterRequest,
    db: AsyncSession = Depends(get_db),
    background_tasks: BackgroundTasks = BackgroundTasks(),
):
    if not await verify_hcaptcha(data.captcha_token):
        raise HTTPException(status_code=400, detail="Проверка CAPTCHA не пройдена")

    existing_user = await db.execute(select(User).where(User.email == data.email))
    if existing_user.scalar_one_or_none():
        raise HTTPException(status_code=400, detail="Этот email уже зарегистрирован")

    existing_username = await db.execute(select(User).where(User.username == data.username))
    if existing_username.scalar_one_or_none():
        raise HTTPException(status_code=400, detail="Имя пользователя уже занято")

    settings = get_settings()
    verification_token = generate_verification_token(str(data.email))
    verification_url = f"{settings.frontend_url}/verify?token={verification_token}"

    hashed_pw = hash_password(data.password)
    user = User(
        username=data.username,
        email=data.email,
        hashed_password=hashed_pw,
        telegram_username=data.telegram_username,
        is_verified=False,
    )

    db.add(user)
    try:
        await db.commit()
    except IntegrityError:
        await db.rollback()
        raise HTTPException(status_code=409, detail="Имя пользователя или email уже заняты")

    logger.info("User %s registered with email %s", data.username, data.email)

    html = f"""
    <h1>Подтвердите регистрацию</h1>
    <p>Здравствуйте, {data.username}!</p>
    <p>Пожалуйста, подтвердите ваш email, перейдя по ссылке ниже:</p>
    <a href="{verification_url}">Подтвердить Email</a>
    """
    background_tasks.add_task(
        send_email,
        to_email=str(data.email),
        subject="Подтверждение регистрации",
        html_content=html,
    )

    return {"message": "Регистрация прошла успешно. Пожалуйста, проверьте вашу почту для подтверждения."}


@router.get("/verify")
async def verify_user(token: str, db: AsyncSession = Depends(get_db)):
    email = verify_token(token)

    result = await db.execute(select(User).where(User.email == email))
    user = result.scalar_one_or_none()
    if user is None:
        raise HTTPException(status_code=404, detail="User not found")

    user.is_verified = True
    await db.commit()

    logger.info("User %s verified their email %s", user.username, user.email)

    return {"message": "User verified successfully"}


@router.post("/login")
@limiter.limit("10/minute")
async def login_user(
    request: Request,
    form_data: OAuth2PasswordRequestForm = Depends(),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(User).where(User.email == form_data.username))
    user = result.scalar_one_or_none()
    access_token = authenticate(user, form_data.username, form_data.password)
    return {"access_token": access_token, "token_type": "bearer"}


@router.post("/forgot-password")
@limiter.limit("3/minute")
async def forgot_password(
    request: Request,
    data: ForgotPasswordRequest,
    db: AsyncSession = Depends(get_db),
    background_tasks: BackgroundTasks = BackgroundTasks(),
):
    result = await db.execute(select(User).where(User.email == data.email))
    user = result.scalar_one_or_none()

    if user and user.is_verified:
        settings = get_settings()
        token = generate_reset_token(user)
        reset_url = f"{settings.frontend_url}/reset?token={token}"

        html = f"""
        <h1>Сброс пароля</h1>
        <p>Здравствуйте, {user.username}!</p>
        <p>Вы запросили сброс пароля. Перейдите по ссылке ниже, чтобы установить новый пароль:</p>
        <a href="{reset_url}">Сбросить пароль</a>
        <p>Ссылка действительна в течение 1 часа.</p>
        <p>Если вы не запрашивали сброс пароля, проигнорируйте это письмо.</p>
        """
        background_tasks.add_task(
            send_email,
            to_email=str(data.email),
            subject="Сброс пароля — JRoots",
            html_content=html,
        )
        logger.info("Password reset requested for %s", data.email)

    return {"message": "Если аккаунт с таким email существует, на него будет отправлена ссылка для сброса пароля."}


@router.post("/reset-password")
async def reset_password(
    data: ResetPasswordRequest,
    db: AsyncSession = Depends(get_db),
):
    email, hash_prefix = verify_reset_token(data.token)

    result = await db.execute(select(User).where(User.email == email))
    user = result.scalar_one_or_none()
    if user is None:
        raise HTTPException(status_code=400, detail="Пользователь не найден")

    if user.hashed_password[:16] != hash_prefix:
        raise HTTPException(status_code=400, detail="Ссылка для сброса пароля уже была использована")

    user.hashed_password = hash_password(data.new_password)
    await db.commit()

    logger.info("Password reset completed for %s", email)
    return {"message": "Пароль успешно изменён. Теперь вы можете войти с новым паролем."}
