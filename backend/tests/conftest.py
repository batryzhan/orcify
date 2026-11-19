from __future__ import annotations

import json
from collections.abc import Callable
from pathlib import Path

import httpx
import pytest
from pydantic import SecretStr

from app.config import Settings

Handler = Callable[[httpx.Request], httpx.Response]


@pytest.fixture
def settings(tmp_path: Path) -> Settings:
    # _env_file=None: тесттер LLM, Telegram кілттері бар нақты backend/.env оқымайды.
    # Тақта, посттар және чаттар — уақытша папкада, backend/var қозғалмауы үшін.
    return Settings(  # type: ignore[call-arg]
        _env_file=None,
        llm_api_key=SecretStr("test-key"),
        llm_max_attempts=2,
        jira_board_path=tmp_path / "jira_board.json",
        posts_dir=tmp_path / "posts",
        finance_reports_dir=tmp_path / "finance_reports",
        finance_budgets_path=tmp_path / "finance_budgets.json",
        telegram_chats_path=tmp_path / "telegram_chats.json",
    )


def chat_response(content: str, finish_reason: str = "stop") -> httpx.Response:
    return httpx.Response(
        200,
        json={
            "choices": [{"index": 0, "finish_reason": finish_reason, "message": {"role": "assistant", "content": content}}],
            "usage": {"prompt_tokens": 10, "completion_tokens": 5},
        },
    )


def intent_json(domain: str = "Legal", confidence: float = 0.9) -> str:
    return json.dumps({"domain": domain, "confidence": confidence, "reasoning": "Келісімшартқа сұраныс."})


VALID_IIN = "900101300017"  # бақылау разряды дұрыс синтетикалық ЖСН


def entities_json(**overrides: object) -> str:
    data: dict[str, object] = {
        "client_name": "ТОО «Тест & Ко»",
        "bin_iin": VALID_IIN,
        "contract_amount": 500000,
        "currency": "KZT",
        "deadline_date": "2026-12-31",
        "scope_of_work": "Корпоративтік сайтты әзірлеу",
    }
    data.update(overrides)
    return json.dumps(data, ensure_ascii=False)


def schema_router(replies: dict[str, str]) -> Handler:
    """LLM моклары: сұралған JSON-схема атауы бойынша жауап береді."""

    def handler(request: httpx.Request) -> httpx.Response:
        name = json.loads(request.content)["response_format"]["json_schema"]["name"]
        return chat_response(replies[name])

    return handler
