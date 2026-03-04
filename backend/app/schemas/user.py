from pydantic import BaseModel, EmailStr


class RegisterRequest(BaseModel):
    username: str
    email: EmailStr
    password: str
    telegram_username: str | None = None
    captcha_token: str


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class AccessRequest(BaseModel):
    image_id: int
    search_text_content: str
