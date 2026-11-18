"""Запуск задач и SSE-стриминг прогресса.

Протокол (EventSource умеет только GET):
1. ``POST /api/tasks`` с текстом -> ``task_id`` и ``events_url``.
2. ``GET /api/tasks/{task_id}/events`` -> поток ``ProgressEvent``.
   Стрим одноразовый: после ``completed``/``failed`` клиент должен
   закрыть EventSource, повторное подключение вернёт 404.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import StreamingResponse

from app.api.deps import get_pipeline, get_task_store
from app.core.logger import get_logger, payload_hash
from app.core.pipeline import TaskPipeline
from app.core.task_store import TaskStore
from app.schemas.tasks import TaskCreatedResponse, TaskCreateRequest

router = APIRouter(prefix="/api/tasks", tags=["tasks"])
log = get_logger(__name__)

SSE_HEADERS = {"Cache-Control": "no-cache", "X-Accel-Buffering": "no"}


@router.post("", response_model=TaskCreatedResponse, status_code=status.HTTP_201_CREATED)
async def create_task(
    body: TaskCreateRequest, store: Annotated[TaskStore, Depends(get_task_store)]
) -> TaskCreatedResponse:
    task_id = store.put(body.text)
    log.info("task_created", task_id=str(task_id), payload_hash=payload_hash(body.text))
    return TaskCreatedResponse(task_id=task_id, events_url=f"/api/tasks/{task_id}/events")


@router.get("/{task_id}/events")
async def stream_task_events(
    task_id: UUID,
    store: Annotated[TaskStore, Depends(get_task_store)],
    pipeline: Annotated[TaskPipeline, Depends(get_pipeline)],
) -> StreamingResponse:
    text = store.pop(task_id)
    if text is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="task not found or already started")

    async def events() -> AsyncIterator[str]:
        async for event in pipeline.run(task_id, text):
            yield event.to_sse()

    return StreamingResponse(events(), media_type="text/event-stream", headers=SSE_HEADERS)
