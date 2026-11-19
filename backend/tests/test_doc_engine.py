from __future__ import annotations

from datetime import date
from decimal import Decimal
from pathlib import Path

import pytest

from app.config import BACKEND_DIR, Settings
from app.core.doc_engine import DocEngine, DocEngineError, format_amount, format_date_ru
from app.schemas.legal import ContractData
from tests.conftest import VALID_IIN


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        (Decimal("500000"), "500 000,00"),
        (Decimal("1250000.5"), "1 250 000,50"),
        (Decimal("999.995"), "1 000,00"),
        (Decimal("0.01"), "0,01"),
    ],
)
def test_format_amount(value: Decimal, expected: str) -> None:
    assert format_amount(value) == expected


def test_format_date_ru() -> None:
    assert format_date_ru(date(2026, 3, 8)) == "«08» наурыз 2026 ж."


def contract() -> ContractData:
    return ContractData(
        client_name="ЖК Иванов",
        bin_iin=VALID_IIN,
        contract_amount=Decimal("100"),
        currency="USD",  # type: ignore[arg-type]
        deadline_date=date(2027, 1, 15),
        scope_of_work="Кеңестер",
    )


def test_context_matches_template_variables(settings: Settings) -> None:
    from docxtpl import DocxTemplate

    engine = DocEngine(BACKEND_DIR / "templates", settings)
    ctx = engine.build_context(contract(), contract_number="N1", contract_date=date(2026, 11, 18))
    declared = DocxTemplate(str(BACKEND_DIR / "templates" / "service_contract_kz.docx")).get_undeclared_template_variables()
    assert declared == set(ctx.model_dump())
    assert ctx.currency_name == "АҚШ доллары"


def test_missing_template(settings: Settings, tmp_path: Path) -> None:
    with pytest.raises(DocEngineError) as exc_info:
        DocEngine(tmp_path, settings).render_contract(contract(), contract_number="N1", contract_date=date.today())
    assert exc_info.value.code == "template_not_found"
