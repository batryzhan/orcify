"""Сценарий Б (SMM, «Awesome Posts»): тексты поста (локальная Gemma, Structured
Output) -> рендер PNG через in-process MCP ``awesome_posts``.

Весь сценарий локальный: ни текст запроса, ни картинка не уходят во внешние
сервисы. Пост можно отправить в Telegram только явным действием пользователя.
"""

from __future__ import annotations

from typing import Final

from pydantic import ValidationError

from app.core.llm_client import ChatMessage, LLMClient
from app.core.prompts import PromptLoader
from app.mcp.manager import MCPServerManager
from app.schemas.smm import PostCopySchema, PostTemplate, RenderedPost, RenderPostArgs

COPY_PROMPT: Final = "post_copywriter"
POSTS_SERVER: Final = "awesome_posts"
RENDER_TOOL: Final = "render_post"


class PostRenderFailedError(Exception):
    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


class SmmService:
    def __init__(self, llm: LLMClient, prompts: PromptLoader, mcp: MCPServerManager) -> None:
        self._llm = llm
        self._prompts = prompts
        self._mcp = mcp

    async def write_copy(self, text: str, forced: PostTemplate | None = None) -> PostCopySchema:
        user = text if forced is None else f"{text}\n\n[Шаблон выбран пользователем: {forced.value}]"
        messages = [
            ChatMessage(role="system", content=self._prompts.load(COPY_PROMPT)),
            ChatMessage(role="user", content=user),
        ]
        content = (await self._llm.structured(messages, PostCopySchema, stage="writing_copy")).data
        return content if forced is None else content.model_copy(update={"template": forced})

    async def render(self, content: PostCopySchema) -> RenderedPost:
        result = await self._mcp.call_tool(
            POSTS_SERVER, RENDER_TOOL, RenderPostArgs(template=content.template, content=content)
        )
        if not result.ok or result.structured is None:
            raise PostRenderFailedError(result.error_code or "render_failed")
        try:
            return RenderedPost.model_validate(result.structured)
        except ValidationError:
            raise PostRenderFailedError("render_contract_mismatch") from None
