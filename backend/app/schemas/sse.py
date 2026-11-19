"""Схемы событий прогресса, отдаваемых через Server-Sent Events."""

from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field

from app.schemas.intent import DomainEnum, IntentClassificationResult
from app.schemas.finance import FinanceResult
from app.schemas.legal import LegalResult
from app.schemas.privacy import AnonymizationReport
from app.schemas.smm import SmmResult


class TaskStatus(StrEnum):
    CLASSIFYING_INTENT = "classifying_intent"
    ROUTING_SMM = "routing_smm"
    ROUTING_FINANCE = "routing_finance"
    ANONYMIZING_PII = "anonymizing_pii"
    ANALYZING = "analyzing"
    EXTRACTING_ENTITIES = "extracting_entities"
    RENDERING_DOCX = "rendering_docx"
    ANALYZING_CSV = "analyzing_csv"
    GENERATING_REPORT = "generating_report"
    GENERATING_VIDEO = "generating_video"
    CREATING_JIRA_ISSUE = "creating_jira_issue"
    COMPLETED = "completed"
    FAILED = "failed"


class ErrorInfo(BaseModel):
    """Ошибка для клиента: машинный код и нейтральное сообщение без PII."""

    model_config = ConfigDict(extra="forbid")

    code: str
    message: str


class TaskResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    intent: IntentClassificationResult
    low_confidence: bool
    legal: LegalResult | None = None
    finance: FinanceResult | None = None
    smm: SmmResult | None = None


class ProgressEvent(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: TaskStatus
    progress: int = Field(ge=0, le=100)
    # Известен после Этапа 1 и приходит во всех следующих событиях.
    domain: DomainEnum | None = None
    message: str | None = None
    # Счётчики маскирования (без значений) — для PrivacyBadge/ProgressStepper.
    anonymization: AnonymizationReport | None = None
    result: TaskResult | None = None
    error: ErrorInfo | None = None

    def to_sse(self) -> str:
        return f"event: progress\ndata: {self.model_dump_json(exclude_none=True)}\n\n"
