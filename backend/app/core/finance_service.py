"""Сценарий В (Finance): CSV -> локальный MCP (pandas) -> агрегаты -> LLM-резюме -> PDF-отчёт.

Отчёт собирается детерминированно (``finance_pdf.py``) и кладётся в локальный
архив окна «Финансы». Бюджеты пользователя сверяются с расходами последнего
полного месяца без участия модели.
"""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from typing import Final
from uuid import uuid4

from pydantic import ValidationError

from app.core.finance_pdf import FinancePdfRenderer
from app.core.finance_store import BudgetStore, ReportStore
from app.core.llm_client import ChatMessage, LLMClient
from app.core.logger import get_logger, payload_hash
from app.core.prompts import PromptLoader
from app.mcp.manager import MCPServerManager
from app.schemas.finance import (
    AnalyzeTransactionsArgs,
    BudgetCheck,
    FinanceMetrics,
    FinanceReportSchema,
    ReportFile,
    ReportRecord,
)

ANALYST_PROMPT: Final = "finance_analyst"
FINANCE_SERVER: Final = "local_finance"
FINANCE_TOOL: Final = "analyze_transactions"

log = get_logger(__name__)


class FinanceAnalysisError(Exception):
    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


class FinanceService:
    def __init__(
        self,
        llm: LLMClient,
        prompts: PromptLoader,
        mcp: MCPServerManager,
        pdf: FinancePdfRenderer,
        reports: ReportStore,
        budgets: BudgetStore,
    ) -> None:
        self._llm = llm
        self._prompts = prompts
        self._mcp = mcp
        self._pdf = pdf
        self._reports = reports
        self._budgets = budgets

    async def analyze(self, csv_text: str, opening_balance: float = 0.0) -> tuple[FinanceMetrics, int]:
        result = await self._mcp.call_tool(
            FINANCE_SERVER,
            FINANCE_TOOL,
            AnalyzeTransactionsArgs(csv_text=csv_text, opening_balance=opening_balance),
        )
        if not result.ok or result.structured is None:
            raise FinanceAnalysisError(result.error_code or "mcp_failed")
        try:
            metrics = FinanceMetrics.model_validate(result.structured)
        except ValidationError:
            raise FinanceAnalysisError("metrics_contract_mismatch") from None
        log.info("finance_analyzed", server=FINANCE_SERVER, latency_ms=result.latency_ms, payload_hash=payload_hash(csv_text))
        return metrics, result.latency_ms

    def check_budgets(self, metrics: FinanceMetrics) -> list[BudgetCheck]:
        return self._budgets.check(metrics)

    async def summarize(self, metrics: FinanceMetrics, budgets: list[BudgetCheck]) -> FinanceReportSchema:
        # Модель видит только агрегаты (и итоги бюджетов), не строки выписки.
        payload = metrics.model_dump(mode="json", exclude={"columns_detected", "warnings"})
        payload["budget_checks"] = [b.model_dump(mode="json") for b in budgets]
        messages = [
            ChatMessage(role="system", content=self._prompts.load(ANALYST_PROMPT)),
            ChatMessage(role="user", content=_json(payload)),
        ]
        response = await self._llm.structured(messages, FinanceReportSchema, stage="generating_report")
        return response.data

    async def build_report(
        self, metrics: FinanceMetrics, report: FinanceReportSchema | None, budgets: list[BudgetCheck]
    ) -> ReportFile:
        created = datetime.now(UTC)
        pdf = await asyncio.to_thread(self._pdf.render, metrics, report, budgets, created)
        report_id = uuid4().hex
        file = ReportFile(
            report_id=report_id,
            filename=f"orcify_finance_{metrics.period_start:%Y%m%d}_{metrics.period_end:%Y%m%d}.pdf",
            download_url=f"/api/finance/reports/{report_id}.pdf",
            sha256=payload_hash(pdf),
            size_bytes=len(pdf),
        )
        self._reports.save(
            ReportRecord(
                file=file,
                created_at=created,
                period_start=metrics.period_start,
                period_end=metrics.period_end,
                rows=metrics.rows,
                net=metrics.net,
                closing_balance=metrics.closing_balance,
                headline=report.headline if report else None,
            ),
            pdf,
        )
        return file

    def attach_issue(self, report_id: str, issue_key: str) -> None:
        self._reports.attach_issue(report_id, issue_key)


def _json(payload: object) -> str:
    import json

    return json.dumps(payload, ensure_ascii=False)
