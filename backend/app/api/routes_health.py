"""Статус локальной LLM (MCP-серверы будут добавлены вместе с MCPServerManager)."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends

from app.api.deps import get_llm_client
from app.core.llm_client import LLMClient
from app.schemas.health import HealthResponse, ServiceStatus

router = APIRouter(prefix="/api", tags=["health"])


@router.get("/health", response_model=HealthResponse)
async def health(llm: Annotated[LLMClient, Depends(get_llm_client)]) -> HealthResponse:
    llm_health = await llm.health()
    ok = llm_health.reachable and llm_health.error_code is None
    return HealthResponse(status=ServiceStatus.OK if ok else ServiceStatus.DEGRADED, llm=llm_health)
