"""Сценарий В (Finance): CSV -> локальный MCP (pandas) -> агрегаты -> LLM-резюме."""

from __future__ import annotations

from typing import Final

from pydantic import ValidationError

from app.core.document_store import DocumentStore
from app.core.llm_client import ChatMessage, LLMClient
from app.core.logger import get_logger, payload_hash
from app.core.prompts import PromptLoader
from app.mcp.manager import MCPServerManager
from app.schemas.finance import AnalyzeTransactionsArgs, FinanceMetrics, FinanceReportSchema
from app.schemas.legal import DocumentInfo

ANALYST_PROMPT: Final = "finance_analyst"
FINANCE_SERVER: Final = "local_finance"
FINANCE_TOOL: Final = "analyze_transactions"
MD_MEDIA_TYPE: Final = "text/markdown; charset=utf-8"

log = get_logger(__name__)


class FinanceAnalysisError(Exception):
    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


def _money(value: float) -> str:
    return f"{value:,.0f}".replace(",", " ") + " ₸"


def render_markdown(metrics: FinanceMetrics, report: FinanceReportSchema | None) -> str:
    """Детерминированный отчёт: цифры из pandas, текст выводов — из Structured Output."""
    lines = [
        "# Финансовая сводка",
        "",
        f"Период: {metrics.period_start:%d.%m.%Y} — {metrics.period_end:%d.%m.%Y} · операций: {metrics.rows}",
        "",
        "| Показатель | Значение |",
        "|---|---|",
        f"| Поступления | {_money(metrics.total_income)} |",
        f"| Расходы | {_money(metrics.total_expense)} |",
        f"| Чистый поток | {_money(metrics.net)} |",
        f"| Остаток на конец | {_money(metrics.closing_balance)} |",
        "",
    ]
    if report:
        lines += [f"## {report.headline}", "", "### Ключевые наблюдения", ""]
        lines += [f"- {x}" for x in report.key_findings]
        if report.risks:
            lines += ["", "### Риски", ""]
            lines += [f"- **{r.title}** ({r.level.value}): {r.detail}" for r in report.risks]
        lines += ["", "### Рекомендации", ""]
        lines += [f"{i}. {x}" for i, x in enumerate(report.recommendations, 1)]
        lines.append("")
    lines += ["## Помесячный поток", "", "| Месяц | Поступления | Расходы | Итог |", "|---|---|---|---|"]
    lines += [f"| {m.month} | {_money(m.income)} | {_money(m.expense)} | {_money(m.net)} |" for m in metrics.monthly]
    if metrics.cash_gaps:
        lines += ["", "## Кассовые разрывы", ""]
        lines += [
            f"- {g.start:%d.%m.%Y} — {g.end:%d.%m.%Y} ({g.days} дн.), минимум {_money(g.min_balance)}"
            for g in metrics.cash_gaps
        ]
    lines += ["", "---", "Сформировано локально в Orcify. Сырые транзакции не передавались в языковую модель.", ""]
    return "\n".join(lines)


class FinanceService:
    def __init__(
        self, llm: LLMClient, prompts: PromptLoader, mcp: MCPServerManager, documents: DocumentStore
    ) -> None:
        self._llm = llm
        self._prompts = prompts
        self._mcp = mcp
        self._documents = documents

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

    async def summarize(self, metrics: FinanceMetrics) -> FinanceReportSchema:
        messages = [
            ChatMessage(role="system", content=self._prompts.load(ANALYST_PROMPT)),
            ChatMessage(role="user", content=metrics.model_dump_json(exclude={"columns_detected", "warnings"})),
        ]
        response = await self._llm.structured(messages, FinanceReportSchema, stage="generating_report")
        return response.data

    def store_report(self, metrics: FinanceMetrics, report: FinanceReportSchema | None) -> DocumentInfo:
        content = render_markdown(metrics, report).encode("utf-8")
        filename = f"finance_report_{metrics.period_start:%Y%m%d}_{metrics.period_end:%Y%m%d}.md"
        doc_id = self._documents.put(filename=filename, media_type=MD_MEDIA_TYPE, content=content)
        return DocumentInfo(
            document_id=doc_id,
            filename=filename,
            download_url=f"/api/documents/{doc_id}",
            sha256=payload_hash(content),
            size_bytes=len(content),
        )
