"""Локальная очередь отложенной синхронизации для недоступных Atlassian/n8n.

В файл пишутся только уже анонимизированные аргументы (их формирует
MCPServerManager до вызова fallback), таблица соответствия не сохраняется.
"""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

from pydantic import BaseModel, JsonValue

from app.core.logger import get_logger
from app.schemas.mcp import McpCallRequest, McpCallResult

log = get_logger(__name__)


class QueuedCall(BaseModel):
    id: str
    queued_at: datetime
    server: str
    tool: str
    arguments: dict[str, JsonValue]
    reason: str


class SyncQueue:
    def __init__(self, path: Path) -> None:
        self._path = path
        self._lock = asyncio.Lock()

    async def enqueue(self, request: McpCallRequest, reason: str) -> QueuedCall:
        item = QueuedCall(
            id=uuid4().hex,
            queued_at=datetime.now(UTC),
            server=request.server,
            tool=request.tool,
            arguments=request.arguments,
            reason=reason[:64],
        )
        async with self._lock:
            self._path.parent.mkdir(parents=True, exist_ok=True)
            with self._path.open("a", encoding="utf-8") as f:
                f.write(item.model_dump_json() + "\n")
        log.info("sync_queued", server=request.server, stage=request.tool, request_id=item.id)
        return item

    async def fallback_handler(self, request: McpCallRequest, reason: str) -> McpCallResult:
        item = await self.enqueue(request, reason)
        return McpCallResult(
            server=request.server,
            tool=request.tool,
            ok=False,
            degraded=True,
            error_code=reason[:64],
            structured={"queued_id": item.id},
        )

    def pending(self) -> list[QueuedCall]:
        if not self._path.is_file():
            return []
        return [QueuedCall.model_validate_json(line) for line in self._path.read_text(encoding="utf-8").splitlines() if line]

