"""Сценарий А (Legal): Unstructured Text -> LLM Extractor -> Pydantic -> docxtpl."""

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from typing import Final
from uuid import uuid4

from pydantic import BaseModel, ValidationError

from app.config import Settings
from app.core.doc_engine import DocEngine
from app.core.document_store import DocumentStore
from app.core.llm_client import ChatMessage, LLMClient, StructuredResponse
from app.core.logger import get_logger, payload_hash
from app.core.prompts import PromptLoader
from app.schemas.legal import ContractData, ContractEntitiesSchema, DocumentInfo

EXTRACTOR_PROMPT: Final = "legal_extractor"
DOCX_MEDIA_TYPE: Final = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"

log = get_logger(__name__)


class ContractValidation(BaseModel):
    contract: ContractData | None
    missing_fields: list[str]
    invalid_fields: list[str]


class LegalService:
    def __init__(
        self,
        llm: LLMClient,
        prompts: PromptLoader,
        engine: DocEngine,
        documents: DocumentStore,
        settings: Settings,
    ) -> None:
        self._llm = llm
        self._prompts = prompts
        self._engine = engine
        self._documents = documents
        self._tz = timezone(timedelta(hours=settings.tz_offset_hours))

    def today(self) -> date:
        return datetime.now(self._tz).date()

    async def extract(self, text: str) -> StructuredResponse[ContractEntitiesSchema]:
        system = self._prompts.load(EXTRACTOR_PROMPT, today=self.today().isoformat())
        messages = [ChatMessage(role="system", content=system), ChatMessage(role="user", content=text)]
        return await self._llm.structured(messages, ContractEntitiesSchema, stage="extracting_entities")

    @staticmethod
    def validate(entities: ContractEntitiesSchema) -> ContractValidation:
        missing = entities.missing_fields()
        try:
            contract = ContractData.from_extraction(entities)
        except ValidationError as exc:
            failed = {str(err["loc"][0]) for err in exc.errors() if err["loc"]}
            invalid = sorted(failed - set(missing))
            return ContractValidation(contract=None, missing_fields=missing, invalid_fields=invalid)
        return ContractValidation(contract=contract, missing_fields=[], invalid_fields=[])

    def render(self, contract: ContractData) -> DocumentInfo:
        today = self.today()
        number = f"ORC-{today:%Y%m%d}-{uuid4().hex[:6].upper()}"
        content = self._engine.render_contract(contract, contract_number=number, contract_date=today)
        filename = f"contract_{number}.docx"
        doc_id = self._documents.put(filename=filename, media_type=DOCX_MEDIA_TYPE, content=content)
        digest = payload_hash(content)
        log.info("docx_rendered", document_id=str(doc_id), payload_hash=digest, size_bytes=len(content))
        return DocumentInfo(
            document_id=doc_id,
            filename=filename,
            download_url=f"/api/documents/{doc_id}",
            sha256=digest,
            size_bytes=len(content),
        )
