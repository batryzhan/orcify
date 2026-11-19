"""Тапсырмаларды іске қосудың HTTP-API схемалары."""

from __future__ import annotations

from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.schemas.intent import DomainEnum
from app.schemas.smm import PostTemplate


class TaskAttachment(BaseModel):
    """Браузерде мәтін ретінде оқылған CSV-файл (дискіге сақталмайды)."""

    model_config = ConfigDict(extra="forbid")

    filename: str = Field(min_length=1, max_length=200)
    media_type: Literal["text/csv"] = "text/csv"
    content: str = Field(min_length=1, max_length=5_000_000)


class TaskCreateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    text: str = Field(min_length=1, max_length=50_000)
    attachment: TaskAttachment | None = None
    opening_balance: float = Field(default=0.0, description="Кезең басындағы қалдық — ақша ағынының үзілістерін есептеу үшін")
    # UI-да пост үлгісін айқын таңдау; None — үлгіні модель таңдайды.
    post_template: PostTemplate | None = None
    # Интерфейс терезесі берген домен; None — доменді Smart Router анықтайды.
    domain: DomainEnum | None = None


class TaskCreatedResponse(BaseModel):
    task_id: UUID
    events_url: str
