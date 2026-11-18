"""Deterministic Core: рендер .docx через docxtpl.

На вход — только провалидированный ``ContractData``. Все значения
форматируются детерминированно (даты, суммы), Jinja работает со
``StrictUndefined`` и автоэкранированием XML.
"""

from __future__ import annotations

import io
from datetime import date
from decimal import ROUND_HALF_UP, Decimal
from pathlib import Path
from typing import Final

from docxtpl import DocxTemplate
from jinja2 import Environment, StrictUndefined
from pydantic import BaseModel, ConfigDict

from app.config import Settings
from app.schemas.legal import ContractData, CurrencyEnum

CONTRACT_TEMPLATE: Final = "service_contract_kz.docx"

MONTHS_GENITIVE: Final = (
    "января", "февраля", "марта", "апреля", "мая", "июня",
    "июля", "августа", "сентября", "октября", "ноября", "декабря",
)

CURRENCY_NAMES: Final = {
    CurrencyEnum.KZT: "тенге",
    CurrencyEnum.USD: "долларов США",
    CurrencyEnum.EUR: "евро",
    CurrencyEnum.RUB: "российских рублей",
}


class DocEngineError(Exception):
    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


def format_date_ru(value: date) -> str:
    return f"«{value.day:02d}» {MONTHS_GENITIVE[value.month - 1]} {value.year} г."


def format_amount(value: Decimal) -> str:
    """500000 -> '500 000,00' (неразрывные пробелы между разрядами)."""
    quantized = value.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    integer, _, cents = f"{quantized:.2f}".partition(".")
    grouped = f"{int(integer):,}".replace(",", " ")
    return f"{grouped},{cents}"


class ContractRenderContext(BaseModel):
    """Ровно те переменные, что объявлены в шаблоне договора."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    contract_number: str
    contract_date: str
    city: str
    executor_name: str
    executor_bin: str
    executor_signatory: str
    executor_basis: str
    client_name: str
    client_bin_iin: str
    scope_of_work: str
    deadline: str
    amount: str
    currency_name: str


class DocEngine:
    def __init__(self, templates_dir: Path, settings: Settings) -> None:
        self._templates_dir = templates_dir
        self._settings = settings

    def build_context(self, contract: ContractData, *, contract_number: str, contract_date: date) -> ContractRenderContext:
        s = self._settings
        return ContractRenderContext(
            contract_number=contract_number,
            contract_date=format_date_ru(contract_date),
            city=s.contract_city,
            executor_name=s.executor_name,
            executor_bin=s.executor_bin,
            executor_signatory=s.executor_signatory,
            executor_basis=s.executor_basis,
            client_name=contract.client_name,
            client_bin_iin=contract.bin_iin,
            scope_of_work=contract.scope_of_work,
            deadline=format_date_ru(contract.deadline_date),
            amount=format_amount(contract.contract_amount),
            currency_name=CURRENCY_NAMES[contract.currency],
        )

    def render_contract(self, contract: ContractData, *, contract_number: str, contract_date: date) -> bytes:
        context = self.build_context(contract, contract_number=contract_number, contract_date=contract_date)
        path = self._templates_dir / CONTRACT_TEMPLATE
        if not path.is_file():
            raise DocEngineError("template_not_found")
        try:
            template = DocxTemplate(str(path))
            template.render(
                context.model_dump(),
                jinja_env=Environment(undefined=StrictUndefined, autoescape=True),
                autoescape=True,
            )
            buffer = io.BytesIO()
            template.save(buffer)
        except Exception:
            # from None: исключения Jinja/lxml могут содержать фрагменты данных.
            raise DocEngineError("render_failed") from None
        return buffer.getvalue()
