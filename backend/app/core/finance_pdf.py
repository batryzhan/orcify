"""Қаржылық талдау бойынша PDF-есеп (fpdf2, кириллицасы бар PT Sans қарпі).

Deterministic Core: барлық цифрлар — жергілікті MCP-дің pandas-агрегаттарынан, қорытынды
мәтіндері — модельдің Structured Output-ынан. Шикі транзакциялар есепке түспейді.
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Final

from fpdf import FPDF
from fpdf.enums import XPos, YPos

from app.schemas.finance import BudgetCheck, FinanceMetrics, FinanceReportSchema

INK: Final = (23, 43, 77)
SOFT: Final = (68, 84, 111)
MUTE: Final = (98, 111, 134)
LINE: Final = (220, 223, 228)
INCOME: Final = (42, 120, 214)
EXPENSE: Final = (235, 104, 52)
GOOD: Final = (31, 132, 90)
BAD: Final = (174, 46, 36)
RISK_LABEL: Final = {"high": "жоғары", "medium": "орташа", "low": "төмен"}
MONTHS: Final = ["қаң", "ақп", "нау", "сәу", "мам", "мау", "шіл", "там", "қыр", "қаз", "қар", "жел"]


class FinancePdfError(Exception):
    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


def money(value: float) -> str:
    return f"{value:,.0f}".replace(",", " ") + " ₸"


def month_label(month: str) -> str:
    year, m = month.split("-")
    return f"{MONTHS[int(m) - 1]} {year}"


# PT Sans ішінде ₸ және көрсеткі глифтері жоқ — әдеттегі «тг» және «->» таңбаларына ауыстырамыз (модель мәтінінде де).
_GLYPHS: Final = str.maketrans({"₸": "тг", "→": "->", "−": "-"})


class _Pdf(FPDF):
    def normalize_text(self, text: str) -> str:
        return super().normalize_text(text.translate(_GLYPHS))

    def footer(self) -> None:
        self.set_y(-14)
        self.set_font("PTSans", size=8)
        self.set_text_color(*MUTE)
        self.cell(0, 6, f"Orcify · жергілікті құрастырылған, шикі транзакциялар модельге берілмеген · {self.page_no()}-бет",
                  align="C")


class FinancePdfRenderer:
    def __init__(self, fonts_dir: Path) -> None:
        self._regular = fonts_dir / "PT_Sans-Web-Regular.ttf"
        self._bold = fonts_dir / "PT_Sans-Web-Bold.ttf"

    def render(
        self,
        metrics: FinanceMetrics,
        report: FinanceReportSchema | None,
        budgets: list[BudgetCheck],
        created_at: datetime,
    ) -> bytes:
        if not self._regular.is_file() or not self._bold.is_file():
            raise FinancePdfError("font_missing")
        pdf = _Pdf(format="A4")
        pdf.set_creation_date(created_at)
        pdf.set_title("Orcify қаржылық қорытындысы")
        pdf.add_font("PTSans", "", str(self._regular))
        pdf.add_font("PTSans", "B", str(self._bold))
        pdf.set_auto_page_break(auto=True, margin=18)
        pdf.set_margins(16, 16, 16)
        pdf.add_page()

        self._header(pdf, metrics, created_at)
        self._kpis(pdf, metrics)
        if report:
            self._conclusions(pdf, report)
        self._monthly_chart(pdf, metrics)
        if metrics.forecast:
            self._forecast(pdf, metrics)
        if metrics.month_over_month:
            self._mom(pdf, metrics)
        if budgets:
            self._budgets(pdf, metrics, budgets)
        if metrics.expense_by_category:
            self._categories(pdf, metrics)
        if metrics.cash_gaps:
            self._gaps(pdf, metrics)
        return bytes(pdf.output())

    # --- бөлімдер -------------------------------------------------------------

    @staticmethod
    def _h2(pdf: FPDF, text: str, need: float = 40.0) -> None:
        """Бөлім тақырыбы. ``need`` — астында қанша мм қажет: сыймаса, бөлім
        толығымен жаңа бетке өтеді (тақырып беттің түбінде жалғыз қалмайды).
        Ұзын тақырыптар (оларды модель жазады) сөздер бойынша тасымалданады, кесілмейді."""
        if pdf.get_y() + need > pdf.h - 18:
            pdf.add_page()
        pdf.ln(4)
        pdf.set_font("PTSans", "B", 13)
        pdf.set_text_color(*INK)
        pdf.multi_cell(0, 6.6, text, new_x=XPos.LMARGIN, new_y=YPos.NEXT, align="L")
        pdf.set_draw_color(*LINE)
        pdf.line(pdf.l_margin, pdf.get_y() + 1, pdf.w - pdf.r_margin, pdf.get_y() + 1)
        pdf.ln(3)

    @staticmethod
    def _text(pdf: FPDF, text: str, size: float = 10.5, color: tuple[int, int, int] = SOFT, bold: bool = False) -> None:
        pdf.set_font("PTSans", "B" if bold else "", size)
        pdf.set_text_color(*color)
        pdf.multi_cell(0, 5.6, text, new_x=XPos.LMARGIN, new_y=YPos.NEXT, align="L")

    def _header(self, pdf: FPDF, m: FinanceMetrics, created_at: datetime) -> None:
        pdf.set_font("PTSans", "B", 22)
        pdf.set_text_color(*INK)
        pdf.cell(0, 11, "Қаржылық қорытынды", new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        self._text(
            pdf,
            f"Кезең: {m.period_start:%d.%m.%Y} — {m.period_end:%d.%m.%Y} · операциялар: {m.rows} · "
            f"есеп күні {created_at:%d.%m.%Y %H:%M}",
            size=10,
            color=MUTE,
        )
        pdf.ln(3)

    def _kpis(self, pdf: FPDF, m: FinanceMetrics) -> None:
        tiles = [
            ("Түсімдер", money(m.total_income), INCOME),
            ("Шығыстар", money(m.total_expense), EXPENSE),
            ("Таза ағын", money(m.net), GOOD if m.net >= 0 else BAD),
            ("Соңғы қалдық", money(m.closing_balance), GOOD if m.closing_balance >= 0 else BAD),
        ]
        gap = 3
        width = (pdf.w - pdf.l_margin - pdf.r_margin - gap * 3) / 4
        y = pdf.get_y()
        for i, (label, value, color) in enumerate(tiles):
            x = pdf.l_margin + i * (width + gap)
            pdf.set_fill_color(247, 248, 249)
            pdf.rect(x, y, width, 20, style="F")
            pdf.set_fill_color(*color)
            pdf.rect(x, y, 1.2, 20, style="F")
            pdf.set_xy(x + 4, y + 3)
            pdf.set_font("PTSans", "", 8.5)
            pdf.set_text_color(*MUTE)
            pdf.cell(width - 6, 4, label)
            pdf.set_xy(x + 4, y + 9)
            pdf.set_font("PTSans", "B", 12)
            pdf.set_text_color(*INK)
            pdf.cell(width - 6, 7, value)
        pdf.set_xy(pdf.l_margin, y + 24)

    def _conclusions(self, pdf: FPDF, r: FinanceReportSchema) -> None:
        self._h2(pdf, r.headline, need=70)
        self._text(pdf, "Негізгі қорытындылар", bold=True, color=INK)
        for item in r.key_findings:
            self._text(pdf, f"•  {item}")
        if r.risks:
            pdf.ln(1)
            self._text(pdf, "Тәуекелдер", bold=True, color=INK)
            for risk in r.risks:
                self._text(pdf, f"•  {risk.title} ({RISK_LABEL.get(risk.level.value, risk.level.value)}): {risk.detail}")
        pdf.ln(1)
        self._text(pdf, "Ұсыныстар", bold=True, color=INK)
        for i, item in enumerate(r.recommendations, 1):
            self._text(pdf, f"{i}.  {item}")

    def _monthly_chart(self, pdf: FPDF, m: FinanceMetrics) -> None:
        if not m.monthly:
            return
        self._h2(pdf, "Айлар бойынша ақша ағыны", need=82)
        x0, y0 = pdf.l_margin, pdf.get_y() + 2
        width, height = pdf.w - pdf.l_margin - pdf.r_margin, 50
        peak = max(max(x.income, x.expense) for x in m.monthly) or 1
        slot = width / len(m.monthly)
        bar = min(9.0, slot / 3)
        pdf.set_draw_color(*LINE)
        pdf.line(x0, y0 + height, x0 + width, y0 + height)
        for i, flow in enumerate(m.monthly):
            cx = x0 + slot * i + slot / 2
            for j, (value, color) in enumerate(((flow.income, INCOME), (flow.expense, EXPENSE))):
                h = height * value / peak
                pdf.set_fill_color(*color)
                pdf.rect(cx - bar - 0.5 + j * (bar + 1), y0 + height - h, bar, h, style="F")
            pdf.set_xy(cx - slot / 2, y0 + height + 1.5)
            pdf.set_font("PTSans", "", 8)
            pdf.set_text_color(*MUTE)
            pdf.cell(slot, 4, month_label(flow.month), align="C")
        pdf.set_xy(x0, y0 + height + 7)
        for label, color in (("Түсімдер", INCOME), ("Шығыстар", EXPENSE)):
            pdf.set_fill_color(*color)
            pdf.rect(pdf.get_x(), pdf.get_y() + 1.2, 3, 3, style="F")
            pdf.set_x(pdf.get_x() + 4.5)
            pdf.set_font("PTSans", "", 8.5)
            pdf.set_text_color(*SOFT)
            pdf.cell(28, 5.5, label)
        pdf.ln(8)

    def _table(self, pdf: FPDF, header: tuple[str, ...], rows: list[tuple[str, ...]], widths: tuple[int, ...]) -> None:
        pdf.set_font("PTSans", "", 9.5)
        pdf.set_text_color(*INK)
        pdf.set_draw_color(*LINE)
        pdf.set_fill_color(255, 255, 255)  # әйтпесе кесте соңғы бояудың түсін мұрагерлейді (график аңызы)
        with pdf.table(col_widths=widths, text_align=("LEFT",) + ("RIGHT",) * (len(header) - 1),
                       line_height=6.2, borders_layout="HORIZONTAL_LINES",
                       headings_style=_headings()) as table:
            head = table.row()
            for h in header:
                head.cell(h)
            for values in rows:
                row = table.row()
                for v in values:
                    row.cell(v)

    def _forecast(self, pdf: FPDF, m: FinanceMetrics) -> None:
        self._h2(pdf, "3 айлық қалдық болжамы", need=48)
        self._text(pdf, f"Соңғы {m.forecast_basis_months} толық айдың орташасы бойынша. Бұл — бағдар, уәде емес.",
                   size=9.5, color=MUTE)
        pdf.ln(1)
        rows = [(month_label(p.month), money(p.income), money(p.expense), money(p.net), money(p.balance))
                for p in m.forecast]
        self._table(pdf, ("Ай", "Түсім", "Шығыс", "Нәтиже", "Қалдық"), rows, (26, 20, 20, 18, 20))
        negative = next((p for p in m.forecast if p.balance < 0), None)
        if negative:
            pdf.ln(1)
            self._text(pdf, f"Назар аударыңыз: қазіргі қарқында қалдық {month_label(negative.month)} айында минусқа кетеді.",
                       color=BAD, bold=True)

    def _mom(self, pdf: FPDF, m: FinanceMetrics) -> None:
        mom = m.month_over_month
        assert mom is not None
        self._h2(
            pdf,
            f"{month_label(mom.current_month)} · алдыңғы ай: {month_label(mom.previous_month)}",
            need=34 + 6.4 * (len(mom.categories) + 1),
        )
        self._text(
            pdf,
            f"Түсімдер: {money(mom.income_previous)} → {money(mom.income_current)} · "
            f"Шығыстар: {money(mom.expense_previous)} → {money(mom.expense_current)}",
            size=9.5,
        )
        if mom.categories:
            pdf.ln(1)
            rows = [
                (c.category, money(c.previous), money(c.current),
                 ("+" if c.change > 0 else "") + money(c.change),
                 "—" if c.change_pct is None else f"{c.change_pct:+.0%}")
                for c in mom.categories
            ]
            self._table(pdf, ("Санат", "Бұрын", "Қазір", "Өзгеріс", "%"), rows, (30, 20, 20, 20, 12))

    def _budgets(self, pdf: FPDF, m: FinanceMetrics, budgets: list[BudgetCheck]) -> None:
        self._h2(
            pdf,
            f"Бюджеттер · {month_label(m.budget_month) if m.budget_month else ''}",
            need=24 + 6.4 * (len(budgets) + 1),
        )
        rows = [
            (b.category, money(b.limit), money(b.spent),
             ("асып кету " + money(-b.remaining)) if b.over else money(b.remaining), f"{b.ratio:.0%}")
            for b in budgets
        ]
        self._table(pdf, ("Санат", "Лимит", "Жұмсалды", "Қалдық", "Пайд."), rows, (30, 20, 20, 26, 12))

    def _categories(self, pdf: FPDF, m: FinanceMetrics) -> None:
        self._h2(pdf, "Кезеңдегі санаттар бойынша шығыстар", need=24 + 6.4 * (len(m.expense_by_category) + 1))
        rows = [(c.category, money(c.amount), f"{c.share:.1%}") for c in m.expense_by_category]
        self._table(pdf, ("Санат", "Сома", "Үлесі"), rows, (40, 24, 14))

    def _gaps(self, pdf: FPDF, m: FinanceMetrics) -> None:
        self._h2(pdf, "Ақша ағынының үзілістері", need=22 + 6 * len(m.cash_gaps))
        for g in m.cash_gaps:
            self._text(pdf, f"•  {g.start:%d.%m.%Y} — {g.end:%d.%m.%Y} ({g.days} күн), минимум {money(g.min_balance)}",
                       color=BAD)


def _headings():  # type: ignore[no-untyped-def]
    from fpdf.fonts import FontFace

    return FontFace(family="PTSans", emphasis="BOLD", color=MUTE, size_pt=8.5, fill_color=(247, 248, 249))
