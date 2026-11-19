"""SMM домені схемалары — «Awesome Posts» (Б сценарийі).

Жергілікті модель суреттерді генерацияламайды: ол тек пост мәтіндерін жазады
(Structured Output ``PostCopySchema``), ал детерминистік рендерер
(Pillow) оларды таңдалған үлгінің фондық фотосына салады.
"""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field


class PostTemplate(StrEnum):
    COSMOS = "cosmos"  # анонс / команданы таныстыру: ғарыш, үлкен градиентті тақырып
    NEON = "neon"  # өнімді іске қосу / акция: түнгі неонды қала, жолақ және батырма
    SUMMIT = "summit"  # дәйексөз / іс-шара: таулар, тыныш типография


class PostCopySchema(BaseModel):
    """Копирайтердің Structured Output-ы. ``null`` = бұл постта элемент қажет емес."""

    model_config = ConfigDict(extra="forbid")

    template: PostTemplate = Field(description="Пост мағынасына сай безендіру үлгісі")
    kicker: str | None = Field(max_length=40, description="Тақырып үстіндегі қысқа жазу (NEW, −30%, 12 ЖЕЛТОҚСАН)")
    headline: str = Field(min_length=1, max_length=48, description="Тақырыптың бірінші жолы, 1–3 сөз")
    headline_accent: str = Field(min_length=1, max_length=48, description="Екінші, акценттік жол, 1–3 сөз")
    subtitle: str = Field(max_length=160, description="Ішкі тақырып, бір сөйлем")
    cta: str | None = Field(max_length=40, description="Батырмадағы әрекетке шақыру, 1–3 сөз")
    handle: str = Field(max_length=40, description="Бренд аккаунты, @ белгісінен басталады")
    caption: str = Field(max_length=1500, description="Instagram үшін постқа жазба")
    hashtags: list[str] = Field(max_length=12, description="Бос орынсыз хэштегтер")


class RenderPostArgs(BaseModel):
    """``render_post`` MCP-құралының аргументтері."""

    template: PostTemplate
    content: PostCopySchema


class RenderedPost(BaseModel):
    post_id: str = Field(pattern=r"^[0-9a-f]{32}$")
    template: PostTemplate
    image_url: str
    width: int
    height: int
    sha256: str
    size_bytes: int
    render_ms: int
    created_at: datetime


class PostRecord(BaseModel):
    """Сақталған пост метадеректері (галерея). Мәтіндер — генерацияланған контент, сұраныс емес."""

    post: RenderedPost
    content: PostCopySchema
    issue_key: str | None = None


class TemplateInfo(BaseModel):
    id: PostTemplate
    title: str
    use_case: str
    background_url: str
    preview_url: str
    credit: str


class PostResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    content: PostCopySchema
    post: RenderedPost
    template_forced: bool = False
