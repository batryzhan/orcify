"""Finance домені схемалары (В сценарийі).

``FinanceMetrics`` — ``analyze_transactions`` MCP-құралы жауабының келісімшарты
(mcp_servers/local_finance_server/analysis.py). Схемалардың сәйкестігін
``test_finance_contract_matches_mcp_server`` тесті тексереді.
"""

from __future__ import annotations

from datetime import date, datetime
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field



class AnalyzeTransactionsArgs(BaseModel):
    """analyze_transactions MCP-құралының аргументтері."""

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


class ForecastPoint(BaseModel):
    month: str
    income: float
    expense: float
    net: float
    balance: float


class CategoryChange(BaseModel):
    category: str
    previous: float
    current: float
    change: float
    change_pct: float | None


class MonthComparison(BaseModel):
    previous_month: str
    current_month: str
    income_previous: float
    income_current: float
    expense_previous: float
    expense_current: float
    categories: list[CategoryChange]


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
    # 3 айлық қалдық болжамы — соңғы толық айлардың орташасы бойынша (детерминистік).
    forecast: list[ForecastPoint] = Field(default_factory=list)
    forecast_basis_months: int = 0
    # Соңғы толық айды алдыңғы аймен салыстыру.
    month_over_month: MonthComparison | None = None
    # Соңғы толық айдағы санаттар бойынша шығыстар — бюджеттерді тексеру негізі.
    budget_month: str | None = None
    last_month_by_category: list[CategoryTotal] = Field(default_factory=list)


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
    """Талдаушының Structured Output-ы: LLM тек агрегаттарды көреді, үзінді жолдарын емес."""

    model_config = ConfigDict(extra="forbid")

    headline: str = Field(max_length=200, description="Бір сөйлеммен басты қорытынды")
    key_findings: list[str] = Field(min_length=2, max_length=6)
    risks: list[FinanceRisk] = Field(max_length=5)
    recommendations: list[str] = Field(min_length=1, max_length=6)


class BudgetItem(BaseModel):
    """Санат бойынша айлық шығыс лимиті («Қаржы» терезесінде беріледі)."""

    model_config = ConfigDict(extra="forbid")

    category: str = Field(min_length=1, max_length=80)
    limit: float = Field(gt=0, le=1e12)


class Budgets(BaseModel):
    model_config = ConfigDict(extra="forbid")

    items: list[BudgetItem] = Field(default_factory=list, max_length=50)


class BudgetCheck(BaseModel):
    category: str
    limit: float
    spent: float
    remaining: float
    ratio: float
    over: bool


class ReportFile(BaseModel):
    """Жергілікті мұрағаттағы PDF-есеп ``backend/var/finance_reports`` (тек агрегаттар)."""

    report_id: str = Field(pattern=r"^[0-9a-f]{32}$")
    filename: str
    download_url: str
    sha256: str
    size_bytes: int


class ReportRecord(BaseModel):
    """Есептер мұрағатының жазбасы: шикі транзакциясыз метадеректер."""

    file: ReportFile
    created_at: datetime
    period_start: date
    period_end: date
    rows: int
    net: float
    closing_balance: float
    headline: str | None = None
    issue_key: str | None = None


class FinanceResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    metrics: FinanceMetrics
    report: FinanceReportSchema | None
    report_error_code: str | None = None
    report_file: ReportFile | None = None
    budget_checks: list[BudgetCheck] = Field(default_factory=list)
    mcp_latency_ms: int
