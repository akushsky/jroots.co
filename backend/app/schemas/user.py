from pydantic import BaseModel, EmailStr, Field, field_validator


class RegisterRequest(BaseModel):
    username: str
    email: EmailStr
    password: str
    telegram_username: str | None = None
    captcha_token: str
    # Client-side fingerprintJS hash (anti-abuse), optional.
    fingerprint: str | None = Field(default=None, max_length=128)

    @field_validator("username")
    @classmethod
    def strip_username(cls, v: str) -> str:
        return v.strip()

    @field_validator("telegram_username")
    @classmethod
    def strip_telegram(cls, v: str | None) -> str | None:
        if v is not None:
            return v.strip() or None
        return v

    @field_validator("fingerprint")
    @classmethod
    def strip_fingerprint(cls, v: str | None) -> str | None:
        if v is not None:
            return v.strip() or None
        return v


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class ForgotPasswordRequest(BaseModel):
    email: EmailStr


class ResetPasswordRequest(BaseModel):
    token: str
    new_password: str


class AccessRequest(BaseModel):
    image_id: int
    search_text_content: str
