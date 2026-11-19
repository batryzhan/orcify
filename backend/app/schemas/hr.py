"""HR домені схемалары: Orcify Jira үшін тапсырмалар жоспарлаушысы (онбординг, жалдау, кадр процестері)."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

from app.schemas.jira import IssuePriority, IssueType


class PlannedIssue(BaseModel):
    model_config = ConfigDict(extra="forbid")

    summary: str = Field(min_length=1, max_length=160, description="Тапсырманың қысқа атауы")
    description: str = Field(max_length=600, description="Не істеу керек және дайындық критерийі")
    type: IssueType = Field(description="task — жұмыс, story — қызметкер үшін нәтиже, bug — мәселе")
    priority: IssuePriority
    story_points: int = Field(ge=1, le=13, description="Еңбек сыйымдылығын бағалау: 1, 2, 3, 5, 8, 13")
    assignee_role: str = Field(max_length=40, description="Орындаушы рөлі: HR, басшы, IT, бухгалтерия")


class JiraPlanSchema(BaseModel):
    """Жоспарлаушының Structured Output-ы."""

    model_config = ConfigDict(extra="forbid")

    epic: str = Field(min_length=1, max_length=160, description="Тапсырмаларды біріктіретін эпик атауы")
    issues: list[PlannedIssue] = Field(min_length=1, max_length=8)


class HrResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    plan: JiraPlanSchema
    issue_keys: list[str]
