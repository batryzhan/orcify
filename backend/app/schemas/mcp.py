"""Схемы MCP Integration Layer."""

from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field, JsonValue

from app.schemas.intent import DomainEnum


class McpTransport(StrEnum):
    STDIO = "stdio"
    HTTP = "http"  # Streamable HTTP


class McpServerSpec(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    name: str
    domains: frozenset[DomainEnum]
    is_external: bool
    transport: McpTransport
    command: str | None = None
    args: tuple[str, ...] = ()
    url: str | None = None
    timeout_s: float = Field(default=60.0, gt=0)
    enabled: bool = True
    description: str = ""


class McpToolInfo(BaseModel):
    server: str
    name: str
    description: str
    input_schema: dict[str, JsonValue]


class McpCallRequest(BaseModel):
    server: str
    tool: str
    arguments: dict[str, JsonValue]


class McpCallResult(BaseModel):
    server: str
    tool: str
    ok: bool
    degraded: bool = False
    text: str | None = None
    structured: dict[str, JsonValue] | None = None
    error_code: str | None = None
    latency_ms: int = 0
    anonymized: bool = False


class McpServerHealth(BaseModel):
    name: str
    domains: list[DomainEnum]
    is_external: bool
    enabled: bool
    reachable: bool
    tools: list[str] = Field(default_factory=list)
    error_code: str | None = None
