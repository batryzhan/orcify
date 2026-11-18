"""Оркестрация задачи: Smart Routing -> исполнение в домене -> события SSE.

Ошибки LLM, MCP и рендера превращаются в событие ``failed`` (или в
деградированный результат), а не в HTTP 500.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from uuid import UUID

from app.core.doc_engine import DocEngineError
from app.core.finance_service import FinanceAnalysisError, FinanceService
from app.core.legal_service import LegalService
from app.core.llm_client import LLMResponseError, LLMUnavailableError
from app.core.logger import get_logger
from app.core.router import IntentRouter
from app.core.smm_service import SmmService
from app.mcp.manager import PiiLeakError
from app.schemas.finance import FinanceResult
from app.schemas.intent import DomainEnum, IntentClassificationResult
from app.schemas.legal import LegalOutcome, LegalResult
from app.schemas.smm import SmmResult
from app.schemas.sse import ErrorInfo, ProgressEvent, TaskResult, TaskStatus
from app.schemas.tasks import TaskCreateRequest

log = get_logger(__name__)

FINANCE_ERRORS = {
    "tool_error:date_column_not_found": "В CSV не найдена колонка с датой операции",
    "tool_error:amount_column_not_found": "В CSV не найдена колонка суммы (или приход/расход)",
    "tool_error:unreadable_csv": "Файл не читается как CSV",
    "tool_error:no_valid_rows": "В файле нет строк с корректной датой и суммой",
    "tool_error:too_many_rows": "Слишком большой файл (больше 200 000 строк)",
    "not_configured": "Локальный финансовый MCP-сервер отключён",
}


class TaskPipeline:
    def __init__(self, router: IntentRouter, legal: LegalService, finance: FinanceService, smm: SmmService) -> None:
        self._router = router
        self._legal = legal
        self._finance = finance
        self._smm = smm

    async def run(self, task_id: UUID, request: TaskCreateRequest) -> AsyncIterator[ProgressEvent]:
        tid = str(task_id)
        stage = TaskStatus.CLASSIFYING_INTENT
        try:
            yield ProgressEvent(status=stage, progress=5, message="Определение бизнес-домена...")
            routed = await self._router.classify(_routing_text(request))
            intent = routed.data
            low = not self._router.is_confident(intent)
            log.info(
                "intent_classified",
                task_id=tid,
                domain=intent.domain,
                confidence=intent.confidence,
                low_confidence=low,
                latency_ms=routed.stats.latency_ms,
                attempts=routed.stats.attempts,
            )

            if intent.domain is DomainEnum.LEGAL:
                runner = self._run_legal(tid, request.text, intent, low)
            elif intent.domain is DomainEnum.FINANCE:
                runner = self._run_finance(tid, request, intent, low)
            elif intent.domain is DomainEnum.SMM:
                runner = self._run_smm(tid, request.text, intent, low)
            else:
                yield ProgressEvent(
                    domain=intent.domain,
                    status=TaskStatus.COMPLETED,
                    progress=100,
                    message=f"Домен {intent.domain.value} определён; его пайплайн пока не подключён",
                    result=TaskResult(intent=intent, low_confidence=low),
                )
                return

            async for event in runner:
                stage = event.status
                yield event.model_copy(update={"domain": intent.domain})

        except LLMUnavailableError as exc:
            log.error("task_failed", task_id=tid, stage=stage, error_code=exc.code)
            yield _failed(exc.code, "Локальная модель недоступна")
        except LLMResponseError as exc:
            log.error("task_failed", task_id=tid, stage=stage, error_code=exc.code)
            yield _failed(exc.code, "Модель вернула ответ не по схеме")
        except DocEngineError as exc:
            log.error("task_failed", task_id=tid, stage=stage, error_code=exc.code)
            yield _failed(exc.code, "Не удалось сформировать документ по шаблону")
        except FinanceAnalysisError as exc:
            log.error("task_failed", task_id=tid, stage=stage, error_code=exc.code[:64])
            yield _failed(exc.code, FINANCE_ERRORS.get(exc.code, "Локальный финансовый анализ недоступен"))
        except PiiLeakError:
            log.error("task_failed", task_id=tid, stage=stage, error_code="pii_leak_blocked")
            yield _failed("pii_leak_blocked", "Вызов внешнего сервиса заблокирован: не удалось замаскировать PII")

    # --- Сценарий А: Legal ------------------------------------------------------

    async def _run_legal(
        self, tid: str, text: str, intent: IntentClassificationResult, low: bool
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
                    low_confidence=low,
                    legal=LegalResult(
                        outcome=LegalOutcome.NEEDS_INPUT,
                        entities=entities,
                        missing_fields=validation.missing_fields,
                        invalid_fields=validation.invalid_fields,
                    ),
                ),
            )
            return

        yield ProgressEvent(status=TaskStatus.RENDERING_DOCX, progress=85, message="Формирование .docx по шаблону...")
        document = self._legal.render(validation.contract)
        log.info("task_completed", task_id=tid, outcome=LegalOutcome.RENDERED, document_id=str(document.document_id))
        yield ProgressEvent(
            status=TaskStatus.COMPLETED,
            progress=100,
            message="Договор готов",
            result=TaskResult(
                intent=intent,
                low_confidence=low,
                legal=LegalResult(
                    outcome=LegalOutcome.RENDERED,
                    entities=entities,
                    missing_fields=[],
                    invalid_fields=[],
                    document=document,
                ),
            ),
        )

    # --- Сценарий В: Finance ----------------------------------------------------

    async def _run_finance(
        self, tid: str, request: TaskCreateRequest, intent: IntentClassificationResult, low: bool
    ) -> AsyncIterator[ProgressEvent]:
        yield ProgressEvent(
            status=TaskStatus.ROUTING_FINANCE, progress=15, message="Подключён только local_finance MCP"
        )
        if request.attachment is None:
            yield ProgressEvent(
                status=TaskStatus.COMPLETED,
                progress=100,
                message="Для финансового анализа прикрепите CSV-выписку",
                result=TaskResult(intent=intent, low_confidence=low),
            )
            return

        yield ProgressEvent(
            status=TaskStatus.ANALYZING_CSV, progress=50, message="Локальный расчёт агрегатов (pandas)..."
        )
        metrics, mcp_latency = await self._finance.analyze(request.attachment.content, request.opening_balance)

        yield ProgressEvent(
            status=TaskStatus.GENERATING_REPORT,
            progress=85,
            message="Резюме по агрегатам (сырые строки в модель не передаются)...",
        )
        report, report_error = None, None
        try:
            report = await self._finance.summarize(metrics)
        except (LLMUnavailableError, LLMResponseError) as exc:
            report_error = exc.code
        document = self._finance.store_report(metrics, report)
        log.info("task_completed", task_id=tid, latency_ms=mcp_latency, degraded=report is None)
        yield ProgressEvent(
            status=TaskStatus.COMPLETED,
            progress=100,
            message="Отчёт готов" if report else "Метрики готовы; резюме модели недоступно",
            result=TaskResult(
                intent=intent,
                low_confidence=low,
                finance=FinanceResult(
                    metrics=metrics,
                    report=report,
                    report_error_code=report_error,
                    document=document,
                    mcp_latency_ms=mcp_latency,
                ),
            ),
        )

    # --- Сценарий Б: SMM --------------------------------------------------------

    async def _run_smm(
        self, tid: str, text: str, intent: IntentClassificationResult, low: bool
    ) -> AsyncIterator[ProgressEvent]:
        yield ProgressEvent(
            status=TaskStatus.ROUTING_SMM, progress=10, message="Подключены только Higgsfield и Atlassian MCP"
        )
        yield ProgressEvent(status=TaskStatus.ANALYZING, progress=20, message="Сценарий и раскадровка (локально)...")
        script = await self._smm.write_script(text)

        yield ProgressEvent(status=TaskStatus.ANONYMIZING_PII, progress=35, message="Маскирование персональных данных...")
        session, external_prompt, report = await self._smm.anonymize(text, script)
        try:
            yield ProgressEvent(
                status=TaskStatus.GENERATING_VIDEO,
                progress=55,
                message=f"Генерация видео через Higgsfield MCP (замаскировано сущностей: {report.entities_total})...",
                anonymization=report,
            )
            video = await self._smm.generate_video(script, session)
            storyboard = self._smm.store_storyboard(script, video)

            yield ProgressEvent(
                status=TaskStatus.CREATING_JIRA_ISSUE, progress=85, message="Задача в Jira через Atlassian MCP..."
            )
            tracker = await self._smm.create_issue(script, video, session)
        finally:
            # Таблица соответствия уничтожается сразу после последнего внешнего вызова.
            session.clear()

        log.info("task_completed", task_id=tid, degraded=video.status.value == "storyboard", outcome=tracker.status)
        yield ProgressEvent(
            status=TaskStatus.COMPLETED,
            progress=100,
            message="Видео готово" if video.url else "Сценарий и раскадровка готовы (видеосервис недоступен)",
            anonymization=report,
            result=TaskResult(
                intent=intent,
                low_confidence=low,
                smm=SmmResult(
                    script=script,
                    external_prompt=external_prompt,
                    anonymization=report,
                    video=video,
                    tracker=tracker,
                    storyboard=storyboard,
                ),
            ),
        )


def _routing_text(request: TaskCreateRequest) -> str:
    if request.attachment is None:
        return request.text
    # В классификатор уходит только имя файла, не содержимое.
    return f"{request.text}\n\n[Приложен CSV-файл: {request.attachment.filename}]"


def _failed(code: str, message: str) -> ProgressEvent:
    return ProgressEvent(status=TaskStatus.FAILED, progress=100, error=ErrorInfo(code=code[:64], message=message))
