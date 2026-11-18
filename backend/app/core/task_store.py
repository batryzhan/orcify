"""In-memory хранилище задач, ожидающих подключения к SSE-стриму.

Текст запроса живёт только в оперативной памяти: он извлекается
(и удаляется) при первом подключении к стриму либо по истечении TTL.
"""

from __future__ import annotations

import time
from uuid import UUID, uuid4

from pydantic import BaseModel


class PendingTask(BaseModel):
    text: str
    created_at: float


class TaskStore:
    def __init__(self, ttl_s: float) -> None:
        self._ttl_s = ttl_s
        self._tasks: dict[UUID, PendingTask] = {}

    def _purge_expired(self) -> None:
        deadline = time.monotonic() - self._ttl_s
        for task_id in [tid for tid, t in self._tasks.items() if t.created_at < deadline]:
            del self._tasks[task_id]

    def put(self, text: str) -> UUID:
        self._purge_expired()
        task_id = uuid4()
        self._tasks[task_id] = PendingTask(text=text, created_at=time.monotonic())
        return task_id

    def pop(self, task_id: UUID) -> str | None:
        self._purge_expired()
        task = self._tasks.pop(task_id, None)
        return task.text if task else None

    def __len__(self) -> int:
        return len(self._tasks)
