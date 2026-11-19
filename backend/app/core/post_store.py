"""Дайын посттар галереясы: PNG + метадеректер ``backend/var/posts`` ішінде (жергілікті, git-те емес)."""

from __future__ import annotations

import re
import threading
from pathlib import Path

from pydantic import ValidationError

from app.core.logger import get_logger
from app.schemas.smm import PostRecord

log = get_logger(__name__)
_ID_RE = re.compile(r"^[0-9a-f]{32}$")


class PostStore:
    def __init__(self, directory: Path) -> None:
        self._dir = directory
        self._lock = threading.Lock()

    def save(self, record: PostRecord, png: bytes) -> None:
        with self._lock:
            self._dir.mkdir(parents=True, exist_ok=True)
            pid = record.post.post_id
            (self._dir / f"{pid}.png").write_bytes(png)
            (self._dir / f"{pid}.json").write_text(record.model_dump_json(indent=1), encoding="utf-8")

    def attach_issue(self, post_id: str, issue_key: str) -> None:
        record = self.get(post_id)
        if record is None:
            return
        record.issue_key = issue_key
        with self._lock:
            (self._dir / f"{post_id}.json").write_text(record.model_dump_json(indent=1), encoding="utf-8")

    def get(self, post_id: str) -> PostRecord | None:
        if not _ID_RE.fullmatch(post_id):
            return None
        path = self._dir / f"{post_id}.json"
        if not path.is_file():
            return None
        try:
            return PostRecord.model_validate_json(path.read_text(encoding="utf-8"))
        except (OSError, ValidationError):
            log.warning("post_record_unreadable", error_code="post_meta_invalid")
            return None

    def png_path(self, post_id: str) -> Path | None:
        if not _ID_RE.fullmatch(post_id):
            return None
        path = self._dir / f"{post_id}.png"
        return path if path.is_file() else None

    def list(self, limit: int = 60) -> list[PostRecord]:
        if not self._dir.is_dir():
            return []
        records = [r for p in self._dir.glob("*.json") if (r := self.get(p.stem)) is not None]
        records.sort(key=lambda r: r.post.created_at, reverse=True)
        return records[:limit]
