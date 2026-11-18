"""Схемы домена Finance (Сценарий В).

``FinanceMetrics`` — контракт ответа MCP-инструмента ``analyze_transactions``
(mcp_servers/local_finance_server/analysis.py). Совпадение схем проверяется
тестом ``test_finance_contract_matches_mcp_server``.
"""

from __future__ import annotations

from datetime import date
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field

from app.schemas.legal import DocumentInfo


class AnalyzeTransactionsArgs(BaseModel):
    """Аргументы MCP-инструмента analyze_transactions."""

    csv_text: str
    opening_balance: float = 0.0


class MonthlyFlow(BaseModel):
    month: str
    income: float
    expense: float
    net: float


class CategoryTotal(BaseModel):
    category: str
    amount: float
    share: float


class CounterpartyTotal(BaseModel):
    name: str
    amount: float
    count: int


class CashGap(BaseModel):
    start: date
    end: date
    days: int
    min_balance: float


class Anomaly(BaseModel):
    date: date
    amount: float
    counterparty: str | None
    category: str | None
    score: float


class FinanceMetrics(BaseModel):
    rows: int
    period_start: date
    period_end: date
    currency: str | None
    total_income: float
    total_expense: float
    net: float
    opening_balance: float
    closing_balance: float
    monthly: list[MonthlyFlow]
    expense_by_category: list[CategoryTotal]
    top_income_counterparties: list[CounterpartyTotal]
    top_expense_counterparties: list[CounterpartyTotal]
    cash_gaps: list[CashGap]
    anomalies: list[Anomaly]
    columns_detected: dict[str, str]
    warnings: list[str] = Field(default_factory=list)


class RiskLevel(StrEnum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class FinanceRisk(BaseModel):
    model_config = ConfigDict(extra="forbid")

    title: str = Field(max_length=120)
    level: RiskLevel
    detail: str = Field(max_length=400)


class FinanceReportSchema(BaseModel):
    """Structured Output аналитика: LLM видит только агрегаты, не строки выписки."""

    model_config = ConfigDict(extra="forbid")

    headline: str = Field(max_length=200, description="Главный вывод одной фразой")
    key_findings: list[str] = Field(min_length=2, max_length=6)
    risks: list[FinanceRisk] = Field(max_length=5)
    recommendations: list[str] = Field(min_length=1, max_length=6)


class FinanceResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    metrics: FinanceMetrics
    report: FinanceReportSchema | None
    report_error_code: str | None = None
    document: DocumentInfo | None = None
    mcp_latency_ms: int
