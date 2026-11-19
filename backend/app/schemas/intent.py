"""Схемы Этапа 1 Smart Routing — классификация намерения."""

from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field


class DomainEnum(StrEnum):
    LEGAL = "Legal"
    SMM = "SMM"
    FINANCE = "Finance"
    HR = "HR"


class IntentClassificationResult(BaseModel):
    """Structured Output классификатора. Поле ``reasoning`` никогда не логируется."""

    model_config = ConfigDict(extra="forbid")

    domain: DomainEnum
    confidence: float = Field(ge=0.0, le=1.0)
    reasoning: str = Field(max_length=500)
