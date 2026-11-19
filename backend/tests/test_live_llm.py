"""Іске қосылған Unsloth Studio-ға қарсы тікелей тесттер.

Іске қосу: ``$env:ORCIFY_LIVE_TESTS=1; .venv\\Scripts\\python -m pytest -m live -s``
Тек синтетикалық деректер қолданылады.
"""

from __future__ import annotations

import os

import pytest

from app.config import Settings
from app.core.llm_client import LLMClient, build_http_client
from app.core.prompts import PromptLoader
from app.core.router import IntentRouter
from app.schemas.intent import DomainEnum

pytestmark = [
    pytest.mark.live,
    pytest.mark.skipif(os.environ.get("ORCIFY_LIVE_TESTS") != "1", reason="set ORCIFY_LIVE_TESTS=1"),
]

CASES = [
    ("ТОО Тест-пен 500 000 теңгеге 31 желтоқсанға дейін қызмет көрсету келісімшартын жаса", DomainEnum.LEGAL),
    ("Жаңа өнімімізді іске қосу туралы Instagram-ға пост жаса", DomainEnum.SMM),
    ("Қазан айындағы шот бойынша үзіндіні талда және ақша ағынының үзілістерін тап", DomainEnum.FINANCE),
    ("Жаңа менеджерді 1 желтоқсаннан бастап жұмысқа қабылдау бұйрығын дайында", DomainEnum.HR),
]


CHAT = """[10:14] Менеджер: Қайырлы күн! Сайт бойынша жұмысты бастауға дайынбыз.
[10:16] Клиент: Сәлеметсіз бе. Иә, келісімшартты рәсімдейік. Біз ТОО «Альфа Трейд», БСН 900101300017.
[10:17] Менеджер: Тамаша. Жұмысқа не кіреді?
[10:19] Клиент: Корпоративтік сайтты үш тілде әзірлеу және хостингті баптау.
[10:20] Менеджер: Құны, келіскендей, 1 250 000 теңге. Мерзімі — 2027 жылғы 15 ақпанға дейін.
[10:21] Клиент: Иә, бәрі дұрыс, келісімшартты жіберіңіздер."""


async def test_live_legal_extraction_and_render() -> None:
    from app.core.doc_engine import DocEngine
    from app.core.document_store import DocumentStore
    from app.core.legal_service import LegalService
    from app.schemas.legal import CurrencyEnum
    from datetime import date
    from decimal import Decimal

    settings = Settings()
    async with build_http_client(settings) as http:
        llm = LLMClient(settings, http)
        prompts = PromptLoader(settings.prompts_dir)
        legal = LegalService(llm, prompts, DocEngine(settings.templates_dir, settings), DocumentStore(60), settings)
        routed = await IntentRouter(llm, prompts, settings).classify(CHAT)
        extracted = await legal.extract(CHAT)

    validation = legal.validate(extracted.data)
    print(
        f"\nrouting={routed.data.domain.value} extract_latency_ms={extracted.stats.latency_ms} "
        f"attempts={extracted.stats.attempts} missing={validation.missing_fields} invalid={validation.invalid_fields}"
    )
    assert routed.data.domain is DomainEnum.LEGAL
    assert validation.contract is not None
    c = validation.contract
    assert c.bin_iin == "900101300017"
    assert c.contract_amount == Decimal("1250000")
    assert c.currency is CurrencyEnum.KZT
    assert c.deadline_date == date(2027, 2, 15)
    assert "Альфа Трейд" in c.client_name
    doc = legal.render(c)
    print(f"rendered {doc.filename} size={doc.size_bytes} sha256={doc.sha256[:12]}…")


@pytest.mark.parametrize(("text", "expected"), CASES)
async def test_live_intent_classification(text: str, expected: DomainEnum) -> None:
    settings = Settings()
    async with build_http_client(settings) as http:
        router = IntentRouter(LLMClient(settings, http), PromptLoader(settings.prompts_dir), settings)
        response = await router.classify(text)
    print(
        f"\n{expected.value}: got={response.data.domain.value} conf={response.data.confidence} "
        f"latency_ms={response.stats.latency_ms} server_prompt_ms={response.stats.server_prompt_ms} "
        f"server_predicted_ms={response.stats.server_predicted_ms} attempts={response.stats.attempts} "
        f"completion_tokens={response.stats.completion_tokens}"
    )
    assert response.data.domain is expected
