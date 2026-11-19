"""Legal домені схемалары (Deterministic Core).

Тізбек: ``ContractEntitiesSchema`` (LLM жауабы, өрістер null болуы мүмкін)
-> ``ContractData`` (қатаң валидация, соның ішінде ЖСН/БСН бақылау разряды)
-> ``docxtpl`` рендері.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from enum import StrEnum
from typing import Annotated, Final
from uuid import UUID

from pydantic import AfterValidator, BaseModel, ConfigDict, Field, StringConstraints

_WEIGHTS_1: Final = (1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11)
_WEIGHTS_2: Final = (3, 4, 5, 6, 7, 8, 9, 10, 11, 1, 2)


def is_valid_kz_id(value: str) -> bool:
    """Қазақстан Республикасы ЖСН/БСН бақылау разрядын тексеру.

    12-ші цифр = алғашқы 11 цифр бойынша сумма(d_i * w1_i) mod 11; егер
    нәтиже 10 болса — салмақтардың екінші жинағымен қайта есептеу; егер қайтадан 10 болса —
    нөмір қате.
    """
    if len(value) != 12 or not value.isascii() or not value.isdigit():
        return False
    digits = [int(c) for c in value]
    control = sum(d * w for d, w in zip(digits[:11], _WEIGHTS_1)) % 11
    if control == 10:
        control = sum(d * w for d, w in zip(digits[:11], _WEIGHTS_2)) % 11
        if control == 10:
            return False
    return control == digits[11]


def _check_kz_id(value: str) -> str:
    if not is_valid_kz_id(value):
        # Хабарлама мәннің өзінсіз әдейі жазылған (Zero-PII).
        raise ValueError("invalid IIN/BIN checksum")
    return value


KzIdDigits = Annotated[str, StringConstraints(pattern=r"^\d{12}$")]
KzId = Annotated[KzIdDigits, AfterValidator(_check_kz_id)]


class CurrencyEnum(StrEnum):
    KZT = "KZT"
    USD = "USD"
    EUR = "EUR"
    RUB = "RUB"


class ContractEntitiesSchema(BaseModel):
    """LLM экстракторының Structured Output-ы. ``null`` = мән мәтіннен табылмады."""

    model_config = ConfigDict(extra="forbid")

    client_name: str | None = Field(description="Клиенттің (тапсырыс берушінің) атауы")
    bin_iin: KzIdDigits | None = Field(description="Клиенттің ЖСН/БСН-і, 12 цифр")
    contract_amount: Annotated[Decimal, Field(ge=0)] | None = Field(description="Келісімшарт сомасы")
    currency: CurrencyEnum | None = Field(description="Келісімшарт валютасы")
    deadline_date: date | None = Field(description="Орындау мерзімі, YYYY-MM-DD")
    scope_of_work: str | None = Field(description="Келісімшарт нысаны: қандай қызметтер көрсетіледі")

    def missing_fields(self) -> list[str]:
        return [name for name, value in self if value is None]


class ContractData(BaseModel):
    """Шаблонизаторға беруге рұқсат етілген тексерілген деректер."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    client_name: str = Field(min_length=1, max_length=300)
    bin_iin: KzId
    contract_amount: Decimal = Field(gt=0, max_digits=15, decimal_places=2)
    currency: CurrencyEnum
    deadline_date: date
    scope_of_work: str = Field(min_length=1, max_length=5000)

    @classmethod
    def from_extraction(cls, entities: ContractEntitiesSchema) -> ContractData:
        return cls.model_validate(entities.model_dump())


class LegalOutcome(StrEnum):
    RENDERED = "rendered"
    NEEDS_INPUT = "needs_input"


class DocumentInfo(BaseModel):
    document_id: UUID
    filename: str
    download_url: str
    sha256: str
    size_bytes: int


class LegalResult(BaseModel):
    """А сценарийінің нәтижесі. ``entities`` тексеру үшін жергілікті UI-ға қайтарылады."""

    model_config = ConfigDict(extra="forbid")

    outcome: LegalOutcome
    entities: ContractEntitiesSchema
    missing_fields: list[str]
    invalid_fields: list[str]
    document: DocumentInfo | None = None
