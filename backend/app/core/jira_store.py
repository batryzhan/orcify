"""Хранилище Orcify Jira: локальная доска задач в JSON-файле (``backend/var``).

Это продуктовые данные трекера, а не логи: файл не покидает устройство и
не коммитится в git. Пайплайны пишут в описание задачи только краткие
итоги (домен, ссылки на артефакты), без сырого текста запроса.
"""

from __future__ import annotations

import json
import threading
from datetime import UTC, datetime
from pathlib import Path
from uuid import UUID

from pydantic import BaseModel, ValidationError

from app.core.logger import get_logger
from app.schemas.jira import (
    BoardColumn,
    IssueCreate,
    IssueStatus,
    IssueUpdate,
    JiraBoard,
    JiraIssue,
)

log = get_logger(__name__)

COLUMNS: tuple[BoardColumn, ...] = (
    BoardColumn(status=IssueStatus.TODO, title="К выполнению"),
    BoardColumn(status=IssueStatus.IN_PROGRESS, title="В работе"),
    BoardColumn(status=IssueStatus.REVIEW, title="Проверка"),
    BoardColumn(status=IssueStatus.DONE, title="Готово"),
)


class IssueNotFoundError(LookupError):
    pass


class _BoardFile(BaseModel):
    next_number: int
    issues: list[JiraIssue]


def _now() -> datetime:
    return datetime.now(UTC)


class JiraStore:
    def __init__(
        self,
        path: Path | None,
        *,
        project_key: str = "ORC",
        project_name: str = "Orcify",
    ) -> None:
        self._path = path
        self._project_key = project_key
        self._project_name = project_name
        self._lock = threading.Lock()
        self._issues: list[JiraIssue] = []
        self._next = 1
        # Доска начинается пустой: задачи появляются, когда их ставят люди или агенты.
        self._load()

    # --- persistence --------------------------------------------------------

    def _load(self) -> bool:
        if self._path is None or not self._path.is_file():
            return False
        try:
            data = _BoardFile.model_validate_json(self._path.read_text(encoding="utf-8"))
        except (OSError, ValidationError, json.JSONDecodeError):
            log.warning("jira_board_unreadable", error_code="board_file_invalid")
            return False
        self._issues, self._next = data.issues, data.next_number
        return True

    def _save(self) -> None:
        if self._path is None:
            return
        self._path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self._path.with_suffix(".tmp")
        tmp.write_text(_BoardFile(next_number=self._next, issues=self._issues).model_dump_json(indent=1), encoding="utf-8")
        tmp.replace(self._path)

    # --- queries ------------------------------------------------------------

    def board(self) -> JiraBoard:
        with self._lock:
            return JiraBoard(
                project_key=self._project_key,
                project_name=self._project_name,
                columns=list(COLUMNS),
                issues=list(self._issues),
            )

    def get(self, key: str) -> JiraIssue:
        with self._lock:
            return self._find(key)

    def by_task(self, task_id: UUID) -> list[JiraIssue]:
        with self._lock:
            return [i for i in self._issues if i.task_id == task_id]

    def _find(self, key: str) -> JiraIssue:
        for issue in self._issues:
            if issue.key == key:
                return issue
        raise IssueNotFoundError(key)

    # --- commands -----------------------------------------------------------

    def _insert(self, data: IssueCreate) -> JiraIssue:
        now = _now()
        issue = JiraIssue(key=f"{self._project_key}-{self._next}", created_at=now, updated_at=now, **data.model_dump())
        self._next += 1
        self._issues.insert(0, issue)
        return issue

    def create(self, data: IssueCreate) -> JiraIssue:
        with self._lock:
            issue = self._insert(data)
            self._save()
        log.info("jira_issue_created", status=issue.status, domain=issue.domain)
        return issue

    def update(self, key: str, changes: IssueUpdate) -> JiraIssue:
        with self._lock:
            current = self._find(key)
            patch = changes.model_dump(exclude_unset=True, exclude={"add_attachments"})
            patch = {k: v for k, v in patch.items() if v is not None}
            if changes.add_attachments:
                urls = {a.url for a in current.attachments}
                fresh = [a for a in changes.add_attachments if a.url not in urls]
                patch["attachments"] = [*current.attachments, *fresh][-10:]
            updated = JiraIssue.model_validate({**current.model_dump(), **patch, "updated_at": _now()})
            index = self._issues.index(current)
            del self._issues[index]
            # Карточка, перенесённая в другую колонку, встаёт наверх колонки.
            self._issues.insert(0 if updated.status != current.status else index, updated)
            self._save()
        return updated

    def clear(self, statuses: set[IssueStatus] | None = None) -> int:
        """Удаляет все задачи (или только с указанными статусами). Возвращает число удалённых."""
        with self._lock:
            before = len(self._issues)
            self._issues = [] if statuses is None else [i for i in self._issues if i.status not in statuses]
            removed = before - len(self._issues)
            if not self._issues:
                self._next = 1  # пустая доска — нумерация с ORC-1
            self._save()
        log.info("jira_board_cleared", status="all" if statuses is None else "filtered")
        return removed

    def delete(self, key: str) -> None:
        with self._lock:
            self._issues.remove(self._find(key))
            self._save()
