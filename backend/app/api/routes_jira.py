"""Orcify Jira: UI үшін тапсырмалар тақтасы (агенттер онымен MCP ``orcify_jira`` арқылы жұмыс істейді)."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Response, status

from app.api.deps import get_jira_store
from app.core.jira_store import IssueNotFoundError, JiraStore
from app.schemas.jira import ClearBoardRequest, IssueStatus, ClearBoardResponse, IssueCreate, IssueUpdate, JiraBoard, JiraIssue

router = APIRouter(prefix="/api/jira", tags=["jira"])
KEY_PATTERN = r"^[A-Z][A-Z0-9]{1,9}-\d+$"


@router.get("/board", response_model=JiraBoard)
async def board(store: Annotated[JiraStore, Depends(get_jira_store)]) -> JiraBoard:
    return store.board()


@router.post("/issues", response_model=JiraIssue, status_code=status.HTTP_201_CREATED)
async def create_issue(body: IssueCreate, store: Annotated[JiraStore, Depends(get_jira_store)]) -> JiraIssue:
    return store.create(body)


@router.patch("/issues/{key}", response_model=JiraIssue)
async def update_issue(
    key: str, body: IssueUpdate, store: Annotated[JiraStore, Depends(get_jira_store)]
) -> JiraIssue:
    try:
        return store.update(key, body)
    except IssueNotFoundError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="issue not found") from None


@router.delete("/issues/{key}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_issue(key: str, store: Annotated[JiraStore, Depends(get_jira_store)]) -> Response:
    try:
        store.delete(key)
    except IssueNotFoundError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="issue not found") from None
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/clear", response_model=ClearBoardResponse)
async def clear_board(
    body: ClearBoardRequest, store: Annotated[JiraStore, Depends(get_jira_store)]
) -> ClearBoardResponse:
    """«Тақтаны тазалау»: барлық тапсырма немесе тек орындалғандар."""
    removed = store.clear(None if body.scope == "all" else {IssueStatus.DONE})
    return ClearBoardResponse(removed=removed)
