"""In-process MCP-сервер ``awesome_posts``: рендер Instagram-поста по текстам от модели.

Заменяет внешний Higgsfield MCP: генеративная графика локальной 4B-модели
недоступна, поэтому картинка собирается детерминированно — фон шаблона
(``backend/assets/background``) + тексты из Structured Output.
"""

from __future__ import annotations

import asyncio
import time
from datetime import UTC, datetime
from uuid import uuid4

from mcp.server.mcpserver import MCPServer
from mcp.server.mcpserver.exceptions import ToolError

from app.core.logger import payload_hash
from app.core.post_renderer import WIDTH, HEIGHT, PostRenderer, PostRenderError
from app.core.post_store import PostStore
from app.schemas.smm import PostCopySchema, PostRecord, PostTemplate, RenderedPost


def build_posts_server(renderer: PostRenderer, store: PostStore) -> MCPServer:
    server = MCPServer(
        name="orcify-awesome-posts",
        instructions="Локальный рендер Instagram-постов 1080×1350 по шаблонам cosmos / neon / summit.",
    )

    @server.tool(
        name="render_post",
        description="Положить тексты поста на фон выбранного шаблона и сохранить PNG в галерею",
    )
    async def render_post(template: PostTemplate, content: PostCopySchema) -> RenderedPost:
        started = time.monotonic()
        try:
            # Pillow — CPU-работа: уносим из event loop, чтобы не тормозить SSE других задач.
            png = await asyncio.to_thread(renderer.render, template, content)
        except PostRenderError as exc:
            raise ToolError(f"posts_input_error:{exc.code}") from None
        post = RenderedPost(
            post_id=uuid4().hex,
            template=template,
            image_url="",
            width=WIDTH,
            height=HEIGHT,
            sha256=payload_hash(png),
            size_bytes=len(png),
            render_ms=round((time.monotonic() - started) * 1000),
            created_at=datetime.now(UTC),
        )
        post.image_url = f"/api/posts/{post.post_id}.png"
        store.save(PostRecord(post=post, content=content.model_copy(update={"template": template})), png)
        return post

    return server
