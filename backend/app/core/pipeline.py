"""Оркестрация задачи: Smart Routing -> исполнение в домене -> события SSE.

Ошибки LLM и рендера превращаются в событие ``failed``, а не в HTTP 500.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from uuid import UUID

from app.core.doc_engine import DocEngineError
from app.core.legal_service import LegalService
from app.core.llm_client import LLMResponseError, LLMUnavailableError
from app.core.logger import get_logger
from app.core.router import IntentRouter
from app.schemas.intent import DomainEnum, IntentClassificationResult
from app.schemas.legal import LegalOutcome, LegalResult
from app.schemas.sse import ErrorInfo, ProgressEvent, TaskResult, TaskStatus

log = get_logger(__name__)


class TaskPipeline:
    def __init__(self, router: IntentRouter, legal: LegalService) -> None:
        self._router = router
        self._legal = legal

    async def run(self, task_id: UUID, text: str) -> AsyncIterator[ProgressEvent]:
        tid = str(task_id)
        stage = TaskStatus.CLASSIFYING_INTENT
        try:
            yield ProgressEvent(status=stage, progress=5, message="Определение бизнес-домена...")
            routed = await self._router.classify(text)
            intent = routed.data
            low_confidence = not self._router.is_confident(intent)
            log.info(
                "intent_classified",
                task_id=tid,
                domain=intent.domain,
                confidence=intent.confidence,
                low_confidence=low_confidence,
                latency_ms=routed.stats.latency_ms,
                attempts=routed.stats.attempts,
            )

            if intent.domain is not DomainEnum.LEGAL:
                yield ProgressEvent(
                    status=TaskStatus.COMPLETED,
                    progress=100,
                    message=f"Домен {intent.domain.value} определён; его пайплайн пока не подключён",
                    result=TaskResult(intent=intent, low_confidence=low_confidence),
                )
                return

            stage = TaskStatus.EXTRACTING_ENTITIES
            async for event in self._run_legal(tid, text, intent, low_confidence):
                stage = event.status
                yield event

        except LLMUnavailableError as exc:
            log.error("task_failed", task_id=tid, stage=stage, error_code=exc.code)
            yield _failed(exc.code, "Локальная модель недоступна")
        except LLMResponseError as exc:
            log.error("task_failed", task_id=tid, stage=stage, error_code=exc.code)
            yield _failed(exc.code, "Модель вернула ответ не по схеме")
        except DocEngineError as exc:
            log.error("task_failed", task_id=tid, stage=stage, error_code=exc.code)
            yield _failed(exc.code, "Не удалось сформировать документ по шаблону")

    async def _run_legal(
        self, tid: str, text: str, intent: IntentClassificationResult, low_confidence: bool
    ) -> AsyncIterator[ProgressEvent]:
        yield ProgressEvent(
            status=TaskStatus.EXTRACTING_ENTITIES, progress=50, message="Извлечение реквизитов договора..."
        )
        extracted = await self._legal.extract(text)
        entities = extracted.data
        validation = self._legal.validate(entities)
        log.info(
            "entities_extracted",
            task_id=tid,
            latency_ms=extracted.stats.latency_ms,
            attempts=extracted.stats.attempts,
            missing_count=len(validation.missing_fields),
            invalid_count=len(validation.invalid_fields),
        )

        if validation.contract is None:
            yield ProgressEvent(
                status=TaskStatus.COMPLETED,
                progress=100,
                message="Не хватает или некорректны реквизиты — проверьте поля и сформируйте договор",
                result=TaskResult(
                    intent=intent,
                    low_confidence=low_confidence,
                    legal=LegalResult(
                        outcome=LegalOutcome.NEEDS_INPUT,
                        entities=entities,
                        missing_fields=validation.missing_fields,
                        invalid_fields=validation.invalid_fields,
                    ),
                ),
            )
            return

        yield ProgressEvent(
            status=TaskStatus.RENDERING_DOCX, progress=85, message="Формирование .docx по шаблону..."
        )
        document = self._legal.render(validation.contract)
        log.info("task_completed", task_id=tid, outcome=LegalOutcome.RENDERED, document_id=str(document.document_id))
        yield ProgressEvent(
            status=TaskStatus.COMPLETED,
            progress=100,
            message="Договор готов",
            result=TaskResult(
                intent=intent,
                low_confidence=low_confidence,
                legal=LegalResult(
                    outcome=LegalOutcome.RENDERED,
                    entities=entities,
                    missing_fields=[],
                    invalid_fields=[],
                    document=document,
                ),
            ),
        )


def _failed(code: str, message: str) -> ProgressEvent:
    return ProgressEvent(status=TaskStatus.FAILED, progress=100, error=ErrorInfo(code=code, message=message))
