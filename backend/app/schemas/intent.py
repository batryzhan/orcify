"""Smart Routing 1-кезеңінің схемалары — ниетті жіктеу."""

from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field


class DomainEnum(StrEnum):
    LEGAL = "Legal"
    SMM = "SMM"
    FINANCE = "Finance"
    HR = "HR"


class IntentClassificationResult(BaseModel):
    """Классификатордың Structured Output-ы. ``reasoning`` өрісі ешқашан логқа жазылмайды."""

    model_config = ConfigDict(extra="forbid")

    domain: DomainEnum
    confidence: float = Field(ge=0.0, le=1.0)
    reasoning: str = Field(max_length=500)
