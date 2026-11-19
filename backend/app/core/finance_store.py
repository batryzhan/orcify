"""«Қаржы» терезесінің жергілікті қоймасы: бюджеттер және PDF-есептер мұрағаты (``backend/var``).

Мұрағатқа тек агрегаттары бар PDF және метадеректер (кезең, қорытынды) түседі — шикі
транзакциясыз. ``backend/var`` папкасы .gitignore ішінде және құрылғыдан шықпайды.
"""

from __future__ import annotations

import re
import threading
from pathlib import Path

from pydantic import ValidationError

from app.core.logger import get_logger
from app.schemas.finance import BudgetCheck, Budgets, FinanceMetrics, ReportRecord

log = get_logger(__name__)
_ID_RE = re.compile(r"^[0-9a-f]{32}$")


class BudgetStore:
    def __init__(self, path: Path | None) -> None:
        self._path = path
        self._lock = threading.Lock()

    def get(self) -> Budgets:
        if self._path is None or not self._path.is_file():
            return Budgets()
        try:
            return Budgets.model_validate_json(self._path.read_text(encoding="utf-8"))
        except (OSError, ValidationError):
            log.warning("budgets_unreadable", error_code="budgets_invalid")
            return Budgets()

    def put(self, budgets: Budgets) -> Budgets:
        # Санат бойынша бір жазба: соңғысы жеңеді.
        unique = {item.category.strip(): item for item in budgets.items}
        clean = Budgets(items=[i.model_copy(update={"category": c}) for c, i in unique.items()])
        if self._path is not None:
            with self._lock:
                self._path.parent.mkdir(parents=True, exist_ok=True)
                self._path.write_text(clean.model_dump_json(indent=1), encoding="utf-8")
        return clean

    def check(self, metrics: FinanceMetrics) -> list[BudgetCheck]:
        """Лимиттерді соңғы толық айдың шығыстарымен салыстырады (детерминистік)."""
        spent_by = {c.category.casefold(): c.amount for c in metrics.last_month_by_category}
        checks = []
        for item in self.get().items:
            spent = spent_by.get(item.category.casefold(), 0.0)
            checks.append(
                BudgetCheck(
                    category=item.category,
                    limit=item.limit,
                    spent=spent,
                    remaining=round(item.limit - spent, 2),
                    ratio=round(spent / item.limit, 4),
                    over=spent > item.limit,
                )
            )
        checks.sort(key=lambda c: c.ratio, reverse=True)
        return checks


class ReportStore:
    def __init__(self, directory: Path) -> None:
        self._dir = directory
        self._lock = threading.Lock()

    def save(self, record: ReportRecord, pdf: bytes) -> None:
        with self._lock:
            self._dir.mkdir(parents=True, exist_ok=True)
            rid = record.file.report_id
            (self._dir / f"{rid}.pdf").write_bytes(pdf)
            (self._dir / f"{rid}.json").write_text(record.model_dump_json(indent=1), encoding="utf-8")

    def get(self, report_id: str) -> ReportRecord | None:
        if not _ID_RE.fullmatch(report_id):
            return None
        path = self._dir / f"{report_id}.json"
        if not path.is_file():
            return None
        try:
            return ReportRecord.model_validate_json(path.read_text(encoding="utf-8"))
        except (OSError, ValidationError):
            return None

    def attach_issue(self, report_id: str, issue_key: str) -> None:
        record = self.get(report_id)
        if record is None:
            return
        record.issue_key = issue_key
        with self._lock:
            (self._dir / f"{report_id}.json").write_text(record.model_dump_json(indent=1), encoding="utf-8")

    def pdf_path(self, report_id: str) -> Path | None:
        if not _ID_RE.fullmatch(report_id):
            return None
        path = self._dir / f"{report_id}.pdf"
        return path if path.is_file() else None

    def delete(self, report_id: str) -> bool:
        if self.get(report_id) is None:
            return False
        with self._lock:
            for suffix in (".pdf", ".json"):
                (self._dir / f"{report_id}{suffix}").unlink(missing_ok=True)
        return True

    def list(self, limit: int = 50) -> list[ReportRecord]:
        if not self._dir.is_dir():
            return []
        records = [r for p in self._dir.glob("*.json") if (r := self.get(p.stem)) is not None]
        records.sort(key=lambda r: r.created_at, reverse=True)
        return records[:limit]
