"""Схемы эндпоинта статуса системы."""

from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel


class ServiceStatus(StrEnum):
    OK = "ok"
    DEGRADED = "degraded"


class LLMHealth(BaseModel):
    reachable: bool
    model: str | None = None
    loaded: bool | None = None
    context_length: int | None = None
    latency_ms: int
    error_code: str | None = None


class HealthResponse(BaseModel):
    status: ServiceStatus
    llm: LLMHealth
