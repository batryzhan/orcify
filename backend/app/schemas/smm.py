"""Схемы домена SMM — «Awesome Posts» (Сценарий Б).

Локальная модель не генерирует картинки: она пишет только тексты поста
(Structured Output ``PostCopySchema``), а детерминированный рендерер
(Pillow) кладёт их на фоновое фото выбранного шаблона.
"""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field


class PostTemplate(StrEnum):
    COSMOS = "cosmos"  # анонс / знакомство с командой: космос, крупный градиентный заголовок
    NEON = "neon"  # запуск продукта / акция: ночной неоновый город, плашка и кнопка
    SUMMIT = "summit"  # цитата / мероприятие: горы, спокойная типографика


class PostCopySchema(BaseModel):
    """Structured Output копирайтера. ``null`` = элемент не нужен в этом посте."""

    model_config = ConfigDict(extra="forbid")

    template: PostTemplate = Field(description="Шаблон оформления под смысл поста")
    kicker: str | None = Field(max_length=40, description="Короткая надпись над заголовком (NEW, −30%, 12 ДЕКАБРЯ)")
    headline: str = Field(min_length=1, max_length=48, description="Первая строка заголовка, 1–3 слова")
    headline_accent: str = Field(min_length=1, max_length=48, description="Вторая, акцентная строка, 1–3 слова")
    subtitle: str = Field(max_length=160, description="Подзаголовок, одно предложение")
    cta: str | None = Field(max_length=40, description="Призыв к действию на кнопке, 1–3 слова")
    handle: str = Field(max_length=40, description="Аккаунт бренда, начинается с @")
    caption: str = Field(max_length=1500, description="Подпись к посту для Instagram")
    hashtags: list[str] = Field(max_length=12, description="Хэштеги без пробелов")


class RenderPostArgs(BaseModel):
    """Аргументы MCP-инструмента ``render_post``."""

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
    """Метаданные сохранённого поста (галерея). Тексты — сгенерированный контент, не запрос."""

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
