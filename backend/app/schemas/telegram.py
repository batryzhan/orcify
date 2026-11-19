"""Схемы Telegram Bot API (только нужные поля) и статуса канала автоматизации."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class _Tg(BaseModel):
    model_config = ConfigDict(extra="ignore")


class TgUser(_Tg):
    id: int
    is_bot: bool = False
    first_name: str = ""
    username: str | None = None


class TgChat(_Tg):
    id: int
    type: str


class TgDocument(_Tg):
    file_id: str
    file_name: str | None = None
    mime_type: str | None = None
    file_size: int | None = None


class TgMessage(_Tg):
    message_id: int
    chat: TgChat
    text: str | None = None
    caption: str | None = None
    document: TgDocument | None = None


class TgUpdate(_Tg):
    update_id: int
    message: TgMessage | None = None


class TgFile(_Tg):
    file_id: str
    file_path: str | None = None
    file_size: int | None = None


class TelegramStatus(BaseModel):
    configured: bool
    polling: bool
    bot_username: str | None = None
    bot_name: str | None = None
    linked_chats: int = 0
    handled_messages: int = 0
    completed_runs: int = 0
    last_error: str | None = None


class SendPostResponse(BaseModel):
    sent: int = Field(ge=0)
    linked_chats: int = Field(ge=0)
