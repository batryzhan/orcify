"""Схемы домена HR: планировщик задач для Orcify Jira (онбординг, найм, кадровые процессы)."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

from app.schemas.jira import IssuePriority, IssueType


class PlannedIssue(BaseModel):
    model_config = ConfigDict(extra="forbid")

    summary: str = Field(min_length=1, max_length=160, description="Короткое название задачи")
    description: str = Field(max_length=600, description="Что сделать и критерий готовности")
    type: IssueType = Field(description="task — работа, story — результат для сотрудника, bug — проблема")
    priority: IssuePriority
    story_points: int = Field(ge=1, le=13, description="Оценка трудоёмкости: 1, 2, 3, 5, 8, 13")
    assignee_role: str = Field(max_length=40, description="Роль исполнителя: HR, руководитель, IT, бухгалтерия")


class JiraPlanSchema(BaseModel):
    """Structured Output планировщика."""

    model_config = ConfigDict(extra="forbid")

    epic: str = Field(min_length=1, max_length=160, description="Название эпика, объединяющего задачи")
    issues: list[PlannedIssue] = Field(min_length=1, max_length=8)


class HrResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    plan: JiraPlanSchema
    issue_keys: list[str]
