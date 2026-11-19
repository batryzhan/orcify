from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest
from pydantic import ValidationError

from app.schemas.legal import ContractData, ContractEntitiesSchema, CurrencyEnum, is_valid_kz_id

# Контрольные разряды посчитаны вручную по алгоритму ИИН/БИН РК.
VALID_FIRST_PASS = "900101300017"  # сумма с весами 1..11 = 51, 51 mod 11 = 7
VALID_SECOND_PASS = "901101300019"  # первый проход = 10, второй (веса 3..11,1,2) = 75 mod 11 = 9


@pytest.mark.parametrize("value", [VALID_FIRST_PASS, VALID_SECOND_PASS])
def test_valid_kz_ids(value: str) -> None:
    assert is_valid_kz_id(value)


@pytest.mark.parametrize(
    "value",
    ["900101300018", "90010130001", "9001013000171", "90010130001a", "", "９００１０１３０００１７"],
)
def test_invalid_kz_ids(value: str) -> None:
    assert not is_valid_kz_id(value)


def _entities(**overrides: object) -> ContractEntitiesSchema:
    data: dict[str, object] = {
        "client_name": "ТОО «Тест»",
        "bin_iin": VALID_FIRST_PASS,
        "contract_amount": "500000",
        "currency": "KZT",
        "deadline_date": "2026-12-31",
        "scope_of_work": "Разработка сайта",
    }
    data.update(overrides)
    return ContractEntitiesSchema.model_validate(data)


def test_contract_data_from_extraction() -> None:
    contract = ContractData.from_extraction(_entities())
    assert contract.contract_amount == Decimal("500000")
    assert contract.currency is CurrencyEnum.KZT
    assert contract.deadline_date == date(2026, 12, 31)


def test_contract_data_rejects_bad_checksum_without_leaking_value() -> None:
    with pytest.raises(ValidationError) as exc_info:
        ContractData.from_extraction(_entities(bin_iin="900101300018"))
    messages = [err["msg"] for err in exc_info.value.errors()]
    assert any("checksum" in m for m in messages)
    assert all("900101300018" not in m for m in messages)


def test_missing_fields_are_reported() -> None:
    entities = _entities(bin_iin=None, deadline_date=None)
    assert entities.missing_fields() == ["bin_iin", "deadline_date"]
    with pytest.raises(ValidationError):
        ContractData.from_extraction(entities)


def test_negative_amount_rejected() -> None:
    with pytest.raises(ValidationError):
        _entities(contract_amount="-1")


def test_extraction_schema_requires_all_keys_for_strict_mode() -> None:
    schema = ContractEntitiesSchema.model_json_schema()
    assert set(schema["required"]) == set(ContractEntitiesSchema.model_fields)
    assert schema["additionalProperties"] is False
