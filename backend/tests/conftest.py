from __future__ import annotations

import json
from collections.abc import Callable

import httpx
import pytest
from pydantic import SecretStr

from app.config import Settings

Handler = Callable[[httpx.Request], httpx.Response]


@pytest.fixture
def settings() -> Settings:
    # _env_file=None: тесты не читают реальный backend/.env с ключом.
    return Settings(_env_file=None, llm_api_key=SecretStr("test-key"), llm_max_attempts=2)  # type: ignore[call-arg]


def chat_response(content: str, finish_reason: str = "stop") -> httpx.Response:
    return httpx.Response(
        200,
        json={
            "choices": [{"index": 0, "finish_reason": finish_reason, "message": {"role": "assistant", "content": content}}],
            "usage": {"prompt_tokens": 10, "completion_tokens": 5},
        },
    )


def intent_json(domain: str = "Legal", confidence: float = 0.9) -> str:
    return json.dumps({"domain": domain, "confidence": confidence, "reasoning": "Запрос на договор."})


VALID_IIN = "900101300017"  # синтетический ИИН с верным контрольным разрядом


def entities_json(**overrides: object) -> str:
    data: dict[str, object] = {
        "client_name": "ТОО «Тест & Ко»",
        "bin_iin": VALID_IIN,
        "contract_amount": 500000,
        "currency": "KZT",
        "deadline_date": "2026-12-31",
        "scope_of_work": "Разработка корпоративного сайта",
    }
    data.update(overrides)
    return json.dumps(data, ensure_ascii=False)


def schema_router(replies: dict[str, str]) -> Handler:
    """Мок LLM: отвечает по имени запрошенной JSON-схемы."""

    def handler(request: httpx.Request) -> httpx.Response:
        name = json.loads(request.content)["response_format"]["json_schema"]["name"]
        return chat_response(replies[name])

    return handler
