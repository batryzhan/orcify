"""Legal без LLM: рендер договора из реквизитов, проверенных пользователем,
и скачивание готовых документов из памяти."""

from __future__ import annotations

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Response, status

from app.api.deps import get_document_store, get_legal_service
from app.core.doc_engine import DocEngineError
from app.core.document_store import DocumentStore
from app.core.legal_service import LegalService
from app.schemas.legal import ContractData, DocumentInfo

router = APIRouter(prefix="/api", tags=["legal"])


@router.post("/legal/contracts", response_model=DocumentInfo, status_code=status.HTTP_201_CREATED)
async def render_contract(
    contract: ContractData, legal: Annotated[LegalService, Depends(get_legal_service)]
) -> DocumentInfo:
    """Для случая ``needs_input``: пользователь поправил поля в UI — рендерим без LLM."""
    try:
        return legal.render(contract)
    except DocEngineError as exc:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=exc.code) from None


@router.get("/documents/{document_id}")
async def download_document(
    document_id: UUID, documents: Annotated[DocumentStore, Depends(get_document_store)]
) -> Response:
    doc = documents.get(document_id)
    if doc is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="document not found or expired")
    return Response(
        content=doc.content,
        media_type=doc.media_type,
        headers={"Content-Disposition": f'attachment; filename="{doc.filename}"', "Cache-Control": "no-store"},
    )
