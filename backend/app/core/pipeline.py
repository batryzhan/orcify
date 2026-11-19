"""Оркестрация задачи: Smart Routing -> карточка в Orcify Jira -> исполнение
в домене -> события SSE.

Каждая задача получает карточку на доске ORC: агенты домена переносят её
по колонкам (К выполнению -> В работе -> Проверка/Готово) через in-process
MCP ``orcify_jira``, а снимок карточки уходит в SSE-событии — UI анимирует
рой агентов-курсоров по этим снимкам.

Ошибки LLM, MCP и рендера превращаются в событие ``failed`` (или в
деградированный результат), а не в HTTP 500.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from dataclasses import dataclass
from typing import Final
from uuid import UUID

from app.core.doc_engine import DocEngineError
from app.core.finance_pdf import FinancePdfError
from app.core.finance_service import FinanceAnalysisError, FinanceService
from app.core.hr_service import HrService
from app.core.jira_tracker import JiraTracker
from app.core.legal_service import LegalService
from app.core.llm_client import LLMResponseError, LLMUnavailableError
from app.core.logger import get_logger
from app.core.post_store import PostStore
from app.core.router import IntentRouter
from app.core.smm_service import PostRenderFailedError, SmmService
from app.mcp.manager import PiiLeakError
from app.schemas.finance import FinanceResult
from app.schemas.hr import HrResult
from app.schemas.intent import DomainEnum, IntentClassificationResult
from app.schemas.jira import (
    AttachmentKind,
    IssueAttachment,
    IssueCreate,
    IssuePriority,
    IssueStatus,
    IssueType,
    IssueUpdate,
)
from app.schemas.legal import LegalOutcome, LegalResult
from app.schemas.smm import PostResult
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

DOMAIN_LABEL: Final = {
    DomainEnum.LEGAL: "LEGAL",
    DomainEnum.FINANCE: "FINANCE",
    DomainEnum.SMM: "AWESOME POSTS",
    DomainEnum.HR: "PLAN",
}
DOMAIN_TYPE: Final = {
    DomainEnum.LEGAL: IssueType.TASK,
    DomainEnum.FINANCE: IssueType.TASK,
    DomainEnum.SMM: IssueType.STORY,
    DomainEnum.HR: IssueType.EPIC,
}
STATUS_TITLE: Final = {
    IssueStatus.TODO: "К выполнению",
    IssueStatus.IN_PROGRESS: "В работе",
    IssueStatus.REVIEW: "Проверка",
    IssueStatus.DONE: "Готово",
}
NEEDS_INPUT: Final = "NEEDS INPUT"


@dataclass
class _Ctx:
    tid: str
    task_id: UUID
    intent: IntentClassificationResult
    low: bool
    issue_key: str | None = None

    @property
    def label(self) -> str:
        return DOMAIN_LABEL[self.intent.domain]


class TaskPipeline:
    def __init__(
        self,
        router: IntentRouter,
        legal: LegalService,
        finance: FinanceService,
        smm: SmmService,
        hr: HrService,
        jira: JiraTracker,
        posts: PostStore,
    ) -> None:
        self._router = router
        self._legal = legal
        self._finance = finance
        self._smm = smm
        self._hr = hr
        self._jira = jira
        self._posts = posts

    async def run(self, task_id: UUID, request: TaskCreateRequest) -> AsyncIterator[ProgressEvent]:
        tid = str(task_id)
        stage = TaskStatus.CLASSIFYING_INTENT
        ctx: _Ctx | None = None
        failure: tuple[str, str] | None = None
        try:
            if request.domain is not None:
                # Окно интерфейса уже задаёт домен (Посты / Финансы / Договоры / Jira):
                # Этап 1 не нужен, сразу Scoped Execution. Smart Routing работает для
                # свободных запросов (Telegram-бот).
                yield ProgressEvent(
                    status=stage, progress=5, message=f"Домен задан окном: {request.domain.value}"
                )
                intent = IntentClassificationResult(
                    domain=request.domain, confidence=1.0, reasoning="Домен выбран в окне интерфейса."
                )
                low = False
                log.info("intent_preset", task_id=tid, domain=intent.domain)
            else:
                yield ProgressEvent(status=stage, progress=5, message="Router определяет бизнес-домен...")
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
            ctx = _Ctx(tid, task_id, intent, low)

            stage = TaskStatus.CREATING_JIRA_ISSUE
            issue = await self._jira.create(
                IssueCreate(
                    summary=_initial_summary(intent.domain, request),
                    description=f"Задача поставлена агентам Orcify. Домен: {intent.domain.value}.",
                    type=DOMAIN_TYPE[intent.domain],
                    priority=IssuePriority.MEDIUM,
                    labels=[ctx.label],
                    assignee="Router",
                    domain=intent.domain,
                    task_id=task_id,
                )
            )
            if issue is not None:
                ctx.issue_key = issue.key
                yield ProgressEvent(
                    status=stage,
                    progress=10,
                    domain=intent.domain,
                    message=f"Карточка {issue.key} создана в Orcify Jira",
                    issue=issue,
                )

            if intent.domain is DomainEnum.LEGAL:
                runner = self._run_legal(ctx, request.text)
            elif intent.domain is DomainEnum.FINANCE:
                runner = self._run_finance(ctx, request)
            elif intent.domain is DomainEnum.SMM:
                runner = self._run_smm(ctx, request)
            else:
                runner = self._run_hr(ctx, request.text)

            async for event in runner:
                stage = event.status
                yield event.model_copy(update={"domain": intent.domain})

        except LLMUnavailableError as exc:
            failure = (exc.code, "Локальная модель недоступна")
        except LLMResponseError as exc:
            failure = (exc.code, "Модель вернула ответ не по схеме")
        except DocEngineError as exc:
            failure = (exc.code, "Не удалось сформировать документ по шаблону")
        except FinanceAnalysisError as exc:
            failure = (exc.code, FINANCE_ERRORS.get(exc.code, "Локальный финансовый анализ недоступен"))
        except PostRenderFailedError as exc:
            failure = (exc.code, "Не удалось собрать пост на шаблоне")
        except FinancePdfError as exc:
            failure = (exc.code, "Не удалось собрать PDF-отчёт")
        except PiiLeakError:
            failure = ("pii_leak_blocked", "Вызов внешнего сервиса заблокирован: не удалось замаскировать PII")

        if failure is not None:
            code, message = failure
            log.error("task_failed", task_id=tid, stage=stage, error_code=code[:64])
            issue = None
            if ctx is not None:
                issue = await self._jira.update(
                    ctx.issue_key, IssueUpdate(status=IssueStatus.TODO, labels=[ctx.label, "ERROR"], assignee="Router")
                )
            yield ProgressEvent(
                status=TaskStatus.FAILED,
                progress=100,
                domain=ctx.intent.domain if ctx else None,
                error=ErrorInfo(code=code[:64], message=message),
                issue=issue,
            )

    # --- Orcify Jira -----------------------------------------------------------

    async def _move(self, ctx: _Ctx, progress: int, message: str, **changes: object) -> ProgressEvent | None:
        issue = await self._jira.update(ctx.issue_key, IssueUpdate.model_validate(changes))
        if issue is None:
            return None
        return ProgressEvent(status=TaskStatus.UPDATING_JIRA, progress=progress, message=message, issue=issue)

    @staticmethod
    def _moved(issue_key: str | None, status: IssueStatus, agent: str) -> str:
        return f"{issue_key or 'Карточка'} → «{STATUS_TITLE[status]}» · агент {agent}"

    def _done(self, ctx: _Ctx, message: str, **result: object) -> ProgressEvent:
        log.info("task_completed", task_id=ctx.tid, domain=ctx.intent.domain)
        return ProgressEvent(
            status=TaskStatus.COMPLETED,
            progress=100,
            message=message,
            result=TaskResult(intent=ctx.intent, low_confidence=ctx.low, issue_key=ctx.issue_key, **result),  # type: ignore[arg-type]
        )

    # --- Сценарий А: Legal ------------------------------------------------------

    async def _run_legal(self, ctx: _Ctx, text: str) -> AsyncIterator[ProgressEvent]:
        if ev := await self._move(ctx, 20, self._moved(ctx.issue_key, IssueStatus.IN_PROGRESS, "Lawyer"),
                                  status=IssueStatus.IN_PROGRESS, assignee="Lawyer"):
            yield ev
        yield ProgressEvent(
            status=TaskStatus.EXTRACTING_ENTITIES, progress=50, message="Lawyer извлекает реквизиты договора..."
        )
        extracted = await self._legal.extract(text)
        entities = extracted.data
        validation = self._legal.validate(entities)
        log.info(
            "entities_extracted",
            task_id=ctx.tid,
            latency_ms=extracted.stats.latency_ms,
            attempts=extracted.stats.attempts,
            missing_count=len(validation.missing_fields),
            invalid_count=len(validation.invalid_fields),
        )

        if validation.contract is None:
            fields = ", ".join([*validation.missing_fields, *validation.invalid_fields])
            if ev := await self._move(
                ctx, 90, self._moved(ctx.issue_key, IssueStatus.REVIEW, "Lawyer"),
                status=IssueStatus.REVIEW, labels=[ctx.label, NEEDS_INPUT], summary="Договор: нужны реквизиты",
                description=f"Не хватает или некорректны поля: {fields}. Заполните их в карточке результата.",
            ):
                yield ev
            yield self._done(
                ctx,
                "Не хватает или некорректны реквизиты — проверьте поля и сформируйте договор",
                legal=LegalResult(
                    outcome=LegalOutcome.NEEDS_INPUT,
                    entities=entities,
                    missing_fields=validation.missing_fields,
                    invalid_fields=validation.invalid_fields,
                ),
            )
            return

        yield ProgressEvent(status=TaskStatus.RENDERING_DOCX, progress=80, message="Формирование .docx по шаблону...")
        document = self._legal.render(validation.contract)
        scope = validation.contract.scope_of_work
        if ev := await self._move(
            ctx, 95, self._moved(ctx.issue_key, IssueStatus.DONE, "Lawyer"),
            status=IssueStatus.DONE, summary=f"Договор: {scope[:150]}",
            description="Договор сформирован по шаблону service_contract_kz.docx (Deterministic Core).",
            add_attachments=[IssueAttachment(kind=AttachmentKind.DOCUMENT, title=document.filename,
                                             url=document.download_url)],
        ):
            yield ev
        yield self._done(
            ctx,
            "Договор готов",
            legal=LegalResult(
                outcome=LegalOutcome.RENDERED,
                entities=entities,
                missing_fields=[],
                invalid_fields=[],
                document=document,
            ),
        )

    # --- Сценарий В: Finance ----------------------------------------------------

    async def _run_finance(self, ctx: _Ctx, request: TaskCreateRequest) -> AsyncIterator[ProgressEvent]:
        yield ProgressEvent(status=TaskStatus.ROUTING_FINANCE, progress=15, message="Подключён только local_finance MCP")
        if request.attachment is None:
            if ev := await self._move(ctx, 90, "Нужен CSV-файл — карточка ждёт вложения",
                                      labels=[ctx.label, NEEDS_INPUT], assignee="Analyst"):
                yield ev
            yield self._done(ctx, "Для финансового анализа прикрепите CSV-выписку")
            return

        if ev := await self._move(ctx, 25, self._moved(ctx.issue_key, IssueStatus.IN_PROGRESS, "Analyst"),
                                  status=IssueStatus.IN_PROGRESS, assignee="Analyst"):
            yield ev
        yield ProgressEvent(status=TaskStatus.ANALYZING_CSV, progress=50, message="Локальный расчёт агрегатов (pandas)...")
        metrics, mcp_latency = await self._finance.analyze(request.attachment.content, request.opening_balance)

        yield ProgressEvent(
            status=TaskStatus.GENERATING_REPORT,
            progress=75,
            message="Резюме по агрегатам (сырые строки в модель не передаются)...",
        )
        budgets = self._finance.check_budgets(metrics)
        report, report_error = None, None
        try:
            report = await self._finance.summarize(metrics, budgets)
        except (LLMUnavailableError, LLMResponseError) as exc:
            report_error = exc.code
        yield ProgressEvent(status=TaskStatus.RENDERING_PDF, progress=88, message="Сборка PDF-отчёта (локально)...")
        report_file = await self._finance.build_report(metrics, report, budgets)
        if ctx.issue_key:
            self._finance.attach_issue(report_file.report_id, ctx.issue_key)
        final = IssueStatus.DONE if report else IssueStatus.REVIEW
        if ev := await self._move(
            ctx, 95, self._moved(ctx.issue_key, final, "Analyst"),
            status=final,
            summary=f"Анализ выписки {metrics.period_start:%d.%m.%Y}–{metrics.period_end:%d.%m.%Y}",
            description=(report.headline if report else "Метрики посчитаны; резюме модели недоступно.")
            + f" Операций: {metrics.rows}, кассовых разрывов: {len(metrics.cash_gaps)}.",
            add_attachments=[IssueAttachment(kind=AttachmentKind.REPORT, title=report_file.filename,
                                             url=report_file.download_url)],
        ):
            yield ev
        log.info("finance_completed", task_id=ctx.tid, latency_ms=mcp_latency, degraded=report is None)
        yield self._done(
            ctx,
            "Отчёт готов" if report else "Метрики готовы; резюме модели недоступно",
            finance=FinanceResult(
                metrics=metrics,
                report=report,
                report_error_code=report_error,
                report_file=report_file,
                budget_checks=budgets,
                mcp_latency_ms=mcp_latency,
            ),
        )

    # --- Сценарий Б: SMM (Awesome Posts) ------------------------------------------

    async def _run_smm(self, ctx: _Ctx, request: TaskCreateRequest) -> AsyncIterator[ProgressEvent]:
        yield ProgressEvent(
            status=TaskStatus.ROUTING_SMM, progress=15, message="Подключены только Awesome Posts и Orcify Jira"
        )
        if ev := await self._move(ctx, 22, self._moved(ctx.issue_key, IssueStatus.IN_PROGRESS, "Copywriter"),
                                  status=IssueStatus.IN_PROGRESS, assignee="Copywriter"):
            yield ev
        yield ProgressEvent(status=TaskStatus.WRITING_COPY, progress=35, message="Copywriter пишет тексты поста (локально)...")
        content = await self._smm.write_copy(request.text, request.post_template)

        headline = f"{content.headline} {content.headline_accent}".strip()
        if ev := await self._move(ctx, 55, f"Designer собирает пост на шаблоне {content.template.value}",
                                  summary=f"Instagram-пост: {headline}"[:200], assignee="Designer"):
            yield ev
        yield ProgressEvent(status=TaskStatus.RENDERING_POST, progress=70, message="Рендер 1080×1350 на фоне шаблона...")
        post = await self._smm.render(content)

        tags = " ".join(h if h.startswith("#") else f"#{h}" for h in content.hashtags)
        if ev := await self._move(
            ctx, 95, self._moved(ctx.issue_key, IssueStatus.DONE, "Designer"),
            status=IssueStatus.DONE,
            description=f"{content.caption}\n\n{tags}".strip()[:4000],
            add_attachments=[IssueAttachment(kind=AttachmentKind.POST, title=f"Пост · {content.template.value}",
                                             url=post.image_url)],
        ):
            yield ev
        if ctx.issue_key:
            self._posts.attach_issue(post.post_id, ctx.issue_key)
        log.info("post_rendered", task_id=ctx.tid, latency_ms=post.render_ms, payload_hash=post.sha256)
        yield self._done(
            ctx,
            "Пост для Instagram готов",
            smm=PostResult(content=content, post=post, template_forced=request.post_template is not None),
        )

    # --- HR: планирование задач в Orcify Jira --------------------------------------

    async def _run_hr(self, ctx: _Ctx, text: str) -> AsyncIterator[ProgressEvent]:
        if ev := await self._move(ctx, 20, self._moved(ctx.issue_key, IssueStatus.IN_PROGRESS, "Planner"),
                                  status=IssueStatus.IN_PROGRESS, assignee="Planner"):
            yield ev
        yield ProgressEvent(status=TaskStatus.PLANNING_TASKS, progress=35, message="Planner раскладывает задачу на шаги...")
        plan = await self._hr.plan(text)
        if ev := await self._move(ctx, 45, f"Эпик: {plan.epic}"[:200], summary=plan.epic):
            yield ev

        keys: list[str] = []
        total = len(plan.issues)
        for index, item in enumerate(plan.issues):
            child = await self._jira.create(
                IssueCreate(
                    summary=item.summary,
                    description=item.description,
                    type=item.type if item.type is not IssueType.EPIC else IssueType.TASK,
                    priority=item.priority,
                    story_points=item.story_points,
                    labels=[ctx.label],
                    assignee=item.assignee_role or None,
                    domain=DomainEnum.HR,
                    task_id=ctx.task_id,
                    parent_key=ctx.issue_key,
                )
            )
            if child is None:
                continue
            keys.append(child.key)
            yield ProgressEvent(
                status=TaskStatus.CREATING_JIRA_ISSUE,
                progress=50 + round(40 * (index + 1) / total),
                message=f"Planner завёл {child.key}: {child.summary}"[:300],
                issue=child,
            )
        yield self._done(ctx, f"План готов: {len(keys)} задач на доске", hr=HrResult(plan=plan, issue_keys=keys))


def _initial_summary(domain: DomainEnum, request: TaskCreateRequest) -> str:
    if domain is DomainEnum.FINANCE:
        return f"Анализ выписки {request.attachment.filename}" if request.attachment else "Финансовый анализ"
    return {
        DomainEnum.LEGAL: "Договор оказания услуг",
        DomainEnum.SMM: "Instagram-пост",
        DomainEnum.HR: "План задач",
    }[domain]


def _routing_text(request: TaskCreateRequest) -> str:
    if request.attachment is None:
        return request.text
    # В классификатор уходит только имя файла, не содержимое.
    return f"{request.text}\n\n[Приложен CSV-файл: {request.attachment.filename}]"

