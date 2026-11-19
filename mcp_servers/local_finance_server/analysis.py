"""Детерминированный анализ банковской выписки (pandas).

Сырые строки таблицы никогда не покидают этот процесс: наружу уходят
только агрегаты ``FinanceMetrics``. Поддерживаются выгрузки с одной
колонкой суммы (знак = направление) или с парой колонок приход/расход.
"""

from __future__ import annotations

import io
import re
from datetime import date, timedelta
from typing import Final

import pandas as pd
from pydantic import BaseModel, Field

ROLE_ALIASES: Final[dict[str, tuple[str, ...]]] = {
    "date": ("date", "дата", "дата операции", "дата платежа", "transaction date", "posting date"),
    "amount": ("amount", "сумма", "сумма операции", "sum", "сумма, kzt", "сумма (kzt)"),
    "income": ("income", "credit", "приход", "поступление", "кредит", "зачисление"),
    "expense": ("expense", "debit", "расход", "списание", "дебет"),
    "category": ("category", "категория", "статья", "статья расходов"),
    "counterparty": ("counterparty", "контрагент", "получатель", "плательщик", "payee", "partner"),
    "description": ("description", "назначение", "назначение платежа", "описание", "comment", "комментарий"),
    "currency": ("currency", "валюта"),
}

MAX_ROWS: Final = 200_000
ANOMALY_THRESHOLD: Final = 3.5  # модифицированный z-score (медиана/MAD)


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
    # Прогноз остатка на 3 месяца по среднему последних полных месяцев (детерминированно).
    forecast: list[ForecastPoint] = Field(default_factory=list)
    forecast_basis_months: int = 0
    # Сравнение последнего полного месяца с предыдущим.
    month_over_month: MonthComparison | None = None
    # Расходы по категориям за последний полный месяц — база для проверки бюджетов.
    budget_month: str | None = None
    last_month_by_category: list[CategoryTotal] = Field(default_factory=list)


class FinanceInputError(ValueError):
    pass


def _norm(name: str) -> str:
    return re.sub(r"\s+", " ", str(name).strip().lower().replace("ё", "е"))


def detect_columns(columns: list[str]) -> dict[str, str]:
    normalized = {_norm(c): c for c in columns}
    found: dict[str, str] = {}
    for role, aliases in ROLE_ALIASES.items():
        for alias in aliases:
            if alias in normalized:
                found[role] = normalized[alias]
                break
    return found


def parse_number(series: pd.Series) -> pd.Series:
    cleaned = (
        series.astype(str)
        .str.replace(r"[\s  ]", "", regex=True)
        .str.replace(r"[^\d,.\-+]", "", regex=True)
        .str.replace(",", ".", regex=False)
    )
    return pd.to_numeric(cleaned, errors="coerce")


_ISO_DATE = re.compile(r"^\s*\d{4}-\d{2}-\d{2}")


def parse_dates(series: pd.Series) -> pd.Series:
    """ISO (2026-01-06) — год впереди; иначе день впереди (06.01.2026, принято в РК)."""
    sample = series.dropna().astype(str).head(50)
    if len(sample) and sample.str.match(_ISO_DATE).all():
        return pd.to_datetime(series, errors="coerce", format="ISO8601")
    return pd.to_datetime(series, dayfirst=True, errors="coerce", format="mixed")


def _r(value: float) -> float:
    return round(float(value), 2)


def _top_counterparties(df: pd.DataFrame, mask: pd.Series, n: int = 5) -> list[CounterpartyTotal]:
    if "counterparty" not in df:
        return []
    grouped = df[mask].groupby("counterparty")["amount"].agg(["sum", "count"])
    grouped["abs"] = grouped["sum"].abs()
    grouped = grouped.sort_values("abs", ascending=False).head(n)
    return [CounterpartyTotal(name=str(k), amount=_r(abs(r["sum"])), count=int(r["count"])) for k, r in grouped.iterrows()]


def _cash_gaps(daily: pd.Series, opening_balance: float) -> list[CashGap]:
    balance = opening_balance + daily.cumsum()
    gaps: list[CashGap] = []
    start: pd.Timestamp | None = None
    low = 0.0
    prev: pd.Timestamp | None = None
    for day, value in balance.items():
        ts = pd.Timestamp(day)
        if value < 0:
            if start is None:
                start, low = ts, float(value)
            low = min(low, float(value))
        elif start is not None and prev is not None:
            gaps.append(CashGap(start=start.date(), end=prev.date(), days=(prev - start).days + 1, min_balance=_r(low)))
            start = None
        prev = ts
    if start is not None and prev is not None:
        gaps.append(CashGap(start=start.date(), end=prev.date(), days=(prev - start).days + 1, min_balance=_r(low)))
    return gaps


def _anomalies(df: pd.DataFrame, n: int = 5) -> list[Anomaly]:
    if len(df) < 8:
        return []
    values = df["amount"].abs()
    median = values.median()
    mad = (values - median).abs().median()
    if mad == 0:
        return []
    score = 0.6745 * (values - median) / mad
    picked = df.assign(score=score)[score > ANOMALY_THRESHOLD].sort_values("score", ascending=False).head(n)
    return [
        Anomaly(
            date=row["date"].date(),
            amount=_r(row["amount"]),
            counterparty=str(row["counterparty"]) if "counterparty" in df and pd.notna(row.get("counterparty")) else None,
            category=str(row["category"]) if "category" in df and pd.notna(row.get("category")) else None,
            score=_r(row["score"]),
        )
        for _, row in picked.iterrows()
    ]


FORECAST_MONTHS: Final = 3


def _complete_months(monthly: list[MonthlyFlow], period_end: date) -> list[MonthlyFlow]:
    """Последний месяц выписки считается полным, только если выписка доходит до его конца."""
    if not monthly:
        return []
    last_is_complete = (period_end + timedelta(days=1)).month != period_end.month
    return monthly if last_is_complete else monthly[:-1]


def _next_month(month: str, step: int) -> str:
    year, m = (int(x) for x in month.split("-"))
    index = year * 12 + (m - 1) + step
    return f"{index // 12:04d}-{index % 12 + 1:02d}"


def _forecast(monthly: list[MonthlyFlow], period_end: date, closing: float) -> tuple[list[ForecastPoint], int]:
    basis = _complete_months(monthly, period_end)[-3:] or monthly[-1:]
    if not basis:
        return [], 0
    income = sum(m.income for m in basis) / len(basis)
    expense = sum(m.expense for m in basis) / len(basis)
    points, balance = [], closing
    for step in range(1, FORECAST_MONTHS + 1):
        balance += income - expense
        points.append(
            ForecastPoint(
                month=_next_month(monthly[-1].month, step),
                income=_r(income),
                expense=_r(expense),
                net=_r(income - expense),
                balance=_r(balance),
            )
        )
    return points, len(basis)


def _category_by_month(months: pd.DataFrame, month: str) -> dict[str, float]:
    if "category" not in months:
        return {}
    rows = months[(months["month"] == month) & (months["amount"] < 0)]
    return {str(k): float(-v) for k, v in rows.groupby("category")["amount"].sum().items()}


def _month_over_month(months: pd.DataFrame, complete: list[MonthlyFlow]) -> MonthComparison | None:
    if len(complete) < 2:
        return None
    prev, cur = complete[-2], complete[-1]
    before, after = _category_by_month(months, prev.month), _category_by_month(months, cur.month)
    changes = []
    for category in sorted(set(before) | set(after)):
        p, c = before.get(category, 0.0), after.get(category, 0.0)
        changes.append(
            CategoryChange(
                category=category,
                previous=_r(p),
                current=_r(c),
                change=_r(c - p),
                change_pct=round((c - p) / p, 4) if p > 0 else None,
            )
        )
    changes.sort(key=lambda x: abs(x.change), reverse=True)
    return MonthComparison(
        previous_month=prev.month,
        current_month=cur.month,
        income_previous=prev.income,
        income_current=cur.income,
        expense_previous=prev.expense,
        expense_current=cur.expense,
        categories=changes[:10],
    )


def analyze_csv(csv_text: str, opening_balance: float = 0.0) -> FinanceMetrics:
    if not csv_text.strip():
        raise FinanceInputError("empty_csv")
    try:
        raw = pd.read_csv(io.StringIO(csv_text), sep=None, engine="python", dtype=str, nrows=MAX_ROWS + 1)
    except Exception:
        raise FinanceInputError("unreadable_csv") from None
    if len(raw) > MAX_ROWS:
        raise FinanceInputError("too_many_rows")

    columns = detect_columns(list(raw.columns))
    if "date" not in columns:
        raise FinanceInputError("date_column_not_found")
    if "amount" not in columns and not ({"income", "expense"} & columns.keys()):
        raise FinanceInputError("amount_column_not_found")

    warnings: list[str] = []
    df = pd.DataFrame({"date": parse_dates(raw[columns["date"]])})
    if "amount" in columns:
        df["amount"] = parse_number(raw[columns["amount"]])
    else:
        income = parse_number(raw[columns["income"]]).fillna(0) if "income" in columns else 0.0
        expense = parse_number(raw[columns["expense"]]).fillna(0).abs() if "expense" in columns else 0.0
        df["amount"] = income - expense
    for role in ("category", "counterparty"):
        if role in columns:
            df[role] = raw[columns[role]].fillna("Без категории" if role == "category" else "Не указан").str.strip()

    bad = df["date"].isna() | df["amount"].isna()
    if bad.any():
        warnings.append(f"skipped_rows:{int(bad.sum())}")
    df = df[~bad].sort_values("date").reset_index(drop=True)
    if df.empty:
        raise FinanceInputError("no_valid_rows")

    currency = None
    if "currency" in columns:
        values = raw[columns["currency"]].dropna().str.strip().unique()
        currency = str(values[0]) if len(values) == 1 else None
        if len(values) > 1:
            warnings.append("multiple_currencies")

    is_income = df["amount"] > 0
    is_expense = df["amount"] < 0
    total_income = float(df.loc[is_income, "amount"].sum())
    total_expense = float(-df.loc[is_expense, "amount"].sum())

    months = df.assign(month=df["date"].dt.strftime("%Y-%m"))
    monthly = [
        MonthlyFlow(
            month=str(month),
            income=_r(g.loc[g["amount"] > 0, "amount"].sum()),
            expense=_r(-g.loc[g["amount"] < 0, "amount"].sum()),
            net=_r(g["amount"].sum()),
        )
        for month, g in months.groupby("month")
    ]

    by_category: list[CategoryTotal] = []
    if "category" in df and total_expense > 0:
        cat = (-df[is_expense].groupby("category")["amount"].sum()).sort_values(ascending=False).head(10)
        by_category = [CategoryTotal(category=str(k), amount=_r(v), share=round(float(v) / total_expense, 4)) for k, v in cat.items()]

    daily = df.groupby(df["date"].dt.normalize())["amount"].sum()
    period_end = df["date"].iloc[-1].date()
    closing = opening_balance + total_income - total_expense
    forecast, basis = _forecast(monthly, period_end, closing)
    complete = _complete_months(monthly, period_end)
    budget_month = complete[-1].month if complete else (monthly[-1].month if monthly else None)
    month_spend = _category_by_month(months, budget_month) if budget_month else {}
    month_total = sum(month_spend.values())
    last_month_by_category = [
        CategoryTotal(category=k, amount=_r(v), share=round(v / month_total, 4) if month_total else 0.0)
        for k, v in sorted(month_spend.items(), key=lambda kv: kv[1], reverse=True)
    ]
    return FinanceMetrics(
        rows=len(df),
        period_start=df["date"].iloc[0].date(),
        period_end=df["date"].iloc[-1].date(),
        currency=currency,
        total_income=_r(total_income),
        total_expense=_r(total_expense),
        net=_r(total_income - total_expense),
        opening_balance=_r(opening_balance),
        closing_balance=_r(opening_balance + total_income - total_expense),
        monthly=monthly,
        expense_by_category=by_category,
        top_income_counterparties=_top_counterparties(df, is_income),
        top_expense_counterparties=_top_counterparties(df, is_expense),
        cash_gaps=_cash_gaps(daily, opening_balance),
        anomalies=_anomalies(df),
        columns_detected=columns,
        warnings=warnings,
        forecast=forecast,
        forecast_basis_months=basis,
        month_over_month=_month_over_month(months, complete),
        budget_month=budget_month,
        last_month_by_category=last_month_by_category,
    )
