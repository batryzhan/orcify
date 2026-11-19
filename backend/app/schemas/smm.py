"""Схемы домена SMM (Сценарий Б)."""

from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field

from app.schemas.legal import DocumentInfo
from app.schemas.privacy import AnonymizationReport


class Scene(BaseModel):
    model_config = ConfigDict(extra="forbid")

    scene_no: int = Field(ge=1, le=12)
    duration_s: int = Field(ge=1, le=60)
    visual: str = Field(max_length=400, description="Что в кадре")
    voiceover: str = Field(max_length=400, description="Закадровый текст")
    on_screen_text: str = Field(max_length=120, description="Текст на экране")


class VideoScriptSchema(BaseModel):
    """Structured Output сценариста."""

    model_config = ConfigDict(extra="forbid")

    title: str = Field(max_length=120)
    goal: str = Field(max_length=300)
    target_audience: str = Field(max_length=300)
    aspect_ratio: str = Field(pattern=r"^(9:16|16:9|1:1)$")
    duration_s: int = Field(ge=5, le=120)
    scenes: list[Scene] = Field(min_length=2, max_length=8)
    video_prompt: str = Field(max_length=1000, description="Промпт для видеомодели на английском")
    hashtags: list[str] = Field(max_length=8)


class HiggsfieldVideoArgs(BaseModel):
    prompt: str
    duration: int
    aspect_ratio: str


class JiraIssueArgs(BaseModel):
    project_key: str
    summary: str
    description: str
    issue_type: str = "Task"
    labels: list[str]


class VideoStatus(StrEnum):
    GENERATED = "generated"
    STORYBOARD = "storyboard"  # Graceful Degradation: Higgsfield недоступен


class TrackerStatus(StrEnum):
    CREATED = "created"
    QUEUED = "queued"  # отложенная синхронизация


class VideoOutcome(BaseModel):
    status: VideoStatus
    url: str | None = None
    error_code: str | None = None
    latency_ms: int


class TrackerOutcome(BaseModel):
    status: TrackerStatus
    issue_key: str | None = None
    queued_id: str | None = None
    error_code: str | None = None


class SmmResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    script: VideoScriptSchema
    external_prompt: str = Field(description="Ровно то, что ушло во внешний MCP (с токенами)")
    anonymization: AnonymizationReport
    video: VideoOutcome
    tracker: TrackerOutcome
    storyboard: DocumentInfo
