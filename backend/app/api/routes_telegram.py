"""Статус Telegram-бота (канал автоматизации)."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends

from app.api.deps import get_telegram_bot
from app.channels.telegram import TelegramBot
from app.schemas.telegram import TelegramStatus

router = APIRouter(prefix="/api/telegram", tags=["telegram"])


@router.get("/status", response_model=TelegramStatus)
async def telegram_status(bot: Annotated[TelegramBot | None, Depends(get_telegram_bot)]) -> TelegramStatus:
    return bot.status() if bot is not None else TelegramStatus(configured=False, polling=False)
