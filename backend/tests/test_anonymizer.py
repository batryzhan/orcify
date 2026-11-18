from __future__ import annotations

import json

import httpx
import pytest

from app.config import BACKEND_DIR, Settings
from app.core.anonymizer import AnonymizationSession, LocalAnonymizer
from app.core.llm_client import LLMClient, build_http_client
from app.core.prompts import PromptLoader
from app.schemas.privacy import PiiCategory
from tests.conftest import chat_response

TEXT = (
    "Клиент ТОО «Альфа Трейд» (БИН 900140300013), контакт Иванов Пётр, "
    "тел. +7 701 123-45-67, почта petr.ivanov@alfa.kz, ИИН 900101300017, "
    "счёт KZ12 3456 7890 1234 5678, карта 4400 1234 5678 9012, а также ИП Сериков."
)


def test_regex_detection_and_tokens() -> None:
    session = AnonymizationSession()
    out = session.anonymize(TEXT)

    for raw in ["ТОО «Альфа Трейд»", "900140300013", "+7 701 123-45-67", "petr.ivanov@alfa.kz",
                "900101300017", "KZ12 3456 7890 1234 5678", "4400 1234 5678 9012", "ИП Сериков"]:
        assert raw not in out
    assert "[COMPANY_1]" in out and "[COMPANY_2]" in out
    assert "[BIN_1]" in out and "[IIN_1]" in out
    assert "[PHONE_1]" in out and "[EMAIL_1]" in out and "[IBAN_1]" in out and "[CARD_1]" in out
    assert session.leaked(out) == 0
    assert session.deanonymize(out) == TEXT


def test_tokens_are_deterministic_within_session() -> None:
    session = AnonymizationSession()
    a = session.anonymize("ИИН 900101300017")
    b = session.anonymize("повторно 900101300017")
    assert a == "ИИН [IIN_1]" and b == "повторно [IIN_1]"


def test_short_value_does_not_corrupt_tokens() -> None:
    session = AnonymizationSession()
    session.register("Иванов Пётр", PiiCategory.PERSON)
    session.register("ER", PiiCategory.COMPANY)  # подстрока токена [PERSON_1]
    out = session.anonymize("Иванов Пётр и ER")
    assert out == "[PERSON_1] и [COMPANY_1]"
    assert session.deanonymize(out) == "Иванов Пётр и ER"


def test_aliases_catch_bare_names_and_hashtags() -> None:
    """Регрессия живого прогона: модель написала «Альфа Трейд» и «#альфатрейд» без «ТОО»."""
    session = AnonymizationSession()
    session.anonymize("Ролик для ТОО «Альфа Трейд», кейс клиента Иванов Пётр")
    session.register("Иванов Пётр", PiiCategory.PERSON)
    generated = "Альфа Трейд: доставка за час. #альфатрейд #АльфаТрейд Иванову понравилось"
    out = session.anonymize(generated)
    assert out == "[COMPANY_1]: доставка за час. #[COMPANY_1] #[COMPANY_1] [PERSON_1]у понравилось"
    assert session.leaked(out) == 0
    assert session.leaked(generated) > 0
    assert session.report().entities_total == 2  # псевдонимы не считаются отдельными сущностями


def test_json_roundtrip_and_leak_check() -> None:
    session = AnonymizationSession()
    payload = {"prompt": "Ролик для ТОО «Бета»", "scenes": [{"text": "звоните +7 777 000 11 22"}], "n": 3}
    masked = session.anonymize_json(payload)
    assert session.leaked_json(masked) == 0
    assert "Бета" not in json.dumps(masked, ensure_ascii=False)
    assert session.deanonymize_json(masked) == payload


def test_clear_destroys_mapping() -> None:
    session = AnonymizationSession()
    session.anonymize(TEXT)
    assert len(session) > 0
    session.clear()
    assert len(session) == 0
    assert session.deanonymize("[IIN_1]") == "[IIN_1]"


async def test_llm_detection_adds_names_and_ignores_hallucinations(settings: Settings) -> None:
    def handler(_req: httpx.Request) -> httpx.Response:
        entities = [
            {"text": "Иванов Пётр", "category": "PERSON"},
            {"text": "Алматы, ул. Абая 10", "category": "ADDRESS"},
            {"text": "Несуществующий Человек", "category": "PERSON"},  # нет в тексте
        ]
        return chat_response(json.dumps({"entities": entities}, ensure_ascii=False))

    llm = LLMClient(settings, build_http_client(settings, transport=httpx.MockTransport(handler)))
    anonymizer = LocalAnonymizer(llm, PromptLoader(BACKEND_DIR / "prompts"))
    text = "Встреча: Иванов Пётр, офис Алматы, ул. Абая 10."
    session = await anonymizer.build_session([text])

    out = session.anonymize(text)
    assert out == "Встреча: [PERSON_1], офис [ADDRESS_1]."
    report = session.report()
    assert report.llm_detection_used is True
    assert report.entities_total == 2


async def test_llm_failure_falls_back_to_regex(settings: Settings) -> None:
    llm = LLMClient(settings, build_http_client(settings, transport=httpx.MockTransport(lambda _r: httpx.Response(503))))
    session = await LocalAnonymizer(llm, PromptLoader(BACKEND_DIR / "prompts")).build_session(["ИИН 900101300017"])
    assert session.llm_detection_used is False
    assert session.anonymize("ИИН 900101300017") == "ИИН [IIN_1]"


@pytest.mark.parametrize("text", ["сумма 1 250 000 тенге", "дата 2027-02-15", "12 сотрудников"])
def test_no_false_positives_on_amounts_and_dates(text: str) -> None:
    assert AnonymizationSession().anonymize(text) == text
