"""SSE-ағынға қосылуды күтіп тұрған тапсырмалардың in-memory қоймасы.

Сұраныс мәтіні мен тіркеме тек жедел жадта тұрады: олар ағынға алғаш
қосылғанда не TTL аяқталғанда алынады (және өшіріледі).
"""

from __future__ import annotations

import time
from uuid import UUID, uuid4

from pydantic import BaseModel

from app.schemas.tasks import TaskCreateRequest


class PendingTask(BaseModel):
    request: TaskCreateRequest
    created_at: float


class TaskStore:
    def __init__(self, ttl_s: float) -> None:
        self._ttl_s = ttl_s
        self._tasks: dict[UUID, PendingTask] = {}

    def _purge_expired(self) -> None:
        deadline = time.monotonic() - self._ttl_s
        for task_id in [tid for tid, t in self._tasks.items() if t.created_at < deadline]:
            del self._tasks[task_id]

    def put(self, request: TaskCreateRequest) -> UUID:
        self._purge_expired()
        task_id = uuid4()
        self._tasks[task_id] = PendingTask(request=request, created_at=time.monotonic())
        return task_id

    def pop(self, task_id: UUID) -> TaskCreateRequest | None:
        self._purge_expired()
        task = self._tasks.pop(task_id, None)
        return task.request if task else None

    def __len__(self) -> int:
        return len(self._tasks)
