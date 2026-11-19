"""Awesome Posts: үлгілер, дайын посттар галереясы және Telegram-ға жіберу."""

from __future__ import annotations

import asyncio
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import FileResponse, Response

from app.api.deps import get_post_renderer, get_post_store, get_telegram_bot
from app.channels.telegram import TelegramBot
from app.core.post_renderer import TEMPLATES, PostRenderer
from app.core.post_store import PostStore
from app.core.post_renderer import PostRenderError
from app.schemas.smm import PostCopySchema, PostRecord, PostTemplate, TemplateInfo
from app.schemas.telegram import SendPostResponse

router = APIRouter(prefix="/api/posts", tags=["posts"])
CACHE = {"Cache-Control": "public, max-age=86400"}

# UI-дағы үлгілер превьюіне арналған демо-мәтіндер (бұл мазмұн мысалы, модель промпты емес).
PREVIEW_COPY: dict[PostTemplate, dict[str, str | None]] = {
    PostTemplate.COSMOS: {"kicker": None, "headline": "Танысыңыз", "headline_accent": "Orcify командасы",
                          "subtitle": "Біз жергілікті ЖИ-ды бизнеске жұмыс істеуге үйретеміз", "cta": None},
    PostTemplate.NEON: {"kicker": "−30%", "headline": "Қара", "headline_accent": "Жұма",
                        "subtitle": "Жексенбіге дейін жеткізудің барлық тарифтеріне жеңілдік", "cta": "Тапсырыс беру"},
    PostTemplate.SUMMIT: {"kicker": "Orcify құндылықтары", "headline": "Клиент деректері",
                          "headline_accent": "құрылғыдан шықпайды",
                          "subtitle": "Коммерциялық құпияны сеніп тапсыруға болатын ЖИ", "cta": None},
}
_previews: dict[PostTemplate, bytes] = {}


@router.get("/templates", response_model=list[TemplateInfo])
async def templates() -> list[TemplateInfo]:
    return [
        TemplateInfo(
            id=spec.id,
            title=spec.title,
            use_case=spec.use_case,
            background_url=f"/api/posts/templates/{spec.id.value}/background",
            preview_url=f"/api/posts/templates/{spec.id.value}/preview",
            credit=spec.credit,
        )
        for spec in TEMPLATES.values()
    ]


@router.get("/templates/{template}/background")
async def template_background(
    template: PostTemplate, renderer: Annotated[PostRenderer, Depends(get_post_renderer)]
) -> FileResponse:
    path = renderer.background_path(template)
    if not path.is_file():
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="background missing")
    return FileResponse(path, media_type="image/jpeg", headers=CACHE)


@router.get("/templates/{template}/preview")
async def template_preview(
    template: PostTemplate, renderer: Annotated[PostRenderer, Depends(get_post_renderer)]
) -> Response:
    """Үлгідегі пост мысалы (бір рет рендерленеді және жадта кэштеледі)."""
    if template not in _previews:
        content = PostCopySchema.model_validate(
            {**PREVIEW_COPY[template], "template": template, "handle": "@orcify", "caption": "", "hashtags": []}
        )
        try:
            _previews[template] = await asyncio.to_thread(renderer.render, template, content)
        except PostRenderError:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="template assets missing") from None
    return Response(_previews[template], media_type="image/png", headers=CACHE)


@router.get("", response_model=list[PostRecord])
async def list_posts(store: Annotated[PostStore, Depends(get_post_store)]) -> list[PostRecord]:
    return store.list()


@router.get("/{post_id}.png")
async def post_image(post_id: str, store: Annotated[PostStore, Depends(get_post_store)]) -> FileResponse:
    path = store.png_path(post_id)
    if path is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="post not found")
    return FileResponse(path, media_type="image/png", filename=f"orcify_post_{post_id[:8]}.png", headers=CACHE)


@router.post("/{post_id}/telegram", response_model=SendPostResponse)
async def send_to_telegram(
    post_id: str,
    store: Annotated[PostStore, Depends(get_post_store)],
    bot: Annotated[TelegramBot | None, Depends(get_telegram_bot)],
) -> SendPostResponse:
    if store.get(post_id) is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="post not found")
    if bot is None or not bot.configured:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="telegram bot not configured")
    sent = await bot.send_post(post_id)
    return SendPostResponse(sent=sent, linked_chats=bot.status().linked_chats)
