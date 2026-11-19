"""Telegram-бот Orcify — канал автоматизации (замена n8n).

Сценарий как воркфлоу n8n, но без внешнего оркестратора:
``Telegram Trigger -> Smart Router (Gemma 4) -> агент домена -> Orcify Jira -> ответ в чат``.

* Пишете боту текст -> бот запускает тот же пайплайн, что и UI, показывает ход
  работы (редактирует одно сообщение) и присылает результат: PNG-пост, отчёт,
  договор или список задач. Карточка появляется на доске Orcify Jira.
* Присылаете CSV-документ (можно с подписью) -> локальный финансовый анализ.
* Команды: /start, /help, /board.

Приватность: Telegram — облачный сервис. Бот отвечает только в тот чат, откуда
пришла задача, и ничего не отправляет сам; из UI пост уходит в Telegram только
по явной кнопке. LLM, трекер и рендер по-прежнему работают локально.
Токен бота живёт в URL запросов, поэтому URL никогда не логируются
(``httpx`` переведён на уровень WARNING в ``configure_logging``).
"""

from __future__ import annotations

import asyncio
import json
import time
from collections.abc import Coroutine
from pathlib import Path
from typing import Any, Final, TypeVar
from uuid import uuid4

import httpx
from pydantic import BaseModel, JsonValue, TypeAdapter, ValidationError

from app.config import Settings
from app.core.document_store import DocumentStore
from app.core.finance_store import ReportStore
from app.core.jira_store import COLUMNS, JiraStore
from app.core.logger import get_logger
from app.core.pipeline import TaskPipeline
from app.core.post_store import PostStore
from app.schemas.legal import LegalOutcome
from app.schemas.sse import ProgressEvent, TaskResult, TaskStatus
from app.schemas.tasks import TaskAttachment, TaskCreateRequest
from app.schemas.telegram import TelegramStatus, TgFile, TgMessage, TgUpdate, TgUser

log = get_logger(__name__)
T = TypeVar("T")

CAPTION_LIMIT: Final = 1024
TEXT_LIMIT: Final = 4000
POLL_TIMEOUT_S: Final = 25
DEFAULT_CSV_TASK: Final = "Проанализируй выписку: кассовые разрывы, крупнейшие расходы и что с этим делать."

FIELD_LABEL: Final = {
    "client_name": "наименование клиента",
    "bin_iin": "ИИН/БИН",
    "contract_amount": "сумма",
    "currency": "валюта",
    "deadline_date": "срок исполнения",
    "scope_of_work": "предмет договора",
}

HELP_TEXT: Final = (
    "Я Orcify — локальные ИИ-агенты для бизнеса.\n\n"
    "Просто напишите задачу:\n"
    "• «Сделай пост для Instagram: знакомство с командой Orcify» — пришлю готовую картинку\n"
    "• «Составь план онбординга нового дизайнера» — заведу задачи в Orcify Jira\n"
    "• перешлите переписку с клиентом — подготовлю договор .docx\n"
    "• пришлите CSV-выписку — посчитаю кассовые разрывы и расходы\n\n"
    "Команды: /board — доска задач, /help — эта справка.\n"
    "Модель работает локально (Gemma 4); каждая задача появляется на доске Orcify Jira."
)


class _ApiResponse(BaseModel):
    ok: bool
    result: JsonValue = None
    error_code: int | None = None
    description: str | None = None


class ChatRegistry:
    """Чаты, которые написали боту (только id; нужны, чтобы отправить пост из UI)."""

    def __init__(self, path: Path | None) -> None:
        self._path = path
        self._ids: set[int] = set()
        if path is not None and path.is_file():
            try:
                self._ids = set(TypeAdapter(list[int]).validate_json(path.read_text(encoding="utf-8")))
            except (OSError, ValidationError):
                self._ids = set()

    def add(self, chat_id: int) -> None:
        if chat_id in self._ids:
            return
        self._ids.add(chat_id)
        if self._path is not None:
            self._path.parent.mkdir(parents=True, exist_ok=True)
            self._path.write_text(json.dumps(sorted(self._ids)), encoding="utf-8")

    @property
    def ids(self) -> list[int]:
        return sorted(self._ids)


class TelegramBot:
    def __init__(
        self,
        settings: Settings,
        http: httpx.AsyncClient,
        pipeline: TaskPipeline,
        posts: PostStore,
        documents: DocumentStore,
        jira: JiraStore,
        reports: ReportStore,
    ) -> None:
        token = settings.telegram_bot_token.get_secret_value().strip()
        self._base = f"{settings.telegram_api_base}/bot{token}"
        self._file_base = f"{settings.telegram_api_base}/file/bot{token}"
        self._http = http
        self._pipeline = pipeline
        self._posts = posts
        self._documents = documents
        self._jira = jira
        self._reports = reports
        self._max_file = settings.telegram_max_file_bytes
        self._chats = ChatRegistry(settings.telegram_chats_path)
        self._status = TelegramStatus(configured=bool(token), polling=False)
        self._slots = asyncio.Semaphore(2)
        self._tasks: set[asyncio.Task[None]] = set()

    @property
    def configured(self) -> bool:
        return self._status.configured

    def status(self) -> TelegramStatus:
        return self._status.model_copy(update={"linked_chats": len(self._chats.ids)})

    # --- Bot API ---------------------------------------------------------------

    async def _call(
        self,
        method: str,
        adapter: TypeAdapter[T],
        *,
        payload: dict[str, JsonValue] | None = None,
        files: dict[str, tuple[str, bytes, str]] | None = None,
        timeout: float | None = None,
    ) -> T | None:
        try:
            if files is not None:
                data = {k: str(v) for k, v in (payload or {}).items() if v is not None}
                response = await self._http.post(f"{self._base}/{method}", data=data, files=files, timeout=timeout)
            else:
                response = await self._http.post(f"{self._base}/{method}", json=payload or {}, timeout=timeout)
        except httpx.HTTPError as exc:
            self._status.last_error = type(exc).__name__
            log.warning("telegram_api_failed", stage=method, error_type=type(exc).__name__)
            return None
        try:
            body = _ApiResponse.model_validate_json(response.content)
        except ValidationError:
            self._status.last_error = f"http_{response.status_code}"
            return None
        if not body.ok:
            # «message is not modified» при редактировании — штатная ситуация, не ошибка канала.
            if method != "editMessageText":
                self._status.last_error = f"api_{body.error_code or response.status_code}"
                log.warning("telegram_api_failed", stage=method, http_status=body.error_code or response.status_code)
            return None
        try:
            return adapter.validate_python(body.result)
        except ValidationError:
            return None

    async def get_me(self) -> TgUser | None:
        me = await self._call("getMe", TypeAdapter(TgUser))
        if me is not None:
            self._status.bot_username = me.username
            self._status.bot_name = me.first_name
        return me

    async def send_message(self, chat_id: int, text: str) -> TgMessage | None:
        return await self._call(
            "sendMessage", TypeAdapter(TgMessage), payload={"chat_id": chat_id, "text": text[:TEXT_LIMIT]}
        )

    async def edit_message(self, chat_id: int, message_id: int, text: str) -> None:
        await self._call(
            "editMessageText",
            TypeAdapter(JsonValue),
            payload={"chat_id": chat_id, "message_id": message_id, "text": text[:TEXT_LIMIT]},
        )

    async def send_photo(self, chat_id: int, png: bytes, caption: str) -> bool:
        sent = await self._call(
            "sendPhoto",
            TypeAdapter(TgMessage),
            payload={"chat_id": chat_id, "caption": caption[:CAPTION_LIMIT]},
            files={"photo": ("orcify_post.png", png, "image/png")},
            timeout=60,
        )
        return sent is not None

    async def send_document(self, chat_id: int, filename: str, content: bytes, media_type: str, caption: str) -> bool:
        sent = await self._call(
            "sendDocument",
            TypeAdapter(TgMessage),
            payload={"chat_id": chat_id, "caption": caption[:CAPTION_LIMIT]},
            files={"document": (filename, content, media_type)},
            timeout=60,
        )
        return sent is not None

    async def _download(self, file_id: str) -> bytes | None:
        meta = await self._call("getFile", TypeAdapter(TgFile), payload={"file_id": file_id})
        if meta is None or meta.file_path is None or (meta.file_size or 0) > self._max_file:
            return None
        try:
            response = await self._http.get(f"{self._file_base}/{meta.file_path}", timeout=60)
        except httpx.HTTPError:
            return None
        return response.content if response.status_code == 200 and len(response.content) <= self._max_file else None

    # --- polling ---------------------------------------------------------------

    async def run_polling(self) -> None:
        """Long polling getUpdates. Работает, пока задача не отменена в lifespan."""
        if not self.configured:
            return
        await self.get_me()
        offset: int | None = None
        backoff = 1.0
        self._status.polling = True
        log.info("telegram_polling_started", status="polling")
        try:
            while True:
                payload: dict[str, JsonValue] = {"timeout": POLL_TIMEOUT_S, "allowed_updates": ["message"]}
                if offset is not None:
                    payload["offset"] = offset
                updates = await self._call(
                    "getUpdates", TypeAdapter(list[TgUpdate]), payload=payload, timeout=POLL_TIMEOUT_S + 10
                )
                if updates is None:
                    await asyncio.sleep(backoff)
                    backoff = min(backoff * 2, 60.0)
                    continue
                backoff = 1.0
                for update in updates:
                    offset = update.update_id + 1
                    if update.message is not None:
                        self._spawn(self.handle_message(update.message))
        finally:
            self._status.polling = False
            for task in self._tasks:
                task.cancel()

    def _spawn(self, coro: Coroutine[Any, Any, None]) -> None:
        task = asyncio.create_task(coro)
        self._tasks.add(task)
        task.add_done_callback(self._tasks.discard)

    # --- обработка сообщений ------------------------------------------------------

    async def handle_message(self, message: TgMessage) -> None:
        chat_id = message.chat.id
        text = (message.text or message.caption or "").strip()
        self._status.handled_messages += 1
        self._chats.add(chat_id)

        command = text.split(maxsplit=1)[0].split("@")[0].lower() if text.startswith("/") else None
        if command in ("/start", "/help"):
            await self.send_message(chat_id, HELP_TEXT)
            return
        if command == "/board":
            await self.send_message(chat_id, self._board_text())
            return

        attachment: TaskAttachment | None = None
        if message.document is not None:
            attachment = await self._csv_attachment(chat_id, message)
            if attachment is None:
                return
        if not text and attachment is None:
            return
        try:
            request = TaskCreateRequest(text=text or DEFAULT_CSV_TASK, attachment=attachment)
        except ValidationError:
            await self.send_message(chat_id, "Слишком длинное сообщение — сократите задачу.")
            return
        async with self._slots:
            await self._run_task(chat_id, request)

    async def _csv_attachment(self, chat_id: int, message: TgMessage) -> TaskAttachment | None:
        doc = message.document
        assert doc is not None
        name = doc.file_name or "statement.csv"
        if not name.lower().endswith(".csv"):
            await self.send_message(chat_id, "Пока я понимаю только CSV-выписки. Пришлите файл .csv.")
            return None
        raw = await self._download(doc.file_id)
        if raw is None:
            await self.send_message(chat_id, "Не удалось скачать файл (лимит — 5 МБ).")
            return None
        for encoding in ("utf-8-sig", "cp1251"):
            try:
                return TaskAttachment(filename=name[:200], content=raw.decode(encoding))
            except (UnicodeDecodeError, ValidationError):
                continue
        await self.send_message(chat_id, "Файл не читается как текстовый CSV.")
        return None

    async def _run_task(self, chat_id: int, request: TaskCreateRequest) -> None:
        started = time.monotonic()
        header = "⏳ Orcify принял задачу — агенты работают локально"
        status_message = await self.send_message(chat_id, header)
        lines: list[str] = []
        final: ProgressEvent | None = None
        issue_key: str | None = None

        async for event in self._pipeline.run(uuid4(), request):
            if event.issue is not None and issue_key is None:
                issue_key = event.issue.key
            if event.status in (TaskStatus.COMPLETED, TaskStatus.FAILED):
                final = event
                break
            if event.message:
                lines.append(f"• {event.message}")
                if status_message is not None:
                    await self.edit_message(chat_id, status_message.message_id, "\n".join([header, *lines[-7:]]))

        seconds = time.monotonic() - started
        if status_message is not None:
            done = "✅ Готово" if final is not None and final.status is TaskStatus.COMPLETED else "⚠️ Остановлено"
            await self.edit_message(
                chat_id, status_message.message_id, "\n".join([f"{done} за {seconds:.1f} с", *lines[-7:]])
            )
        if final is None:
            return
        if final.status is TaskStatus.FAILED:
            await self.send_message(chat_id, f"⚠️ {final.error.message if final.error else 'Ошибка'}")
            log.info("telegram_task", stage="task", status=final.status, latency_ms=round(seconds * 1000))
            return

        footer = f"\n\n📋 Карточка {issue_key} на доске Orcify Jira" if issue_key else ""
        await self._deliver(chat_id, final, footer)
        self._status.completed_runs += 1
        log.info("telegram_task", stage="task", status=final.status, latency_ms=round(seconds * 1000))

    async def _deliver(self, chat_id: int, event: ProgressEvent, footer: str) -> None:
        result: TaskResult | None = event.result
        if result is None:
            await self.send_message(chat_id, (event.message or "Готово") + footer)
            return
        if result.smm is not None:
            png_path = self._posts.png_path(result.smm.post.post_id)
            content = result.smm.content
            tags = " ".join(h if h.startswith("#") else f"#{h}" for h in content.hashtags)
            caption = f"{content.caption}\n\n{tags}".strip()
            if png_path is not None:
                await self.send_photo(chat_id, png_path.read_bytes(), caption[: CAPTION_LIMIT - len(footer)] + footer)
            else:
                await self.send_message(chat_id, caption + footer)
            return
        if result.finance is not None:
            await self.send_message(chat_id, _finance_text(result) + footer)
            file = result.finance.report_file
            path = self._reports.pdf_path(file.report_id) if file else None
            if file is not None and path is not None:
                await self.send_document(chat_id, file.filename, path.read_bytes(), "application/pdf", "Полный отчёт (PDF)")
            return
        if result.legal is not None:
            legal = result.legal
            if legal.outcome is LegalOutcome.RENDERED and legal.document is not None:
                stored = self._documents.get(legal.document.document_id)
                if stored is not None:
                    await self.send_document(
                        chat_id, legal.document.filename, stored.content, stored.media_type, "Договор готов" + footer
                    )
                    return
            missing = [FIELD_LABEL.get(f, f) for f in [*legal.missing_fields, *legal.invalid_fields]]
            await self.send_message(
                chat_id, "Для договора не хватает или некорректны: " + ", ".join(missing) + ". Допишите и пришлите снова." + footer
            )
            return
        if result.hr is not None:
            items = [f"• {key} — {issue.summary}" for key, issue in zip(result.hr.issue_keys, result.hr.plan.issues)]
            await self.send_message(chat_id, f"🗂 {result.hr.plan.epic}\n\n" + "\n".join(items) + footer)
            return
        await self.send_message(chat_id, (event.message or "Готово") + footer)

    def _board_text(self) -> str:
        board = self._jira.board()
        parts = [f"📋 Orcify Jira · {board.project_key}"]
        for column in COLUMNS:
            issues = [i for i in board.issues if i.status == column.status]
            parts.append(f"\n{column.title} ({len(issues)})")
            parts += [f"• {i.key} {i.summary}" for i in issues[:5]]
        return "\n".join(parts)

    # --- отправка из UI -----------------------------------------------------------

    async def send_report(self, report_id: str) -> int:
        """Явное действие пользователя в окне «Финансы»: отправить PDF-отчёт во все чаты бота."""
        record = self._reports.get(report_id)
        path = self._reports.pdf_path(report_id)
        if record is None or path is None:
            return 0
        caption = (
            f"📊 {record.headline or 'Финансовая сводка'}\n"
            f"Период: {record.period_start:%d.%m.%Y} — {record.period_end:%d.%m.%Y}"
        )
        pdf = path.read_bytes()
        sent = 0
        for chat_id in self._chats.ids:
            sent += await self.send_document(chat_id, record.file.filename, pdf, "application/pdf", caption)
        log.info("telegram_report_sent", stage="send_report", status="sent" if sent else "none",
                 payload_hash=record.file.sha256)
        return sent

    async def send_post(self, post_id: str) -> int:
        """Явное действие пользователя в UI: отправить готовый пост во все чаты бота."""
        record = self._posts.get(post_id)
        png_path = self._posts.png_path(post_id)
        if record is None or png_path is None:
            return 0
        tags = " ".join(h if h.startswith("#") else f"#{h}" for h in record.content.hashtags)
        caption = f"{record.content.caption}\n\n{tags}".strip()
        png = png_path.read_bytes()
        sent = 0
        for chat_id in self._chats.ids:
            sent += await self.send_photo(chat_id, png, caption)
        log.info("telegram_post_sent", stage="send_post", status="sent" if sent else "none", payload_hash=record.post.sha256)
        return sent


def _finance_text(result: TaskResult) -> str:
    finance = result.finance
    assert finance is not None
    m = finance.metrics

    def money(value: float) -> str:
        return f"{value:,.0f}".replace(",", " ") + " ₸"

    lines = [
        f"📊 {finance.report.headline if finance.report else 'Финансовая сводка'}",
        f"Период: {m.period_start:%d.%m.%Y} — {m.period_end:%d.%m.%Y}, операций: {m.rows}",
        f"Поступления: {money(m.total_income)} · Расходы: {money(m.total_expense)}",
        f"Чистый поток: {money(m.net)} · Остаток: {money(m.closing_balance)}",
    ]
    if m.cash_gaps:
        lines.append(f"Кассовых разрывов: {len(m.cash_gaps)}")
    if finance.report:
        lines += ["", "Выводы:", *[f"• {x}" for x in finance.report.key_findings[:4]]]
        lines += ["", "Рекомендации:", *[f"{i}. {x}" for i, x in enumerate(finance.report.recommendations[:4], 1)]]
    return "\n".join(lines)
