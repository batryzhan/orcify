"""Orcify Jira схемалары — тапсырмалардың өз жергілікті трекері (ORC тақтасы).

Трекер толығымен құрылғыда жұмыс істейді: агенттер ``orcify_jira`` in-process
MCP-сервері арқылы тапсырмалар жасайды және жылжытады (``app/mcp/jira_server.py`` қараңыз),
UI тақтаны ``/api/jira`` арқылы оқиды.
"""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.schemas.intent import DomainEnum


class IssueStatus(StrEnum):
    TODO = "todo"
    IN_PROGRESS = "in_progress"
    REVIEW = "review"
    DONE = "done"


class IssueType(StrEnum):
    TASK = "task"
    STORY = "story"
    BUG = "bug"
    EPIC = "epic"


class IssuePriority(StrEnum):
    HIGHEST = "highest"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


class AttachmentKind(StrEnum):
    POST = "post"  # Instagram-постының PNG-і (backend/var/posts ішінде сақталады)
    DOCUMENT = "document"  # in-memory DocumentStore-дағы .docx келісімшарт (шектеулі уақыт тұрады)
    REPORT = "report"  # «Қаржы» терезесінің мұрағатындағы PDF-есеп (backend/var/finance_reports)


Label = str


class IssueAttachment(BaseModel):
    model_config = ConfigDict(extra="forbid")

    kind: AttachmentKind
    title: str = Field(min_length=1, max_length=120)
    url: str = Field(pattern=r"^/api/[A-Za-z0-9/_.\-]+$")


class JiraIssue(BaseModel):
    model_config = ConfigDict(extra="forbid")

    key: str = Field(pattern=r"^[A-Z][A-Z0-9]{1,9}-\d+$")
    summary: str = Field(min_length=1, max_length=200)
    description: str = Field(default="", max_length=4000)
    status: IssueStatus
    type: IssueType
    priority: IssuePriority
    labels: list[Label] = Field(default_factory=list, max_length=6)
    story_points: int | None = Field(default=None, ge=0, le=21)
    assignee: str | None = Field(default=None, max_length=40)
    domain: DomainEnum | None = None
    # Пайплайн тапсырмасымен байланыс (қазір агенттер «құрып жатқан» карточканы белгілеу үшін).
    task_id: UUID | None = None
    parent_key: str | None = None
    attachments: list[IssueAttachment] = Field(default_factory=list, max_length=10)
    created_at: datetime
    updated_at: datetime


class BoardColumn(BaseModel):
    status: IssueStatus
    title: str


class JiraBoard(BaseModel):
    project_key: str
    project_name: str
    columns: list[BoardColumn]
    # Баған ішіндегі реттілік = тізімдегі реттілік (жаңалары жоғарыда).
    issues: list[JiraIssue]


class IssueCreate(BaseModel):
    """Тапсырма жасау аргументтері (UI және ``create_issue`` MCP-құралы)."""

    model_config = ConfigDict(extra="forbid")

    summary: str = Field(min_length=1, max_length=200)
    description: str = Field(default="", max_length=4000)
    status: IssueStatus = IssueStatus.TODO
    type: IssueType = IssueType.TASK
    priority: IssuePriority = IssuePriority.MEDIUM
    labels: list[Label] = Field(default_factory=list, max_length=6)
    story_points: int | None = Field(default=None, ge=0, le=21)
    assignee: str | None = Field(default=None, max_length=40)
    domain: DomainEnum | None = None
    task_id: UUID | None = None
    parent_key: str | None = None


class IssueUpdate(BaseModel):
    """Ішінара жаңарту: ``None`` = өріс өзгермейді."""

    model_config = ConfigDict(extra="forbid")

    summary: str | None = Field(default=None, min_length=1, max_length=200)
    description: str | None = Field(default=None, max_length=4000)
    status: IssueStatus | None = None
    type: IssueType | None = None
    priority: IssuePriority | None = None
    labels: list[Label] | None = Field(default=None, max_length=6)
    story_points: int | None = Field(default=None, ge=0, le=21)
    assignee: str | None = Field(default=None, max_length=40)
    add_attachments: list[IssueAttachment] = Field(default_factory=list, max_length=4)


class CreateIssueToolArgs(BaseModel):
    issue: IssueCreate


class UpdateIssueToolArgs(BaseModel):
    key: str
    changes: IssueUpdate


class ClearBoardRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    scope: Literal["done", "all"]


class ClearBoardResponse(BaseModel):
    removed: int
