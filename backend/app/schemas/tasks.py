"""Схемы HTTP-API запуска задач."""

from __future__ import annotations

from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class TaskAttachment(BaseModel):
    """CSV-файл, прочитанный в браузере как текст (на диск не сохраняется)."""

    model_config = ConfigDict(extra="forbid")

    filename: str = Field(min_length=1, max_length=200)
    media_type: Literal["text/csv"] = "text/csv"
    content: str = Field(min_length=1, max_length=5_000_000)


class TaskCreateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    text: str = Field(min_length=1, max_length=50_000)
    attachment: TaskAttachment | None = None
    opening_balance: float = Field(default=0.0, description="Остаток на начало периода для расчёта кассовых разрывов")


class TaskCreatedResponse(BaseModel):
    task_id: UUID
    events_url: str
