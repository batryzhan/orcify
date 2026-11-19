"""Local Anonymizer схемалары (сыртқы MCP алдында PII маскалау)."""

from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field


class PiiCategory(StrEnum):
    PERSON = "PERSON"
    COMPANY = "COMPANY"
    ADDRESS = "ADDRESS"
    IIN = "IIN"
    BIN = "BIN"
    PHONE = "PHONE"
    EMAIL = "EMAIL"
    IBAN = "IBAN"
    CARD = "CARD"


class LlmPiiCategory(StrEnum):
    """LLM іздейтін санаттар (қалғанын регулярлық өрнектер сенімдірек табады)."""

    PERSON = "PERSON"
    COMPANY = "COMPANY"
    ADDRESS = "ADDRESS"


class PiiSpan(BaseModel):
    model_config = ConfigDict(extra="forbid")

    text: str = Field(min_length=2, max_length=200, description="Үзінді мәтінде қалай жазылса, дәл солай")
    category: LlmPiiCategory


class PiiDetectionResult(BaseModel):
    """PII детекторының Structured Output-ы."""

    model_config = ConfigDict(extra="forbid")

    entities: list[PiiSpan] = Field(max_length=50)


class AnonymizationReport(BaseModel):
    """UI және метрикаларға арналған жиынтық: тек санауыштар, мәндердің өздерінсіз."""

    entities_total: int
    by_category: dict[PiiCategory, int]
    llm_detection_used: bool
    leaked_count: int = 0
