"""Схемы HTTP-API запуска задач."""

from __future__ import annotations

from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class TaskCreateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    text: str = Field(min_length=1, max_length=50_000)


class TaskCreatedResponse(BaseModel):
    task_id: UUID
    events_url: str
