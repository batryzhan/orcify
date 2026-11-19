"""Дайын құжаттардың in-memory қоймасы (дискіге ештеңе жазылмайды)."""

from __future__ import annotations

import time
from uuid import UUID, uuid4

from pydantic import BaseModel


class StoredDocument(BaseModel):
    filename: str
    media_type: str
    content: bytes
    created_at: float


class DocumentStore:
    def __init__(self, ttl_s: float) -> None:
        self._ttl_s = ttl_s
        self._docs: dict[UUID, StoredDocument] = {}

    def _purge_expired(self) -> None:
        deadline = time.monotonic() - self._ttl_s
        for doc_id in [d for d, doc in self._docs.items() if doc.created_at < deadline]:
            del self._docs[doc_id]

    def put(self, filename: str, media_type: str, content: bytes) -> UUID:
        self._purge_expired()
        doc_id = uuid4()
        self._docs[doc_id] = StoredDocument(
            filename=filename, media_type=media_type, content=content, created_at=time.monotonic()
        )
        return doc_id

    def get(self, doc_id: UUID) -> StoredDocument | None:
        self._purge_expired()
        return self._docs.get(doc_id)
