"""Жергілікті LLM және MCP-серверлердің күйі."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends

from app.api.deps import get_llm_client, get_mcp_manager
from app.core.llm_client import LLMClient
from app.mcp.manager import MCPServerManager
from app.schemas.health import HealthResponse, ServiceStatus
from app.schemas.mcp import McpServerHealth

router = APIRouter(prefix="/api", tags=["health"])


@router.get("/health", response_model=HealthResponse)
async def health(llm: Annotated[LLMClient, Depends(get_llm_client)]) -> HealthResponse:
    """Жергілікті модельді жылдам тексеру (UI әр 15 с сайын сұратады)."""
    llm_health = await llm.health()
    ok = llm_health.reachable and llm_health.error_code is None
    return HealthResponse(status=ServiceStatus.OK if ok else ServiceStatus.DEGRADED, llm=llm_health)


@router.get("/health/mcp", response_model=list[McpServerHealth])
async def mcp_health(manager: Annotated[MCPServerManager, Depends(get_mcp_manager)]) -> list[McpServerHealth]:
    """MCP-серверлер күйі: жергілікті серверлер іске қосылады және сұратылады, сыртқылар — бапталған болса."""
    return await manager.health()
