from __future__ import annotations

import asyncio
import json

import httpx
import pytest

from app.config import Settings
from app.core.llm_client import (
    ChatMessage,
    LLMClient,
    LLMResponseError,
    LLMUnavailableError,
    build_http_client,
)
from app.schemas.intent import DomainEnum, IntentClassificationResult
from tests.conftest import Handler, chat_response, intent_json

MESSAGES = [ChatMessage(role="user", content="келісімшарт")]


def make_client(settings: Settings, handler: Handler) -> LLMClient:
    return LLMClient(settings, build_http_client(settings, transport=httpx.MockTransport(handler)))


async def test_structured_sends_strict_json_schema(settings: Settings) -> None:
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return chat_response(intent_json())

    result = await make_client(settings, handler).structured(MESSAGES, IntentClassificationResult, stage="t")

    assert result.data.domain is DomainEnum.LEGAL
    assert result.stats.attempts == 1
    assert result.stats.prompt_tokens == 10

    request = seen[0]
    assert request.url.path == "/v1/chat/completions"
    assert request.headers["Authorization"] == "Bearer test-key"
    body = json.loads(request.content)
    fmt = body["response_format"]
    assert fmt["type"] == "json_schema"
    assert fmt["json_schema"]["strict"] is True
    assert fmt["json_schema"]["schema"] == IntentClassificationResult.model_json_schema()


async def test_retries_once_on_schema_mismatch(settings: Settings) -> None:
    replies = iter([chat_response('{"domain": "Space"}'), chat_response(intent_json("HR"))])
    client = make_client(settings, lambda _req: next(replies))

    result = await client.structured(MESSAGES, IntentClassificationResult, stage="t")

    assert result.data.domain is DomainEnum.HR
    assert result.stats.attempts == 2
    assert result.stats.completion_tokens == 10


async def test_gives_up_after_max_attempts(settings: Settings) -> None:
    client = make_client(settings, lambda _req: chat_response("not json"))
    with pytest.raises(LLMResponseError) as exc_info:
        await client.structured(MESSAGES, IntentClassificationResult, stage="t")
    assert exc_info.value.code == "schema_mismatch"
    assert exc_info.value.attempts == 2
    assert exc_info.value.__cause__ is None  # input_value бар ValidationError тіркелмеген


async def test_truncated_output(settings: Settings) -> None:
    client = make_client(settings, lambda _req: chat_response('{"dom', finish_reason="length"))
    with pytest.raises(LLMResponseError) as exc_info:
        await client.structured(MESSAGES, IntentClassificationResult, stage="t")
    assert exc_info.value.code == "truncated"


@pytest.mark.parametrize(
    ("response", "code"),
    [(httpx.Response(401), "unauthorized"), (httpx.Response(503), "http_503"), (httpx.Response(200, text="<html>"), "malformed_api_response")],
)
async def test_http_errors(settings: Settings, response: httpx.Response, code: str) -> None:
    client = make_client(settings, lambda _req: response)
    with pytest.raises(LLMUnavailableError) as exc_info:
        await client.structured(MESSAGES, IntentClassificationResult, stage="t")
    assert exc_info.value.code == code


async def test_connection_error(settings: Settings) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("refused", request=request)

    with pytest.raises(LLMUnavailableError) as exc_info:
        await make_client(settings, handler).structured(MESSAGES, IntentClassificationResult, stage="t")
    assert exc_info.value.code == "connection_error"


async def test_deadline_covers_slow_server(settings: Settings) -> None:
    # Сервер жалпы дедлайннан баяу, бірақ httpx read-timeout-тан жылдам жауап береді.
    fast_deadline = settings.model_copy(update={"llm_deadline_s": 0.2, "llm_timeout_s": 10.0})

    async def slow_handler(_req: httpx.Request) -> httpx.Response:
        await asyncio.sleep(1.0)
        return chat_response(intent_json())

    client = LLMClient(fast_deadline, build_http_client(fast_deadline, transport=httpx.MockTransport(slow_handler)))
    with pytest.raises(LLMUnavailableError) as exc_info:
        await client.structured(MESSAGES, IntentClassificationResult, stage="t")
    assert exc_info.value.code == "deadline_exceeded"
    assert exc_info.value.attempts == 1


async def test_deadline_covers_all_retries(settings: Settings) -> None:
    # Әр әрекет жылдам, бірақ қайталаулармен бірге дедлайнға сыймайды.
    tight = settings.model_copy(update={"llm_deadline_s": 0.25, "llm_max_attempts": 5})

    async def handler(_req: httpx.Request) -> httpx.Response:
        await asyncio.sleep(0.1)
        return chat_response("not json")

    client = LLMClient(tight, build_http_client(tight, transport=httpx.MockTransport(handler)))
    with pytest.raises(LLMUnavailableError) as exc_info:
        await client.structured(MESSAGES, IntentClassificationResult, stage="t")
    assert exc_info.value.code == "deadline_exceeded"
    assert exc_info.value.attempts == 3


async def test_server_timings_are_summed_across_attempts(settings: Settings) -> None:
    def with_timings(content: str, prompt_ms: float, predicted_ms: float) -> httpx.Response:
        body = json.loads(chat_response(content).content)
        body["timings"] = {"prompt_ms": prompt_ms, "predicted_ms": predicted_ms, "predicted_n": 5}
        return httpx.Response(200, json=body)

    replies = iter([with_timings("bad", 100.4, 2000.2), with_timings(intent_json(), 50.3, 1000.1)])
    result = await make_client(settings, lambda _req: next(replies)).structured(
        MESSAGES, IntentClassificationResult, stage="t"
    )
    assert result.stats.server_prompt_ms == 151
    assert result.stats.server_predicted_ms == 3000


async def test_server_timings_absent(settings: Settings) -> None:
    result = await make_client(settings, lambda _req: chat_response(intent_json())).structured(
        MESSAGES, IntentClassificationResult, stage="t"
    )
    assert result.stats.server_prompt_ms is None
    assert result.stats.server_predicted_ms is None


async def test_health_reports_loaded_model(settings: Settings) -> None:
    def handler(_req: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200, json={"data": [{"id": settings.llm_model, "loaded": True, "context_length": 8192, "quant": "Q4"}]}
        )

    health = await make_client(settings, handler).health()
    assert health.reachable and health.loaded and health.context_length == 8192
    assert health.error_code is None


async def test_health_unauthorized(settings: Settings) -> None:
    health = await make_client(settings, lambda _req: httpx.Response(401)).health()
    assert not health.reachable
    assert health.error_code == "unauthorized"
