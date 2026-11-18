"""Схемы Local Anonymizer (маскирование PII перед внешними MCP)."""

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
    """Категории, которые ищет LLM (остальное надёжнее ловят регулярные выражения)."""

    PERSON = "PERSON"
    COMPANY = "COMPANY"
    ADDRESS = "ADDRESS"


class PiiSpan(BaseModel):
    model_config = ConfigDict(extra="forbid")

    text: str = Field(min_length=2, max_length=200, description="Фрагмент ровно так, как он написан в тексте")
    category: LlmPiiCategory


class PiiDetectionResult(BaseModel):
    """Structured Output детектора PII."""

    model_config = ConfigDict(extra="forbid")

    entities: list[PiiSpan] = Field(max_length=50)


class AnonymizationReport(BaseModel):
    """Сводка для UI и метрик: только счётчики, без самих значений."""

    entities_total: int
    by_category: dict[PiiCategory, int]
    llm_detection_used: bool
    leaked_count: int = 0
