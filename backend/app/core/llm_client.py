"""Жергілікті LLM клиенті (Unsloth Studio-дағы Gemma 4, OpenAI-үйлесімді API).

Әр шақыру — тек Structured Outputs: мақсатты Pydantic-модельдің
JSON Schema-сы ``response_format``-қа беріледі (strict), жауап сол
модельмен валидацияланады. Еркін мәтін талданбайды.
"""

from __future__ import annotations

import asyncio
import time
from typing import Generic, Literal, TypeVar

import httpx
from pydantic import BaseModel, ConfigDict, Field, ValidationError

from app.config import Settings
from app.core.logger import get_logger
from app.schemas.health import LLMHealth

T = TypeVar("T", bound=BaseModel)

log = get_logger(__name__)


class LLMError(Exception):
    """LLM негізгі қатесі. ``code`` — пайдаланушы деректерінсіз машиналық код."""

    def __init__(self, code: str, attempts: int = 1) -> None:
        super().__init__(code)
        self.code = code
        self.attempts = attempts


class LLMUnavailableError(LLMError):
    """Сервер қолжетімсіз, авторизацияланбаған немесе HTTP-қате қайтарды."""


class LLMResponseError(LLMError):
    """Модель жауап берді, бірақ жауап схемаға сәйкес келмейді."""


# --- Сұраныс келісімшарты ---------------------------------------------------------


class ChatMessage(BaseModel):
    role: Literal["system", "user", "assistant"]
    content: str


class JsonSchemaSpec(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    name: str
    strict: bool = True
    schema_: dict[str, object] = Field(alias="schema")


class ResponseFormat(BaseModel):
    type: Literal["json_schema"] = "json_schema"
    json_schema: JsonSchemaSpec


class ChatCompletionRequest(BaseModel):
    model: str
    messages: list[ChatMessage]
    temperature: float
    max_tokens: int
    response_format: ResponseFormat
    stream: Literal[False] = False


# --- Жауап келісімшарты (артық өрістер еленбейді) -------------------------------


class _Message(BaseModel):
    content: str | None = None


class _Choice(BaseModel):
    message: _Message
    finish_reason: str | None = None


class _Usage(BaseModel):
    prompt_tokens: int = 0
    completion_tokens: int = 0


class _Timings(BaseModel):
    """llama.cpp сервер таймингтері (барлық OpenAI-үйлесімді серверлерде бола бермейді)."""

    prompt_ms: float = 0.0
    predicted_ms: float = 0.0


class _ChatCompletionResponse(BaseModel):
    choices: list[_Choice]
    usage: _Usage = Field(default_factory=_Usage)
    timings: _Timings | None = None


class _ModelEntry(BaseModel):
    id: str
    loaded: bool | None = None
    context_length: int | None = None


class _ModelsResponse(BaseModel):
    data: list[_ModelEntry]


# --- Нәтиже ----------------------------------------------------------------


class LLMCallStats(BaseModel):
    """docs/metrics.md үшін шақыру телеметриясы (PII-сіз).

    ``latency_ms`` — ``time.monotonic()`` бойынша клиент жағындағы уақыт:
    Windows-та бұл сағат ноутбук ұйықтағанда жүрмейді (Modern Standby), сондықтан
    ұйқы метрикаға түспейді. ``server_prompt_ms``/``server_predicted_ms`` —
    llama.cpp деректері бойынша таза инференс уақыты, барлық әрекеттер бойынша қосынды.
    """

    model: str
    latency_ms: int
    attempts: int
    prompt_tokens: int
    completion_tokens: int
    server_prompt_ms: int | None = None
    server_predicted_ms: int | None = None


class StructuredResponse(BaseModel, Generic[T]):
    data: T
    stats: LLMCallStats


def build_http_client(
    settings: Settings, transport: httpx.AsyncBaseTransport | None = None
) -> httpx.AsyncClient:
    headers: dict[str, str] = {}
    api_key = settings.llm_api_key.get_secret_value()
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"
    return httpx.AsyncClient(
        base_url=str(settings.llm_base_url),
        timeout=settings.llm_timeout_s,
        headers=headers,
        transport=transport,
    )


class LLMClient:
    def __init__(self, settings: Settings, http: httpx.AsyncClient) -> None:
        self._settings = settings
        self._http = http

    async def structured(
        self, messages: list[ChatMessage], schema: type[T], *, stage: str
    ) -> StructuredResponse[T]:
        request = ChatCompletionRequest(
            model=self._settings.llm_model,
            messages=messages,
            temperature=self._settings.llm_temperature,
            max_tokens=self._settings.llm_max_tokens,
            response_format=ResponseFormat(
                json_schema=JsonSchemaSpec(name=schema.__name__, schema=schema.model_json_schema())
            ),
        )
        body = request.model_dump(mode="json", by_alias=True)
        attempt_box = [0]
        try:
            async with asyncio.timeout(self._settings.llm_deadline_s):
                return await self._run_attempts(body, schema, stage, attempt_box)
        except TimeoutError:
            log.error("llm_call_failed", stage=stage, attempts=attempt_box[0], error_code="deadline_exceeded")
            raise LLMUnavailableError("deadline_exceeded", attempts=attempt_box[0]) from None

    async def _run_attempts(
        self, body: dict[str, object], schema: type[T], stage: str, attempt_box: list[int]
    ) -> StructuredResponse[T]:
        started = time.monotonic()
        prompt_tokens = completion_tokens = 0
        server_prompt_ms = server_predicted_ms = 0.0
        has_server_timings = False
        last_error = LLMResponseError("no_attempts", attempts=0)

        for attempt in range(1, self._settings.llm_max_attempts + 1):
            attempt_box[0] = attempt
            completion = await self._post_chat(body, attempt)
            prompt_tokens += completion.usage.prompt_tokens
            completion_tokens += completion.usage.completion_tokens
            if completion.timings is not None:
                has_server_timings = True
                server_prompt_ms += completion.timings.prompt_ms
                server_predicted_ms += completion.timings.predicted_ms
            try:
                data = self._parse(completion, schema)
            except LLMResponseError as exc:
                last_error = LLMResponseError(exc.code, attempts=attempt)
                log.warning("llm_invalid_output", stage=stage, attempt=attempt, error_code=exc.code)
                continue

            stats = LLMCallStats(
                model=self._settings.llm_model,
                latency_ms=round((time.monotonic() - started) * 1000),
                attempts=attempt,
                prompt_tokens=prompt_tokens,
                completion_tokens=completion_tokens,
                server_prompt_ms=round(server_prompt_ms) if has_server_timings else None,
                server_predicted_ms=round(server_predicted_ms) if has_server_timings else None,
            )
            log.info(
                "llm_call_ok",
                stage=stage,
                attempts=attempt,
                latency_ms=stats.latency_ms,
                prompt_tokens=prompt_tokens,
                completion_tokens=completion_tokens,
            )
            return StructuredResponse[T](data=data, stats=stats)

        log.error("llm_call_failed", stage=stage, attempts=last_error.attempts, error_code=last_error.code)
        raise last_error

    async def _post_chat(self, body: dict[str, object], attempt: int) -> _ChatCompletionResponse:
        try:
            response = await self._http.post("/chat/completions", json=body)
        except httpx.TimeoutException:
            raise LLMUnavailableError("timeout", attempts=attempt) from None
        except httpx.HTTPError:
            raise LLMUnavailableError("connection_error", attempts=attempt) from None

        if response.status_code in (401, 403):
            raise LLMUnavailableError("unauthorized", attempts=attempt)
        if response.status_code >= 400:
            raise LLMUnavailableError(f"http_{response.status_code}", attempts=attempt)
        try:
            return _ChatCompletionResponse.model_validate_json(response.content)
        except ValidationError:
            raise LLMUnavailableError("malformed_api_response", attempts=attempt) from None

    @staticmethod
    def _parse(completion: _ChatCompletionResponse, schema: type[T]) -> T:
        if not completion.choices:
            raise LLMResponseError("empty_choices")
        choice = completion.choices[0]
        if choice.finish_reason == "length":
            raise LLMResponseError("truncated")
        if not choice.message.content:
            raise LLMResponseError("empty_content")
        try:
            return schema.model_validate_json(choice.message.content)
        except ValidationError:
            # from None: ValidationError құрамында input_value, яғни ықтимал PII бар.
            raise LLMResponseError("schema_mismatch") from None

    async def health(self) -> LLMHealth:
        started = time.monotonic()

        def elapsed() -> int:
            return round((time.monotonic() - started) * 1000)

        try:
            response = await self._http.get("/models")
        except httpx.HTTPError:
            return LLMHealth(reachable=False, latency_ms=elapsed(), error_code="connection_error")
        if response.status_code in (401, 403):
            return LLMHealth(reachable=False, latency_ms=elapsed(), error_code="unauthorized")
        if response.status_code >= 400:
            return LLMHealth(reachable=False, latency_ms=elapsed(), error_code=f"http_{response.status_code}")
        try:
            models = _ModelsResponse.model_validate_json(response.content)
        except ValidationError:
            return LLMHealth(reachable=False, latency_ms=elapsed(), error_code="malformed_api_response")

        entry = next((m for m in models.data if m.id == self._settings.llm_model), None)
        if entry is None:
            return LLMHealth(reachable=True, latency_ms=elapsed(), error_code="model_not_found")
        return LLMHealth(
            reachable=True,
            model=entry.id,
            loaded=entry.loaded,
            context_length=entry.context_length,
            latency_ms=elapsed(),
        )
