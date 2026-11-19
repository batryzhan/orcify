"""«Қаржы» терезесі: бюджеттер, PDF-есептер мұрағаты және есепті Telegram-ға жіберу."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Response, status
from fastapi.responses import FileResponse

from app.api.deps import get_budget_store, get_report_store, get_telegram_bot
from app.channels.telegram import TelegramBot
from app.core.finance_store import BudgetStore, ReportStore
from app.schemas.finance import Budgets, ReportRecord
from app.schemas.telegram import SendPostResponse

router = APIRouter(prefix="/api/finance", tags=["finance"])


@router.get("/budgets", response_model=Budgets)
async def get_budgets(store: Annotated[BudgetStore, Depends(get_budget_store)]) -> Budgets:
    return store.get()


@router.put("/budgets", response_model=Budgets)
async def put_budgets(body: Budgets, store: Annotated[BudgetStore, Depends(get_budget_store)]) -> Budgets:
    return store.put(body)


@router.get("/reports", response_model=list[ReportRecord])
async def list_reports(store: Annotated[ReportStore, Depends(get_report_store)]) -> list[ReportRecord]:
    return store.list()


@router.get("/reports/{report_id}.pdf")
async def report_pdf(report_id: str, store: Annotated[ReportStore, Depends(get_report_store)]) -> FileResponse:
    path = store.pdf_path(report_id)
    record = store.get(report_id)
    if path is None or record is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="report not found")
    return FileResponse(path, media_type="application/pdf", filename=record.file.filename,
                        content_disposition_type="inline")


@router.delete("/reports/{report_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_report(report_id: str, store: Annotated[ReportStore, Depends(get_report_store)]) -> Response:
    if not store.delete(report_id):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="report not found")
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/reports/{report_id}/telegram", response_model=SendPostResponse)
async def send_report(
    report_id: str,
    store: Annotated[ReportStore, Depends(get_report_store)],
    bot: Annotated[TelegramBot | None, Depends(get_telegram_bot)],
) -> SendPostResponse:
    """Пайдаланушының айқын әрекеті: PDF-ті боттың жазған барлық чаттарына жіберу."""
    if store.get(report_id) is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="report not found")
    if bot is None or not bot.configured:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="telegram bot not configured")
    sent = await bot.send_report(report_id)
    return SendPostResponse(sent=sent, linked_chats=bot.status().linked_chats)
