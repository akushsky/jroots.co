from typing import Optional

from pydantic import BaseModel, Field


class TelegramUser(BaseModel):
    id: int
    first_name: str
    username: Optional[str] = None


class Chat(BaseModel):
    id: int
    type: str


class Message(BaseModel):
    message_id: int
    chat: Chat
    caption: str | None = None


class CallbackQuery(BaseModel):
    id: str
    from_user: TelegramUser = Field(..., alias="from")
    message: Optional[Message] = None
    data: Optional[str] = None


class Update(BaseModel):
    update_id: int
    callback_query: Optional[CallbackQuery] = None
