"""In-process MCP-сервері ``awesome_posts``: модель мәтіндері бойынша Instagram-пост рендері.

Сыртқы Higgsfield MCP-нің орнын басады: жергілікті 4B-модельге генеративті графика
қолжетімсіз, сондықтан сурет детерминистік жиналады — үлгі фоны
(``backend/assets/background``) + Structured Output мәтіндері.
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
        instructions="cosmos / neon / summit үлгілері бойынша 1080×1350 Instagram-посттарының жергілікті рендері.",
    )

    @server.tool(
        name="render_post",
        description="Пост мәтіндерін таңдалған үлгі фонына салып, PNG-ді галереяға сақтау",
    )
    async def render_post(template: PostTemplate, content: PostCopySchema) -> RenderedPost:
        started = time.monotonic()
        try:
            # Pillow — CPU жұмысы: басқа тапсырмалардың SSE-ін тежемеу үшін event loop-тан шығарамыз.
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
